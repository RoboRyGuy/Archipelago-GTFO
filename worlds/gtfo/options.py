from typing import Any, Dict
from Options import *

## GTFO Game Options

class RequiredExpeditions(OptionSet):
    """
    The expeditions to use for randomization, specified by name.
    The special name \"ALL\" can be used to select all available
     expeditions, though this is not recommended.
    At least one expedition must be specified.
    """
    display_name = "Required Expeditions List"
    rich_text_doc = True

    default = {"R1B1", "R3A2", "R6BX", "R6D2", "R7C1", "R8C2"}
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
    default = { "All" }

class RandomizationBlacklist(OptionSet):
    """
    Items and locations matching this blacklist will not randomize.
    Blacklist takes priority over the whitelist
    """
    display_name = "Randomization Blacklist"
    rich_text_doc = True
    default = { "All Scans", "All Warps" }

class EarlyItems(OptionCounter):
    """
    Items matching tags in this list will be added to the first sphere.
    All items matching the tag are candidate; that is, using a parent tag will allow 
     any child (or nested child) item to be added.
    This will only work on items which both exist and are randomized.
    """
    display_name = "Early Items"
    rich_text_doc = True
    default = { "Expedition Unlock Items": 1 }

class GTFOStartInventory(OptionCounter):
    """
    Start inventory, specified as a list of tags. The requested number of
    items matching the named tag will be removed from randomization and added
    to the starting inventory. Relevant items must be randomized to be added.
    """
    display_name = "Start Inventory"
    rich_text_doc = True
    default = {
        "Expedition Unlock Items": 1,
        "Unlock Lobby Slot Items": 1,
        "Melee Gear Items": 1,
        "Primary Gear Items": 1,
        "Special Gear Items": 1,
        "Tool Gear Items": 1
    }


@dataclass
class GTFOOptions(CommonOptions):
    """Configuration options for GTFO randomization"""

    local_items: LocalItems                  ## TODO
    non_local_items: NonLocalItems           ## TODO
    start_inventory: GTFOStartInventory
    start_hints: StartHints                  ## TODO
    start_location_hints: StartLocationHints ## TODO
    exclude_locations: ExcludeLocations      ## TODO
    priority_locations: PriorityLocations    ## TODO
    item_links: ItemLinks                    ## TODO
    plando_items: PlandoItems                ## TODO

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
]