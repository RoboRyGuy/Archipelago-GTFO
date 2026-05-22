# world/gtfo/__init__.py

from __future__ import annotations
import dataclasses
import importlib.resources
from importlib.resources.abc import Traversable
import itertools
import json
import logging
from pathlib import Path
import settings
from typing import Set, Dict, Iterable, Callable, override, ClassVar
from types import SimpleNamespace
import Utils

import Options
from BaseClasses import Region, Location, Item, ItemClassification, LocationProgressType
from rule_builder.cached_world import CachedRuleBuilderWorld
from rule_builder.rules import Rule, And, Or, Has, HasGroup, CanReachRegion, HasAll, False_

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
    """Actual options instance. This will be populated by Archipelago using the overwritten dataclass above."""
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
    option_effects: ClassVar[List[Mapping[Any, Mapping[str, List[int]]]]]
    """One mapping per options. Maps option value to effect. Effect is a map of effect type to a list of tags."""
    option_groups: ClassVar[List[Options.OptionGroup]]
    """List of generated option groups for the option dataclass"""
    gen_model: ClassVar[Gen_GameData]
    """Imported MID data"""
    tag_model_by_id: ClassVar[Mapping[int, Gen_Tag]]
    """Tag lookup via ID"""
    tag_model_by_name: ClassVar[Mapping[str, Gen_Tag]]
    """Tag lookup via name"""
    item_model_by_id: ClassVar[Mapping[int, Gen_Item]]
    """Item lookup by id"""
    empty_item_model: ClassVar[Gen_Item]
    """Default filler item which does nothing. To be replaced with filler items in future update"""

    ## Per-player variables
    logger: logging.Logger
    """Logger for the world instance, ie one per player"""
    early_items: Dict[int, int]
    """Dict of (tag, count) of items to set as early"""
    #local_items: Set[int]
    """Tags for items to force as local. Removed because we make Archipelago handle this for us."""
    #non_local_items: Set[int]
    """Tags for items to force as nonlocal. Removed because we make Archipelago handle this for us."""
    #start_inventory: Mapping[int, int]
    """Tags and counts for items to place in our starting inventory. Removed because we make Archipelago handle this"""
    #start_hints: Mapping[int, int]
    """Tags and counts for items and locations which start hinted. Removed because we make Archieplago handle this."""
    exclude_locations: Set[int]
    """Tags for locations to override and mark as excluded"""
    priority_locations: Set[int]
    """Tags for locations to override and mark as priorities"""
    goal_blacklist: Set[int]
    """Tag blacklist for goal items. The whitelist is all goal items"""
    reachable_regions: Set[int]
    """The set of region IDs that can be reached using the provided settings"""
    reachable_locations: Set[Gen_Location]
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
    filled_empty_locations: List[int]
    """List of empty locations that were filled with a floating item during generation"""
    goal_items: List[int]
    """List of items required to reach the goal"""

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

        ## Universal Tracker integration
        re_gen_passthrough = getattr(self.multiworld, "re_gen_passthrough", {})
        if re_gen_passthrough and self.game in re_gen_passthrough:
            slot_data: Dict[str, Any] = re_gen_passthrough[self.game]
            self.root_seed = slot_data["RootSeed"]
            self.required_expeditions = slot_data["ExpeditionNames"]

        ## Enforces consistency between UT and non-UT
        self.random.seed(self.root_seed)

        ## Identify reachable regions
        expedition_lookup = { e.name: e for e in self.gen_model.expeditions }
        not_found_expeditions: List[str] = []
        self.reachable_regions = set()
        for e_name in self.required_expeditions:
            if e_name is None: continue
            e: Optional[Gen_ExpeditionData] = expedition_lookup.get(e_name)
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

        not_found_tags: Dict[str, List[str]] = dict()
        def move_to_tag_set(dest: Set[int], source: Iterable[str], debug_name: str) -> None:
            """Helper which moves a list of tag names into a set"""
            for key in source:
                found_tag = type(self).tag_model_by_name.get(key.lower(), None)
                if found_tag is None:
                    not_found_tags.setdefault(debug_name, []).append(key)
                else:
                    dest.add(found_tag.id)

        def move_to_tag_dict(dest: Dict[int, int], source: Mapping[str, int], debug_name: str) -> None:
            """Helper which moves a dict of string tag names into a dict of tag counts"""
            for key, value in source.items():
                found_tag = type(self).tag_model_by_name.get(key.lower(), None)
                if found_tag is None:
                    not_found_tags.setdefault(debug_name, []).append(key)
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

        local_items: Set[int] = set()
        move_to_tag_set(local_items, self.options.gtfo_local_items.value, "local_items")

        non_local_items: Set[int] = set()
        move_to_tag_set(non_local_items, self.options.gtfo_non_local_items.value, "non_local_items")

        start_inventory: Dict[int, int] = dict()
        move_to_tag_dict(start_inventory, self.options.gtfo_start_inventory.value, "start_inventory")

        start_hints: Dict[int, int] = dict()
        move_to_tag_dict(start_hints, self.options.gtfo_start_hints.value, "start_hints")

        self.exclude_locations = set()
        move_to_tag_set(self.exclude_locations, self.options.gtfo_exclude_locations.value, "exclude_locations")

        self.priority_locations = set()
        move_to_tag_set(self.priority_locations, self.options.gtfo_priority_locations.value, "priority_locations")

        self.goal_blacklist = set()
        move_to_tag_set(self.goal_blacklist, self.options.goal_blacklist.value, "goal_blacklist")

        ## Report badly-formatted (or erroneous) expedition names and tag names
        if not_found_expeditions or not_found_tags:
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
            for option_name, tags in not_found_tags:
                error_message += f"Failed to find {len(tags)} tags in setting {option_name}."
                for t_name in tags:
                    match = Utils.get_fuzzy_results(t_name, tag_choices, 1)
                    if match and match[0][1] > .3:
                        error_message += f'\n -"{t_name}" (Did you mean "{match[0][0]}"? {100 * match[0][1]}% certain)'
                    else:
                        error_message += f'\n -"{t_name}" (No likely matches found)'

            raise Exception(error_message)

        for i in range(len(type(self).option_effects)):
            option = self.options.__dict__[f"option_{i}"]
            effect = type(self).option_effects[i][option.value]
            for effect_type, tags in effect.items():
                if effect_type == "": ## So I can use elif for all the options (so it's ~pretty~)
                    raise Exception()
                elif effect_type == "Whitelist":
                    self.whitelist_tags.update(tags)
                elif effect_type == "Blacklist":
                    self.blacklist_tags.update(tags)
                elif effect_type == "StartInventory":
                    for tag in tags: start_inventory[tag] = start_inventory.get(tag, 0) + 1
                elif effect_type == "EarlyItems":
                    for tag in tags: self.early_items[tag] = self.early_items.get(tag, 0) + 1
                elif effect_type == "LocalItems":
                    local_items.update(tags)
                elif effect_type == "NonLocalItems":
                    non_local_items.update(tags)
                elif effect_type == "StartHints":
                    for tag in tags: start_hints[tag] = start_hints.get(tag, 0) + 1
                elif effect_type == "CustomExcludeLocations":
                    self.exclude_locations.update(tags)
                elif effect_type == "CustomPriorityLocations":
                    self.priority_locations.update(tags)
                elif effect_type == "GoalBlacklist":
                    self.goal_blacklist.update(tags)
                else:
                    raise Exception(f"Unsupported option effect: {effect_type}")

        ## Overwrite the settings we don't control so we can pass them off to Archipelago
        local_items_setting = options.LocalItems([
            self.tag_model_by_id[item.name_tag].name for item in type(self).gen_model.items
            if item.required_expedition in self.required_expeditions
            and type(self).tags_listed(item.name_tag, item.tag2, item.tag3, wl=local_items, bl=set())
        ])
        nonlocal_items_setting = options.NonLocalItems([
            self.tag_model_by_id[item.name_tag].name for item in type(self).gen_model.items
            if item.required_expedition in self.required_expeditions
            and type(self).tags_listed(item.name_tag, item.tag2, item.tag3, wl=non_local_items, bl=set())
        ])
        start_inventory_setting = options.StartInventory({
            self.tag_model_by_id[key.name_tag].name: value for key, value
            in self.sample_items(start_inventory, True, "Start Inventory").items()
        })
        start_hints_results = self.sample_items(
            start_hints, True, "Start Hints",
            list(itertools.chain[Gen_Location | Gen_Item](
                (i for i in type(self).gen_model.items if i.required_expedition in self.required_expeditions),
                (l for l in self.reachable_locations)
            ))
        )
        start_item_hints = Options.StartHints([
            self.tag_model_by_id[entity.name_tag].name for entity in start_hints_results if entity is Gen_Item
        ])
        start_location_hints = Options.StartLocationHints([
            self.tag_model_by_id[entity.name_tag].name for entity in start_hints_results if entity is Gen_Location
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

        ## Fetch and set randomization on relevant locations
        for loc in self.reachable_locations:
            loc.is_randomized = self.tags_listed_default(loc.name_tag, loc.tag2, loc.tag3)
            if loc.is_randomized and loc.rand_data.is_empty:
                loc.item_id = 0 ## In case we accidentally pull used data

        ## Set randomization on relevant items - we won't really be referencing the relevant item set after this
        relevant_item_ids = { loc.item_id for loc in self.reachable_locations if loc.item_id != 0 }
        relevant_item_ids.update(self.gen_model.floating_items)
        for item_id in relevant_item_ids:
            gen_item = self.item_model_by_id[item_id]
            gen_item.is_randomized = \
                gen_item.required_expedition in self.required_expeditions \
                and self.tags_listed_default(gen_item.name_tag, gen_item.tag2, gen_item.tag3)

        #######################################################################
        ## Floating Item Distribution

        self.filled_empty_locations = list()
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
                    self.filled_empty_locations.append(empty_locations[index].id)

        ## Round 1: Progression items into priority locations
        floating_items = [ 
            i for i in self.gen_model.floating_items 
            if self.item_model_by_id[i].is_randomized
            and self.item_model_by_id[i].rand_data.is_progression
        ]
        seen_items = { f for f in floating_items }
        distribute([
            l for l in self.reachable_locations
            if l.is_randomized and l.item_id == 0
            and (
                (l.rand_data.priority_mode == "Priority" and l.id not in self.exclude_locations)
                or l.id in self.priority_locations
            )
        ])

        ## Round 2: Progression items in all locations
        distribute([
            l for l in self.reachable_locations
            if l.is_randomized and l.item_id == 0
            and (
                (l.rand_data.priority_mode != "Excluded" and l.id not in self.exclude_locations)
                or l.id in self.priority_locations
            )
        ])

        ## Round 3: All items into all locations
        floating_items.extend(
            i for i in self.gen_model.floating_items 
            if self.item_model_by_id[i].is_randomized
            and not i in seen_items
        )
        distribute([
            l for l in self.reachable_locations
            if l.is_randomized and l.item_id == 0
        ])

        ## Round 4: All remaining items are given
        for i in floating_items:
            name = self.tag_model_by_id[self.item_model_by_id[i].name_tag].name
            self.logger.warning(f"Not enough empty locations. Adding starting item: {name}")
            self.push_precollected(self.create_item_by_id(i))
        
        #######################################################################
        ## Item Creation and Submission
        
        rand_items: List[Gen_Item] = []
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
            if gen_location.is_randomized and gen_item.is_randomized:
                rand_items.append(gen_item)
                item_tag = self.tag_model_by_id[gen_item.name_tag]
                self.logger.debug(f"Randomized: {location.name} - {item_tag.name}")
            else:
                item = self.create_item_by_model(gen_item, True)
                location.address = None
                location.place_locked_item(item)
                self.logger.debug(f"Locked: {location.name} - {item.name}")

        ## Handling unused floating items
        ## Some unused floating items, such as expedition unlocks, are presume held if not randomized.
        ## We handle this by just giving it to the play as part of the starting inventory
        for i in self.gen_model.floating_items:
            gen_item = self.item_model_by_id[i]
            if (not gen_item.is_randomized) and gen_item.rand_data.collected_by_default \
                and gen_item.required_expedition in self.required_expeditions:
                self.multiworld.push_precollected(self.create_item_by_model(gen_item))
        
        #######################################################################
        ## Early Items

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
        bl = self.goal_blacklist

        ## Check each item ID that is *actually* spawned (including if it's spawned multiple times)
        all_item_ids = itertools.chain( 
            ( loc.item_id for loc in self.reachable_locations if loc.item_id != 0 ),
            self.gen_model.floating_items
        )
        goal_names: List[str] = [ ]
        self.goal_items = []

        for item_id in all_item_ids:
            gen_item = self.item_model_by_id.get(item_id, None)
            if gen_item is None:
                self.logger.warning(f"Failed to look up potential goal item with ID: {item_id}")
                continue

            if gen_item.required_expedition in self.required_expeditions \
                    and type(self).tags_listed(gen_item.name_tag, gen_item.tag2, gen_item.tag3, wl=wl, bl=bl):
                item_tag = self.tag_model_by_id.get(gen_item.name_tag, None)
                if item_tag is None:
                    self.logger.error(f"Failed to find name tag for goal item: {item_id}")
                else:
                    self.goal_items.append(item_tag.id)
                    goal_names.append(item_tag.name)

        self.set_completion_rule(HasAll( *goal_names ))

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

    def create_item_by_model(self, gen_item: Gen_Item, is_event: bool = False) -> GTFOItem:

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
        }

    @classmethod
    def tag_matches(cls, tag: int, tag_set: Set[int]) -> bool:
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
    def tags_listed(cls, *tags: int, wl: Set[int], bl: Set[int]) -> bool:
        """Check if any tag matches a particular whitelist and not a particular blacklist"""
        return any( cls.tag_matches(tag, wl) and not cls.tag_matches(tag, bl) for tag in tags )

    def tags_listed_default(self, *tags: int) -> bool:
        """Check if any tag matches the default whitelist and not the default blacklist"""
        return type(self).tags_listed(*tags, wl=self.whitelist_tags, bl=self.blacklist_tags)

    def sample_items(self, desired_tags: Mapping[int, int], allow_duplicates: bool, debug_name: str,
                     source_list: Optional[List[Gen_Item | Gen_Location]] = None
                     ) -> Mapping[Gen_Item | Gen_Location, int]:
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

        results: Dict[Gen_Item | Gen_Location, int] = {}
        def add_result(items: List[Gen_Item | Gen_Location]) -> None:
            """Small helper to add items to the results"""
            for it in items:
                results[it] = results.get(it, 0) + 1

        for key, value in desired_tags.items():
            ## Collect items from source list which match
            candidates = [
                item for item in source_list
                if type(self).tags_listed(item.name_tag, item.tag2, item.tag3, wl={key}, bl=set())
            ]

            if not candidates:
                self.logger.warning(
                    f"Desired {value} items for tag {key} in {debug_name},"
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
        world_class = SimpleNamespace(**GTFOWorld.__dict__)
        world_class: Type[GTFOWorld]

        ## Attempt to find and load data from file
        try:
            with world_file.open("r") as file_data:
                loaded_mid_model = Mid_GameData(json.load(file_data))
                world_class.gen_model = Gen_GameData(loaded_mid_model)
                del loaded_mid_model
        except OSError as e: ## Failed to open file
            raise Exception(f"Failed to find GTFO MID file for game: {world_name}") from e
        except json.JSONDecodeError as e: ## JSON parsing failed
            raise Exception(f"Failed to parse GTFO MID file for game: {world_name}") from e
        except Exception as e: ## Generic failure during gen_model instantiation
            raise Exception(f"Malformed GTFO MID file for game: {world_name}") from e

        ## Init class variables
        world_class.game = world_name
        world_class.__doc__ = GTFOWorldBuilder.docstring
        world_class.gen_model = world_class.gen_model
        world_class.class_logger = logging.getLogger(f"GTFO.{world_name}")
        world_class.tag_model_by_id = { tag.id: tag for tag in world_class.gen_model.tags }
        world_class.tag_model_by_name = { tag.name.lower(): tag for tag in world_class.gen_model.tags }
        world_class.item_model_by_id = { item.id: item for item in world_class.gen_model.items }
        world_class.location_name_to_id = \
            { world_class.tag_model_by_id[loc.name_tag].name: loc.id for loc in world_class.gen_model.locations }
        world_class.item_name_to_id = \
            { world_class.tag_model_by_id[item.name_tag].name: item.id for item in world_class.gen_model.items }

        empty_item = world_class.item_name_to_id.get("Empty", None)
        if empty_item is None:
            world_class.class_logger.error(f"Failed to find the empty item for game: {world_name}")
        else:
            world_class.empty_item_model = world_class.item_model_by_id[empty_item]

        ## Set up item groups and name mapping
        world_class.item_name_groups = dict()
        world_class.item_mapping = dict()
        for gen_item in world_class.gen_model.items:
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

        ## Create options dataclass
        options_dict = GTFOOptions.__dict__.copy()
        del options_dict["__init__"] ## Fun little quirk which would prevent dataclass from generating a new __init__
        option_groups_raw: Dict[str, List[Type[Options.Option]]] = options.gtfo_option_grouping.copy()
        option_effects: List[Mapping[Any, Mapping[str, List[int]]]] = []
        option_count = 0
        for option in world_class.gen_model.options:

            ## Figure out which option we're making
            option_base: Type[Options.Option]
            if option.type == "Toggle":
                option_base = Options.Toggle
            elif option.type == "DefaultOnToggle":
                option_base = Options.DefaultOnToggle
            elif option.type == "Choice":
                option_base = Options.Choice
            else:
                raise Exception(f"Failed to identify option type: {option.type}")

            ## Common option configuration
            option_dict: Dict[str, Any] = option_base.__dict__.copy()
            option_dict["display_name"] = option.name
            option_dict["__doc__"] = option.description

            ## Set up the effects list
            effect_list: Mapping[Any, Mapping[str, List[int]]] = option.choices
            if option.type in [ "Toggle", "DefaultOnToggle" ]:
                effect_list = {
                    True: effect_list["True"],
                    False: effect_list["False"]
                }
            elif option.type == "Choice":
                numbered_effect_list: Dict[int, Mapping[str, List[int]]] = dict()
                option_i = 0
                for choice, effect in effect_list.items():
                    option_dict[f"option_{choice}"] = option_i
                    numbered_effect_list[choice] = effect
                    option_i += 1
                option_dict["default"] = option_dict[f"option_{option.default_value}"]
                effect_list = numbered_effect_list
            option_effects.append(effect_list)

            ## Create the option and set it up as an annotation in the options class
            option_name = f"option_{option_count}"
            option_class = type(option_base)(f"{world_class.game} {option_name}", (option_base,), option_dict)
            options_dict["__annotations__"][option_name] = option_class
            option_count += 1

            ## Add the new option to the relevant group
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
        world_class.option_effects = option_effects

        ## Note that we use the metaclass associated with GTFOWorld to create the derived instance
        return cast(Type[GTFOWorld], type(GTFOWorld)(world_name, (GTFOWorld,), world_class.__dict__))

## Now we simply create all the GTFO worlds
GTFOWorldBuilder.make_worlds()


