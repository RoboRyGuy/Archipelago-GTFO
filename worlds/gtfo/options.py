from __future__ import annotations

import random
from typing import Any, Collection, Dict, List, Optional, Set, Tuple, Type, TYPE_CHECKING

from Options import  Accessibility, DefaultOnToggle, ExcludeLocations, StartHints, ItemLinks, LocalItems, \
    StartLocationHints, NonLocalItems, NumericOption, Option, OptionCounter, OptionSet, PlandoItems, \
    PriorityLocations, ProgressionBalancing, Range, StartInventory
from .model import OptionSetTarget, OptionDictTarget

if TYPE_CHECKING:
    from .__init__ import GTFOWorld

class OptionsEvaluator:
    """Wraps and supports option evaluation"""

    def __init__(self, parent_world: GTFOWorld):
        self.parent_world = parent_world
        self.option_results = dict()

    parent_world: GTFOWorld
    """The world options are being evaluated for"""
    option_results: Dict[int, Optional[Collection[int]]]
    """Option results. Key is option ID; value is None if mid-evaluation, else the resulting value"""

    def get_output(self, option_id: int) -> Collection[int]:
        """Evaluate an option and get its resulting value"""
        if not id in self.option_results:
            self.option_results[option_id] = None
            self.option_results[option_id] = self.parent_world.option_model_by_id[option_id].evaluate(self)
        value = self.option_results[option_id]
        if value is None:
            raise Exception(f"Circular dependency detected in option evaluation for option id {option_id}")
        return value

    def get_set_target(self, target: OptionSetTarget) -> Set[int]:
        """Get a particular set representing the desired target"""
        match target:
            case "RegionWhitelist":
                return self.parent_world.region_whitelist
            case "RegionBlacklist":
                return self.parent_world.region_blacklist
            case "LocationWhitelist":
                return self.parent_world.location_whitelist
            case "LocationBlacklist":
                return self.parent_world.location_blacklist
            case "ItemWhitelist":
                return self.parent_world.item_whitelist
            case "ItemBlacklist":
                return self.parent_world.item_blacklist
            case _:
                raise NotImplementedError

    def get_dict_target(self, target: OptionDictTarget) -> Dict[int, int]:
        """Get a particular dict representing the desired target"""
        match target:
            case "GoalItems":
                return self.parent_world.goal_items
            case "StartInventory":
                return self.parent_world.start_inventory
            case "StartVouchers":
                return self.parent_world.start_vouchers
            case "EarlyItems":
                return self.parent_world.early_items
            case "LocalItems":
                return self.parent_world.local_items
            case "NonLocalItems":
                return self.parent_world.non_local_items
            case "ItemHints":
                return self.parent_world.item_hints
            case "LocationHints":
                return self.parent_world.location_hints
            case "PriorityLocations":
                return self.parent_world.priority_locations
            case "ExcludeLocations":
                return self.parent_world.exclude_locations
            case _:
                raise NotImplementedError

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


gtfo_option_grouping: Dict[str, List[Tuple[List[int], Type[Option]]]] = {
    "Game Options": [
        ([0], RootSeed),
        ([0], ProgressionBalancing),
        ([0], Accessibility),
        ([0], FailIfInsufficientEmptyLocations),
        ([0], FailDuringSampling),
    ],
    "Goal": [
        ([0], SkippableGoalCount),
    ],
    "": [ ## Item & Location Options are automatically added
        ([0], ItemLinks),
        ([0], PlandoItems),
        ([0], StartInventory),
        ([0], LocalItems),
        ([0], NonLocalItems),
        ([0], StartHints),
        ([0], StartLocationHints),
        ([0], ExcludeLocations),
        ([0], PriorityLocations),
    ],
    "GTFO Item & Location Options": [
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
