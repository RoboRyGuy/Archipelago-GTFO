
from typing import Any, Dict, List, Optional, Mapping, Union

# Basic types
class WeightedItem:
    name: str
    weight: float

    def __init__(self, json: Dict[str, Any]):
        self.name = json["name"]
        self.weight = float(json["weight"])


class ZonePosition:
    local_index: int
    dimension_index: int

    def __init__(self, json: Dict[str, Any]):
        self.local_index = int(json["local_index"])
        self.dimension_index = int(json["dimension_index"])


class KeyData:
    type: str
    zone_alias: int
    terminal_index: int
    positions: List[ZonePosition]

    def __init__(self, json: Dict[str, Any]):
        self.type = str(json["type"])
        self.zone_alias = int(json["zone_alias"])
        self.terminal_index = int(json["terminal_index"])
        self.positions = [ ZonePosition(x) for x in json["positions"] ]


class BigPickupData:
    item_type: int

    def __init__(self, json: Dict[str, Any]):
        self.item_type = int(json["item_type"])


# Event actions
class WardenAction:
    def __init__(self, json: Dict[str, Any]):
        # Base action has no fields by default
        pass


class SpecificZoneEventAction(WardenAction):
    target_zone_local_index: int
    target_zone_layer: int
    target_zone_dimension: int

    def __init__(self, json: Dict[str, Any]):
        self.target_zone_local_index = int(json["target_zone_local_index"])
        self.target_zone_layer = int(json["target_zone_layer"])
        self.target_zone_dimension = int(json["target_zone_dimension"])


class StartScanEventAction(SpecificZoneEventAction):
    scan_name: str

    def __init__(self, json: Dict[str, Any]):
        super().__init__(json)
        self.scan_name = str(json["scan_name"])


class WarpEventAction(WardenAction):
    target_dimension_index: int
    target_zone_local_index: int

    def __init__(self, json: Dict[str, Any]):
        self.target_dimension_index = int(json["target_dimension_index"])
        self.target_zone_local_index = int(json["target_zone_local_index"])


class ObjectiveEventAction(WardenAction):
    objective_layer: int

    def __init__(self, json: Dict[str, Any]):
        self.objective_layer = int(json["objective_layer"])


# WardenEvent and subclasses
class WardenEvent:
    type: str
    action_data: Optional[WardenAction]

    def __init__(self, json: Dict[str, Any]):
        
        type_mapping = {
            "UnlockZoneDoor":           SpecificZoneEventAction,
            "OpenZoneDoor":             SpecificZoneEventAction,
            "StepObjectiveProgression": ObjectiveEventAction,
            "ForceCompleteObjective":   ObjectiveEventAction,
            "ForceInstantWin":          ObjectiveEventAction,
            "ActivateWinOnDeath":       ObjectiveEventAction,
            "DimensionWarp":            WarpEventAction,
            "StartScan":                StartScanEventAction,
        }
        
        self.type = str(json["type"])
        self.action_data = type_mapping[self.type](json["action_data"])


class ApproachZoneEvent(WardenEvent):
    target_alias: int

    def __init__(self, json: Dict[str, Any]):
        super().__init__(json)
        self.target_alias = int(json["target_alias"])


class TriggerEvent(WardenEvent):
    trigger_name: str

    def __init__(self, json: Dict[str, Any]):
        super().__init__(json)
        self.trigger_name = str(json["trigger_name"])


# Objective data classes
class ObjectiveData:
    objective_type: str
    sub_objective_count: int
    positions: List[List[ZonePosition]]
    events_on_activate: List[List[WardenEvent]]
    events_on_goto_win: List[WardenEvent]

    def __init__(self, json: Dict[str, Any]):
        self.objective_type = str(json["objective_type"])
        self.sub_objective_count = int(json["sub_objective_count"])
        self.positions = [ [ ZonePosition(y) for y in x ] for x in json["positions"] ]
        self.events_on_activate = [ [ WardenEvent(y) for y in x ] for x in json["events_on_activate"] ]
        self.events_on_goto_win = [ WardenEvent(x) for x in json["events_on_goto_win"] ]

    @classmethod
    def make(json: Dict[str, Any]) -> "ObjectiveData":
        t = str(json["objective_type"])
        if t in ["ReactorStartup", "ReactorStartup_Empty"]:
            return ReactorStartupObjectiveData(json)
        elif t == "TimedTerminalSequence":
            return TimedSequenceObjectiveData(json)
        else:
            return ObjectiveData(json)


class ReactorStartupObjectiveData(ObjectiveData):
    wave_count: int
    events_on_finish_wave: List[List[WardenEvent]]

    def __init__(self, json: Dict[str, Any]):
        super().__init__(json)
        self.wave_count = int(json["wave_count"])
        self.events_on_finish_wave = [ [ WardenEvent(y) for y in x ] for x in json["events_on_finish_wave"] ]


class TimedSequenceObjectiveData(ObjectiveData):
    num_rounds: int
    events_on_start_round: List[List[WardenEvent]]
    events_on_succeed_round: List[List[WardenEvent]]
    events_on_fail_round: List[List[WardenEvent]]

    def __init__(self, json: Dict[str, Any]):
        super().__init__(json)
        self.num_rounds = int(json["num_rounds"])
        self.events_on_start_round   = [ [ WardenEvent(y) for y in x ] for x in json["events_on_start_round"] ]
        self.events_on_succeed_round = [ [ WardenEvent(y) for y in x ] for x in json["events_on_succeed_round"] ]
        self.events_on_fail_round    = [ [ WardenEvent(y) for y in x ] for x in json["events_on_fail_round"] ]


