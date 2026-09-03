from __future__ import annotations

from collections import Counter, defaultdict
import itertools
import logging
import random
from typing import Any, ClassVar, Callable, Collection, Dict, FrozenSet, Iterable, List, Mapping, Optional, Set, \
    Tuple, Type, TYPE_CHECKING

from Options import OptionsMetaProperty, Accessibility, DefaultOnToggle, ExcludeLocations, StartHints, LocalItems, \
    StartLocationHints, NonLocalItems, NumericOption, Option, OptionCounter, OptionSet, \
    PriorityLocations, ProgressionBalancing, Range, StartInventory, PerGameCommonOptions
import Utils
from worlds.gtfo import SlotDataModel

from .model import OptionSetTarget, OptionDictTarget, RealLocationTagModel, TagModel

if TYPE_CHECKING:
    from .__init__ import GTFOWorld

class TagSet(OptionSet):
    """
    Base class for options which accept a set of tags
    """
    value: Set[str]

class TagCounter(OptionCounter):
    """
    Base class for options which accept a dict of tags
    """
    value: Dict[str, int]

class GTFOAccessibility(Accessibility):
    default = "Minimal"

class RootSeed(NumericOption):
    """
    A custom seed used for randomizing particular parts of GTFO.
    This seed can be any value; any value which is not an integer is hashed to produce an integer.
    Set to 0 to use a random seed.
    """
    display_name = "Root Seed"
    rich_text_doc = True
    default = 0

    def __init__(self, value):
        self.value = value
        super().__init__()

    @classmethod
    def from_any(cls, data: Any) -> RootSeed:
        value: int
        try:
            value = int(data)
        except ValueError:
            value = hash(data)
        except TypeError:
            if isinstance(data, list):
                value = random.choice(data)
            elif isinstance(data, dict):
                if any(v < 0 for v in data.values()):
                    raise Exception("Cannot parse RootSeed: random seed selection failed because a weight is negative")
                total = sum(data.values())
                if total == 0:
                    raise Exception("Cannot parse RootSeed: random seed selection failed, all weights are at zero")
                value = random.sample(list(data.keys()), k=1, counts=data.values())[0]
            else:
                raise Exception("Cannot parse RootSeed; unrecognized input!")
        return RootSeed(value)

    def get_option_name(cls, value: int) -> str:
        return str(value)

class RegionWhitelist(TagSet):
    """
    Which regions to consider/enable for randomization.
    Regions are sorted hierarchically. The root region is the 'All Expeditions' region; its children are the
    expeditions regions, ie 'R1A1'; its children are its layers, such as 'R1A1 (Main)' or 'R1A1 (Dim #1)';
    its children are zones, objectives, and so forth.
    Whitelisting or blacklisting a region applies the same to all its children.
    This set is a whitelist; for a region to be randomized it must match the whitelist and not the blacklist.
    """
    display_name = "Region Whitelist"
    rich_text_doc = True
    default = set()

class RegionBlacklist(TagSet):
    """
    Which regions to block/disable from randomization.
    Regions are sorted hierarchically. The root region is the 'All Expeditions' region; its children are the
    expeditions regions, ie 'R1A1'; its children are its layers, such as 'R1A1 (Main)' or 'R1A1 (Dim #1)';
    its children are zones,  objectives, and so forth.
    Whitelisting or blacklisting a region applies the same to all its children.
    This set is a blacklist; for a region to be randomized it must match the whitelist and not the blacklist.
    """
    display_name = "Region Blacklist"
    rich_text_doc = True
    default = set()

class LocationWhitelist(TagSet):
    """
    Which locations to consider/enable for randomization.
    Locations are sorted hierarchically; at the root is 'all' locations, with children such as 'scan' locations,
    'warp' locations, 'event' locations, and so forth. Each of these has child locations, often sorted by expedition,
    layer, zone, or objective.
    Whitelisting or blacklisting a location applies the same to all its children.
    This set is a whitelist; for a location to be randomized it must match the whitelist and not the blacklist.
    """
    display_name = "Location Whitelist"
    rich_text_doc = True
    default = set()

class LocationBlacklist(TagSet):
    """
    Which locations to block/disable from randomization.
    Locations are sorted hierarchically; at the root is 'all' locations, with children such as 'scan' locations,
    'warp' locations, 'event' locations, and so forth. Each of these has child locations, often sorted by expedition,
    layer, zone, or objective.
    Whitelisting or blacklisting a location applies the same to all its children.
    This set is a blacklist; for a location to be randomized it must match the whitelist and not the blacklist.
    """
    display_name = "Location Blacklist"
    rich_text_doc = True
    default = set()

class ItemWhitelist(TagSet):
    """
    Which items to consider/enable for randomization.
    Items are sorted hierarchically; at the root is 'all' item, with children such as 'scan' items,
    'warp' items, 'event' items, and so forth. Each of these has child items, often sorted by expedition,
    layer, zone, or objective.
    Whitelisting or blacklisting an item applies the same to all its children.
    This set is a whitelist; for an item to be randomized it must match the whitelist and not the blacklist.
    """
    display_name = "Item Whitelist"
    rich_text_doc = True
    default = set()

class ItemBlacklist(TagSet):
    """
    Which items to block/disable from randomization.
    Items are sorted hierarchically; at the root is 'all' item, with children such as 'scan' items,
    'warp' items, 'event' items, and so forth. Each of these has child items, often sorted by expedition,
    layer, zone, or objective.
    Whitelisting or blacklisting an item applies the same to all its children.
    This set is a blacklist; for an item to be randomized it must match the whitelist and not the blacklist.
    """
    display_name = "Item Blacklist"
    rich_text_doc = True
    default = set()

class StartVouchers(TagCounter):
    """
    Start vouchers, specified as a list of tags. During randomization, one
    item per requested voucher will be removed from the item pool and placed
    in the starting inventory. If you use a tag which is a parent of multiple
    items, one random applicable item is selected per request. If duplicate
    items exist in the item pool, they are equally likely to be selected, but
    no more than the quantity of items in the pool can be selected.

    This differs from Start Inventory in that it will never create new items,
    it can only move randomized items out of the pool and into the starting inventory.
    """
    display_name = "Start Vouchers"
    rich_text_doc = True
    default = dict()

