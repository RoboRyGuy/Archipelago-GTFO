from __future__ import annotations

from typing import Dict, List, Literal, Set, Type
from Options import *
from .model import OptionBaseModel, OptionEffectTargets
from . import __init__ as gtfo_world

## GTFO Game Options

class TagSet(OptionSet):
    """
    Base class for options which accept a set of tags
    """

class TagCounter(OptionCounter):
    """
    Base class for options which accept a dict of tags
    """

class RequiredExpeditions(OptionSet):
    """
    The expeditions to use for randomization, specified by name.
    The special name \"ALL\" can be used to select all available expeditions, though
    this is not recommended.
    At least one expedition must be specified.
    """
    display_name = "Required Expeditions List"
    rich_text_doc = True

    default = { "R1B1", "R3A2", "R6BX", "R6D2", "R7C1", "R8C2" }

class RandomizationWhitelist(TagSet):
    """
    For each (item, location) pair: If one or both match the whitelist, and neither
    match the blacklist, the pair is randomized.
    This set is the whitelist; you may specify parent tags to enable a large swath of
    items or locations, or child tags to precisely enable individual entity pairings.
    """
    display_name = "Randomization Whitelist"
    default = { "All" }

class RandomizationBlacklist(TagSet):
    """
    For each (item, location) pair: If one or both match the whitelist, and neither
    match the blacklist, the pair is randomized.
    This set is the blacklist; you may specify parent tags to block a large swath of
    items or locations, or child tags to precisely block individual entity pairings.
    """
    display_name = "Randomization Blacklist"
    rich_text_doc = True
    default = set()

class StartVouchers(TagCounter):
    """
    Start vouchers, specified as a list of tags. During randomization, one
    item per requested voucher will be removed from the item pool and placed
    in the starting inventory. If you use a tag which is a parent of multiple
    items, one random applicable item is selected per request. If duplicate
    items exist in the item pool, they are equally likely to be selected, but
    no more that the quantity of items in the pool can be selected.

    This differs from Start Inventory in that it will never create new items,
    it can only move randomized items out of the pool and into the starting inventory.
    """
    display_name = "Start Vouchers"
    rich_text_doc = True
    default = dict()

class EarlyItems(TagCounter):
    """
    Items matching tags in this list will be added to the first sphere.
    If a parent tag is specified, the requested quantity of children will
    be randomly selected from the random items pool for randomization.
    For example, you may specify `"Expedition Unlock Items": 1` to choose
    one random available expedition unlock to be an early item.
    This will only work on items which both exist and are randomized.
    The special value "-1" will randomize all matching child tags.
    """
    display_name = "Early Items"
    rich_text_doc = True
    default = dict()

class GoalBlacklist(TagCounter):
    """
    The specified count of items matching the provided tag are removed from the goal list.
    For example, specifying `"R4D1 (Secondary) Sector Clear": 1` would allow you to skip
    clearing R4D1's secondary, even if you set secondaries as required.
    If the count is `-1`, all matching tags are removed. For example, specifying
    `"Main Sector Clear": -1` would allow you to skip all main sector clears.
    """
    display_name = "Goal Blacklist"
    rich_text_doc = True
    default = dict()

class SkippableGoalCount(Range):
    """
    The number of goal items which can be skipped. For example, specifying `3` would allow
    you to skip any 3 goal items. In vanilla, this is equivalent to allowing you to skip any
    3 sector clears.
    """
    display_name = "Skippable Goal Count"
    rich_text_doc = True
    default = 0
    range_start = 0
    range_end = 99

class GTFOLocalItems(TagSet):
    """
    All items matching tags in this list will be forced to stay in their native world.
    """
    display_name = "Local Items"
    rich_text_doc = True
    default = set()

class GTFONonLocalItems(TagSet):
    """
    All items matching tags in this list will be forced outside their native world.
    """
    display_name = "Non-Local Items"
    rich_text_doc = True
    default = set()

class GTFOStartInventory(TagCounter):
    """
    Start inventory, specified as a list of tags. A copy of each requested
    item will be placed in the player's starting inventory. If you use a
    tag which is a parent of multiple items, one random applicable item
    is selected per request with an aversion to duplicates.

    This differs from Start Vouchers in that it creates new items and does
    not care if items are randomized; if it is in this list, it will be in
    your start inventory.
    """
    display_name = "Start Inventory"
    rich_text_doc = True
    default = dict()

class GTFOStartHints(TagCounter):
    """
    Items and locations matching tags in this counter will be hinted at the start.
    For each tag, if it has multiple children, the requested number of the children
    will be randomly hinted.
    Alternatively, you may also specify "-1" to hint everything matching the tags.
    """
    display_name = "Start Hints"
    rich_text_doc = True
    default = dict()

class GTFOExcludeLocations(TagSet):
    """
    Locations matching the tags in this list will be marked as "excluded", preventing
    progression items from being placed on those locations.
    """
    display_name = "Excluded Locations"
    rich_text_doc = True