class CommandData:
    command_name: str
    events: List[WardenEvent]

    def __init__(self, json: Dict[str, Any]):
        self.command_name = json["command_name"]
        self.events = [ WardenEvent(x) for x in json["events"] ]


class TerminalData:
    passwordCount: int
    commands: List[CommandData]
    logs: List[str]

    def __init__(self, json: Dict[str, Any]):
        self.password_count = int(json["password_count"])
        self.commands = [ CommandData(x) for x in json["commands"] ]
        self.logs = [ str(x) for x in json["logs"] ]


class ZoneData:
    alias: int
    entrance_index: int
    lock_type: str
    terminals: List[TerminalData]
    big_pickups: List[BigPickupData]
    events_on_unlock_door: List[WardenEvent]
    events_on_door_scan_start: List[WardenEvent]
    events_on_door_scan_done: List[WardenEvent]
    events_on_open_door: List[WardenEvent]
    events_on_boss_death: List[WardenEvent]
    events_on_portal_warp: List[WardenEvent]
    events_on_trigger: List['TriggerEvent']
    events_on_approach_zone: List['ApproachZoneEvent']

    def __init__(self, json: Dict[str, Any]):
        self.alias = int(json["alias"])
        self.entrance_index = int(json["entrance_index"])
        self.lock_type = str(json["lock_type"])
        self.terminals = [ TerminalData(x) for x in json["terminals"] ]
        self.big_pickups = [ BigPickupData(x) for x in json["big_pickups"] ]

        self.events_on_unlock_door     = [ [ WardenEvent(x) for x in y ] for y in json["events_on_unlock_door"    ] ]
        self.events_on_door_scan_start = [ [ WardenEvent(x) for x in y ] for y in json["events_on_door_scan_start"] ]
        self.events_on_door_scan_done  = [ [ WardenEvent(x) for x in y ] for y in json["events_on_door_scan_done" ] ]
        self.events_on_open_door       = [ [ WardenEvent(x) for x in y ] for y in json["events_on_open_door"      ] ]
        self.events_on_boss_death      = [ [ WardenEvent(x) for x in y ] for y in json["events_on_boss_death"     ] ]
        self.events_on_portal_warp     = [ [ WardenEvent(x) for x in y ] for y in json["events_on_portal_warp"    ] ]
        self.events_on_trigger         = [ [TriggerEvent(x) for x in y ] for y in json["events_on_trigger"        ] ]
        self.events_on_approach_zone = [ 
            [ ApproachZoneEvent(x) for x in y ] for y in json["events_on_approach_zone"] 
        ]


class LevelData:
    start_zone: int
    zones: List[ZoneData]
    keys: List[KeyData]
    objectives: List[ObjectiveData]
    events_on_approach_level: List[ApproachZoneEvent]

    def __init__(self, json: Dict[str, Any]):
        self.start_zone = int(json["start_zone"])
        self.zones = [ZoneData(x) for x in json["zones"] ]
        self.keys  = [ KeyData(x) for x in json["keys"] ]
        self.objectives = [ ObjectiveData.make(x) for x in json["objectives"] ]
        self.events_on_approach_level = [ ApproachZoneEvent(x) for x in json["events_on_approach_level"] ]


class BuildFromData:
    layer_index: int
    zone_index: int

    def __init__(self, json: Dict[str, Any]):
        self.layer_index = int(json["layer_index"])
        self.zone_index = int(json["zone_index"])


class ExpeditionData:
    name: str
    main_level: LevelData
    secondary_level: Optional[LevelData]
    secondary_build_from: BuildFromData
    overload_level: Optional[LevelData]
    overload_build_from: BuildFromData
    dimension_data: Dict[int, LevelData]
    events_on_elevator_land: List[WardenEvent]
    events_on_progress_exit_scan: List[WardenEvent]

    def __init__(self, json: Dict[str, Any]):
        self.name = str(json["name"])
        self.main_level = LevelData(json["main_level"])
        
        sec_json = json.get("secondary_level")
        self.secondary_level = None if sec_json is None else LevelData(sec_json)
        self.secondary_build_from = BuildFromData(json["secondary_build_from"])

        ovl_json = json.get("overload_level")
        self.overload_level = None if ovl_json is None else LevelData(ovl_json)
        self.overload_build_from = BuildFromData(json["overload_build_from"])

        self.dimension_data = { int(k): LevelData(v) for k, v in json["dimension_data"].items() }
        self.events_on_elevator_land = [ WardenEvent(x) for x in json["events_on_elevator_land"] ]
        self.events_on_progress_exit_scan = [ WardenEvent(x) for x in json["events_on_progress_exit_scan"] ]


class ModdedInstanceData:
    expeditions: List[ExpeditionData]
    gear_names: List[str]
    filler_items: List[WeightedItem]
    trap_items: List[WeightedItem]

    def __init__(self, json: Dict[str, Any]):
        self.expeditions = [ ExpeditionData(x) for x in json["expeditions"] ]
        self.gear_names = [ str(x) for x in json["gear_names"] ]
        self.filler_items = [ WeightedItem(x) for x in json["fillter_items"] ]
        self.trap_items = [ WeightedItem(x) for x in json["trap_items"] ]