class EarlyItems(TagCounter):
    """
    Items matching tags in this list will be added to the first sphere.
    If a parent tag is specified, the requested quantity of children will be randomly
    selected from the random items pool for randomization.
    For example, if using the 'ITEM' progressive style, you may specify `"Expedition Unlock Items": 1`
    to choose one random available expedition unlock to be an early item.
    This will only work on items which both exist and are randomized.
    The special value "-1" will randomize all matching child tags.
    """
    display_name = "Early Items"
    rich_text_doc = True
    default = dict()

class GoalItems(TagCounter):
    """
    During randomization, all reachable items are identified. This tag counter is then
    used to randomly pick items from that list and mark them as goal items. All goal items
    must be collected to win, except those skipped via Skippable Goal Count.
    """
    display_name = "Goal Items"
    rich_text_doc = True
    default = dict()

class SkippableGoalCount(Range):
    """
    The number of goal items which can be skipped. For example, specifying `3` would allow you to
    skip any 3 goal items. If your goal were 'All Main Sectors Cleared', this would allow you to skip
    clearing 3 main sectors.
    """
    display_name = "Skippable Goal Count"
    rich_text_doc = True
    default = 0
    range_start = 0
    range_end = 99

class GTFOLocalItems(TagCounter):
    """
    During randomization, a set of all unique randomized items is created. For each `tag: count`
    in this option, `count` items which are children of `tag` are marked as local items, making
    them and all items sharing their name local items.
    The special value "-1" will mark all matching child items.
    """
    display_name = "GTFO Local Items"
    rich_text_doc = True
    default = dict()

class GTFONonLocalItems(TagCounter):
    """
    During randomization, a set of all unique randomized items is created. For each `tag: count`
    in this option, `count` items which are children of `tag` are marked as nonlocal items, making
    them and all items sharing their name nonlocal items.
    The special value "-1" will mark all matching child items.
    """
    display_name = "GTFO Non-Local Items"
    rich_text_doc = True
    default = dict()

class GTFOStartInventory(TagCounter):
    """
    During randomization, a set of all unique reachable items is created. This includes both
    randomized items and non-randomized items. For each `tag: count` in this option, `count`
    items which are children of `tag` are selected and duplicated, creating a copy which is
    added to the starting inventory. If no matches are found, `tag` is assumed to be an item
    and is created by name, adding `count` duplicates of it to the starting inventory.
    """
    display_name = "GTFO Start Inventory"
    rich_text_doc = True
    default = dict()

class GTFOItemHints(TagCounter):
    """
    During randomization, a set of all unique randomized items is created. For each `tag: count`
    in this option, `count` items which are children of `tag` are marked as hint items, which
    results in hints being created for all instances of the item.
    The special value "-1" will mark all matching child items.
    """
    display_name = "GTFO Item Hints"
    rich_text_doc = True
    default = dict()

class GTFOLocationHints(TagCounter):
    """
    During randomization, a set of all locations is created. For each `tag: count` in this option,
    `count` locations which are children of `tag` are marked as hint locations, which results in
    hints being created for those locations.
    The special value "-1" will mark all matching child locations.
    """
    display_name = "GTFO Location Hints"
    rich_text_doc = True
    default = dict()

class GTFOExcludeLocations(TagCounter):
    """
    During randomization, a set of all locations is created. For each `tag: count` in this option,
    `count` locations which are children of `tag` are marked as excluded locations.
    The special value "-1" will mark all matching child locations.
    """
    display_name = "GTFO Excluded Locations"
    rich_text_doc = True
    default = dict()

class GTFOPriorityLocations(TagCounter):
    """
    During randomization, a set of all locations is created. For each `tag: count` in this option,
    `count` locations which are children of `tag` are marked as priority locations.
    The special value "-1" will mark all matching child locations.
    """
    display_name = "GTFO Priority Locations"
    rich_text_doc = True
    default = dict()

class FailIfInsufficientEmptyLocations(DefaultOnToggle):
    """
    If true, when randomizing, if there is an insufficient number of empty locations,
    immediately fail; this is useful to ensure the game randomizes as intended.
    Disable this only if generation fails AND you don't want to change your settings.
    """
    display_name = "Fail If Insufficient Empty Locations"
    rich_text_doc = True

class FailDuringSampling(DefaultOnToggle):
    """
    If true, when randomizing, when sampling for items and locations from the item pool
    in order to meet specific settings, if there is an insufficient number of matches, fail.
    For example, if you set "Early Primary Gear" to 3 and only two are found, this would
    cause it to fail.
    Disable this only if generation fails AND you don't want to change your settings.
    """
    display_name = "Fail During Sampling"
    rich_text_doc = True

