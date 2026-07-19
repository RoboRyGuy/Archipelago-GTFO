# world/gtfo/__init__.py

from __future__ import annotations

from collections import Counter
import importlib.resources
from importlib.resources.abc import Traversable
import inspect
import itertools
import json
import logging
from pathlib import Path
from typing import Any, cast, Callable, ClassVar, Dict, Iterable, List, Mapping, Optional, override, Set, Tuple, \
    Type, Union
from types import SimpleNamespace

from BaseClasses import Region, Location, Item, ItemClassification, LocationProgressType
import Options
from Options import Option
from rule_builder.cached_world import CachedRuleBuilderWorld
from rule_builder.rules import And, CanReachRegion, False_, Has, HasGroup, HasFromList, Or, Rule, True_
import Utils
from worlds.AutoWorld import WebWorld

from .model import SlotDataModel, GameDataModel, TagModel, TaggedRegionModel, PathModel, PathReqModel, \
    LocationTagModel, RealLocationTagModel, LocationModel, ItemTagModel, ItemModel, FloatingItemModel, \
    OptionBaseModel, OptionInputModel, RealItemTagModel
from .options import OptionsEvaluator, SkippableGoalCount, FailIfInsufficientEmptyLocations, \
    RegionWhitelist, RegionBlacklist, LocationWhitelist, LocationBlacklist, ItemWhitelist, ItemBlacklist, \
    EarlyItems, StartVouchers, GTFOLocalItems, GTFONonLocalItems, GTFOStartInventory, RootSeed, \
    GTFOExcludeLocations, GTFOPriorityLocations, GoalItems, GTFOLocationHints, GTFOItemHints, FailDuringSampling

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
    options_dataclass: ClassVar[object]
    """The dataclass to use for this world. This will be set from MID data."""
    location_name_to_id: ClassVar[Dict[str, int]]
    """Map of location names to location IDs. This will be populated from MID data"""
    item_name_to_id: ClassVar[Dict[str, int]]
    """Map of item names to item IDs. This will be populated from MID data"""
    item_name_groups: ClassVar[Dict[str, Set[str]]]
    """Maps an item group name to a set of item names. This will be populated from MID data"""
    item_mapping: ClassVar[Dict[str, str]] = dict()
    """Maps an actual item name to a logical item name. For GTFO, this is kept empty."""
    web: ClassVar[WebWorld]
    """Web world to be used by this world"""

    ## Options handled as a property so we can perform some funny business when it's assigned
    _options: object
    """Actual options instance for this world"""
    @property
    def options(self) -> object:
        """Options getter; required because we need to react to set operations"""
        return self._options
    @options.setter
    def options(self, value: object):
        """Options setter, used to update internal state when the options are set/changed"""
        self._options = value
        self.setup_from_options()

    ## Class variables
    class_logger: ClassVar[logging.Logger]
    """Logger for the class (world)"""
    gen_model: ClassVar[GameDataModel]
    """Imported MID data"""
    region_name_to_id_casefold: ClassVar[Dict[str, int]]
    """Map of regions name to region IDs"""
    location_name_to_id_casefold: ClassVar[Dict[str, int]]
    """Map of location names to location IDs"""
    item_name_to_id_casefold: ClassVar[Dict[str, int]]
    """Map of item names to item IDs"""
    region_model_by_id: ClassVar[Mapping[int, TaggedRegionModel]]
    """Region lookup by id"""
    location_model_by_id: ClassVar[Mapping[int, LocationTagModel]]
    """Location lookup by id"""
    item_model_by_id: ClassVar[Mapping[int, ItemTagModel]]
    """Item lookup by id"""
    empty_item_model: ClassVar[RealItemTagModel]
    """Default filler item which does nothing. To be replaced with filler items in future update"""
    option_model_by_id: ClassVar[Mapping[int, OptionBaseModel]]
    """Option model lookup used for options evaluation"""

    ## Per-player variables
    logger: logging.Logger
    """Logger for the world instance, ie one per player"""
    options_evaluation: OptionsEvaluator
    """Option evaluation created and evaluated when the options are assigned"""
    fail_if_insufficient_empty_locations: bool
    """If true, raise an exception if there are insufficient empty locations for the selected floating items"""
    fail_during_sampling: bool
    """If true, raise an exception if sampling fails to one or more tag matches"""
    slot_data: SlotDataModel
    """Future slot data"""
    root_seed: int
    """Seed chosen and shared for generation"""

    reachable_regions: Set[int] ## It's just easier to track this as ints
    """Set of all regions which are both randomized and reachable"""
    reachable_locations: List[RealLocationTagModel]
    """List of all locations which are fully contained in the reachable regions set AND are not randomized"""
    randomized_locations: List[RealLocationTagModel]
    """List of all locations which are fully contained in the reachable regions set AND are randomized"""
    item_pool: Counter[int]
    """Counter of items which are randomized"""
    filled_empty_locations: List[Tuple[int, int]]
    """Maps reachable empty locations to the items they get filled with during generation"""
    growing_item_counts: Counter[int] = Counter()
    """Current sum of encountered growing paths"""
    goal_item_results: Counter[int]
    """Resulting list of goal items calculated from reachable items"""
    skippable_goal_count: int
    """Number of goal items we can skip"""

    region_whitelist: Set[int]
    """Whitelist for regions"""
    region_blacklist: Set[int]
    """Blacklist for regions"""
    location_whitelist: Set[int]
    """Whitelist for locations"""
    location_blacklist: Set[int]
    """Blacklist for locations"""
    item_whitelist: Set[int]
    """Whitelist for items"""
    item_blacklist: Set[int]
    """Blacklist for items"""

    goal_items: Counter[int]
    """Dict of (tag, count) of items to demand for the player to win the goal"""
    start_inventory: Counter[int]
    """Tags and counts for items to place in our starting inventory"""
    start_vouchers: Counter[int]
    """Dict of (tag, count) of items to pull prior to randomization and add to the starting inventory"""
    early_items: Counter[int]
    """Dict of (tag, count) of items to set as early"""
    local_items: Counter[int]
    """Tags for items to force as local"""
    non_local_items: Counter[int]
    """Tags for items to force as nonlocal"""
    item_hints: Counter[int]
    """Tags and counts for items which start hinted."""
    location_hints: Counter[int]
    """Tags and counts for locations which start hinted."""
    priority_locations: Counter[int]
    """Tags for locations to override and mark as priorities"""
    exclude_locations: Counter[int]
    """Tags for locations to override and mark as excluded"""

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

        def get_option[T: Option](opt_type: Type[T]) -> T:
            """Helper to get a particular option from the options class"""
            return getattr(self.options, getattr(opt_type, "display_name", opt_type.__name__))

        cls = type(self)
        self.root_seed = get_option(RootSeed).value or self.random.randrange(0, 2**52)
        self.fail_if_insufficient_empty_locations = get_option(FailIfInsufficientEmptyLocations).value != 0
        self.fail_during_sampling = get_option(FailDuringSampling).value != 0
        self.skippable_goal_count = get_option(SkippableGoalCount).value

        #######################################################################
        ## Import user options as tags

        errors: List[Tuple[str, List[str], Dict[str, int]]] = list()

        def move_to_tag_set(src: Iterable[str], dest: Set[int], tag_lookup: Dict[str, int], debug_name: str) -> None:
            """Helper which moves a list of tag names into a set"""
            local_errors = list()
            for key in src:
                found_tag = tag_lookup.get(key.casefold(), None)
                if found_tag is None:
                    local_errors.append(key)
                else:
                    dest.add(found_tag)
            if local_errors:
                errors.append((debug_name, local_errors, tag_lookup))

        self.region_whitelist = set()
        opt = get_option(RegionWhitelist)
        move_to_tag_set(
            opt.value,
            self.region_whitelist,
            cls.region_name_to_id_casefold,
            opt.display_name
        )
        self.region_whitelist.add(cls.region_name_to_id_casefold["always"])

        self.region_blacklist = set()
        opt = get_option(RegionBlacklist)
        move_to_tag_set(
            opt.value,
            self.region_blacklist,
            cls.region_name_to_id_casefold, opt.display_name
        )
        self.region_blacklist.add(cls.region_name_to_id_casefold["never"])

        self.location_whitelist = set()
        opt = get_option(LocationWhitelist)
        move_to_tag_set(
            opt.value,
            self.location_whitelist,
            cls.location_name_to_id_casefold, opt.display_name
        )
        self.location_whitelist.add(cls.location_name_to_id_casefold["always"])

        self.location_blacklist = set()
        opt = get_option(LocationBlacklist)
        move_to_tag_set(
            opt.value,
            self.location_blacklist,
            cls.location_name_to_id_casefold, opt.display_name
        )
        self.location_blacklist.add(cls.location_name_to_id_casefold["never"])

        self.item_whitelist = set()
        opt = get_option(ItemWhitelist)
        move_to_tag_set(
            opt.value,
            self.item_whitelist,
            cls.item_name_to_id_casefold, opt.display_name
        )
        self.item_whitelist.add(cls.item_name_to_id_casefold["always"])

        self.item_blacklist = set()
        opt = get_option(ItemBlacklist)
        move_to_tag_set(
            opt.value,
            self.item_blacklist,
            cls.item_name_to_id_casefold, opt.display_name
        )
        self.item_blacklist.add(cls.item_name_to_id_casefold["never"])

        def move_to_tag_dict(src: Mapping[str, int], dest: Counter[int],
                             tag_lookup: Dict[str, int], debug_name: str) -> None:
            """Helper which moves a dict of string tag names into a dict of tag counts"""
            local_errors = list()
            for k, v in src.items():
                found_tag = tag_lookup.get(k.casefold(), None)
                if found_tag is None:
                    local_errors.append(k)
                elif found_tag in tag_lookup:
                    raise NotImplementedError(f"The key '{k}' cannot be defined twice for option '{debug_name}'")
                else:
                    dest[found_tag] = v
            if local_errors:
                errors.append((debug_name, local_errors, tag_lookup))

        self.goal_items = Counter()
        opt = get_option(GoalItems)
        move_to_tag_dict(
            opt.value,
            self.goal_items,
            cls.item_name_to_id_casefold,
            opt.display_name
        )

        self.start_inventory = Counter()
        opt = get_option(GTFOStartInventory)
        move_to_tag_dict(
            opt.value,
            self.start_inventory,
            cls.item_name_to_id_casefold,
            opt.display_name
        )

        self.start_vouchers = Counter()
        opt = get_option(StartVouchers)
        move_to_tag_dict(
            opt.value,
            self.start_vouchers,
            cls.item_name_to_id_casefold,
            opt.display_name
        )

        self.early_items = Counter()
        opt = get_option(EarlyItems)
        move_to_tag_dict(
            opt.value,
            self.early_items,
            cls.item_name_to_id_casefold,
            opt.display_name
        )

        self.local_items = Counter()
        opt = get_option(GTFOLocalItems)
        move_to_tag_dict(
            opt.value,
            self.local_items,
            cls.item_name_to_id_casefold,
            opt.display_name
        )

        self.non_local_items = Counter()
        opt = get_option(GTFONonLocalItems)
        move_to_tag_dict(
            opt.value,
            self.non_local_items,
            cls.item_name_to_id_casefold,
            opt.display_name
        )

        self.item_hints = Counter()
        opt = get_option(GTFOItemHints)
        move_to_tag_dict(
            opt.value,
            self.item_hints,
            cls.item_name_to_id_casefold,
            opt.display_name
        )

        self.location_hints = Counter()
        opt = get_option(GTFOLocationHints)
        move_to_tag_dict(
            opt.value,
            self.location_hints,
            cls.item_name_to_id_casefold,
            opt.display_name
        )

        self.priority_locations = Counter()
        opt = get_option(GTFOPriorityLocations)
        move_to_tag_dict(
            opt.value,
            self.priority_locations,
            cls.item_name_to_id_casefold,
            opt.display_name
        )

        self.exclude_locations = Counter()
        opt = get_option(GTFOExcludeLocations)
        move_to_tag_dict(
            opt.value,
            self.exclude_locations,
            cls.item_name_to_id_casefold,
            opt.display_name
        )

        ## Evaluate options
        re_gen_passthrough = getattr(self.multiworld, "re_gen_passthrough", {})
        if re_gen_passthrough and self.game in re_gen_passthrough:
            ## Universal Tracker integration
            slot_data = SlotDataModel(re_gen_passthrough[self.game])
            self.root_seed = slot_data.root_seed

            self.random.seed(self.root_seed) ## Enforces consistency between UT and non-UT
            oe = OptionsEvaluator(self)
            for option in self.option_model_by_id.keys():
                oe.get_output(option)

            self.region_whitelist = set(slot_data.region_whitelist)
            self.region_blacklist = set(slot_data.region_blacklist)
            self.location_whitelist = set(slot_data.location_whitelist)
            self.location_blacklist = set(slot_data.location_blacklist)
            self.item_whitelist = set(slot_data.item_whitelist)
            self.item_blacklist = set(slot_data.item_blacklist)
        else:
            self.random.seed(self.root_seed) ## Enforces consistency between UT and non-UT
            oe = OptionsEvaluator(self)
            for option in self.option_model_by_id.keys():
                oe.get_output(option)


        ## Report errors!
        if errors:
            error_message: str = \
                f"YAML file parsing failed for player: {self.multiworld.get_player_name(self.player)}" \
                + "\nDebug is printed below. All tag names are case-insensitive."

            for opt_name, error_items, tag_dict in errors:
                count = len(error_items)
                error_message += f'\nFailed to find {count} tag{"" if count == 1 else "s"} for option "{opt_name}":'
                for e in error_items:
                    match = Utils.get_fuzzy_results(e.casefold(), tag_dict.keys(), 1)
                    if match and match[0][1] > .3:
                        error_message += f'\n -"{e}" (Did you mean "{match[0][0]}"? {100 * match[0][1]}% certain)'
                    else:
                        error_message += f'\n -"{e}" (No likely matches found)'

            raise Exception(error_message)

        #######################################################################
        ## Regions, Locations, and Items

        ## Region reachability. We use some minor optimizations to guarantee we get all matches
        self.reachable_regions = {
            r for r in self.region_whitelist
            if not GTFOWorld.tag_matches(r, self.region_blacklist, cls.region_model_by_id)
        }
        for reg in cls.region_model_by_id.values():
            if any(p in self.reachable_regions for p in reg.parents) and not reg.id in self.region_blacklist:
                self.reachable_regions.add(reg.id)
        self.reachable_regions = { r for r in self.reachable_regions if cls.region_model_by_id[r].reachable }

        ## Calculating reachable and randomized locations
        self.reachable_locations = list()
        self.randomized_locations = list()
        empty_locations: List[RealLocationTagModel] = list()
        for loc in self.gen_model.locations:
            if loc.value is None:
                continue
            loc: RealLocationTagModel
            if any(r not in self.reachable_regions for r in loc.value.owning_regions):
                continue

            is_whitelisted = GTFOWorld.tag_matches(loc.id, self.location_whitelist, self.location_model_by_id)
            is_blacklisted = GTFOWorld.tag_matches(loc.id, self.location_blacklist, self.location_model_by_id)

            if loc.value.is_empty:
                if is_whitelisted and not is_blacklisted:
                    empty_locations.append(loc)
            else:
                assert loc.value.item_id != 0, f"Non-empty location has null item ID: {loc.id} - {loc.name}"
                item_whitelisted = GTFOWorld.tag_matches(loc.value.item_id, self.item_whitelist, self.item_model_by_id)
                item_blacklisted = GTFOWorld.tag_matches(loc.value.item_id, self.item_blacklist, self.item_model_by_id)
                if (is_whitelisted or item_whitelisted) and not (is_blacklisted or item_blacklisted):
                    self.randomized_locations.append(loc)
                else:
                    self.reachable_locations.append(loc)

        ## We need to know our priority and exclude locations so we can pick empty locations ~intelligently~
        def custom_combine(a: Dict[int, int], b: Set[str]) -> Iterable[tuple[int, int]]:
            """Combine our custom tag set with the simpler location set"""
            b = { cls.location_name_to_id_casefold[k.casefold()] for k in b }
            keys = b.union(a.keys())
            return [ (k, -1 if k in b else a[k]) for k in keys ]

        priority_locations = set(
            self.sample_tags(
                (l.id for l in itertools.chain(self.randomized_locations, empty_locations)),
                custom_combine(self.priority_locations, get_option(Options.PriorityLocations).value),
                cls.location_model_by_id,
                False,
                GTFOPriorityLocations.display_name
            ).keys()
        )
        exclude_locations = set(
            self.sample_tags(
                (l.id for l in itertools.chain(self.randomized_locations, empty_locations)),
                custom_combine(self.exclude_locations, get_option(Options.ExcludeLocations).value),
                cls.location_model_by_id,
                False,
                GTFOExcludeLocations.display_name
            ).keys()
        )

        ## Grouping empty locations by priority
        grouped_empty_locations: List[List[RealLocationTagModel]] = [[], [], []]
        for loc in empty_locations:
            cat: int = NotImplemented
            if loc.id in priority_locations:
                cat = 0
            elif loc.id in exclude_locations:
                cat = 2
            else:
                match loc.value.priority_mode:
                    case "Priority":
                        cat = 0
                    case "Default":
                        cat = 1
                    case _:
                        cat = 2
            grouped_empty_locations[cat].append(loc)

        ## Collecting a list of floating items
        grouped_floating_items: List[List[int]] = [[], [], []]
        for fi in cls.gen_model.floating_items:
            is_randomized = True \
                and fi.region in self.reachable_regions \
                and GTFOWorld.tag_matches(fi.item, self.item_whitelist, cls.item_model_by_id) \
                and not GTFOWorld.tag_matches(fi.item, self.item_blacklist, cls.item_model_by_id)
            if not is_randomized:
                continue
            item = cls.item_model_by_id[fi.item]
            if item.value is None:
                raise Exception("Floating item contains id pointing to null item!")
            if item.value.is_progression:
                grouped_floating_items[0].append(item.id)
            elif item.value.is_useful:
                grouped_floating_items[1].append(item.id)
            else:
                grouped_floating_items[2].append(item.id)

        ## Counts for all items we're using
        self.item_pool = Counter(
            itertools.chain(
                (loc.value.item_id for loc in self.randomized_locations),
                (i for items in grouped_floating_items for i in items)
            )
        )

        ## Cash in the vouchers
        sample = self.sample_tags(
            self.item_pool.keys(),
            self.start_vouchers.items(),
            cls.item_model_by_id,
            False,
            StartVouchers.display_name,
            repeats=self.item_pool.values()
        )
        starting_inventory = Counter(sample)
        for tag, count in sample.items():
            self.item_pool[tag] -= count

        ## Remove relevant items from our floating distribution, if needed
        for sublist in grouped_floating_items:
            for j in reversed(range(len(sublist))):
                item = sublist[j]
                if sample[item] > 0:
                    sample[item] -= 1
                    sample[item] += 1
                    sublist.pop(j)

        ## Move non-empty locations into the empty set if necessary
        high_priority_group = list()
        grouped_empty_locations.insert(0, high_priority_group)
        for loc in self.randomized_locations:
            if sample[loc.value.item_id] > 0:
                high_priority_group.append(loc)

        ## We need to ensure those locations are filled. If necessary, create empty items for them
        empty_count = len(high_priority_group) - sum(len(g) for g in grouped_floating_items)
        if empty_count > 0:
            self.grouped_floating_items[-1] += ( self.empty_item.id for _ in range(empty_count) )
            self.item_pool[self.empty_item.id] += empty_count

        ## Distributing them all!
        queued_locations: List[RealLocationTagModel] = grouped_empty_locations.pop(0)
        queued_items: List[int] = grouped_floating_items.pop(0)
        self.filled_empty_locations = list()
        while True:
            while not queued_locations and grouped_empty_locations:
                queued_locations.extend(grouped_empty_locations.pop(0))
            while not queued_items and grouped_floating_items:
                queued_items.extend(grouped_floating_items.pop(0))

            count = min(len(queued_locations), len(queued_items))
            if count == 0:
                if self.fail_if_insufficient_empty_locations and queued_items and not queued_locations:
                    raise Exception(f"Insufficient empty locations! {len(queued_items)} floating items unplaced!")
                elif queued_items:
                    starting_inventory.update(queued_items)
                break

            results = zip(
                sorted(self.random.sample(range(len(queued_locations)), count), reverse=True),
                sorted(self.random.sample(range(len(queued_items)), count), reverse=True),
            )
            for l, i in results:
                loc = queued_locations.pop(l)
                item = queued_items.pop(i)

                if loc.value.is_empty: ## Because we mix in some non-empty locations during voucher claims
                    loc.value.item_id = item
                    self.filled_empty_locations.append((loc.id, item))
                    self.randomized_locations.append(loc)

        #######################################################################
        ## Options Spoofing

        ## Creating counters of encounterable items
        item_counts = Counter( loc.value.item_id for loc in self.randomized_locations if loc.value.item_id != 0 )

        sample = self.sample_tags(
            item_counts.keys(),
            self.local_items.items(),
            cls.item_model_by_id,
            False,
            GTFOLocalItems.display_name,
        )
        opt = get_option(Options.LocalItems)
        local_items_setting = Options.LocalItems(opt.value.union({
            cls.item_model_by_id[item].name for item in sample.keys()
        }))

        sample = self.sample_tags(
            item_counts.keys(),
            self.non_local_items.items(),
            cls.item_model_by_id,
            False,
            GTFONonLocalItems.display_name,
        )
        opt = get_option(Options.NonLocalItems)
        non_local_items_setting = Options.LocalItems(opt.value.union({
            cls.item_model_by_id[item].name for item in sample.keys()
        }))

        sample = self.sample_tags(
            item_counts.keys(),
            self.item_hints.items(),
            cls.item_model_by_id,
            False,
            GTFOItemHints.display_name,
        )
        opt = get_option(Options.StartHints)
        item_hints_setting = Options.StartHints(opt.value.union({
            cls.item_model_by_id[item].name for item in sample.keys()
        }))

        sample = self.sample_tags(
            (loc.id for loc in itertools.chain(self.reachable_locations, self.randomized_locations)),
            self.location_hints.items(),
            cls.location_model_by_id,
            False,
            GTFOLocationHints.display_name,
        )
        opt = get_option(Options.StartLocationHints)
        location_hints_setting = Options.StartLocationHints(opt.value.union({
            cls.location_model_by_id[item].name for item in sample.keys()
        }))

        def inventory_item_not_found(not_found_tag: int, not_found_count: int):
            """Callback for if a starting inventory item is not found during sampling"""
            item_model = cls.item_model_by_id[not_found_tag]
            if not_found_count == 0:
                return
            if item_model.value is None:
                raise Exception(
                    f"No match for starting inventory item {item_model.name} could be found."
                    + " No matching items are in the item pool, and that exact name is only a parent, not an item"
                )
            starting_inventory[not_found_tag] += not_found_count

        item_counts.update( loc.value.item_id for loc in self.reachable_locations if loc.value.item_id != 0 )
        sample = self.sample_tags(
            item_counts.keys(),
            self.start_inventory.items(),
            cls.item_model_by_id,
            True,
            GTFOStartInventory.display_name,
            on_none_found=inventory_item_not_found
        )
        starting_inventory.update(sample)
        opt = get_option(Options.StartInventory)
        named_starting_inventory = {
            self.item_model_by_id[key].name: count for key, count in starting_inventory.items()
        }
        start_inventory_setting = Options.StartInventory(dict(Counter(named_starting_inventory) + Counter(opt.value)))

        ## List of options we've provided spoofing implementations for
        spoof_options: Dict[Type[Option], Option] = {
            Options.LocalItems: local_items_setting,
            Options.NonLocalItems: non_local_items_setting,
            Options.StartInventory: start_inventory_setting,
            Options.StartHints: item_hints_setting,
            Options.StartLocationHints: location_hints_setting,
            Options.ExcludeLocations: Options.PriorityLocations(
                { cls.location_model_by_id[p].name for p in priority_locations }
            ),
            Options.PriorityLocations: Options.ExcludeLocations(
                { cls.location_model_by_id[p].name for p in exclude_locations }
            ),
        }

        def get_annotations_recursive(ty: Type) -> Iterable[Tuple[str, Type]]:
            if ty == object:
                return []
            return itertools.chain(
                inspect.get_annotations(ty, eval_str=True).items(),
                *(get_annotations_recursive(b) for b in ty.__bases__)
            )

        for key, typ in get_annotations_recursive(Options.PerGameCommonOptions):
            if issubclass(typ, Option):
                if typ in spoof_options:
                    setattr(self.options, key, spoof_options[typ])
                else:
                    setattr(self.options, key, get_option(typ))
                #print(f"Set option: {key} to {typ.__name__}")

        return

    @override
    def create_regions(self) -> None:
        """
        For the sake of simplicity, we will do all our work in this one method
        """

        cls = type(self)
        #######################################################################
        ## Regions

        ## Create the regions!
        region_lookup = {
            r: Region(cls.region_model_by_id[r].name, self.player, self.multiworld) for r in self.reachable_regions
        }
        self.multiworld.regions += region_lookup.values()

        #######################################################################
        ## Paths

        for gen_path in self.gen_model.paths:

            ## Get the regions, check if path exists
            start_region = region_lookup.get(gen_path.starting_region, None)
            end_region = region_lookup.get(gen_path.ending_region, None)
            if start_region is None or end_region is None:
                continue

            ## Build the rule
            def make_rule(req: PathReqModel) -> Rule:
                req_count = req.count
                if req.type in ("ItemGrowing", "CategoryGrowing"):
                    req_count += self.growing_item_counts[req.target]
                    self.growing_item_counts[req.target] = req_count

                if req.type in ("Item", "ItemConsumed", "ItemGrowing"):
                    target_tag = cls.item_model_by_id[req.target]
                    return Has(target_tag.name, req_count)
                elif req.type in ("Category", "CategoryGrowing"):
                    target_tag = cls.item_model_by_id[req.target]
                    if not target_tag.name in cls.item_name_groups:
                        ## Condition is impossible to satisfy
                        ## This can happen if no items in the desired category actually exist
                        return False_()
                    return HasGroup(target_tag.name, req_count)
                else:
                    raise Exception(f"Unknown path req type: {gen_path.req_item.type}")

            path_rule = And( *(make_rule(r) for r in gen_path.reqs) ) if gen_path.reqs else True_()

            ## Create the path!
            path_name = f"Path {gen_path.id} {start_region.name} -> {end_region.name}" \
                if gen_path.name is None else gen_path.name
            start_region.connect(end_region, path_name, path_rule)

        #######################################################################
        ## Item Creation and Submission

        def create_location(loc_model: RealLocationTagModel) -> GTFOLocation:
            """Creates a GTFO location from its model"""

            ## Identify the location's 'main' region
            assert loc_model.value.owning_regions, f"Error while placing location {loc_model.id}; no owning regions"
            main_region = region_lookup.get(loc_model.value.owning_regions[0])
            assert main_region is not None, f"Error while placing location {loc_model.id}; main region not found"

            ## Compile 'other' regions for reference
            other_regions = [ region_lookup.get(r) for r in loc_model.value.owning_regions ]
            assert all(r is not None for r in other_regions), \
                f"Error while placing location {loc_model.id}; one of the other regions was not found"
            other_regions: List[Region]

            ## Identify the location's progress type (priority)
            progress_type = LocationProgressType.DEFAULT
            if loc_model.value.priority_mode == "Priority":
                progress_type = LocationProgressType.PRIORITY
            elif loc_model.value.priority_mode in [ "Excluded", "Trap" ]:
                progress_type = LocationProgressType.EXCLUDED

            ## Create the location!
            result = GTFOLocation(self.player, loc_model.name, loc_model.id, main_region)
            result.progress_type = progress_type
            main_region.locations.append(result)
            if other_regions:
                self.set_rule(result, And( *(CanReachRegion(o.name) for o in other_regions) ))
            return result

        ## Non-randomized locations will be modified to be event pairs
        for loc in self.reachable_locations:
            location = create_location(loc)
            item_model = cls.item_model_by_id[loc.value.item_id]
            assert item_model.value is not None, "Locations contains fake item model"
            item_model: RealItemTagModel
            if not (item_model.value.is_randomlike and not loc.value.is_empty):
                location.address = None
            item = self.create_item_by_model(item_model)
            location.place_locked_item(item)

        ## Randomized locations
        for loc in self.randomized_locations:
            create_location(loc)

        ## Randomized items
        for item_id in self.item_pool.elements():
            item = self.create_item_by_id(item_id)
            self.multiworld.itempool.append(item)

        ## Sample and apply early items
        early_items = self.sample_tags(
            self.item_pool.keys(),
            self.early_items.items(),
            self.item_model_by_id,
            False,
            EarlyItems.display_name,
            repeats=self.item_pool.values()
        )
        early_items_dict = self.multiworld.early_items.setdefault(self.player, dict())
        early_items_dict.update( (self.item_model_by_id[k].name, v) for (k, v) in early_items.items() )

        #######################################################################
        ## Goal Condition

        self.goal_item_results = self.sample_tags(
            itertools.chain(
                self.item_pool.keys(),
                (loc.value.item_id for loc in self.reachable_locations)
            ),
            self.goal_items.items(),
            self.item_model_by_id,
            False,
            GoalItems.display_name,
            itertools.chain(
                self.item_pool.values(),
                (1 for _ in self.reachable_locations)
            )
        )
        total = self.goal_item_results.total()
        if total <= 0:
            self.logger.error("No goal items found for world!")
            raise Exception("No goal items found for world!")
        self.set_completion_rule(HasFromList(
            *( self.item_model_by_id[i].name for i in self.goal_item_results.elements() ),
            count=total-self.skippable_goal_count
        ))

    @override
    def create_item(self, item_name: str) -> GTFOItem:
        """
        Create an item for this world type and player.
        Warning: this may be called with self.world = None, for example by MultiServer
        """
        item_id = self.item_name_to_id_casefold.get(item_name.casefold(), None)
        if item_id is None:
            raise Exception(f"Failed to look up item by name: {item_name}; cannot create null item")
        return self.create_item_by_id(item_id)
    
    def create_item_by_id(self, item_id: int) -> GTFOItem:
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
        return self.create_item_by_model(item_model)

    def create_item_by_model(self, item_model: RealItemTagModel) -> GTFOItem:
        """
        Create a particular item from its model.
        """
        ## Create classification data
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

        return GTFOItem(item_model.name, classification, item_model.id, self.player)

    @override
    def get_filler_item_name(self):
        return "Empty"

    @override
    def create_filler(self) -> GTFOItem:
        """Create a random filler item, which may be a trap item"""
        return self.create_item_by_model(self.empty_item_model)

    @override
    def fill_slot_data(self) -> Mapping[str, Any]:
        return SlotDataModel({
            "root_seed": self.root_seed,
            "region_whitelist": self.region_whitelist,
            "region_blacklist": self.region_blacklist,
            "location_whitelist": self.location_whitelist,
            "location_blacklist": self.location_blacklist,
            "item_whitelist": self.item_whitelist,
            "item_blacklist": self.item_blacklist,
            "filled_empty_locations": self.filled_empty_locations,
            "goal_items": list(self.goal_item_results.items()),
            "skippable_goal_count": self.skippable_goal_count,
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

    def sample_tags(self, src: Iterable[int], desired: Iterable[Tuple[int, int]], lookup: Mapping[int, TagModel],
                    allow_duplicates: bool, debug_name: str, repeats: Optional[Iterable[int]] = None,
                    on_none_found: Optional[Callable[[int, int], None]] = None) -> Counter[int]:
        """
        Samples a collection of tag IDs with respect to a target multiset of tags. For each (tag, count) in `desired`,
        attempts to find `count` tags which match or are children of `tag`, with aversion to duplicates.
         -> `allow_duplicates` optionally allows duplicates to be provided if `count` is greater than what's available
         -> `repeats`, if provided, should be equal in length to `src` and indicates how many copies of each source
            item should be provided.
         -> `on_none_found` is called when candidates are not found for a tag. It is called with (tag, count).
            If None (the default), this will instead raise an error if count is greater than 0.
        """
        if repeats is None:
            repeats = itertools.repeat(1)
        src = list(zip(src, repeats))

        results: Counter[int] = Counter() ## Multiset
        for tag, count in desired:
            ## Ignore empty keys in case we happen across them
            if count == 0:
                continue

            ## Collect items from source list which match
            candidates = Counter()
            for t, repeat in src:
                if GTFOWorld.tag_matches_single(t, tag, lookup):
                    candidates[t] += repeat

            total = candidates.total()
            if total <= 0:
                if on_none_found is not None:
                    on_none_found(tag, count)
                elif count > 0:
                    msg = f"During sampling, found no matches for tag {tag} ({lookup[tag].name}) in {debug_name}"
                    self.logger.warning(msg)
                    if self.fail_during_sampling:
                        raise Exception(msg)
                continue

            ## Move duplicates to a separate counter
            duplicates = Counter()
            for t, qty in candidates.items():
                result = results[t]
                if result > 0:
                    dif = min(result, qty)
                    duplicates[t] = dif
                    candidates[t] -= dif

            ## Deal with / apply duplication if necessary
            total = candidates.total()
            if total < count:
                if not allow_duplicates:
                    msg = f"Desired {count} items for tag {tag} in {debug_name}, but only found {total} matches"
                    self.logger.warning(msg)
                    if self.fail_during_sampling:
                        raise Exception(msg)
                    count = -1
                else:
                    results.update(candidates)
                    count -= total
                    candidates.update(duplicates)
                    total = candidates.total()
                    while total < count:
                        results.update(candidates)
                        count -= total

            ## Add sample
            if count == -1:
                results.update(candidates)
            elif count > 0: ## Small edge case we need to catch where count == 0
                results.update(self.random.sample(list(candidates.keys()), k=count, counts=candidates.values()))

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
        gen_model.paths.sort(key=lambda path: path.name if path.name is not None else "")
        world_class.location_name_to_id = { loc.name: loc.id for loc in gen_model.locations }
        world_class.location_name_to_id_casefold = { loc.name.casefold(): loc.id for loc in gen_model.locations }
        world_class.location_model_by_id = { loc.id: loc for loc in gen_model.locations }
        world_class.item_model_by_id = { item.id: item for item in gen_model.items }
        world_class.item_name_to_id = { item.name: item.id for item in gen_model.items }
        world_class.item_name_to_id_casefold = { item.name.casefold(): item.id for item in gen_model.items }

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
        world_class.item_name_groups = dict()
        def add_item_group_recursive(i_name: str, tag_id: int):
            """Helper to add items to groups"""
            if tag_id == 0: return
            tag_model = world_class.item_model_by_id[tag_id]
            world_class.item_name_groups.setdefault(tag_model.name, set()).add(i_name)
            for p in tag_model.parents:
                add_item_group_recursive(i_name, p)

        for gen_item in gen_model.items:
            if gen_item.value is not None:
                add_item_group_recursive(gen_item.name, gen_item.id)

        ###########################################################################################
        ## Options creation

        ## Creating the options lookup
        world_class.option_model_by_id = { o.id: o for o in gen_model.options }

        ## Define the options dataclass
        options_dict = { "__annotations__": dict() }

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
        names: Set[str] = set()
        for tup in (o for os in option_groups_raw.values() for o in os):
            display_name = getattr(tup[1], "display_name", tup[1].__name__)
            assert isinstance(display_name, str), f"display_name is not a string!"
            options_dict["__annotations__"][display_name] = tup[1]
            names.add(display_name)

        ## Define an init function (normally done via dataclass decorator)
        def init(self, **kwargs: Option):
            if kwargs.keys() != names:
                raise Exception(
                    "Unexpected number of inputs to generated options class's __init__"
                    f"\nMissing inputs: {names - kwargs.keys()}"
                    f"\nExtra inputs: {kwargs.keys() - names}"
                )
            for k, v in kwargs.items():
                setattr(self, k, v)

        options_dict["__init__"] = init # type: ignore[misc]

        ## Finally, create the options dataclass and assign it to our generated world
        options_class = type(Options.CommonOptions)(f"GTFO Options ({gen_model.name})", (object,), options_dict)
        #options_class = cast(CommonOptions, dataclasses.dataclass(options_class, init=True))
        world_class.options_dataclass = options_class

        ###########################################################################################
        ## Web World creation

        ## Defining a derived class
        web_class = SimpleNamespace()
        web_class: Type[WebWorld]
        web_class.option_groups = [
            Options.OptionGroup(name, [i[1] for i in items]) for name, items in option_groups_raw.items() if name != ""
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
        return cast(Type[GTFOWorld], type(GTFOWorld)(f"GTFO World ({gen_model.name})", (GTFOWorld,), world_class.__dict__))

## Now we simply create all the GTFO worlds
GTFOWorldBuilder.make_worlds()


