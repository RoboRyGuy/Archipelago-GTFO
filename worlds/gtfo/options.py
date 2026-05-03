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
    default = set([ "R1B1", "R1A1", "R8B2", "R1C1", "R8D1", "R8E1"])
    verify_item_name = False
    verify_location_name = False

class RequireSecondaries(Toggle):
    """
    If true, winning requires clearing secondary (as well as main) on all selected expeditions
    """
    display_name = "Require Secondaries"

class RequireOverloads(Toggle):
    """
    If true, winning requires clearing overload (as well as main) on all selected expeditions
    """
    display_name = "Require Overloads"

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

class EarlyItems(OptionList):
    """
    One item from each tag specified in this list will be added to first sphere items.
    """
    display_name = "Early Items"


@dataclass
class GTFOOptions(PerGameCommonOptions):
    """Configuration options for GTFO randomization"""

    required_expeditions: RequiredExpeditions
    require_secondaries: RequireSecondaries
    require_overloads: RequireOverloads
    whitelist: RandomizationWhitelist
    blacklist: RandomizationBlacklist
    early_items: EarlyItems


gtfo_option_groups = [
    OptionGroup("Main Conditions", [
        RequiredExpeditions,
        RequireSecondaries,
        RequireOverloads
    ]),
    OptionGroup("Randomization", [
        RandomizationWhitelist,
        RandomizationBlacklist,
    ]),
]