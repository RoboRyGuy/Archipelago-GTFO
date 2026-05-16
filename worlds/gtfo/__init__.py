# world/gtfo/__init__.py

from __future__ import annotations
import importlib.resources
import json
from typing import cast, Set, Dict, Iterable, Callable, override, ClassVar

from BaseClasses import Region, Location, Item, ItemClassification, LocationProgressType
from rule_builder.cached_world import CachedRuleBuilderWorld
from rule_builder.rules import Rule, And, Or, Has, HasGroup, CanReachRegion, HasAll, False_

from pathlib import Path
from importlib.resources.abc import Traversable
import itertools
import logging
import settings
from types import SimpleNamespace
import Utils

from .options import GTFOOptions
from .mid_model import *
from .gen_model import *

class GTFOLocation(Location):
    game: str = "GTFO"

class GTFOItem(Item):
    game: str = "GTFO"

class GTFOWorld(CachedRuleBuilderWorld):
    """
    Base class used for GTFO worlds. Derived classes will be dynamically
    created on-demand using AutoWorldRegister (see bottom of file)
    """

    class GTFOSettings(settings.Group):
        """Settings class for GTFO (unused)"""
        game: ClassVar[str] ## Overwritten when created

    ## Constants
    origin_region_name: str = "Menu"

    ## Required by AP
    game: ClassVar[str]
    topology_present: bool = True
    options_dataclass = GTFOOptions
    options: GTFOOptions
    location_name_to_id: ClassVar[Dict[str, int]]
    item_name_to_id: ClassVar[Dict[str, int]]
    item_name_groups: ClassVar[Dict[str, Set[str]]]
    item_mapping: ClassVar[Dict[str, str]]

    ## Class variables
    class_logger: ClassVar[logging.Logger]
    gen_model: ClassVar[Gen_GameData]
    tag_model_by_id: ClassVar[Mapping[int, Gen_Tag]]
    tag_model_by_name: ClassVar[Mapping[str, Gen_Tag]]
    item_model_by_id: ClassVar[Mapping[int, Gen_Item]]
    empty_item_model: ClassVar[Gen_Item] ## To be replaced with filler items in the future

    ## Per-player variables
    logger: logging.Logger

    root_seed: int = 0
    required_expeditions: Set[str]
    whitelist_tags: Set[int]
    blacklist_tags: Set[int]
    require_secondaries: bool
    require_overloads: bool

    ## Game options converted to tags
    early_items: Dict[int, int]
    start_inventory: Dict[int, int]

    ## Per-game Common options that are not implemented yet
    # local_items
    # non_local_items
    # start_hints
    # start_location_hints
    # exclude_locations
    # priority_locations
    # item_links
    # plando_items

    ## Universal Tracker integration
    ut_can_gen_without_yaml: bool = True

    @staticmethod
    def interpret_slot_data(slot_data: dict[str, Any]) -> dict[str, Any]:
        """Triggers a regen in Universal Tracker"""
        return slot_data

    @override
    def generate_early(self) -> None:
        """
        Run before any general steps of the MultiWorld other than options. Useful for getting and adjusting option
        results and determining layouts for entrance rando etc. start inventory gets pushed after this step.
        """

        ## Init slot data
        self.logger = logging.getLogger(f"GTFO.{type(self).game}.{self.multiworld.get_player_name(self.player)}")
        self.root_seed = self.random.randrange(0, 2**52) ## I could do 2**63... but why?
        self.required_expeditions = self.options.required_expeditions.value
        self.require_secondaries = self.options.require_secondaries != 0
        self.require_overloads = self.options.require_overloads != 0

        ## Import the user's tag declarations
        def move_to_tag_set(dest: Set[int], source: Iterable[str], debug_name: str) -> None:
            """Helper which moves a list of tag names into a set"""
            for key in source:
                tag = type(self).tag_model_by_name.get(key.lower(), None)
                if tag is None:
                    self.logger.error(f"Failed to find tag while parsing {debug_name}: {key}")
                    continue
                dest.add(tag.id)

        def move_to_tag_dict(dest: Dict[int, int], source: Mapping[str, int], debug_name: str) -> None:
            """Helper which moves a dict of string tag names into a dict of tag counts"""
            for key, value in source.items():
                tag = type(self).tag_model_by_name.get(key.lower(), None)
                if tag is None:
                    self.logger.error(f"Failed to find tag while parsing {debug_name}: {key}")
                    continue
                dest[tag.id] = (value if value is not None else 0)

        self.whitelist_tags = set()
        move_to_tag_set(self.whitelist_tags, self.options.whitelist.value, "whitelist_tags")
        always_tag = type(self).tag_model_by_name.get("Always".lower(), None)
        if always_tag is not None: self.whitelist_tags.add(always_tag.id)

        self.blacklist_tags = set()
        move_to_tag_set(self.blacklist_tags, self.options.blacklist.value, "blacklist_tags")
        always_tag = type(self).tag_model_by_name.get("Never".lower(), None)
        if always_tag is not None: self.blacklist_tags.add(always_tag.id)

        self.early_items = dict()
        move_to_tag_dict(self.early_items, self.options.early_items.value, "early_items")

        self.start_inventory = dict()
        move_to_tag_dict(self.start_inventory, self.options.start_inventory.value, "start_inventory")
        self.options.start_inventory.value.clear() ## Prevent Archipelago from trying to use this

        ## Universal Tracker integration
        re_gen_passthrough = getattr(self.multiworld, "re_gen_passthrough", {})
        if re_gen_passthrough and self.game in re_gen_passthrough:
            slot_data: Dict[str, Any] = re_gen_passthrough[self.game]

            self.root_seed = slot_data["RootSeed"]
            self.required_expeditions = slot_data["ExpeditionNames"]
            self.whitelist_tags = slot_data["WhitelistTags"]
            self.blacklist_tags = slot_data["BlacklistTags"]
            self.require_secondaries = slot_data["RequiresSecondaries"]
            self.require_overloads = slot_data["RequiresOverloads"]

        ## Init random with our seed so it's consistent between UT and non-UT
        self.random.seed(self.root_seed)

    @override
    def create_regions(self) -> None:
        """
        For the sake of simplicity, we will do all our work in this one method
        """

        #######################################################################
        ## Regions
        
        ## Find all the regions we're working with
        expedition_lookup = { exp.name: exp for exp in self.gen_model.expeditions }
        reachable_region_ids: Set[int]

        if "All" in self.required_expeditions:
            if len(self.required_expeditions) > 1:
                self.logger.warning(
                    "When using the \"All\" expedition filter it should be the only filter."
                    + " All other entries are being ignored!"
                )
            self.required_expeditions = { e.name for e in self.gen_model.expeditions }
            reachable_region_ids = { r.id for r in self.gen_model.regions }
        else:
            reachable_region_ids = set()
            for exp in self.required_expeditions:
                edata = expedition_lookup.get(exp, None)
                if edata is None:
                    self.logger.warning(f"Failed to find and enable expedition: {exp}")
                    continue
                reachable_region_ids.update(edata.reachable_regions)
        
            ## We'll handle the origin region as a special case
            for r in self.gen_model.regions: ## Typically first (or near front)
                if r.name == self.origin_region_name:
                    reachable_region_ids.add(r.id)
                    break
            else:
                self.logger.error("Failed to find origin region ID")

        ## Create the regions!
        region_lookup = { 
            r.id: Region(r.name, self.player, self.multiworld)
                for r in self.gen_model.regions if r.id in reachable_region_ids
        }
        if any( i not in region_lookup for i in reachable_region_ids ):
            self.logger.error("Failed to find all expected regions during creation!")
        self.multiworld.regions += region_lookup.values()
            
        #######################################################################
        ## Locations and Items Init

        ## Fetch and set randomization on relevant locations
        reachable_locations = [ 
            loc for loc in self.gen_model.locations 
                if all( r in reachable_region_ids for r in loc.owning_regions ) 
        ]
        for loc in reachable_locations: 
            loc.is_randomized = self.tags_listed_default(loc.name_tag, loc.tag2, loc.tag3)
            if loc.is_randomized and loc.rand_data.is_empty:
                loc.item_id = 0 ## In case we accidentally pull used data

        ## Set randomization on relevant items - we won't really be referencing the relevant item set after this
        relevant_item_ids = { loc.item_id for loc in reachable_locations if loc.item_id != 0 }
        relevant_item_ids.update(self.gen_model.floating_items)
        for item_id in relevant_item_ids:
            gen_item = self.item_model_by_id[item_id]
            gen_item.is_randomized = \
                (gen_item.required_expedition is None or gen_item.required_expedition in self.required_expeditions) \
                and self.tags_listed_default(gen_item.name_tag, gen_item.tag2, gen_item.tag3)

        #######################################################################
        ## Floating Item Distribution

        floating_items: List[int] = []
        def distribute(empty_locations: List[Gen_Location]) -> None:
            """Helper to distribute currently queued floating items into available empty locations"""
            if not floating_items: ## Must have at least one floating item to distribute
                return

            step: float
            if len(floating_items) >= len(empty_locations):
                step = 1.0 ## Fill all locations
            else:
                step = len(floating_items) / len(empty_locations)
            accum: float = 0.2 ## Starts at .2 to avoid rounding issues

            for i in range(len(empty_locations)):
                accum += step
                if accum >= 1.0:
                    index = (i + abs(self.root_seed)) % len(empty_locations)
                    if empty_locations[index].item_id != 0:
                        raise Exception("Overwriting floating item ID. I messed up somewhere!")
                    empty_locations[index].item_id = floating_items.pop(0)
                    accum -= 1.0

                    self.logger.debug(
                        f"Distributed item {empty_locations[index].item_id} into location {empty_locations[index].id}"
                    )

        ## Round 1: Progression items into priority locations
        floating_items = [ 
            i for i in self.gen_model.floating_items 
                if self.item_model_by_id[i].is_randomized 
                and self.item_model_by_id[i].rand_data.is_progression
        ]
        seen_items = { f for f in floating_items }
        distribute([
            l for l in reachable_locations 
                if l.is_randomized 
                and l.item_id == 0 
                and l.rand_data.priority_mode == "Priority" 
        ])

        ## Round 2: Progression items in all locations
        distribute([
            l for l in reachable_locations 
                if l.is_randomized 
                and l.item_id == 0 
                and l.rand_data.priority_mode != "Excluded" 
        ])

        ## Round 3: All items into all locations
        floating_items.extend(
            i for i in self.gen_model.floating_items 
                if self.item_model_by_id[i].is_randomized 
                and not i in seen_items
        )
        distribute([
            l for l in reachable_locations 
                if l.is_randomized 
                and l.item_id == 0 
        ])

        ## Round 4: All remaining items are given
        for i in floating_items:
            name = self.tag_model_by_id[self.item_model_by_id[i].name_tag].name
            self.logger.warning(f"Not enough empty locations. Adding starting item: {name}")
            self.push_precollected(self.create_item_by_id(i))
        
        #######################################################################
        ## Item Creation and Submission
        
        rand_items: List[Gen_Item] = []
        for gen_location in reachable_locations:
            ## Any location still empty is ignored!
            if gen_location.item_id == 0:
                continue
            
            ## Identify the name
            loc_tag = self.tag_model_by_id.get(gen_location.name_tag, None)
            if loc_tag is None:
                self.logger.error(f"Name tag for location {gen_location.id} not found!")
                continue

            ## Identify the main region
            if not gen_location.owning_regions:
                self.logger.error(f"Location not contained in any regions: {loc_tag.name}")
                continue
            main_region = region_lookup.get(gen_location.owning_regions[0], None)
            if main_region is None:
                self.logger.error(f"Location's main region could not be found: {loc_tag.name}")
                continue

            ## Identify the progress type
            progress_type = LocationProgressType.DEFAULT
            if gen_location.rand_data.priority_mode == "Priority":
                progress_type = LocationProgressType.PRIORITY
            elif gen_location.rand_data.priority_mode in [ "Excluded", "Trap" ]:
                progress_type = LocationProgressType.EXCLUDED

            ## Build the location and item pair
            location = GTFOLocation(self.player, loc_tag.name, gen_location.id, main_region)
            location.progress_type = progress_type
            main_region.locations.append(location)

            ## Add the access rule (if needed)
            if len(gen_location.owning_regions) > 1:
                rule = And(*( CanReachRegion(region_lookup[r].name) for r in gen_location.owning_regions[1:] ))
                self.set_rule(location, rule)

            ## Either pair them together or randomize them!
            gen_item = self.item_model_by_id[gen_location.item_id]
            if gen_location.is_randomized and gen_item.is_randomized:
                rand_items.append(gen_item)
                item_tag = self.tag_model_by_id[gen_item.name_tag]
                self.logger.debug(f"Randomized: {location.name} - {item_tag.name}")
            else:
                item = self.create_item_by_model(gen_item)
                location.place_locked_item(item)
                self.logger.debug(f"Locked: {location.name} - {item.name}")

        ## Handling unused floating items
        ## Some unused floating items, such as expedition unlocks, are presume held if not randomized.
        ## We handle this by just giving it to the play as part of the starting inventory
        for i in self.gen_model.floating_items:
            gen_item = self.item_model_by_id[i]
            if (not gen_item.is_randomized) and gen_item.rand_data.collected_by_default:
                ## Create and give the item - We'll catch it during init
                self.multiworld.push_precollected(self.create_item_by_model(gen_item))
        
        #######################################################################
        ## Early and Start Items

        ## Checking to ensure at least one expedition is unlocked at game start
        unlock_tags = {
            type(self).tag_model_by_name[f"{exp} Expedition Unlock".lower()].id for exp in self.required_expeditions
        }
        if all(self.tags_listed_default(tag) for tag in unlock_tags):
            start_tags = {key for key, value in self.start_inventory.items() if value is not None and value > 0}
            if not any(type(self).tag_matches(tag, start_tags) for tag in unlock_tags):
                self.logger.warning(
                    "Detected that all expeditions are locked. Randomly picking one starting expedition."
                )
                self.start_inventory[type(self).tag_model_by_name["Expedition Unlock Items".lower()].id] = 1

        ## Setting up the help used to get items by tag
        def claim_by_tags(requested_tags: Mapping[int, int], callback: Callable[[Gen_Item], None], debug_name: str):
            """Claims items by ID from the randomization list and calls the provided callback"""

            ## "r_" is short for "requested" and is used to prevent shadowing
            for r_tag, r_count in requested_tags.items():
                r_wl = {r_tag}
                r_bl = set()

                matches = [
                    (1 if type(self).tags_listed(gi.name_tag, gi.tag2, gi.tag3, wl=r_wl, bl=r_bl) else 0)
                    for gi in rand_items
                ]
                match_count = sum(matches)

                if match_count < r_count:
                    self.logger.warning(
                        f"Requested {r_count} items matching tag {type(self).tag_model_by_id[r_tag].name}"
                        f" for {debug_name}, found {match_count}; {match_count} items will be supplied."
                    )
                    for i in reversed(range(len(matches))):
                        if matches[i] == 1:
                            callback(rand_items.pop(i))
                else:
                    sample = self.random.sample(range(len(rand_items)), r_count, counts=matches)
                    for i in reversed(sample):
                        callback(rand_items.pop(i))

        ## Starting items
        def start_item_callback(local_gi: Gen_Item) -> None:
            local_item = self.create_item_by_model(local_gi)
            self.multiworld.push_precollected(local_item)
            self.multiworld.itempool.append(self.create_filler()) ## To maintain balance
            self.logger.debug(f"Added as a starting item: {local_item.name}")
        claim_by_tags(self.start_inventory, start_item_callback, "start_inventory")

        def early_item_callback(local_gi: Gen_Item) -> None:
            local_item = self.create_item_by_model(local_gi)
            self.multiworld.itempool.append(local_item)
            early_items = self.multiworld.early_items.get(self.player, None)
            if early_items is None:
                early_items = dict()
                self.multiworld.early_items[self.player] = early_items
            early_items[local_item.name] = early_items.get(local_item.name, 0) + 1
            self.logger.debug(f"Added as an early item: {local_item.name}")
        claim_by_tags(self.early_items, early_item_callback, "early_items")

        ## Finally, we simply add any remaining randomized items to the pool
        self.multiworld.itempool.extend(self.create_item_by_model(m) for m in rand_items)
        
        #######################################################################
        ## Paths - Added after items to ensure item_name_groups is valid

        for gen_path in self.gen_model.paths:

            ## Get the regions, check if path exists
            start_region = region_lookup.get(gen_path.starting_region, None)
            end_region = region_lookup.get(gen_path.ending_region, None)
            if start_region is None or end_region is None:
                continue
            path_name = f"{start_region.name} -> {end_region.name}" \
                if gen_path.name is None else gen_path.name

            ## Build the rule
            path_rule: Optional[Rule] = None
            if gen_path.name == "R6B1 (Main) ZONE_33 Main Entry":
                path_rule = False_()

            if gen_path.req_item.type != "None":
                target_tag = type(self).tag_model_by_id[gen_path.req_item.target]

                if gen_path.req_item.type == "Item":
                    path_rule = Has(target_tag.name, gen_path.req_count)
                elif gen_path.req_item.type == "Category":
                    if not target_tag.name in type(self).item_name_groups:
                        type(self).item_name_groups[target_tag.name] = set()
                    path_rule = HasGroup(target_tag.name, gen_path.req_count)
                elif gen_path.req_item.type == "Blocked":
                    path_rule = False_()
                else:
                    raise Exception(f"Unknown path req type: {gen_path.req_item.type}")
                path_rule: Rule

                if gen_path.alt_item.type != "None":
                    target_tag = self.tag_model_by_id[gen_path.alt_item.target]

                    if gen_path.alt_item.type == "Item":
                        path_rule = Or(path_rule, Has(target_tag.name, 1))
                    elif gen_path.alt_item.type == "Category":
                        if not target_tag.name in type(self).item_name_groups:
                            type(self).item_name_groups[target_tag.name] = set()
                        path_rule = Or(path_rule, HasGroup(target_tag.name, 1))
                    elif gen_path.req_item.type == "Blocked":
                        path_rule = Or(path_rule, False_())
                    else:
                        raise Exception(f"Unknown path alt type: {gen_path.alt_item.type}")

            ## Create the path!
            start_region.connect(end_region, path_name, path_rule)
            self.logger.debug(f"Path {start_region.name} -> {end_region.name} | Rule: {path_rule.__str__()}")

        #######################################################################
        ## Win Condition

        ## Set the tags so we can filter by tag for relevant goal items
        wl = { type(self).tag_model_by_name["Goal Items".lower()].id } ## By default, all goal items
        bl = { ## Blacklist all goal items for expeditions we're not completing
            type(self).tag_model_by_name[f"{exp.name} Goal Items".lower()].id for exp in self.gen_model.expeditions
                if exp.name not in self.required_expeditions 
        }

        for exp in self.required_expeditions:

            if not self.options.require_secondaries:
                tag_name = f"{exp} (Secondary) Sector Clear"
                tag = self.tag_model_by_name.get(tag_name.lower(), None)
                if tag is not None:
                    bl.add(tag.id)

            if not self.options.require_overloads:
                tag_name = f"{exp} (Overload) Sector Clear"
                tag = self.tag_model_by_name.get(tag_name.lower(), None)
                if tag is not None:
                    bl.add(tag.id)

        ## Check each item ID that is *actually* spawned (including if it's spawned multiple times)
        all_item_ids = itertools.chain( 
            ( loc.item_id for loc in reachable_locations if loc.item_id != 0 ),
            self.gen_model.floating_items
        )
        win_items: List[str] = [ ]

        for item_id in all_item_ids:
            gen_item = self.item_model_by_id.get(item_id, None)
            if gen_item is None:
                self.logger.warning(f"Failed to look up potential goal item with ID: {item_id}")
                continue

            is_needed: bool = gen_item.required_expedition is None \
                or gen_item.required_expedition in self.required_expeditions
            is_needed = is_needed \
                and type(self).tags_listed(gen_item.name_tag, gen_item.tag2, gen_item.tag3, wl=wl, bl=bl)

            if is_needed:
                item_tag = self.tag_model_by_id.get(gen_item.name_tag, None)
                if item_tag is None:
                    self.logger.error(f"Failed to find name tag for goal item: {item_id}")
                else:
                    win_items.append(item_tag.name)

        rule = HasAll( *win_items )
        self.set_completion_rule(rule)

    @override
    def create_item(self, item_name: str) -> GTFOItem:
        """
        Create an item for this world type and player.
        Warning: this may be called with self.world = None, for example by MultiServer
        """
        item_id = self.item_name_to_id.get(item_name, None)
        if item_id is None:
            self.logger.warning(f"Failed to look up item by name: {item_name}, using filler instead")
            return self.create_filler()
        return self.create_item_by_id(item_id)
    
    def create_item_by_id(self, item_id: int) -> GTFOItem:
        
        gen_item = self.item_model_by_id.get(item_id, None)
        if gen_item is None:
            self.logger.error(f"Failed to create item by id: {item_id}, using filler instead")
            return self.create_filler()
        
        return self.create_item_by_model(gen_item)

    def create_item_by_model(self, gen_item: Gen_Item) -> GTFOItem:

        ## Create classification data
        classification: ItemClassification = cast(ItemClassification, 0)
        if gen_item.rand_data.is_progression:
            classification |= ItemClassification.progression
        if gen_item.rand_data.is_useful:
            classification |= ItemClassification.useful
        if gen_item.rand_data.is_filler:
            classification |= ItemClassification.filler
        if gen_item.rand_data.is_trap:
            classification |= ItemClassification.trap
        if gen_item.rand_data.do_skip_balancing:
            classification |= ItemClassification.skip_balancing
        if gen_item.rand_data.is_deprioritized:
            classification |= ItemClassification.deprioritized

        ## Create the item itself and add custom properties
        name_tag = self.tag_model_by_id.get(gen_item.name_tag, None)
        if name_tag is None:
            self.logger.error(f"Failed to find name tag for item with id: {gen_item.id}")
            return self.create_filler()
        item = GTFOItem(name_tag.name, classification, gen_item.id, self.player)

        return item

    @override
    def get_filler_item_name(self):
        return "Empty"

    @override
    def create_filler(self) -> GTFOItem:
        """Create a random filler item, which may be a trap item"""
        return self.create_item_by_model(self.empty_item_model)

    @override
    def fill_slot_data(self) -> Mapping[str, Any]:
        return {
            "RootSeed": self.root_seed,
            "ExpeditionNames": self.required_expeditions,
            "WhitelistTags": self.whitelist_tags,
            "BlacklistTags": self.blacklist_tags,
            "RequiresSecondaries": self.require_secondaries,
            "RequiresOverloads": self.require_overloads,
        }

    @classmethod
    def tag_matches(cls, tag: int, tag_set: Set[int]):
        """Check if a tag matches against a set of tags. Adds the tag's parents if it does."""
        if tag in tag_set:
            return True

        tag_def: Optional[Gen_Tag] = cls.tag_model_by_id.get(tag, None)
        if tag_def is not None and cls.tag_matches(tag_def.parent, tag_set):
            tag_set.add(tag)
            return True
        else:
            return False

    @classmethod
    def tags_listed(cls, *tags: int, wl: Set[int], bl: Set[int]):
        """Check if any tag matches a particular whitelist and not a particular blacklist"""
        return any( cls.tag_matches(tag, wl) and not cls.tag_matches(tag, bl) for tag in tags )

    def tags_listed_default(self, *tags: int):
        """Check if any tag matches the default whitelist and not the default blacklist"""
        return type(self).tags_listed(*tags, wl=self.whitelist_tags, bl=self.blacklist_tags)