class GTFOPriorityLocations(TagSet):
    """
    Locations matching the tags in this list will be marked as "priority", forcing
    progression items to be placed there if at all possible.
    """
    display_name = "Priority Locations"
    rich_text_doc = True

class FailIfInsufficientEmptyLocations(DefaultOnToggle):
    """
    If true, when randomizing, if there is an insufficient number of empty locations,
    immediately fail; this is useful to ensure the game randomizes as intended.
    Disable this only if generation fails and you don't want to change your settings.
    """
    display_name = "Fail If Insufficient Empty Locations"
    rich_text_doc = True

@dataclass
class GTFOOptions(CommonOptions):
    """
    Configuration options for GTFO randomization.
    This class is just a base; the actual class used is generated at runtime using
    information from the imported MID file, which adds dynamic options to the subclass.
    """

    ## These will be added at generate time because Archipelago is hardcoded to look for them
    #local_items: LocalItems
    #non_local_items: NonLocalItems
    #start_inventory: StartInventory
    #start_hints: StartHints
    #start_location_hints: StartLocationHints
    #exclude_locations: ExcludeLocations
    #priority_locations: PriorityLocations
    #item_links: ItemLinks
    #plando_items: PlandoItems

    ## Custom implementation(s) of the above options
    gtfo_local_items: GTFOLocalItems
    gtfo_non_local_items: GTFONonLocalItems
    gtfo_start_inventory: GTFOStartInventory
    gtfo_start_hints: GTFOStartHints
    gtfo_exclude_locations: GTFOExcludeLocations
    gtfo_priority_locations: GTFOPriorityLocations

    ## I don't know how these work super well, so I'm holding off on customizing them
    gtfo_item_links: ItemLinks     ## TODO
    gtfo_plando_items: PlandoItems ## TODO

    ## Base configuration options / settings required for GTFO to work
    required_expeditions: RequiredExpeditions
    whitelist: RandomizationWhitelist
    blacklist: RandomizationBlacklist
    start_vouchers: StartVouchers
    early_items: EarlyItems
    goal_blacklist: GoalBlacklist
    skippable_goal_count: SkippableGoalCount
    fail_if_insufficient_empty_locations: FailIfInsufficientEmptyLocations


gtfo_option_grouping: Dict[str, List[Type[Option]]] = {
    "Goal": [
        RequiredExpeditions,
        SkippableGoalCount
    ],
    "Miscellaneous Options": [
        FailIfInsufficientEmptyLocations
    ],
    "Advanced": [
        RandomizationWhitelist,
        RandomizationBlacklist,
        GoalBlacklist,
        GTFOLocalItems,
        GTFONonLocalItems,
        GTFOStartInventory,
        StartVouchers,
        GTFOStartHints,
        GTFOExcludeLocations,
        GTFOPriorityLocations,
    ]
}
"""
Maps option group names to the actual list of options.
This will be used to generate the actual list of options stored as a 
class variable in the generated GTFO world.
"""

class OptionEvaluationState:
    """Used during option evaluation to track progress and such"""
    world: gtfo_world.GTFOWorld
    """The world being currently evaluated"""
    evaluated_ids: Set[int]
    """IDs which are fully evaluated"""
    started_ids: Set[int]
    """IDs which have started evaluating, used to check for loops"""

    ## Targets which aren't contained in the world and only exist during option setup
    not_found_tags: Dict[str, List[str]]
    local_items: Set[int] = set()
    non_local_items: Set[int] = set()
    start_inventory: Dict[int, int] = dict()
    start_hints: Dict[int, int] = dict()

    def evaluate(self, option: OptionBaseModel):
        """Evaluate a particular option. This forces re-evaluation of the option, but not its dependencies"""
        if option.id in self.started_ids:
            raise Exception(f"Detected loop during option evaluation of option: {option.id}")
        self.started_ids.add(option.id)
        option.evaluate(self)
        self.evaluated_ids.add(option.id)

    def get_output(self, option_id: int) -> float:
        """Get the output from an option. Evaluate it if needed"""
        option = self.world.option_model_by_id.get(option_id)
        if option is None:
            raise Exception(f"Cannot evaluate option with id {option_id}: Targeted option does not exist!")
        if option_id not in self.evaluated_ids:
            self.evaluate(option)
        return option.output

    def get_target(self, target: OptionEffectTargets):
        """Get a specific target from the list of known targets"""
        match target:
            case "Whitelist":
                return self.world.whitelist_tags
            case "Blacklist":
                return self.world.blacklist_tags
            case "StartInventory":
                return self.start_inventory
            case "StartVouchers":
                return self.world.start_vouchers
            case "EarlyItems":
                return self.world.early_items
            case "LocalItems":
                return self.local_items
            case "NonLocalItems":
                return self.non_local_items
            case "StartHints":
                return self.start_hints
            case "CustomExcludeLocations":
                return self.world.exclude_locations
            case "CustomPriorityLocations":
                return self.world.priority_locations
            case "GoalBlacklist":
                return self.world.goal_blacklist
            case _:
                raise NotImplementedError
