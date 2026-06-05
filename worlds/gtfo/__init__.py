# world/gtfo/__init__.py

from __future__ import annotations
import dataclasses
import importlib.resources
from importlib.resources.abc import Traversable
import itertools
import json
import logging
from pathlib import Path
from typing import Any, cast, ClassVar, Dict, Iterable, List, Mapping, Optional, override, Set, Tuple, Type, Union
from types import SimpleNamespace
import Utils

import Options
from BaseClasses import Region, Location, Item, ItemClassification, LocationProgressType
from rule_builder.cached_world import CachedRuleBuilderWorld
from rule_builder.rules import Rule, And, Or, Has, HasGroup, CanReachRegion, HasFromList, False_

from .options import GTFOOptions, OptionEvaluationState
from .model import GameDataModel, ExpeditionDataModel, TagModel, RegionModel, PathModel, ReqItemModel, \
                    LocationModel, LocationDataModel, ItemModel, ItemDataModel, \
                    OptionBaseModel, OptionInputModel
from pydantic import ValidationError

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
    topology_present: bool = True
    """Indicates the regions of this game correspond to actual physical locations (which is mostly true)"""
    options_dataclass: ClassVar[GTFOOptions]
    """The dataclass to use for this world. This will be set from MID data."""

    _options: GTFOOptions
    """Actual options instance for this world"""

    @property
    def options(self) -> GTFOOptions:
        """Options getter; required because we need to react to set operations"""
        return self._options

    @options.setter
    def options(self, value: GTFOOptions):
        """Options setter, used to update internal state when the options are set/changed"""
        self._options = value
        self.setup_from_options()

    location_name_to_id: ClassVar[Dict[str, int]]
    """Map of location names to location IDs. This will be populated from MID data"""
    item_name_to_id: ClassVar[Dict[str, int]]
    """Map of item names to item IDs. This will be populated from MID data"""
    item_name_groups: ClassVar[Dict[str, Set[str]]]
    """Maps an item group name to a set of item names. This will be populated from MID data"""
    item_mapping: ClassVar[Dict[str, str]]
    """Maps an item name to its group. This will be populated from MID data"""

    ## Class variables
    class_logger: ClassVar[logging.Logger]
    """Logger for the class (world)"""
    gen_model: ClassVar[GameDataModel]
    """Imported MID data"""
    tag_model_by_id: ClassVar[Mapping[int, TagModel]]
    """Tag lookup via ID"""
    tag_model_by_name: ClassVar[Mapping[str, TagModel]]
    """Tag lookup via name"""
    item_model_by_id: ClassVar[Mapping[int, ItemModel]]
    """Item lookup by id"""
    empty_item_model: ClassVar[ItemModel]
    """Default filler item which does nothing. To be replaced with filler items in future update"""
    option_model_by_id: ClassVar[Mapping[int, OptionBaseModel]]
    """Option model lookup used for options evaluation"""
    option_groups: ClassVar[List[Options.OptionGroup]]
    """List of generated option groups for the option dataclass"""

    ## Per-player variables
    logger: logging.Logger
    """Logger for the world instance, ie one per player"""
    start_vouchers: Dict[int, int]
    """Dict of (tag, count) of items to pull prior to randomization and add to the starting inventory"""
    early_items: Dict[int, int]
    """Dict of (tag, count) of items to set as early"""
    #local_items: Set[int]
    """Tags for items to force as local. Removed because we make Archipelago handle this for us."""
    #non_local_items: Set[int]
    """Tags for items to force as nonlocal. Removed because we make Archipelago handle this for us."""
    #start_inventory: Mapping[int, int]
    """Tags and counts for items to place in our starting inventory. Removed because we make Archipelago handle this"""
    #start_hints: Mapping[int, int]
    """Tags and counts for items and locations which start hinted. Removed because we make Archipelago handle this."""
    exclude_locations: Set[int]
    """Tags for locations to override and mark as excluded"""
    priority_locations: Set[int]
    """Tags for locations to override and mark as priorities"""
    goal_blacklist: Dict[int, int]
    """Tag blacklist for goal items. The whitelist is all goal items"""
    reachable_regions: Set[int]
    """The set of region IDs that can be reached using the provided settings"""
    reachable_locations: Set[LocationModel]
    """The set of location IDs fully contained within reachable_regions"""

    ## Slot data
    root_seed: int = 0
    """Seed used for randomization"""
    required_expeditions: Set[Optional[str]]
    """Set of expeditions the player is required to explore; set of expeditions available to the player"""
    whitelist_tags: Set[int]
    """Whitelist tags for testing randomization of locations and items"""
    blacklist_tags: Set[int]
    """Blacklist tags for testing randomization of locations and items"""
    filled_empty_locations: List[Tuple[int, int]]
    """List of empty locations that were filled with a floating item during generation"""
    goal_items: List[int]
    """List of items required to reach the goal"""
    skippable_goal_count: int
    """Number of goal items which can be skipped"""
    fail_if_insufficient_empty_locations: bool
    """If true, raise an exception if there are insufficient empty locations for the selected floating items"""

    ## Universal Tracker integration
    ut_can_gen_without_yaml: ClassVar[bool] = True
    """Indicates UT can skip YAML parsing for this world during UT's generation passes"""

    @staticmethod
    def interpret_slot_data(slot_data: dict[str, Any]) -> dict[str, Any]:
        """Triggers a regen in Universal Tracker"""
        return slot_data

    def __init__(self, *args, **kwargs):
        """Init this world (specifically, the logger)"""
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(f"GTFO.{type(self).game}.{self.multiworld.get_player_name(self.player)}")

    def setup_from_options(self):
        """
        Called by the `options` setter. Initializes necessary data from the options class.
        Also sets up the options class with relevant data.
        """

        #######################################################################
        ## Init data

        self.root_seed = self.random.randrange(0, 2**52)
        self.required_expeditions = self.options.required_expeditions.value.copy()
        if "All" in self.required_expeditions:
            self.required_expeditions = { e.name for e in self.gen_model.expeditions }
        self.skippable_goal_count = self.options.skippable_goal_count.value
        self.fail_if_insufficient_empty_locations = self.options.fail_if_insufficient_empty_locations.value != 0

        ## Universal Tracker integration
        re_gen_passthrough = getattr(self.multiworld, "re_gen_passthrough", {})
        if re_gen_passthrough and self.game in re_gen_passthrough:
            slot_data: Dict[str, Any] = re_gen_passthrough[self.game]
            self.root_seed = slot_data["RootSeed"]
            self.required_expeditions = slot_data["ExpeditionNames"]
            self.skippable_goal_count = slot_data["SkippableGoalCount"]

        ## Enforces consistency between UT and non-UT
        self.random.seed(self.root_seed)

        ## Identify reachable regions
        expedition_lookup = { e.name: e for e in self.gen_model.expeditions }
        not_found_expeditions: List[str] = []
        self.reachable_regions = set()
        for e_name in self.required_expeditions:
            if e_name is None: continue
            e: Optional[ExpeditionDataModel] = expedition_lookup.get(e_name)
            if e is None:
                not_found_expeditions.append(e_name)
            else:
                self.reachable_regions.update(e.reachable_regions)

        ## Identify and add menu region
        for r in self.gen_model.regions:
            if r.name == self.origin_region_name:
                self.reachable_regions.add(r.id)

        self.required_expeditions.add(None)  ## Makes logic easier
        self.reachable_locations = {
            l for l in self.gen_model.locations if all(r in self.reachable_regions for r in l.owning_regions)
         }

        #######################################################################
        ## Import user options as tags

        oe_state = OptionEvaluationState()
        oe_state.world = self
        oe_state.started_ids = set()
        oe_state.evaluated_ids = set()
        oe_state.not_found_tags = dict()
        def move_to_tag_set(dest: Set[int], source: Iterable[str], debug_name: str) -> None:
            """Helper which moves a list of tag names into a set"""
            for key in source:
                found_tag = type(self).tag_model_by_name.get(key.lower(), None)
                if found_tag is None:
                    oe_state.not_found_tags.setdefault(debug_name, []).append(key)
                else:
                    dest.add(found_tag.id)

        def move_to_tag_dict(dest: Dict[int, int], source: Mapping[str, int], debug_name: str) -> None:
            """Helper which moves a dict of string tag names into a dict of tag counts"""
            for key, value in source.items():
                found_tag = type(self).tag_model_by_name.get(key.lower(), None)
                if found_tag is None:
                    oe_state.not_found_tags.setdefault(debug_name, []).append(key)
                else:
                    dest[found_tag.id] = (value if value is not None else 0)

        self.whitelist_tags = set()
        move_to_tag_set(self.whitelist_tags, self.options.whitelist.value, "whitelist_tags")
        always_tag = type(self).tag_model_by_name.get("Always".lower(), None)
        if always_tag is not None: self.whitelist_tags.add(always_tag.id)

        self.blacklist_tags = set()
        move_to_tag_set(self.blacklist_tags, self.options.blacklist.value, "blacklist_tags")
        never_tag = type(self).tag_model_by_name.get("Never".lower(), None)
        if never_tag is not None: self.blacklist_tags.add(never_tag.id)

        self.early_items = dict()
        move_to_tag_dict(self.early_items, self.options.early_items.value, "early_items")

        self.start_vouchers = dict()
        move_to_tag_dict(self.start_vouchers, self.options.start_vouchers.value, "start_vouchers")

        oe_state.local_items = set()
        move_to_tag_set(oe_state.local_items, self.options.gtfo_local_items.value, "local_items")

        oe_state.non_local_items = set()
        move_to_tag_set(oe_state.non_local_items, self.options.gtfo_non_local_items.value, "non_local_items")

        oe_state.start_inventory = dict()
        move_to_tag_dict(oe_state.start_inventory, self.options.gtfo_start_inventory.value, "start_inventory")

        oe_state.start_hints = dict()
        move_to_tag_dict(oe_state.start_hints, self.options.gtfo_start_hints.value, "start_hints")

        self.exclude_locations = set()
        move_to_tag_set(self.exclude_locations, self.options.gtfo_exclude_locations.value, "exclude_locations")

        self.priority_locations = set()
        move_to_tag_set(self.priority_locations, self.options.gtfo_priority_locations.value, "priority_locations")

        self.goal_blacklist = dict()
        move_to_tag_dict(self.goal_blacklist, self.options.goal_blacklist.value, "goal_blacklist")

        ## Evaluate options
        for option in self.option_model_by_id.values():
            oe_state.evaluate(option)

        ## Report badly-formatted (or erroneous) expedition names and tag names
        if not_found_expeditions or oe_state.not_found_tags:
            error_message: str = f"YAML file parsing failed for player: {self.multiworld.get_player_name(self.player)}"

            ## Expedition checking
            if not_found_expeditions:
                error_message += f"Failed to find {len(not_found_expeditions)} expeditions."
                choices = expedition_lookup.keys()
                for e_name in not_found_expeditions:
                    match = Utils.get_fuzzy_results(e_name, choices, 1)
                    if match and match[0][1] > .3:
                        error_message += f'\n -"{e_name}" (Did you mean "{match[0][0]}"? {100 * match[0][1]}% certain)'
                    else:
                        error_message += f'\n -"{e_name}" (No likely matches found)'

            ## Tag checking
            tag_choices = self.tag_models.keys()
            for option_name, tags in oe_state.not_found_tags:
                error_message += f"Failed to find {len(tags)} tags in setting {option_name}."
                for t_name in tags:
                    match = Utils.get_fuzzy_results(t_name, tag_choices, 1)
                    if match and match[0][1] > .3:
                        error_message += f'\n -"{t_name}" (Did you mean "{match[0][0]}"? {100 * match[0][1]}% certain)'
                    else:
                        error_message += f'\n -"{t_name}" (No likely matches found)'

            raise Exception(error_message)

        ## Overwrite the settings we don't control so we can pass them off to Archipelago
        local_items_setting = options.LocalItems([
            self.tag_model_by_id[item.name_tag].name for item in type(self).gen_model.items
            if item.required_expedition in self.required_expeditions
            and type(self).tags_match(*item.tags(), tag_set=oe_state.local_items)
        ])
        nonlocal_items_setting = options.NonLocalItems([
            self.tag_model_by_id[item.name_tag].name for item in type(self).gen_model.items
            if item.required_expedition in self.required_expeditions
            and type(self).tags_match(*item.tags(), tag_set=oe_state.non_local_items)
        ])
        start_inventory_setting = options.StartInventory({
            self.tag_model_by_id[key.name_tag].name: value for key, value
            in self.sample_items(oe_state.start_inventory, True, "Start Inventory").items()
        })
        start_hints_results = self.sample_items(
            oe_state.start_hints, True, "Start Hints",
            list(itertools.chain[LocationModel | ItemModel](
                (i for i in type(self).gen_model.items if i.required_expedition in self.required_expeditions),
                (l for l in self.reachable_locations)
            ))
        )
        start_item_hints = Options.StartHints([
            self.tag_model_by_id[entity.name_tag].name for entity in start_hints_results if entity is ItemModel
        ])
        start_location_hints = Options.StartLocationHints([
            self.tag_model_by_id[entity.name_tag].name for entity in start_hints_results if entity is LocationModel
        ])

        ## Spoof the options class so Archipelago doesn't throw errors
        spoof_options = {
            "local_items": local_items_setting,
            "non_local_items": nonlocal_items_setting,
            "start_inventory": start_inventory_setting,
            "start_hints": start_item_hints,
            "start_location_hints": start_location_hints,
            "exclude_locations": options.ExcludeLocations(list()),
            "priority_locations": options.PriorityLocations(list()),
            "item_links": self.options.gtfo_item_links,
            "plando_items": self.options.gtfo_plando_items,
        }
        for key, value in spoof_options.items():
            self.options.__dict__[key] = value
        return

    @override
    def create_regions(self) -> None:
        """
        For the sake of simplicity, we will do all our work in this one method
        """

        #######################################################################
        ## Regions

        ## Create the regions!
        region_lookup = { 
            r.id: Region(r.name, self.player, self.multiworld)
                for r in self.gen_model.regions if r.id in self.reachable_regions
        }
        if any( i not in region_lookup for i in self.reachable_regions ):
            self.logger.error("Failed to find all expected regions during creation!")
        self.multiworld.regions += region_lookup.values()
            
        #######################################################################
        ## Locations and Items Init

        ## Reset locations and items (since the model is reused between players)
        for gen_loc in type(self).gen_model.locations:
            gen_loc.is_in_required_expeditions = gen_loc.is_whitelisted = gen_loc.is_blacklisted = False
            if gen_loc.rand_data.is_empty:
                gen_loc.item_id = 0
        for gen_item in type(self).gen_model.items:
            gen_item.is_in_required_expeditions = gen_item.is_whitelisted = gen_item.is_blacklisted = False

        ## Set randomization on relevant locations
        for gen_loc in self.reachable_locations:
            gen_loc.is_in_required_expeditions = True
            gen_loc.is_whitelisted = type(self).tags_match(*gen_loc.tags(), tag_set=self.whitelist_tags)
            gen_loc.is_blacklisted = type(self).tags_match(*gen_loc.tags(), tag_set=self.blacklist_tags)

        ## Set randomization on relevant items - we won't really be referencing the relevant item set after this
        relevant_item_ids = { loc.item_id for loc in self.reachable_locations if loc.item_id != 0 }
        relevant_item_ids.update(self.gen_model.floating_items)
        for item_id in relevant_item_ids:
            gen_item = self.item_model_by_id[item_id]
            gen_item.is_in_required_expeditions = gen_item.required_expedition in self.required_expeditions
            gen_item.is_whitelisted = type(self).tags_match(*gen_item.tags(), tag_set=self.whitelist_tags)
            gen_item.is_blacklisted = type(self).tags_match(*gen_item.tags(), tag_set=self.blacklist_tags)

        #######################################################################
        ## Floating Item Distribution

        self.filled_empty_locations = list()
        floating_items: List[int] = []
        def distribute(empty_locations: List[LocationModel]) -> None:
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
                    empty_locations[index].item_id = floating_items.pop()
                    accum -= 1.0
                    self.filled_empty_locations.append((empty_locations[index].id, empty_locations[index].item_id))

        ## Round 1: Progression items into priority locations
        floating_items = [ 
            i for i in self.gen_model.floating_items 
            if self.item_model_by_id[i].should_be_randomized()
            and self.item_model_by_id[i].rand_data.is_progression
        ]
        seen_items = { f for f in floating_items }
        distribute([
            l for l in self.reachable_locations
            if l.should_be_randomized() and l.item_id == 0
            and (
                (l.rand_data.priority_mode == "Priority" and l.id not in self.exclude_locations)
                or l.id in self.priority_locations
            )
        ])

        ## Round 2: Progression items in all locations
        distribute([
            l for l in self.reachable_locations
            if l.should_be_randomized() and l.item_id == 0
            and (
                (l.rand_data.priority_mode != "Excluded" and l.id not in self.exclude_locations)
                or l.id in self.priority_locations
            )
        ])

        ## Round 3: All items into all locations
        floating_items.extend(
            i for i in self.gen_model.floating_items 
            if self.item_model_by_id[i].should_be_randomized()
            and not i in seen_items
        )
        distribute([
            l for l in self.reachable_locations
            if l.should_be_randomized() and l.item_id == 0
        ])

        ## Round 4: All remaining items are given (or raise an exception)
        if len(floating_items) > 0 and self.fail_if_insufficient_empty_locations:
            raise Exception(
                f"Insufficient empty locations! There are {len(floating_items)} unplaced floating items"
                + "\nConsider adding more expeditions or, if possible, enabling more empty locations."
            )
        for i in floating_items:
            name = self.tag_model_by_id[self.item_model_by_id[i].name_tag].name
            self.logger.warning(f"Not enough empty locations. Adding starting item: {name}")
            self.push_precollected(self.create_item_by_id(i))
        
        #######################################################################
        ## Item Creation and Submission
        rand_items: List[ItemModel] = []
        for gen_location in self.reachable_locations:
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
            is_randomized = True \
                and gen_location.is_in_required_expeditions and gen_item.is_in_required_expeditions \
                and (gen_location.is_whitelisted or gen_item.is_whitelisted) \
                and not (gen_location.is_blacklisted or gen_item.is_blacklisted)
            if is_randomized:
                rand_items.append(gen_item)
                item_tag = self.tag_model_by_id[gen_item.name_tag]
                self.logger.debug(f"Randomized: {location.name} - {item_tag.name}")
            else:
                item = self.create_item_by_model(gen_item, not gen_item.rand_data.is_randomlike)
                location.address = gen_location.id if gen_item.rand_data.is_randomlike else None
                location.place_locked_item(item)
                self.logger.debug(f"Locked: {location.name} - {item.name}")

        ## Handling unused floating items
        ## Some unused floating items, such as expedition unlocks, are presumed held if not randomized.
        ## We handle this by just giving it to the play as part of the starting inventory
        for i in self.gen_model.floating_items:
            gen_item = self.item_model_by_id[i]
            if (not gen_item.should_be_randomized()) and gen_item.rand_data.is_collected_by_default:
                self.multiworld.push_precollected(self.create_item_by_model(gen_item))
        
        #######################################################################
        ## Start Vouchers and Early Items

        start_items = self.sample_items(self.start_vouchers, False, "start_vouchers", rand_items)
        for i in range(len(rand_items)):
            gen_item = rand_items[i]
            count = start_items.get(gen_item, 0)
            if count <= 0: continue
            start_items[gen_item] = count - 1
            rand_items[i] = type(self).empty_item_model
            self.multiworld.push_precollected(self.create_item_by_model(gen_item))

        early_items = self.sample_items(self.early_items, False, "early_items", rand_items)
        early_items_dict = self.multiworld.early_items.setdefault(self.player, dict())
        early_items_dict.update({ self.tag_model_by_id[k.name_tag].name: v for k, v in early_items.items() })

        ## Finally, we simply add any remaining randomized items to the pool
        self.multiworld.itempool.extend(self.create_item_by_model(m) for m in rand_items)
        
        #######################################################################
        ## Paths

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
        ## Goal Condition

        ## Set the tags so we can filter by tag for relevant goal items
        wl = { type(self).tag_model_by_name["Goal Items".lower()].id } ## By default, all goal items
        bl = set()

        ## Check each item ID that is *actually* spawned (including if it's spawned multiple times)
        all_item_ids = itertools.chain( 
            ( loc.item_id for loc in self.reachable_locations ),
            self.gen_model.floating_items
        )

        ## Collect all goal items!
        all_goal_items = list()
        for item_id in all_item_ids:
            if item_id == 0: continue
            gen_item = self.item_model_by_id[item_id]

            if gen_item.required_expedition not in self.required_expeditions: continue
            if not type(self).tags_match(*gen_item.tags(), tag_set=wl): continue
            if type(self).tags_match(*gen_item.tags(), tag_set=bl): continue

            all_goal_items.append(gen_item)

        ## From available goal items, sample the items to be removed
        blacklisted_items = self.sample_items(self.goal_blacklist, False, "goal_blacklist", all_goal_items)

        ## Sort through the goal items and add them to our requirements
        goal_names: List[str] = []
        self.goal_items = []
        for gen_item in all_goal_items:
            blacklist_count = blacklisted_items.get(gen_item, 0)
            if blacklist_count > 0:
                blacklisted_items[gen_item] = blacklist_count - 1
                continue

            goal_names.append(type(self).tag_model_by_id[gen_item.name_tag].name)
            self.goal_items.append(gen_item.id)

        ## Rule!
        desired_count: int = len(goal_names) - self.skippable_goal_count
        self.set_completion_rule(HasFromList(*goal_names, count=desired_count))

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
        """
        Create a particular item from just its ID.
        """
        gen_item = self.item_model_by_id.get(item_id, None)
        if gen_item is None:
            self.logger.error(f"Failed to create item by id: {item_id}, using filler instead")
            return self.create_filler()
        
        return self.create_item_by_model(gen_item)

    def create_item_by_model(self, gen_item: ItemModel, is_event: bool = False) -> GTFOItem:

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

        ## Identify the name
        name_tag = self.tag_model_by_id.get(gen_item.name_tag, None)
        if name_tag is None:
            self.logger.error(f"Failed to find name tag for item with id: {gen_item.id}")
            return self.create_filler()

        ## Create the item
        item = GTFOItem(name_tag.name, classification, gen_item.id, self.player)

        ## If it's an event, we can modify it
        if is_event:
            item.code = None

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
            "FilledEmptyLocations": self.filled_empty_locations,
            "GoalItems": self.goal_items,
            "SkippableGoalCount": self.skippable_goal_count
        }

    @classmethod
    def tag_matches(cls, tag: int, tag_set: Set[int]) -> bool:
        """Check if a tag matches against a set of tags. Adds the tag's parents if it does."""
        if tag in tag_set:
            return True

        tag_def: Optional[TagModel] = cls.tag_model_by_id.get(tag, None)
        if tag_def is not None and cls.tag_matches(tag_def.parent, tag_set):
            #tag_set.add(tag)
            return True
        else:
            return False

    @classmethod
    def tags_match(cls, *tags: int, tag_set: Set[int]) -> bool:
        """Returns true if any tag matches against the set of tags"""
        return any( cls.tag_matches(tag, tag_set) for tag in tags )

    def sample_items(self, desired_tags: Mapping[int, int], allow_duplicates: bool, debug_name: str,
                     source_list: Optional[List[ItemModel | LocationModel]] = None
                     ) -> Dict[ItemModel | LocationModel, int]:
        """
        Samples and returns a dict of (object, count) entries from the provided list matching the desired_tags arg.
        Tries to avoid duplicates. source_list defaults to all declared items in required_expeditions.
        """
        ## Set up defaults
        if source_list is None:
            source_list = [
                item for item in self.gen_model.items
                if item.required_expedition in self.required_expeditions
            ]

        results: Dict[ItemModel | LocationModel, int] = {}
        def add_result(items: List[ItemModel | LocationModel]) -> None:
            """Small helper to add items to the results"""
            for it in items:
                results[it] = results.get(it, 0) + 1

        for key, value in desired_tags.items():
            ## Ignore empty keys in case we happen across them
            if value == 0:
                continue

            ## Collect items from source list which match
            candidates = [
                item for item in source_list
                if type(self).tags_match(*item.tags(), tag_set={key})
            ]

            if not candidates:
                self.logger.warning(
                    f"Desired {value} items for tag {key} ({type(self).tag_model_by_id[key].name}) in {debug_name}"
                    + f" but only found {len(candidates)} matches"
                )
                continue

            ## Move duplicates to a separate list
            duplicates = list()
            for i in reversed(range(len(candidates))):
                if results.get(candidates[i], 0) > 0:
                    duplicates.append(candidates[i])
                    candidates.pop(i)

            ## Deal with / apply duplication if necessary
            if len(candidates) < value:
                if not allow_duplicates:
                    self.logger.warning(
                        f"Desired {value} items for tag {key} in {debug_name},"
                        + f" but only found {len(candidates)} matches"
                    )
                    value = -1
                else:
                    add_result(candidates)
                    value -= len(candidates)
                    candidates.extend(duplicates)
                    #duplicates = candidates ## Not necessary right now
                    while len(candidates) < value:
                        add_result(candidates)
                        value -= len(candidates)

            ## Add sample
            if value == -1:
                add_result(candidates)
            elif value > 0: ## Small edge case we need to catch where value == 0
                add_result(self.random.sample(candidates, value))

        return results


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
                gen_model = GameDataModel.model_validate_json(file_data.read())
        except OSError as e:  ## Failed to open file
            cls.logger.error(f"Failed open GTFO MID file: {filename}")
            cls.logger.exception(e)
        except json.JSONDecodeError as e:  ## JSON parsing failed
            cls.logger.error(f"Failed to parse GTFO MID file: {filename}")
            cls.logger.exception(e)
        except ValidationError as e:  ## pydantic failed to validate data
            cls.logger.error(f"Failed to validate GTFO MID data: {filename}")
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
        for file in Path(f"{Utils.local_path()}/Players").iterdir():
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
                raise NotImplementedError
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
        world_class.tag_model_by_id = { tag.id: tag for tag in gen_model.tags }
        world_class.tag_model_by_name = { tag.name.lower(): tag for tag in gen_model.tags }
        world_class.item_model_by_id = { item.id: item for item in gen_model.items }
        world_class.location_name_to_id = \
            { world_class.tag_model_by_id[loc.name_tag].name: loc.id for loc in gen_model.locations }
        world_class.item_name_to_id = \
            { world_class.tag_model_by_id[item.name_tag].name: item.id for item in gen_model.items }

        empty_item = world_class.item_name_to_id.get("Empty", None)
        if empty_item is None:
            world_class.class_logger.error(f"Failed to find the empty item for GTFO world: {gen_model.name}")
        else:
            world_class.empty_item_model = world_class.item_model_by_id[empty_item]

        ## Set up item groups and name mapping
        world_class.item_name_groups = dict()
        world_class.item_mapping = dict()
        for gen_item in gen_model.items:
            if gen_item.path_reqs.type != "Category": continue
            item_name = world_class.tag_model_by_id[gen_item.name_tag].name
            group_name = world_class.tag_model_by_id[gen_item.path_reqs.target].name

            group = world_class.item_name_groups.get(group_name, None)
            if group is None:
                group = { item_name }
                world_class.item_name_groups[group_name] = group
            else:
                group.add(item_name)

            world_class.item_mapping[item_name] = group_name

        ###########################################################################################
        ## Options creation

        ## Creating the options lookup
        world_class.option_model_by_id = { o.id: o for o in gen_model.options }

        ## Define the options dataclass
        options_dict = { "__annotations__": dict() }
        #options_dict = GTFOOptions.__dict__.copy()
        #del options_dict["__init__"] ## Fun little quirk which would prevent dataclass from generating a new __init__

        ## Options grouping by name; we later calc the option groups once we've created all option inputs
        option_groups_raw: Dict[str, List[Type[Options.Option]]] = options.gtfo_option_grouping.copy()

        ## Search for and add input options
        for option in gen_model.options:

            ## If this is an input, add it to the options dataclass
            if isinstance(option, OptionInputModel):

                ## Create the option class
                option: OptionInputModel
                option_base, option_dict = option.get_class()
                option_name = option.get_name()
                option_class = type(option_base)(option_name, (option_base,), option_dict)

                ## Add the option to the options class and groupings
                options_dict["__annotations__"][option_name] = option_class
                group = option_groups_raw.get(option.category, None)
                if group is None:
                    group = list()
                    option_groups_raw[option.category] = group
                group.append(option_class)

        ## Finally, create the options dataclass and assign it to our generated world
        options_class = type(GTFOOptions)(f"{world_class.game} options_dataclass", (GTFOOptions,), options_dict)
        options_class = cast(GTFOOptions, dataclasses.dataclass(options_class, init=True))
        world_class.options_dataclass = options_class
        world_class.option_groups = [ Options.OptionGroup(name, items) for name, items in option_groups_raw.items() ]

        ###########################################################################################
        ## Create the world class!

        ## Note that we use the metaclass associated with GTFOWorld to create the derived instance
        return cast(Type[GTFOWorld], type(GTFOWorld)(f"GTFO ({gen_model.name})", (GTFOWorld,), world_class.__dict__))

## Now we simply create all the GTFO worlds
GTFOWorldBuilder.make_worlds()