class OptionsEvaluator:
    """Wraps and supports option evaluation"""

    def __init__(self, options: GTFOOptions, world_instance: Optional[GTFOWorld]):
        self.options = options
        self.world_instance = world_instance
        self.option_results = dict()

    options: GTFOOptions
    """The world options are being evaluated for"""
    world_instance: Optional[GTFOWorld]
    """The world instance being evaluated, if available"""
    option_results: Dict[int, Optional[Collection[int]]]
    """Option results. Key is option ID; value is None if mid-evaluation, else the resulting value"""

    def get_output(self, option_id: int) -> Collection[int]:
        """Evaluate an option and get its resulting value"""
        if not id in self.option_results:
            self.option_results[option_id] = None
            self.option_results[option_id] = self.options.world.option_model_by_id[option_id].evaluate(self)
        value = self.option_results[option_id]
        if value is None:
            raise Exception(f"Circular dependency detected in option evaluation for option id {option_id}")
        return value

    def get_set_target(self, target: OptionSetTarget) -> Set[int]:
        """Get a particular set representing the desired target"""
        match target:
            case "RegionWhitelist":
                return self.options.region_whitelist
            case "RegionBlacklist":
                return self.options.region_blacklist
            case "LocationWhitelist":
                return self.options.location_whitelist
            case "LocationBlacklist":
                return self.options.location_blacklist
            case "ItemWhitelist":
                return self.options.item_whitelist
            case "ItemBlacklist":
                return self.options.item_blacklist
            case _:
                raise NotImplementedError

    def get_dict_target(self, target: OptionDictTarget) -> Dict[int, int]:
        """Get a particular dict representing the desired target"""
        match target:
            case "GoalItems":
                return self.options.goal_items
            case "StartInventory":
                return self.options.gtfo_start_inventory
            case "StartVouchers":
                return self.options.start_vouchers
            case "EarlyItems":
                return self.options.early_items
            case "LocalItems":
                return self.options.gtfo_local_items
            case "NonLocalItems":
                return self.options.gtfo_non_local_items
            case "ItemHints":
                return self.options.gtfo_item_hints
            case "LocationHints":
                return self.options.gtfo_location_hints
            case "PriorityLocations":
                return self.options.gtfo_priority_locations
            case "ExcludeLocations":
                return self.options.gtfo_exclude_locations
            case _:
                raise NotImplementedError

class StateReachability:
    """
    Helper used to track the reachability of regions, locations, items, etc. in various states
    """
    reachable_regions: Set[int]
    reachable_locations: Set[int]
    item_counts: Counter[int]
    prog_counts: Counter[int]
    cats_counts: Counter[int]
    blocked_paths: List[int]

    def __init__(self):
        self.reachable_regions = set()
        self.reachable_locations = set()
        self.item_counts = Counter()
        self.prog_counts = Counter()
        self.cats_counts = Counter()
        self.blocked_paths = list()