class GTFOWorldBuilder:
    """Wraps the creation and storage of GTFO Worlds"""

    vanilla_world: Optional[Type[GTFOWorld]] = None
    """The main, "Vanilla" world created by this builder"""

    all_worlds: Dict[str, Type[GTFOWorld]] = dict()
    """
    All worlds made by this builder, keyed by name (ie "GTFO (MyModSet)"). 
    Includes the vanilla world, which is keyed under the name "GTFO"
    """

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
    def make_worlds(cls):
        """
        Create / rebuild all GTFO worlds from file.
        For internal use only; this supports rebuild, but does not account for AutoWorldRegister needing to be
         cleaned of existing GTFO worlds, or for any other dangling references.
        """

        ## Define this now so we can choose to overwrite it as we scan
        main_file: Union[Traversable, Path] = importlib.resources.files().joinpath("data").joinpath("GTFO.ini")

        ## Check players folder for modded worlds or vanilla override data (new version, for example)
        for file in Path(f"{Utils.local_path()}/Players").iterdir():
            lower = file.name.lower()
            if not file.is_file():
                pass
            elif lower.startswith("gtfo-") and lower.endswith(".ini"):
                g_name = f"GTFO ({file.name[5:-4]})" ## Removes gtfo- and .ini
                cls.all_worlds[g_name] = cls.make_world(g_name, file)
            elif lower == "gtfo.ini":
                main_file = file.resolve() ## Overrides the vanilla definition

        ## Create the main ("vanilla") world
        g_name = "GTFO"
        klass = cls.make_world(g_name, main_file)
        cls.vanilla_world = klass
        cls.all_worlds[g_name] = klass

    @classmethod
    def make_world(cls, world_name: str, world_file: Union[Path, Traversable]) -> Type[GTFOWorld]:
        """Programmatically create a new AutoWorldRegister for the given GTFO world."""

        if world_name in GTFOWorldBuilder.all_worlds is None:
            raise Exception("Exception!")

        ## Using a SimpleNamespace to provide type hints
        klass = SimpleNamespace(GTFOWorld.__dict__.copy())
        klass: Type[GTFOWorld]

        ## Attempt to find and load data from file
        try:
            with world_file.open("r") as file_data:
                loaded_mid_model = Mid_GameData(json.load(file_data))
                klass.gen_model = Gen_GameData(loaded_mid_model)
                del loaded_mid_model
        except OSError as e: ## Failed to open file
            raise Exception(f"Failed to find GTFO MID file for game: {world_name}") from e
        except json.JSONDecodeError as e: ## JSON parsing failed
            raise Exception(f"Failed to parse GTFO MID file for game: {world_name}") from e
        except Exception as e: ## Generic failure during gen_model instantiation
            raise Exception(f"Malformed GTFO MID file for game: {world_name}") from e

        ## Init class variables
        klass.game = world_name
        klass.__doc__ = GTFOWorldBuilder.docstring
        klass.gen_model = klass.gen_model
        klass.class_logger = logging.getLogger(f"GTFO.{world_name}")
        klass.tag_model_by_id = { tag.id: tag for tag in klass.gen_model.tags }
        klass.tag_model_by_name = { tag.name.lower(): tag for tag in klass.gen_model.tags }
        klass.item_model_by_id = { item.id: item for item in klass.gen_model.items }
        klass.location_name_to_id = { klass.tag_model_by_id[loc.name_tag].name: loc.id for loc in klass.gen_model.locations }
        klass.item_name_to_id = { klass.tag_model_by_id[item.name_tag].name: item.id for item in klass.gen_model.items }

        empty_item = klass.item_name_to_id.get("Empty", None)
        if empty_item is None:
            klass.class_logger.error(f"Failed to find the empty item for game: {world_name}")
        else:
            klass.empty_item_model = klass.item_model_by_id[empty_item]

        ## Set up item groups and name mapping
        klass.item_name_groups = dict()
        klass.item_mapping = dict()
        for gen_item in klass.gen_model.items:
            if gen_item.path_reqs.type != "Category": continue
            item_name = klass.tag_model_by_id[gen_item.name_tag].name
            group_name = klass.tag_model_by_id[gen_item.path_reqs.target].name

            group = klass.item_name_groups.get(group_name, None)
            if group is None:
                group = { item_name }
                klass.item_name_groups[group_name] = group
            else:
                group.add(item_name)

            klass.item_mapping[item_name] = group_name

        ## We overwrite "klass" with an actual instance (instead of faking it with a SimpleNamespace)
        ## Note that we use the metaclass associated with GTFOWorld to create the derived instance
        return cast(Type[GTFOWorld], type(GTFOWorld)(world_name, (GTFOWorld,), klass.__dict__))

## Now we simply create all the GTFO worlds
GTFOWorldBuilder.make_worlds()


