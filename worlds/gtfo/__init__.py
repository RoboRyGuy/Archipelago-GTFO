# world/gtfo/__init__.py

from __future__ import annotations

from collections import defaultdict, Counter
import dataclasses
import importlib.resources
from importlib.resources.abc import Traversable
import json
import logging
from pathlib import Path
from typing import Any, cast, ClassVar, Dict, FrozenSet, Iterable, List, Mapping, Optional, override, Set, Type, Union
from types import SimpleNamespace

from BaseClasses import Region, Location, Item, ItemClassification, LocationProgressType
import Options
from Options import Option
from rule_builder.cached_world import CachedRuleBuilderWorld
from rule_builder.rules import And, CanReachRegion, False_, HasFromList, Or, Rule, True_
import Utils
from worlds.AutoWorld import WebWorld

from .model import SlotDataModel, GameDataModel, TagModel, TaggedRegionModel, PathModel, PathReqModel, \
    LocationTagModel, ItemTagModel, OptionBaseModel, OptionInputModel, RealItemTagModel, ChoiceModel
from .options import EarlyItems, GTFOOptions
from .rules import GTFOHas, GTFOHasGroup

class GTFOLocation(Location):
    game: str = "GTFO"

class GTFOItem(Item):
    game: str = "GTFO"

class GTFOWorld(CachedRuleBuilderWorld):
    """
    Base class used for GTFO worlds. Derived classes will be dynamically
    created on-demand using AutoWorldRegister (see bottom of file)
    """

    ## Constants
    origin_region_name: str = "Menu"
    """Name of the origin region. Same as the default."""

    ## Required by AP
    game: ClassVar[str]
    """The name of this game. This will be overwritten from MID data"""
    topology_present: bool = False
    """Indicates the regions of this game correspond to actual physical locations (which is mostly true)"""
    options_dataclass: ClassVar[Type[GTFOOptions]]
    """The dataclass to use for this world. This will be set from MID data."""
    options: GTFOOptions
    """Actual options instance used for generation"""
    location_name_to_id: ClassVar[Dict[str, int]]
    """Map of location names to location IDs. This will be populated from MID data"""
    item_name_to_id: ClassVar[Dict[str, int]]
    """Map of item names to item IDs. This will be populated from MID data"""
    item_name_groups: ClassVar[Dict[str, FrozenSet[str]]]
    """Maps an item group name to a set of item names. This will be populated from MID data"""
    item_mapping: ClassVar[Dict[str, str]] = dict()
    """Maps an actual item name to a logical item name. For GTFO, this is kept empty."""
    web: ClassVar[WebWorld]
    """Web world to be used by this world"""

    ## Class variables
    class_logger: ClassVar[logging.Logger]
    """Logger for the class (world)"""
    gen_model: ClassVar[GameDataModel]
    """Imported MID data"""
    region_name_to_id_casefold: ClassVar[Dict[str, int]]
    """Map of regions name to region IDs"""
    region_to_paths: ClassVar[Mapping[int, List[PathModel]]]
    """Maps regions to paths leaving those regions"""
    menu_region_id: ClassVar[int]
    """ID of the menu region"""
    location_name_to_id_casefold: ClassVar[Dict[str, int]]
    """Map of location names to location IDs"""
    item_name_to_id_casefold: ClassVar[Dict[str, int]]
    """Map of item names to item IDs"""
    region_model_by_id: ClassVar[Mapping[int, TaggedRegionModel]]
    """Region lookup by id"""
    path_model_by_id: ClassVar[Mapping[int, PathModel]]
    """Path lookup by id"""
    location_model_by_id: ClassVar[Mapping[int, LocationTagModel]]
    """Location lookup by id"""
    item_model_by_id: ClassVar[Mapping[int, ItemTagModel]]
    """Item lookup by id"""
    item_children_by_parent: ClassVar[Mapping[int, List[ItemTagModel]]]
    """Reverse parent mapping; maps items to their children"""
    empty_item_model: ClassVar[RealItemTagModel]
    """Default filler item which does nothing. To be replaced with filler items in future update"""
    choice_lookup: ClassVar[Mapping[FrozenSet[int], ChoiceModel]]
    """Maps choices superstates to their choice definition"""
    option_model_by_id: ClassVar[Mapping[int, OptionBaseModel]]
    """Option model lookup used for options evaluation"""

    ## Per-player variables
    logger: logging.Logger
    """Logger for the world instance, ie one per player"""

    ## Universal Tracker integration
    ut_can_gen_without_yaml: ClassVar[bool] = True
    """Indicates UT can skip YAML parsing for this world's generation pass"""

    @staticmethod
    def interpret_slot_data(slot_data: dict[str, Any]) -> dict[str, Any]:
        """Triggers a regen in Universal Tracker"""
        return slot_data

    def __init__(self, *args, **kwargs):
        """Init this world (specifically, the logger)"""
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(f"GTFO.{type(self).game}.{self.multiworld.get_player_name(self.player)}")

    @override
    def create_regions(self) -> None:
        """
        For the sake of simplicity, we will do all our work in this one method
        """

        cls = type(self)

        #######################################################################
        ## Options Re-evaluation
        ## Options are auto-magically evaluated when they're created in order to
        ## provide Archipelago with relevant information (and fulfill type consistency);
        ## however, they are re-evaluated here to include the world instance so
        ## things like generation_is_fake can be accurately accounted for
        self.options.evaluate(self)

        #######################################################################
        ## Choice Regions, Paths, Locations, and Items

        ## Creating choice states
        choice_regions: Dict[FrozenSet[int], Dict[int, Region]] = dict()

        for choice, reach in self.options.state_reachability.items():
            ## Creating regions
            choice_model = cls.choice_lookup[choice]
            regions = choice_regions[choice] = {
                r: Region(f"C#{choice_model.id} {cls.region_model_by_id[r].name}", self.player, self.multiworld)
                for r in reach.reachable_regions
            }
            self.multiworld.regions += regions.values()

            ## Creating locations
            for l in reach.reachable_locations:
                loc_model = cls.location_model_by_id[l]
                assert loc_model.value is not None

                ## Reachability
                main_region = regions[loc_model.value.owning_regions[0]]
                rule: Optional[Rule] = None
                if len(loc_model.value.owning_regions) == 2:
                    rule = CanReachRegion(regions[loc_model.value.owning_regions[1]].name)
                elif len(loc_model.value.owning_regions) > 2:
                    rule = And(*(CanReachRegion(regions[r].name) for r in loc_model.value.owning_regions[1:]))

                ## Progress type (priority)
                progress_type = LocationProgressType.DEFAULT
                if loc_model.value.priority_mode == "Priority":
                    progress_type = LocationProgressType.PRIORITY
                elif loc_model.value.priority_mode in ["Excluded", "Trap"]:
                    progress_type = LocationProgressType.EXCLUDED

                ## Creating the location
                name = f"C#{choice_model.id} {loc_model.name}"
                location = GTFOLocation(self.player, name, None, main_region)
                location.progress_type = progress_type
                main_region.locations.append(location)
                if rule is not None:
                    self.set_rule(location, rule)
                location.place_locked_item(self.create_item_by_id(loc_model.value.item_id, choice_model.id))

        ## Connecting paths
        for choice, region_map in choice_regions.items():

            ## Calculating the cost of entering this state
            choice_model = cls.choice_lookup[choice]
            state_cost: Counter[int] = Counter()
            for req in ( r for p in choice for r in cls.path_model_by_id[p].reqs ):
                if req.is_consume:
                    state_cost[req.target] += req.count

            ## Creating paths inside this state
            paths = (p for r in region_map.keys() for p in cls.region_to_paths[r])
            for path_model in paths:

                ## Get the regions, check if path exists
                start_region = region_map[path_model.starting_region]
                end_region = region_map.get(path_model.ending_region, None)

                ## Check if traversing this path constitutes a state change (and if we need a new end region)
                if any( r.is_consume for r in path_model.reqs ) and path_model.id not in choice:
                    new_choice = frozenset((path_model.id, *choice))
                    if not new_choice in choice_regions:
                        continue ## Not a relevant choice, so we can ditch it
                    end_region = choice_regions[new_choice][cls.menu_region_id]

                if end_region is None:
                    continue ## Path does not exist in current game

                ## Build the rule
                def make_rule(req_index: int, req: PathReqModel) -> Rule:
                    """Helper which makes a rule for a single requirement"""
                    if req.is_growing:
                        req_count = self.options.growth_reqs[path_model.id][req_index]
                    else:
                        req_count = req.count

                    if req.is_consume and path_model.id in choice:
                        req_count -= req.count
                    else:
                        req_count += state_cost[req.target]

                    target_tag = cls.item_model_by_id[req.target]
                    if req.is_category:
                        if not target_tag.name in cls.item_name_groups:
                            ## Condition is impossible to satisfy
                            ## This can happen if no items in the desired category actually exist
                            return False_()
                        else:
                            return GTFOHasGroup(choice_model.id, target_tag.name, req_count)
                    else:
                        return GTFOHas(choice_model.id, target_tag.name, req_count)

                path_rule: Rule
                if path_model.reqs:
                    path_rule = And(*(make_rule(i, r) for i, r in enumerate(path_model.reqs)))
                else:
                    path_rule = True_()

                ## Create the path!
                path_name = f"Path {path_model.id} | {start_region.name} -> {end_region.name}" \
                    if path_model.name is None else path_model.name
                start_region.connect(end_region, f"C#{choice_model.id} {path_name}", path_rule)

        menu_region = Region(cls.origin_region_name, self.player, self.multiworld)
        self.multiworld.regions.append(menu_region)
        menu_region.connect(choice_regions[frozenset()][cls.menu_region_id])

        #######################################################################
        ## Global Locations and Items

        for l in self.options.global_reachability.reachable_locations:
            loc_model = cls.location_model_by_id[l]
            assert loc_model.value is not None

            if loc_model.value.is_empty and not loc_model.id in self.options.filled_empty_locations:
                continue

            ## Reachability
            main_region = menu_region
            rule: Rule

            def make_subrule(r: int) -> Rule:
                """Helper which makes subrule for reaching a particular global region"""
                viable_regions = [ rs[r] for rs in choice_regions.values() if r in rs ]
                if not viable_regions:
                    ## This should never occur if our graph traversal is working correctly
                    self.logger.error(f"Location {loc_model.id} is unreachable because region {r} is unreachable")
                    return False_()
                elif len(viable_regions) == 1:
                    return CanReachRegion(viable_regions[0].name)
                else:
                    return Or(*(CanReachRegion(re.name) for re in viable_regions))

            if not loc_model.value.owning_regions:
                ## This should never occur if our graph traversal is working correctly
                self.logger.error(f"Location {loc_model.id} is unreachable because it has no owning regions")
                rule = False_()
            elif len(loc_model.value.owning_regions) == 1:
                rule = make_subrule(loc_model.value.owning_regions[0])
            elif getattr(self.multiworld, "generation_is_fake", False):  ## Universal Tracker Integration
                rule = Or(*(make_subrule(r) for r in loc_model.value.owning_regions))
            else:
                rule = And(*(make_subrule(r) for r in loc_model.value.owning_regions))

            ## Progress type (priority)
            progress_type = LocationProgressType.DEFAULT
            if loc_model.value.priority_mode == "Priority":
                progress_type = LocationProgressType.PRIORITY
            elif loc_model.value.priority_mode in ["Excluded", "Trap"]:
                progress_type = LocationProgressType.EXCLUDED

            ## Creating the location
            location = GTFOLocation(self.player, loc_model.name, loc_model.id, main_region)
            location.progress_type = progress_type
            main_region.locations.append(location)
            self.set_rule(location, rule)

            ## Is it possible this location is randomlike?
            if not loc_model.value.is_empty and cls.item_model_by_id[loc_model.value.item_id].value.is_randomlike:
                ## Checking
                item_model = cls.item_model_by_id[loc_model.value.item_id]
                assert item_model.value is not None
                item_model: RealItemTagModel

                loc_white = cls.tag_matches(loc_model.id, self.options.location_whitelist, cls.location_model_by_id)
                loc_black = cls.tag_matches(loc_model.id, self.options.location_blacklist, cls.location_model_by_id)
                item_white = cls.tag_matches(item_model.id, self.options.item_whitelist, cls.item_model_by_id)
                item_black = cls.tag_matches(item_model.id, self.options.item_blacklist, cls.item_model_by_id)

                if not ((loc_white or item_white) and not (loc_black or item_black)):
                    ## This location is randomlike
                    location.place_locked_item(self.create_item_by_model(item_model, None))
                    self.options.global_reachability.item_counts[item_model.id] -= 1

        ## Randomized items
        for item_id in self.options.global_reachability.item_counts.elements():
            if item_id != 0:
                item = self.create_item_by_id(item_id, None)
                self.multiworld.itempool.append(item)

        ## Push starting inventory
        for i in self.options.start_inventory_results.elements():
            self.multiworld.push_precollected(self.create_item_by_id(i, None))
        for i in self.options.start_voucher_results.elements():
            self.multiworld.push_precollected(self.create_item_by_id(i, None))

        ## Sample and apply early items
        early_items = options.TagSampler(self.logger, self.options.random, self.options.fail_during_sampling).sample(
            self.options.global_reachability.item_counts.keys(),
            self.options.early_items.items(),
            self.item_model_by_id,
            False,
            EarlyItems.display_name,
            repeats=self.options.global_reachability.item_counts.values()
        )
        early_items_dict = self.multiworld.early_items.setdefault(self.player, dict())
        early_items_dict.update( (self.item_model_by_id[k].name, v) for (k, v) in early_items.items() )

        #######################################################################
        ## Goal Condition

        self.set_completion_rule(HasFromList(
            *( cls.item_model_by_id[i].name for i in self.options.goal_item_results.elements() ),
            count=self.options.goal_item_results.total()-self.options.skippable_goal_count
        ))

    @override
    def create_item(self, item_name: str) -> GTFOItem:
        """
        Create an item for this world type and player.
        Warning: this may be called with self.world = None, for example by MultiServer
        """
        name_casefold = item_name.casefold()
        item_id = self.item_name_to_id_casefold.get(name_casefold, None)
        if item_id is None:
            if name_casefold.startswith("c#"):
                try:
                    space = name_casefold.index(" ")
                    choice_index = int(name_casefold[2:space])
                    item_id = self.item_name_to_id_casefold[name_casefold[space+1:]]
                    return self.create_item_by_id(item_id, choice_index)
                except Exception as e:
                    raise Exception(f"Failed to look up item by name: {item_name}; cannot create null item") from e
            raise Exception(f"Failed to look up item by name: {item_name}; cannot create null item")
        return self.create_item_by_id(item_id, None)
    
    def create_item_by_id(self, item_id: int, choice: Optional[int]) -> GTFOItem:
        """
        Create a particular item from just its ID.
        """
        item_model = self.item_model_by_id.get(item_id, None)
        if item_model is None:
            self.logger.error(f"Failed to create item by id: {item_id}; item model not found")
            raise Exception(f"Failed to create item by id: {item_id}; item model not found")
        elif item_model.value is None:
            self.logger.error(f"Failed to create item by id: {item_id}; item model has no value")
            raise Exception(f"Failed to create item by id: {item_id}; item model has no value")
        item_model: RealItemTagModel
        return self.create_item_by_model(item_model, choice)

    def create_item_by_model(self, item_model: RealItemTagModel, choice: Optional[int]) -> GTFOItem:
        """
        Create a particular item from its model.
        """

        classification: ItemClassification = cast(ItemClassification, 0)
        if item_model.value.is_progression:
            classification |= ItemClassification.progression
        if item_model.value.is_useful:
            classification |= ItemClassification.useful
        if item_model.value.is_filler:
            classification |= ItemClassification.filler
        if item_model.value.is_trap:
            classification |= ItemClassification.trap
        if item_model.value.do_skip_balancing:
            classification |= ItemClassification.skip_balancing
        if item_model.value.is_deprioritized:
            classification |= ItemClassification.deprioritized

        name = item_model.name if choice is None else f"C#{choice} {item_model.name}"

        return GTFOItem(name, classification, item_model.id, self.player)

    @classmethod
    def get_item_group(cls, i_name: str, choice: Optional[int]) -> FrozenSet[str]:
        """Makes item groups on demand; registers them"""
        group_name = i_name if choice is None else f"C#{choice} {i_name}"
        if group_name in cls.item_name_groups:
            return cls.item_name_groups[group_name]

        tag_id = cls.item_name_to_id_casefold[i_name.casefold()]
        item_model = cls.item_model_by_id[tag_id]

        def children_iterator(im: ItemTagModel) -> Iterable[RealItemTagModel]:
            """Helper which iterates through an item and all its children"""
            if im.value is not None:
                yield cast(RealItemTagModel, cast(TagModel, im))
            for c in cls.item_children_by_parent[im.id]:
                yield from children_iterator(c)

        result = cls.item_name_groups[group_name] = frozenset(
            i.name if choice is None else f"C#{choice} {i.name}" for i in children_iterator(item_model)
        )
        return result

    @override
    def get_filler_item_name(self):
        return "Empty"

    @override
    def create_filler(self) -> GTFOItem:
        """Create a random filler item, which may be a trap item"""
        return self.create_item_by_model(self.empty_item_model, None)

    @override
    def fill_slot_data(self) -> Mapping[str, Any]:
        return SlotDataModel({
            "root_seed": self.options.root_seed,
            "region_whitelist": self.options.region_whitelist,
            "region_blacklist": self.options.region_blacklist,
            "location_whitelist": self.options.location_whitelist,
            "location_blacklist": self.options.location_blacklist,
            "item_whitelist": self.options.item_whitelist,
            "item_blacklist": self.options.item_blacklist,
            "filled_empty_locations": list(self.options.filled_empty_locations.items()),
            "goal_item_results": list(self.options.goal_item_results.items()),
            "skippable_goal_count": self.options.skippable_goal_count,
            "start_inventory_results": list(self.options.start_inventory_results.items()),
        }).dump()

    @staticmethod
    def tag_matches(tag: int, tag_set: Set[int], tag_dict: Mapping[int, TagModel]) -> bool:
        """Check if a tag matches against a set of tags given its reference dict"""
        if tag == 0:
            return False
        if tag in tag_set:
            return True

        tag_def: Optional[TagModel] = tag_dict.get(tag, None)
        if tag_def is not None and any(GTFOWorld.tag_matches(p, tag_set, tag_dict) for p in tag_def.parents):
            return True
        else:
            return False

    @staticmethod
    def tag_matches_single(tag: int, parent: int, tag_dict: Mapping[int, TagModel]) -> bool:
        """Check if a tag matches against a set of tags given its reference dict"""
        if tag == 0:
            return False
        if tag == parent:
            return True

        tag_def: Optional[TagModel] = tag_dict.get(tag, None)
        if tag_def is not None and any(GTFOWorld.tag_matches_single(p, parent, tag_dict) for p in tag_def.parents):
            return True
        else:
            return False


