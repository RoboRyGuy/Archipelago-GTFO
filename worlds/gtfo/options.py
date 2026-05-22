import typing
from typing import Dict, List, Type
from Options import *

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
    The special name \"ALL\" can be used to select all available
     expeditions, though this is not recommended.
    At least one expedition must be specified.
    """
    display_name = "Required Expeditions List"
    rich_text_doc = True

    default = { "R1B1", "R3A2", "R6BX", "R6D2", "R7C1", "R8C2" }

class RandomizationWhitelist(TagSet):
    """
    Items and locations matching tags in this whitelist will attempt to randomize.
    Nothing randomizes by default; it must be whitelisted.
    The other settings you choose may add tags to the whitelist.
    """
    display_name = "Randomization Whitelist"
    default = { "All" }

class RandomizationBlacklist(TagSet):
    """
    Items and locations matching this blacklist will not randomize.
    The Blacklist takes priority over the whitelist
    The other settings you choose may add tags to the blacklist.
    """
    display_name = "Randomization Blacklist"
    rich_text_doc = True
    default = set()

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

class GoalBlacklist(TagSet):
    """
    Items matching the tags in this list will be removed from the goal items list.
    For example, specifying "R4D1 (Secondary) Sector Clear" would allow you to skip
     clearing R4D1's secondary, even if you set secondaries as required.
    """
    display_name = "Goal Blacklist"
    rich_text_doc = True
    default = set()

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
    default = set()

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

@dataclass
class GTFOOptions(CommonOptions):
    """
    Configuration options for GTFO randomization.
    This class is just a base; the actual class used is generated at runtime using
     information from the imported MID file, which adds dynamic options to the subclass.
    """

    ## These will be added in generate_early to satisfy Archipelago's requirements
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
    goal_blacklist: GoalBlacklist
    early_items: EarlyItems


gtfo_option_grouping: Dict[str, List[Type[Option]]] = {
    "Goal": [ RequiredExpeditions ],
    "Advanced": [
        RandomizationWhitelist,
        RandomizationBlacklist,
        GoalBlacklist,
        GTFOLocalItems,
        GTFONonLocalItems,
        GTFOStartInventory,
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
