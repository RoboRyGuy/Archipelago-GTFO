from typing import Any, Dict
from Options import *

## GTFO Game Options

class RequiredExpeditions(OptionSet):
    """
    The expeditions to use for randomization, specified by name.
    The special name \"ALL\" can be used to select all available
     expeditions, though this is not recommended.
    The expeditions will be hinted to appear in the order listed.
    At least one expedition must be specified.
    """
    display_name = "Required Expeditions List"
    rich_text_doc = True

    default = set([ "R1B1", "R1A1", "R8B2", "R1C1", "R8D1", "R8E1"])
    verify_item_name = False
    verify_location_name = False

class RequireSecondaries(Toggle):
    """
    If true, winning requires clearing secondary (as well as main) on all selected expeditions
    """
    display_name = "Require Secondaries"
    rich_text_doc = True

class RequireOverloads(Toggle):
    """
    If true, winning requires clearing overload (as well as main) on all selected expeditions
    """
    display_name = "Require Overloads"
    rich_text_doc = True

class RandomizationWhitelist(OptionSet):
    """
    Items and locations matching this whitelist will attempt to randomize.
    Nothing randomizes by default; it must be whitelisted.
    """
    display_name = "Randomization Whitelist"

class RandomizationBlacklist(OptionSet):
    """
    Items and locations matching this blacklist will not randomize.
    Blacklist takes priority over the whitelist
    """
    display_name = "Randomization Blacklist"
    rich_text_doc = True

class GTFOStartItems(OptionCounter):
    """
    Items matching tags in this list will be added to the start inventory.
    All items matching the tag are candidate; that is, using a parent tag will allow 
     any child (or nested child) item to be added.
    This will only work on items which both exist and are randomized.
    """
    display_name = "Start Items"
    rich_text_doc = True


class EarlyItems(OptionCounter):
    """
    Items matching tags in this list will be added to the first sphere.
    All items matching the tag are candidate; that is, using a parent tag will allow 
     any child (or nested child) item to be added.
    This will only work on items which both exist and are randomized.
    """
    display_name = "Early Items"
    rich_text_doc = True


@dataclass
class GTFOOptions(CommonOptions):
    """Configuration options for GTFO randomization"""
    
    local_items: LocalItems
    non_local_items: NonLocalItems
    start_items: GTFOStartItems ## CUSTOM, not default start invetory
    start_hints: StartHints
    start_location_hints: StartLocationHints
    exclude_locations: ExcludeLocations
    priority_locations: PriorityLocations
    item_links: ItemLinks
    plando_items: PlandoItems

    required_expeditions: RequiredExpeditions
    require_secondaries: RequireSecondaries
    require_overloads: RequireOverloads
    whitelist: RandomizationWhitelist
    blacklist: RandomizationBlacklist
    early_items: EarlyItems

gtfo_option_groups = [
    OptionGroup("Goal Conditions", [
        RequiredExpeditions,
        RequireSecondaries,
        RequireOverloads
    ]),
    OptionGroup("Randomization", [
        RandomizationWhitelist,
        RandomizationBlacklist,
    ]),
    OptionGroup("Common Options", [
        LocalItems,         ## Need to customize this to use tags
        NonLocalItems,      ## Need to customize this to use tags
        GTFOStartItems,     
        StartHints,         ## Need to customize this to use tags
        StartLocationHints, ## Need to customize this to use tags
        ExcludeLocations,   ## Need to customize this to use tags
        PriorityLocations,  ## Need to customize this to use tags
        ItemLinks,          ## Need to customize this to use tags
        PlandoItems,        ## Need to customize this to use tags
    ])
]