class GTFOWorldBuilder:
    """Wraps the creation and storage of GTFO Worlds"""

    all_worlds: ClassVar[Dict[Optional[str], Type[GTFOWorld]]] = dict()
    """
    All worlds made by this builder, keyed by name (ie "GTFO (MyModSet)"). 
    Includes the vanilla world, which is keyed under None.
    """

    logger: ClassVar[logging.Logger] = logging.getLogger("GTFO World Builder")
    """Logger used for building worlds"""

    ## Might add string formatting to this later to include some info about the mod set
    docstring: ClassVar[str] = \
        """
        GTFO is a cooperative first-person shooter developed by 10 Chambers.
        Teams of 4 players take on the role of prisoners forced to explore a vast underground complex
         filled with terrifying creatures in a series of `Expeditions`.
        Working together, they must use stealth, teamwork, and their limited resources to fend off
         dangerous foes, complete their objective stack, and extract alive.
        """
    """The docstring used by worlds created by this builder"""

    @classmethod
    def try_load_file(cls, file: Union[Traversable, Path], filename: str) -> Optional[GameDataModel]:
        """Attempt to load the model from the asset; returns None on fail and logs the exception"""
        gen_model: Optional[GameDataModel] = None
        try:
            with file.open("r") as file_data:
                gen_model = GameDataModel(json.load(file_data))
        except OSError as e:  ## Failed to open file
            cls.logger.error(f"Failed open GTFO MID file: {filename}")
            cls.logger.exception(e)
        except json.JSONDecodeError as e:  ## JSON parsing failed
            cls.logger.error(f"Failed to parse GTFO MID file: {filename}")
            cls.logger.exception(e)
        except Exception as e:  ## Generic failure during gen_model instantiation
            cls.logger.error(f"Malformed GTFO MID data: {filename}")
            cls.logger.exception(e)
        return gen_model

    @classmethod
    def make_worlds(cls):
        """
        Create / rebuild all GTFO worlds from file.
        For internal use only; this supports rebuild, but does not account for AutoWorldRegister needing to be
         cleaned of existing GTFO worlds, or for any other dangling references.
        """

        ## Scan for worlds in the players directory
        found_worlds: Dict[Optional[str], GameDataModel] = dict()
        path = Path(f"{Utils.local_path()}/Players")
        if path.exists():
            for file in path.iterdir():
                lower = file.name.lower()
                if not file.is_file():
                    continue
                if not (lower.startswith("gtfo-") and lower.endswith(".ini")):
                    continue

                gen_model = cls.try_load_file(file, file.name)
                if gen_model is None:
                    continue
                if gen_model.name in cls.all_worlds:
                    cls.logger.warning(f"Skipping MID file because a duplicate is already defined: {file.name}")
                    del gen_model
                    continue
                found_worlds[gen_model.name] = gen_model

        ## Add the vanilla world (if an override was not found)
        if None not in found_worlds:
            file = importlib.resources.files().joinpath("data").joinpath("GTFO.ini")
            gen_model = cls.try_load_file(file, "builtin")
            if gen_model is None:
                raise Exception("Failed to load vanilla GTFO world from apworld file")
            found_worlds[None] = gen_model

        ## Create all the worlds!
        for value in found_worlds.values():
            cls.make_world(value)

    @classmethod
    def make_world(cls, gen_model: GameDataModel) -> Type[GTFOWorld]:
        """Programmatically create a new AutoWorldRegister for the given GTFO world."""

        ## If we attempt to create a duplicate world, Archipelago will throw a fit
        if gen_model.name in GTFOWorldBuilder.all_worlds:
            raise Exception("Cannot create duplicate GTFO world!")

        ## Using a SimpleNamespace to provide type hints
        world_class = SimpleNamespace(**GTFOWorld.__dict__)
        world_class: Type[GTFOWorld]

        ###########################################################################################
        ## Init class variables

        world_class.game = "GTFO" if gen_model.name is None else f"GTFO ({gen_model.name})"
        world_class.__doc__ = GTFOWorldBuilder.docstring
        world_class.gen_model = gen_model
        world_class.class_logger = logging.getLogger(f"GTFO.{gen_model.name}")
        world_class.region_name_to_id_casefold = { reg.name.casefold(): reg.id for reg in gen_model.regions }
        world_class.region_model_by_id = { reg.id: reg for reg in gen_model.regions }
        world_class.menu_region_id = world_class.region_name_to_id_casefold["menu"]
        world_class.region_to_paths = defaultdict(list)
        for path_model in gen_model.paths:
            world_class.region_to_paths[path_model.starting_region].append(path_model)
        world_class.path_model_by_id = { p.id: p for p in gen_model.paths }
        gen_model.paths.sort(key=lambda path: path.name if path.name is not None else "")
        world_class.location_name_to_id = { loc.name: loc.id for loc in gen_model.locations }
        world_class.location_name_to_id_casefold = { loc.name.casefold(): loc.id for loc in gen_model.locations }
        world_class.location_model_by_id = { loc.id: loc for loc in gen_model.locations }
        world_class.item_model_by_id = { item.id: item for item in gen_model.items }
        world_class.item_name_to_id = { item.name: item.id for item in gen_model.items }
        world_class.item_name_to_id_casefold = { item.name.casefold(): item.id for item in gen_model.items }
        world_class.choice_lookup = { choice.choice_paths: choice for choice in gen_model.choices }
        for idx, choice in enumerate(gen_model.choices):
            choice.id = idx

        empty_item = world_class.item_name_to_id_casefold.get("Empty".casefold(), None)
        if empty_item is None:
            world_class.class_logger.error(f"Failed to find the empty item for GTFO world: {gen_model.name}")
        else:
            empty_item_model = world_class.item_model_by_id[empty_item]
            if empty_item_model.value is None:
                world_class.logger.error(f"Empty item has no value for GTFO world: {gen_model.name}")
            else:
                empty_item_model: RealItemTagModel
                world_class.empty_item_model = empty_item_model

        ## Set up location groups
        world_class.location_name_groups = dict()
        def add_location_group_recursive(l_name: str, tag_id: int):
            """Helper to add locations to groups"""
            if tag_id == 0: return
            tag_model = world_class.location_model_by_id[tag_id]
            world_class.location_name_groups.setdefault(tag_model.name, set()).add(l_name)
            for p in tag_model.parents:
                add_location_group_recursive(l_name, p)

        for gen_loc in gen_model.locations:
            if gen_loc.value is not None:
                add_location_group_recursive(gen_loc.name, gen_loc.id)

        ## Set up item groups
        world_class.item_children_by_parent = defaultdict(list)
        for item in gen_model.items:
            for p in item.parents:
                world_class.item_children_by_parent[p].append(item)

        item_name_groups = defaultdict(set)
        def add_item_group_recursive(i_name: str, tag_id: int):
            """Helper to add items to groups"""
            if tag_id == 0: return
            tag_model = world_class.item_model_by_id[tag_id]
            item_name_groups[tag_model.name].add(i_name)
            for p in tag_model.parents:
                add_item_group_recursive(i_name, p)

        for gen_item in gen_model.items:
            if gen_item.value is not None:
                add_item_group_recursive(gen_item.name, gen_item.id)
        world_class.item_name_groups = { k: frozenset(v) for k, v in item_name_groups.items() }
        del item_name_groups

        ###########################################################################################
        ## Options creation

        ## Creating the options lookup
        world_class.option_model_by_id = { o.id: o for o in gen_model.options }

        ## Define the options dataclass
        options_dict: Dict[str, Any] = { "__annotations__": dict() }

        ## Options grouping by name; we later calc the option groups once we've created all option inputs
        option_groups_raw = options.gtfo_option_grouping.copy()

        ## Search for and add input options
        for option in gen_model.options:

            if isinstance(option, OptionInputModel):
                option: OptionInputModel
                option_class = option.create_class(gen_model.name)
                group = option_groups_raw.setdefault(option.category, list())
                group.append((option.category_sort, option_class))

        ## Sort option groups
        for option_group in option_groups_raw.values():
            option_group.sort(key=lambda pair: pair[0])

        ## Push options to class as annotations
        type_hints: Dict[str, Type[Option[Any]]] = dict()
        for tup in (o for os in option_groups_raw.values() for o in os):
            display_name = getattr(tup[1], "display_name", tup[1].__name__)
            assert isinstance(display_name, str), f"display_name is not a string!"
            options_dict["__annotations__"][display_name] = tup[1]
            type_hints[display_name] = tup[1]

        ## Push base class fields as well - this will get all inherited fields too
        type_hints.update(
            (f.name, eval(f"Options.{f.type}") if isinstance(f.type, str) else f.type)
            for f in dataclasses.fields(Options.PerGameCommonOptions)
        )

        ## Class variables
        #options_dict["world"] = world_class  ## Cannot assign until the world class is actually created
        options_dict["logger"] = logging.Logger(f"GTFO Options ({gen_model.name})", logging.INFO)
        options_dict["gtfo_type_hints"] = type_hints

        ## Finally, create the options dataclass and assign it to our generated world
        options_class = type(GTFOOptions)(f"GTFO Options ({gen_model.name})", (GTFOOptions,), options_dict)
        world_class.options_dataclass = options_class

        ###########################################################################################
        ## Web World creation

        ## Defining a derived class
        web_class = SimpleNamespace()
        web_class: Type[WebWorld]
        option_groups_raw["Game Options"].insert(0, ([0], Options.Accessibility))
        option_groups_raw["Game Options"].insert(1, ([0], Options.ProgressionBalancing))
        web_class.option_groups = [
            Options.OptionGroup(name, [i[1] for i in items]) for name, items in option_groups_raw.items()
        ]
        web_class = type(WebWorld)(f"GTFO WebWorld ({gen_model.name})", (WebWorld,), web_class.__dict__)
        web_class: Type[WebWorld]

        ## Creating an instance of that derived class
        web = web_class()
        web.options_page = True
        web.game_model = ["en"]
        web.tutorials = [] ## TODO
        web.theme = "stone"
        web.bugreports = "https://github.com/RoboRyGuy/Archipelago-GTFO/issues"
        web.options_presets = dict()
        web.rich_text_options_doc = True
        web.location_descriptions = {
            t.name: t.description for t in gen_model.locations
        }
        web_class.item_descriptions = {
            t.name: t.description for t in gen_model.items
        }

        ## Assign to new world
        world_class.web = web

        ###########################################################################################
        ## Create the world class!

        ## Note that we use the metaclass associated with GTFOWorld to create the derived instance
        result = type(GTFOWorld)(f"GTFO World ({gen_model.name})", (GTFOWorld,), world_class.__dict__)
        options_class.world = result
        return result

## Now we simply create all the GTFO worlds
GTFOWorldBuilder.make_worlds()


