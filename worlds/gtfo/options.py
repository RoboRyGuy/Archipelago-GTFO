from dataclasses import dataclass
import json
from typing import Any, Dict

from Options import Choice, DeathLink, DefaultOnToggle, ExcludeLocations, NamedRange, OptionDict, \
    OptionGroup, PerGameCommonOptions, Range, Removed, Toggle, ItemSet

## Game Options

gtfo_big_number = 99999
"""An arbitrarily large value"""

class RequiredExpeditions(ItemSet):
    """
    The expeditions required for completion. Up to four of each tier.
    All other expeditions will be removed from the game.
    Items and locations will randomize only into the expeditions listed here.
    Use the name as found in the level's description (before pressing "Host Lobby")
    """
    default = set([ "R1A1", "R1B1", "R8B2", "R1C1", "R8D1", "R8E1"])

class RequireAllObjectives(Toggle):
    """
    If true, the goal is to complete main, secondary, overload, and PE on all expeditions listed in 
    required_expeditions.
    If false, you only need to complete main on all listed expeditions.
    """

class LockExpeditions(DefaultOnToggle):
    """
    Start with all levels locked except for the first one listed in required_expeditions.
    The level unlocks will be added as items to the multiworld.
    """

class LockGear(DefaultOnToggle):
    """
    Start with all gear locked.
    Gear unlocks will be added as items to the multiworld.
    Make sure to add entries to starting_gear to allow progression.
    """

class StartingGear(ItemSet):
    """
    Gear that will start unlocked. Only valid if lock_gear is enabled.
    The name of the gear is the weapon's make and model name, case insensitive.
    For example, the "Pistol" is "Shelling S49", or "shelling s49", or "SHELLING S49".
    The default list is a bat, the burst pistol, the short rifle, and the bio tracker.
    """
    default = set(["Kovac Peacekeeper", "Shelling Nano", "Drekker CLR", "D-Tek Optron IV"])

class LockPlayerSlots(NamedRange):
    """
    Lock some or all of the lobby slots, preventing bots and humans from joining.
    Any number higher than the max (3 by default, 7 when using LobbyExapansion) will act as additional filler unlocks.
    """
    range_start = 0
    range_end = gtfo_big_number
    special_range_names = {
        "None": 0,
        "False": 0,
        "True": 7,
    }
    default = 0

class FillerCount(Range):
    """
    How many filler items to add. The more the merrier!
    """
    range_start = 0
    range_end = gtfo_big_number
    default = 100

class TrapPercent(NamedRange):
    """
    The percentage of filler items which will be traps.
    """
    range_start = 0
    range_end = 1
    special_range_names = {
        "None": 0,
        "False": 0,
        "True": 1,
    }
    default = 0.5

class TrapWeight(Range):
    """
    Used when generating traps to determine how bad the traps are.
    Higher values result in dangerous traps being more common.
    Lower values result in less dangerous traps being more common.
    """
    range_start = 0
    range_end = 1
    special_range_names = {
        "Min": 0,
        "Low": 0.2,
        "Medium": 0.5,
        "High": 0.8,
        "Max": 1,
    }
    default = 0.5


@dataclass
class GTFOOptions(PerGameCommonOptions):
    """Configuration options for GTFO randomization"""

    required_expeditions: RequiredExpeditions
    lock_expeditions: LockExpeditions
    lock_gear: LockGear
    starting_gear: StartingGear
    lock_player_slots: LockPlayerSlots
    filler_count: FillerCount
    trap_precent: TrapPercent
    trap_weight: TrapWeight


gtfo_option_groups = [
    OptionGroup("Expeditions", [
        RequiredExpeditions,
        LockExpeditions
    ]),
    OptionGroup("Gear", [
        LockGear,
        StartingGear,
        LockPlayerSlots,
    ]),
    OptionGroup("Filler", [
        FillerCount,
        TrapPercent,
        TrapWeight,
    ]),
]