class TagSampler:
    """Simple wrapper class used to support tag sampling."""
    logger: Optional[logging.Logger]
    rand: random.Random
    fail_during_sampling: bool

    def __init__(self, logger: Optional[logging.Logger], rand: random.Random, fail_during_sampling: bool):
        self.logger = logger
        self.rand = rand
        self.fail_during_sampling = fail_during_sampling

    def try_warn(self, msg: str):
        if self.logger:
            self.logger.warning(msg)

    def sample(self, src: Iterable[int], desired: Iterable[Tuple[int, int]], lookup: Mapping[int, TagModel],
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
        from . import GTFOWorld
        if repeats is None:
            repeats = itertools.repeat(1)
        src = list(zip(src, repeats))

        results: Counter[int] = Counter()  ## Multiset
        for tag, count in desired:
            ## Ignore empty keys in case we happen across them
            if count is None or count == 0:
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
                    self.try_warn(msg)
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
                    msg = f"Desired {count} items for tag {tag} ({lookup[tag].name}) in {debug_name}," \
                          + f" but only found {total} matches"
                    self.try_warn(msg)
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
            elif count > 0:  ## Small edge case we need to catch where count == 0
                results.update(self.rand.sample(list(candidates.keys()), k=count, counts=candidates.values()))

        return results

class GTFOOptionsMetaclass(OptionsMetaProperty):
    """
    This metaclass is necessary because option's type_hints property cannot handle class variables.
    This simply overrides that one property to support type_hints.
    """

    @property
    def type_hints(cls: Type[GTFOOptions]) -> Dict[str, Type[Option[Any]]]:
        return cls.gtfo_type_hints

class GTFOOptions(PerGameCommonOptions, metaclass=GTFOOptionsMetaclass):
    """Base options class"""

    world: ClassVar[Type[GTFOWorld]]
    """World class which uses this options class"""
    logger: ClassVar[logging.Logger]
    """Logger for this options type (since logging per instance isn't really useful..."""
    gtfo_type_hints: ClassVar[Dict[str, Type[Option[Any]]]]
    """The typing for options in this options class."""

    @classmethod
    @property
    def type_hints(cls) -> Dict[str, Type[Option[Any]]]:
        """Overriding the parent property because it assumes no class variables"""
        return cls.gtfo_type_hints

    random: random.Random
    """Instance of random for this options"""
    growth_reqs: Dict[int, Dict[int, int]]
    """Tracks the final cost of growth path requirements. Dict[path.id, Dict[req.index, count]]"""
    global_reachability: StateReachability
    """Tracks if regions can be reached in any state, and persistent item/location pairs"""
    state_reachability: Dict[FrozenSet[int], StateReachability]
    """Tracks reachability for particular states"""
    filled_empty_locations: Dict[int, int]
    """Maps reachable empty locations to the items they get filled with during generation"""
    growing_item_counts: Counter[int]
    """Current sum of encountered growing paths"""
    start_inventory_results: Counter[int]
    """Resulting list of start items from both start inventories"""
    start_voucher_results: Counter[int]
    """Resulting list of items claimed as starting items via start vouchers"""
    goal_item_results: Counter[int]
    """Resulting list of goal items calculated from reachable items"""
    skippable_goal_count: int
    """Number of goal items we can skip"""

    errors: List[Tuple[str, List[str], Dict[str, int]]]
    """
    Errors encountered while processing tags, accumulated and logged by the world class later.
    List[ (thing_being_processed_name, List[error_strings], tag_lookup_for_these_tags) ]
    """

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

    arch_start_inventory: Counter[int]
    """Copy of archipelago start inventory as item IDs"""
    arch_local_items: Set[int]
    """Copy of archipelago local items as item IDs"""
    arch_non_local_items: Set[int]
    """Copy of archipelago nonlocal items as item IDs"""
    arch_item_hints: Set[int]
    """Copy of archipelago item hints as item IDs"""
    arch_location_hints: Set[int]
    """Copy of archipelago location hints as location IDs"""
    arch_priority_locations: Set[int]
    """Copy of archipelago priority locations as location IDs"""
    arch_exclude_locations: Set[int]
    """Copy of archipelago exclude exclude locations as location IDs"""

    goal_items: Counter[int]
    """Dict of (tag, count) of items to demand for the player to win the goal"""
    gtfo_start_inventory: Counter[int]
    """Tags and counts for items to place in our starting inventory"""
    start_vouchers: Counter[int]
    """Dict of (tag, count) of items to pull prior to randomization and add to the starting inventory"""
    early_items: Counter[int]
    """Dict of (tag, count) of items to set as early"""
    gtfo_local_items: Counter[int]
    """Tags for items to force as local"""
    gtfo_non_local_items: Counter[int]
    """Tags for items to force as nonlocal"""
    gtfo_item_hints: Counter[int]
    """Tags and counts for items which start hinted."""
    gtfo_location_hints: Counter[int]
    """Tags and counts for locations which start hinted."""
    gtfo_priority_locations: Counter[int]
    """Tags for locations to override and mark as priorities"""
    gtfo_exclude_locations: Counter[int]
    """Tags for locations to override and mark as excluded"""

    fail_if_insufficient_empty_locations: bool
    """If true, raise an exception if there are insufficient empty locations for the selected floating items"""
    fail_during_sampling: bool
    """If true, raise an exception if sampling fails to one or more tag matches"""
    root_seed: int
    """Seed chosen and shared for generation"""

    def __init__(self, **kwargs: Mapping[str, Any]):
        """Init using metadata to check validity"""

        ## Parse arguments and init
        if kwargs.keys() != self.gtfo_type_hints.keys():
            raise Exception(
                "Unexpected inputs to generated options class's __init__"
                f"\n  Missing inputs: {self.gtfo_type_hints.keys() - kwargs.keys()}"
                f"\n  Extra inputs: {kwargs.keys() - self.gtfo_type_hints.keys()}"
            )

        for k, v in kwargs.items():
            setattr(self, k, v)

        self.random = random.Random()
        self.errors = list()

        self.parse_inputs()
        self.evaluate(None)
        self.spoof()

    def parse_inputs(self):
        """Parse the option inputs, IE the auto-generated options"""

        def get_option[T: Option](opt_type: Type[T]) -> T:
            """Helper to get a particular option from this options class"""
            return getattr(self, getattr(opt_type, "display_name", opt_type.__name__))

        #######################################################################
        ## General

        root_seed = get_option(RootSeed)
        self.root_seed = root_seed.value or random.randrange(0, 2 ** 52)
        ## ^ Pushing the resulting root seed back so it can be read in universal tracker

        fail_if_insufficient_empty_locations = get_option(FailIfInsufficientEmptyLocations)
        self.fail_if_insufficient_empty_locations = fail_if_insufficient_empty_locations.value != 0

        fail_during_sampling = get_option(FailDuringSampling)
        self.fail_during_sampling = fail_during_sampling.value != 0

        skippable_goal_count = get_option(SkippableGoalCount)
        self.skippable_goal_count = skippable_goal_count.value

        #######################################################################
        ## Converting user options to tags

        self.errors = list()
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
                self.errors.append((debug_name, local_errors, tag_lookup))

        self.arch_local_items = set()
        move_to_tag_set(
            self.local_items.value,
            self.arch_local_items,
            self.world.item_name_to_id_casefold,
            "local_items"
        )

        self.arch_non_local_items = set()
        move_to_tag_set(
            self.non_local_items.value,
            self.arch_non_local_items,
            self.world.item_name_to_id_casefold,
            "non_local_items"
        )

        self.arch_item_hints = set()
        move_to_tag_set(
            self.start_hints.value,
            self.arch_item_hints,
            self.world.item_name_to_id_casefold,
            "start_hints"
        )

        self.arch_location_hints = set()
        move_to_tag_set(
            self.start_location_hints.value,
            self.arch_location_hints,
            self.world.location_name_to_id_casefold,
            "start_location_hints"
        )

        self.arch_priority_locations = set()
        move_to_tag_set(
            self.priority_locations.value,
            self.arch_priority_locations,
            self.world.location_name_to_id_casefold,
            "priority_locations"
        )

        self.arch_exclude_locations = set()
        move_to_tag_set(
            self.exclude_locations.value,
            self.arch_exclude_locations,
            self.world.location_name_to_id_casefold,
            "exclude_locations"
        )

        self.region_whitelist = set()
        opt = get_option(RegionWhitelist)
        move_to_tag_set(
            opt.value,
            self.region_whitelist,
            self.world.region_name_to_id_casefold,
            opt.display_name
        )
        self.region_whitelist.add(self.world.region_name_to_id_casefold["always"])

        self.region_blacklist = set()
        opt = get_option(RegionBlacklist)
        move_to_tag_set(
            opt.value,
            self.region_blacklist,
            self.world.region_name_to_id_casefold, opt.display_name
        )
        self.region_blacklist.add(self.world.region_name_to_id_casefold["never"])

        self.location_whitelist = set()
        opt = get_option(LocationWhitelist)
        move_to_tag_set(
            opt.value,
            self.location_whitelist,
            self.world.location_name_to_id_casefold, opt.display_name
        )
        self.location_whitelist.add(self.world.location_name_to_id_casefold["always"])

        self.location_blacklist = set()
        opt = get_option(LocationBlacklist)
        move_to_tag_set(
            opt.value,
            self.location_blacklist,
            self.world.location_name_to_id_casefold, opt.display_name
        )
        self.location_blacklist.add(self.world.location_name_to_id_casefold["never"])

        self.item_whitelist = set()
        opt = get_option(ItemWhitelist)
        move_to_tag_set(
            opt.value,
            self.item_whitelist,
            self.world.item_name_to_id_casefold, opt.display_name
        )
        self.item_whitelist.add(self.world.item_name_to_id_casefold["always"])

        self.item_blacklist = set()
        opt = get_option(ItemBlacklist)
        move_to_tag_set(
            opt.value,
            self.item_blacklist,
            self.world.item_name_to_id_casefold, opt.display_name
        )
        self.item_blacklist.add(self.world.item_name_to_id_casefold["never"])

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
                self.errors.append((debug_name, local_errors, tag_lookup))

        self.arch_start_inventory = Counter()
        move_to_tag_dict(
            self.start_inventory.value,
            self.arch_start_inventory,
            self.world.item_name_to_id_casefold,
            "start_inventory"
        )

        self.goal_items = Counter()
        opt = get_option(GoalItems)
        move_to_tag_dict(
            opt.value,
            self.goal_items,
            self.world.item_name_to_id_casefold,
            opt.display_name
        )

        self.gtfo_start_inventory = Counter()
        opt = get_option(GTFOStartInventory)
        move_to_tag_dict(
            opt.value,
            self.gtfo_start_inventory,
            self.world.item_name_to_id_casefold,
            opt.display_name
        )

        self.start_vouchers = Counter()
        opt = get_option(StartVouchers)
        move_to_tag_dict(
            opt.value,
            self.start_vouchers,
            self.world.item_name_to_id_casefold,
            opt.display_name
        )

        self.early_items = Counter()
        opt = get_option(EarlyItems)
        move_to_tag_dict(
            opt.value,
            self.early_items,
            self.world.item_name_to_id_casefold,
            opt.display_name
        )

        self.gtfo_local_items = Counter()
        opt = get_option(GTFOLocalItems)
        move_to_tag_dict(
            opt.value,
            self.gtfo_local_items,
            self.world.item_name_to_id_casefold,
            opt.display_name
        )

        self.gtfo_non_local_items = Counter()
        opt = get_option(GTFONonLocalItems)
        move_to_tag_dict(
            opt.value,
            self.gtfo_non_local_items,
            self.world.item_name_to_id_casefold,
            opt.display_name
        )

        self.gtfo_item_hints = Counter()
        opt = get_option(GTFOItemHints)
        move_to_tag_dict(
            opt.value,
            self.gtfo_item_hints,
            self.world.item_name_to_id_casefold,
            opt.display_name
        )

        self.gtfo_location_hints = Counter()
        opt = get_option(GTFOLocationHints)
        move_to_tag_dict(
            opt.value,
            self.gtfo_location_hints,
            self.world.location_name_to_id_casefold,
            opt.display_name
        )

        self.gtfo_priority_locations = Counter()
        opt = get_option(GTFOPriorityLocations)
        move_to_tag_dict(
            opt.value,
            self.gtfo_priority_locations,
            self.world.location_name_to_id_casefold,
            opt.display_name
        )

        self.gtfo_exclude_locations = Counter()
        opt = get_option(GTFOExcludeLocations)
        move_to_tag_dict(
            opt.value,
            self.gtfo_exclude_locations,
            self.world.location_name_to_id_casefold,
            opt.display_name
        )

        return

    def evaluate(self, world_instance: Optional[GTFOWorld]):
        """Using the provided world instance, evaluate all options and perform the graph traversal"""

        from . import GTFOWorld

        ## Init / reset
        self.goal_items = Counter()
        self.gtfo_start_inventory = Counter()
        self.start_vouchers = Counter()
        self.early_items = Counter()
        self.gtfo_local_items = Counter()
        self.gtfo_non_local_items = Counter()
        self.gtfo_item_hints = Counter()
        self.gtfo_location_hints = Counter()
        self.gtfo_priority_locations = Counter()
        self.gtfo_exclude_locations = Counter()
        generation_is_fake = False

        def check_errors():
            if world_instance is None or not self.errors:
                return

            error_message: str
            player_name = world_instance.multiworld.get_player_name(world_instance.player)
            error_message = \
                f"YAML file parsing failed for player: {player_name}" \
                + "\nDebug is printed below. All tag names are case-insensitive."

            for opt_name, error_items, tag_dict in self.errors:
                count = len(error_items)
                error_message += f'\nFailed to find {count} tag{"" if count == 1 else "s"} for option "{opt_name}":'
                for e in error_items:
                    match = Utils.get_fuzzy_results(e.casefold(), tag_dict.keys(), 1)
                    if match and match[0][1] > .3:
                        error_message += f'\n -"{e}" (Did you mean "{match[0][0]}"? {match[0][1]}% certain)'
                    else:
                        error_message += f'\n -"{e}" (No likely matches found)'

            if world_instance is None:
                self.logger.error(error_message)
            else:
                raise Exception(error_message)

        ## Universal Tracker Integration
        if world_instance is not None:
            re_gen_passthrough = getattr(world_instance.multiworld, "re_gen_passthrough", {})
            generation_is_fake = re_gen_passthrough and world_instance.game in re_gen_passthrough
        if not generation_is_fake:
            check_errors() ## Errors from previous attempt at generation

        self.random.seed(self.root_seed) ## Enforces consistency between UT and non-UT
        self.errors = list()
        oe = OptionsEvaluator(self, world_instance)
        for option in self.world.option_model_by_id.keys():
            oe.get_output(option)
        check_errors() ## Errors from evaluating just now

        if generation_is_fake:
            re_gen_passthrough = world_instance.multiworld.re_gen_passthrough
            slot_data = SlotDataModel(re_gen_passthrough[world_instance.game])
            self.root_seed = slot_data.root_seed
            self.region_whitelist = set(slot_data.region_whitelist)
            self.region_blacklist = set(slot_data.region_blacklist)
            self.location_whitelist = set(slot_data.location_whitelist)
            self.location_blacklist = set(slot_data.location_blacklist)
            self.item_whitelist = set(slot_data.item_whitelist)
            self.item_blacklist = set(slot_data.item_blacklist)
            self.filled_empty_locations = Counter({ k: v for k, v in slot_data.filled_empty_locations } )
            self.goal_item_results = Counter({ k: v for k, v in slot_data.goal_item_results } )
            self.skippable_goal_count = slot_data.skippable_goal_count
            self.start_inventory_results = Counter({ k: v for k, v in slot_data.start_inventory_results } )


        #######################################################################
        ## Regions, Locations, and Items

        ## Tag sampler used for, well, sampling tags
        self.random.seed(self.root_seed)
        tag_sampler = TagSampler(
            world_instance.logger if world_instance is not None else None,
            self.random,
            self.fail_during_sampling if world_instance is not None else False
        )

        ## Parsing the white and black lists
        enabled_regions = {
            i for i in self.region_whitelist
            if not GTFOWorld.tag_matches(i, self.region_blacklist, self.world.region_model_by_id)
        }
        for tag_model in self.world.region_model_by_id.values():
            if tag_model.id == 38:
                pass
            if len(tag_model.parents) <= 1:
                ## More optimized check which only works if there's only one parent
                if tag_model.parents[0] in enabled_regions and not tag_model.id in self.region_blacklist:
                    enabled_regions.add(tag_model.id)
            else:
                ## Less optimized but more through check for multi-parent tags. Can probably be optimized
                if any(p in enabled_regions for p in tag_model.parents) and not \
                        GTFOWorld.tag_matches(tag_model.id, self.region_blacklist, self.world.region_model_by_id):
                    enabled_regions.add(tag_model.id)

        enabled_locations: Set[int] = set()
        for loc_model in self.world.gen_model.locations:
            if loc_model.value is None: continue
            if not all(r in enabled_regions for r in loc_model.value.owning_regions): continue

            loc_white = GTFOWorld.tag_matches(loc_model.id, self.location_whitelist, self.world.location_model_by_id)
            loc_black = GTFOWorld.tag_matches(loc_model.id, self.location_blacklist, self.world.location_model_by_id)

            if loc_model.value.is_empty:
                if loc_white and not loc_black:
                    enabled_locations.add(loc_model.id)
                continue
            assert loc_model.value.item_id != 0, "Location model is both empty and has item ID of zero!"

            item_id = loc_model.value.item_id
            item_white = GTFOWorld.tag_matches(item_id, self.item_whitelist, self.world.item_model_by_id)
            item_black = GTFOWorld.tag_matches(item_id, self.item_blacklist, self.world.item_model_by_id)

            if (loc_white or item_white) and not (loc_black or item_black):
                enabled_locations.add(loc_model.id)

        ## Growing path requirements
        growth_counts: Counter[int] = Counter()
        self.growth_reqs = defaultdict(lambda: dict())  ## The lambda satisfies the type checker, for some reason
        for path_model in self.world.gen_model.paths:
            if path_model.starting_region not in enabled_regions or path_model.ending_region not in enabled_regions:
                continue
            for i, req in enumerate(path_model.reqs):
                if req.is_growing:
                    growth_counts[req.target] += req.count
                    self.growth_reqs[path_model.id][i] = growth_counts[req.target]
        del growth_counts

        ## Starting inventory
        if not generation_is_fake:
            self.start_inventory_results = Counter(self.arch_start_inventory)

            def inventory_item_not_found(not_found_tag: int, not_found_count: int):
                """Callback for if a starting inventory item is not found during sampling"""
                item_model = self.world.item_model_by_id[not_found_tag]
                if not_found_count == 0:
                    return
                if item_model.value is None:
                    raise Exception(
                        f"No match for starting inventory item {item_model.name} could be found."
                        + " No matching items are in the item pool, and that exact name is only a parent, not an item"
                    )
                self.start_inventory_results[not_found_tag] += not_found_count

            encounterable_items = {
                loc.value.item_id for l in enabled_locations
                if (loc := self.world.location_model_by_id[l]).value.item_id != 0
            }
            encounterable_items.update(
                pair.item for pair in self.world.gen_model.floating_items
                if pair.region in enabled_regions
                and GTFOWorld.tag_matches(pair.item, self.item_whitelist, self.world.item_model_by_id)
                and not GTFOWorld.tag_matches(pair.item, self.item_blacklist, self.world.item_model_by_id)
            )
            self.start_inventory_results.update(
                tag_sampler.sample(
                    encounterable_items,
                    self.gtfo_start_inventory.items(),
                    self.world.item_model_by_id,
                    True,
                    GTFOStartInventory.display_name,
                    on_none_found=inventory_item_not_found
                )
            )
            del encounterable_items

        def update_item_count(reach: StateReachability, item_id: int, count: int = 1):
            """Helper which updates category counts"""
            reach.prog_counts[item_id] += count
            seen_items = {0}

            def add_items_recursive(item_id: int):
                if item_id in seen_items: return
                seen_items.add(item_id)
                reach.cats_counts[item_id] += count
                for p in self.world.item_model_by_id[item_id].parents:
                    add_items_recursive(p)

            add_items_recursive(item_id)

        ## Used to track progress during/after graph traversal
        self.global_reachability = StateReachability()
        for k, v in self.start_inventory_results.items():
            update_item_count(self.global_reachability, k, v)
        self.state_reachability = dict()
        new_states: List[FrozenSet[int]] = [frozenset()]

        ## Location lookup for optimization's sake
        locations_by_region: Dict[int, List[RealLocationTagModel]] = defaultdict(list)
        for loc in self.world.gen_model.locations:
            if loc.value is not None:
                loc: RealLocationTagModel
                for r in loc.value.owning_regions:
                    locations_by_region[r].append(loc)

        ## Collecting a list of floating items
        grouped_floating_items: List[List[int]] = [[], [], []]
        for fi in self.world.gen_model.floating_items:
            is_randomized = True \
                            and fi.region in enabled_regions \
                            and GTFOWorld.tag_matches(fi.item, self.item_whitelist, self.world.item_model_by_id) \
                            and not GTFOWorld.tag_matches(fi.item, self.item_blacklist, self.world.item_model_by_id)
            if is_randomized:
                item = self.world.item_model_by_id[fi.item]
                assert item.value is not None, "Floating item contains id pointing to null item!"
                if item.value.is_progression:
                    grouped_floating_items[0].append(item.id)
                elif item.value.is_useful:
                    grouped_floating_items[1].append(item.id)
                else:
                    grouped_floating_items[2].append(item.id)

        ## For the traversal, we simply assume we can reach all the floating items (somewhere)
        self.global_reachability.item_counts.update(i for items in grouped_floating_items for i in items)
        for i in grouped_floating_items[0]:
            update_item_count(self.global_reachability, i)

        def discover_region(reach: StateReachability, region: int, is_global: bool = False):
            """Helper which updates reachability for a region in a particular state"""
            if region in reach.reachable_regions: return
            reach.reachable_regions.add(region)
            reach.blocked_paths.extend(p.id for p in self.world.region_to_paths[region])
            if not is_global:
                discover_region(self.global_reachability, region, True)

            for loc_model in locations_by_region[region]:
                if not all(r in reach.reachable_regions for r in loc_model.value.owning_regions): continue
                if loc_model.id in reach.reachable_locations: continue  ## Should never trigger

                loc_is_global = (loc_model.id in enabled_locations)
                loc_is_progression = False
                if not loc_model.value.is_empty:
                    assert loc_model.value.item_id != 0, f"Non-empty location {loc_model.id} has item id of 0"
                    item_model = self.world.item_model_by_id[loc_model.value.item_id]
                    assert item_model.value is not None
                    loc_is_global = loc_is_global or item_model.value.is_randomlike
                    loc_is_progression = item_model.value.is_progression

                if loc_is_global == is_global:
                    reach.reachable_locations.add(loc_model.id)
                    reach.item_counts[loc_model.value.item_id] += 1
                    if loc_is_progression:
                        update_item_count(reach, loc_model.value.item_id)

        ## Graph traversal!
        made_progress: bool = True  ## Set to true whenever a path is traversed
        while made_progress:
            made_progress = False

            for state in new_states:
                ## Initialize new states
                reach = self.state_reachability[state] = StateReachability()
                for req in (r for p in state for r in self.world.path_model_by_id[p].reqs if r.is_consume):
                    update_item_count(reach, req.target, -req.count)
                discover_region(reach, self.world.menu_region_id)
            new_states.clear()

            for choice, reach in self.state_reachability.items():
                path_idx = 0
                while path_idx < len(reach.blocked_paths):
                    path_id = reach.blocked_paths[path_idx]
                    path = self.world.path_model_by_id[path_id]

                    ## Checking if the path is relevant to this playthrough
                    if path.ending_region not in enabled_regions:
                        reach.blocked_paths.pop(path_idx)
                        continue

                    ## Check traversability
                    is_traversable: bool = True
                    for i, req in enumerate(path.reqs):
                        if req.is_consume and path_id in choice:
                            continue  ## We've already paid to cross this path
                        count: int = req.count
                        if req.is_growing:
                            count = self.growth_reqs[path_id][i]
                        has: int
                        if not req.is_category:
                            has = reach.prog_counts[req.target] + self.global_reachability.prog_counts[req.target]
                        else:
                            has = reach.cats_counts[req.target] + self.global_reachability.cats_counts[req.target]
                        is_traversable = is_traversable and (has >= count)

                    if not is_traversable:
                        path_idx += 1
                        continue
                    reach.blocked_paths.pop(path_idx)
                    made_progress = True

                    ## Check if traversal constitutes a state change
                    if any(r.is_consume for r in path.reqs) and not path_id in choice:
                        new_choice = frozenset((path_id, *choice))
                        if new_choice in self.world.choice_lookup:
                            new_states.append(new_choice)

                    ## Check if this region is relevant to the current choice
                    elif path.ending_region in self.world.choice_lookup[choice].get_regions():
                        discover_region(reach, path.ending_region)

        ## Cleaning up unused lists - This makes debugging easier too, as typos throw errors :)
        del self.global_reachability.prog_counts
        del self.global_reachability.cats_counts
        del self.global_reachability.blocked_paths
        for reach in self.state_reachability.values():
            del reach.item_counts
            del reach.prog_counts
            del reach.cats_counts
            del reach.blocked_paths

        ## All the code below is unnecessary for options spoofing.
        ## As such, if there is no world consuming this result, we early exit.
        ## (This also avoids a few errors in UT)
        if world_instance is None:
            return

        ## Used during location sampling to prioritize important empty locations
        priority_locations = set(
            tag_sampler.sample(
                self.global_reachability.reachable_locations,
                itertools.chain(self.gtfo_priority_locations.items(), ((k, -1) for k in self.arch_priority_locations)),
                self.world.location_model_by_id,
                False,
                GTFOPriorityLocations.display_name
            ).keys()
        )
        exclude_locations = set(
            tag_sampler.sample(
                self.global_reachability.reachable_locations,
                itertools.chain(self.gtfo_exclude_locations.items(), ((k, -1) for k in self.arch_exclude_locations)),
                self.world.location_model_by_id,
                False,
                GTFOExcludeLocations.display_name
            ).keys()
        )

        ## Pushing those results to the options
        self.priority_locations = PriorityLocations({
            self.world.location_model_by_id[l].name for l in priority_locations
        })
        self.exclude_locations = ExcludeLocations({
            self.world.location_model_by_id[l].name for l in exclude_locations
        })

        ## Grouping empty locations by priority
        grouped_empty_locations: List[List[RealLocationTagModel]] = [[], [], []]
        empty_locations = (
            loc for l in self.global_reachability.reachable_locations \
            if (loc := self.world.location_model_by_id[l]).value is not None and loc.value.is_empty
        )
        for loc in empty_locations:
            loc: RealLocationTagModel
            cat: int
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

        ## Cash in the vouchers
        self.start_voucher_results = tag_sampler.sample(
            self.global_reachability.item_counts.keys(),
            self.start_vouchers.items(),
            self.world.item_model_by_id,
            False,
            StartVouchers.display_name,
            repeats=self.global_reachability.item_counts.values()
        )
        self.global_reachability.item_counts -= self.start_voucher_results
        voucher_results = Counter(self.start_voucher_results) ## Mutable copy

        ## Remove relevant items from our floating distribution, if possible
        for sublist in grouped_floating_items:
            for j in reversed(range(len(sublist))):
                item = sublist[j]
                if voucher_results[item] > 0:
                    voucher_results[item] -= 1
                    sublist.pop(j)

        ## For remaining items, find in the world and move the location to the empty list
        high_priority_group = list()
        grouped_empty_locations.insert(0, high_priority_group)
        for l in self.global_reachability.reachable_locations:
            loc = self.world.location_model_by_id[l]
            assert loc.value is not None
            if voucher_results[loc.value.item_id] > 0:
                high_priority_group.append(loc)
                voucher_results[loc.value.item_id] -= 1

        ## In theory, this is impossible, but better safe than sorry
        assert all(v == 0 for v in voucher_results.values()), "Failed to find all requested voucher items!"
        del voucher_results

        ## We need to ensure emptied locations are filled, so we create Empty items if necessary
        empty_count = len(high_priority_group) - sum(len(g) for g in grouped_floating_items)
        if empty_count > 0:
            grouped_floating_items[-1] += (self.world.empty_item.id for _ in range(empty_count))
            self.global_reachability.item_counts[self.world.empty_item.id] += empty_count

        ## Distributing them all!
        queued_locations: List[RealLocationTagModel] = grouped_empty_locations.pop(0)
        queued_items: List[int] = grouped_floating_items.pop(0)

        ## Fill the empty locations!
        if not generation_is_fake:
            self.filled_empty_locations = dict()
            while True:
                while not queued_locations and grouped_empty_locations:
                    queued_locations.extend(grouped_empty_locations.pop(0))
                while not queued_items and grouped_floating_items:
                    queued_items.extend(grouped_floating_items.pop(0))

                count = min(len(queued_locations), len(queued_items))
                if count == 0:
                    if self.fail_if_insufficient_empty_locations and queued_items and not queued_locations:
                        raise Exception(f"Insufficient empty locations! {len(queued_items)} floating items unplaced!")
                    elif queued_items and not generation_is_fake:
                        self.start_voucher_results += queued_items
                    break

                locs = self.random.sample(range(len(queued_locations)), count)
                items = self.random.sample(range(len(queued_items)), count)

                for l, i in zip(locs, items):
                    loc = queued_locations[l]
                    item = queued_items[i]
                    if loc.value.is_empty:  ## Because we mix in some non-empty locations during voucher claims
                        self.filled_empty_locations[loc.id] = item

                for l in sorted(locs, reverse=True): queued_locations.pop(l)
                for i in sorted(items, reverse=True): queued_items.pop(i)

        ## Calculating goal items
        if not generation_is_fake:
            self.goal_item_results = tag_sampler.sample(
                self.global_reachability.item_counts.keys(),
                self.goal_items.items(),
                self.world.item_model_by_id,
                False,
                GoalItems.display_name,
                self.global_reachability.item_counts.values()
            )

        total = self.goal_item_results.total()
        if total <= 0:
            self.logger.error("No goal items found for world!")
            raise Exception("No goal items found for world!")

        return

    def spoof(self):
        """Overwrite the base class's options to include our custom implementation's results"""

        ## Tag sampler for tag sampling!
        self.random.seed(self.root_seed)
        tag_sampler = TagSampler(None, self.random, False)

        sample = tag_sampler.sample(
            self.global_reachability.item_counts.keys(),
            self.gtfo_local_items.items(),
            self.world.item_model_by_id,
            False,
            GTFOLocalItems.display_name,
        )
        self.local_items = LocalItems({
            self.world.item_model_by_id[item].name
            for item in itertools.chain(sample.keys(), self.arch_local_items)
        })

        sample = tag_sampler.sample(
            self.global_reachability.item_counts.keys(),
            self.gtfo_non_local_items.items(),
            self.world.item_model_by_id,
            False,
            GTFONonLocalItems.display_name,
        )
        self.non_local_items = NonLocalItems({
            self.world.item_model_by_id[item].name
            for item in itertools.chain(sample.keys(), self.arch_non_local_items)
        })

        self.start_inventory = StartInventory(dict()) ## We will manually push items in create_regions

        sample = tag_sampler.sample(
            self.global_reachability.item_counts.keys(),
            self.gtfo_item_hints.items(),
            self.world.item_model_by_id,
            False,
            GTFOItemHints.display_name,
        )
        self.start_hints = StartHints({
            self.world.item_model_by_id[item].name
            for item in itertools.chain(sample.keys(), self.arch_item_hints)
        })

        sample = tag_sampler.sample(
            self.global_reachability.reachable_locations,
            self.gtfo_location_hints.items(),
            self.world.location_model_by_id,
            False,
            GTFOLocationHints.display_name,
        )
        self.start_location_hints = StartLocationHints({
            self.world.location_model_by_id[item].name
            for item in itertools.chain(sample.keys(), self.arch_location_hints)
        })

        ## priority_locations is set in evaluate
        ## exclude_locations is set in evaluate
        ## item_links is not handled
        ## plando is not handled

        return

gtfo_option_grouping: Dict[str, List[Tuple[List[int], Type[Option]]]] = {
    "Game Options": [
        ([0], RootSeed),
        ([0], FailIfInsufficientEmptyLocations),
        ([0], FailDuringSampling),
    ],
    "Goal": [
        ([0], SkippableGoalCount),
    ],
    "GTFO Item & Location Options (Advanced)": [
        ([0], RegionWhitelist),
        ([0], RegionBlacklist),
        ([0], LocationWhitelist),
        ([0], LocationBlacklist),
        ([0], ItemWhitelist),
        ([0], ItemBlacklist),
        ([0], GoalItems),
        ([0], GTFOStartInventory),
        ([0], StartVouchers),
        ([0], EarlyItems),
        ([0], GTFOLocalItems),
        ([0], GTFONonLocalItems),
        ([0], GTFOItemHints),
        ([0], GTFOLocationHints),
        ([0], GTFOExcludeLocations),
        ([0], GTFOPriorityLocations),
    ],
}
"""
Maps option group names to the actual list of options.
This will be used to generate the actual list of options stored as a 
class variable in the generated web world.
The mapping is `{ category_name: [ (sort_key, option), ... ] }`
"""
