
from typing import Any, List, Mapping, Optional, Union, Type, TypeVar, get_origin, get_args
from dataclasses import dataclass

from .mid_model import *

"""
Gen model is a __slots__ based model for imported json data.
The prefix `Gen_` is added to classes in this file to prevent naming conflicts.
"""

@dataclass(init=False, slots=True)
class Gen_ExpeditionData():

    name: str
    reachable_regions: List[int]

    def __init__(self, source: Mid_ExpeditionData):
        self.name = source.get_name()
        self.reachable_regions = source.get_reachable_regions()


@dataclass(init=False, slots=True)
class Gen_Tag():

    id: int
    name: str
    description: str
    parent: int

    def __init__(self, source: Mid_Tag):
        self.id = source.get_id()
        self.name = source.get_name()
        self.description = source.get_description()
        self.parent = source.get_parent()


    
@dataclass(init=False, slots=True)
class Gen_Region():

    id: int
    name: str
    
    def __init__(self, source: Mid_Region):
        self.id = source.get_id()
        self.name = source.get_name()

    
@dataclass(init=False, slots=True)
class Gen_ReqItem():

    type: str
    target: int
    
    def __init__(self, source: Mid_ReqItem):
        self.type = source.get_type()
        self.target = source.get_target()

    
@dataclass(init=False, slots=True)
class Gen_Path():

    id: int
    name: Optional[str]
    starting_region: int
    ending_region: int
    req_item: Gen_ReqItem
    req_count: int
    alt_item: Gen_ReqItem

    def __init__(self, source: Mid_Path):
        self.id = source.get_id()
        self.name = source.get_name()
        self.starting_region = source.get_starting_region()
        self.ending_region = source.get_ending_region()
        self.req_item = Gen_ReqItem(source.get_req_item())
        self.req_count = source.get_req_count()
        self.alt_item = Gen_ReqItem(source.get_alt_item())

    
@dataclass(init=False, slots=True)
class Gen_LocationData():

    priority_mode: str
    is_empty: bool

    def __init__(self, source: Mid_LocationData):
        self.priority_mode = source.get_priority_mode()
        self.is_empty = source.get_is_empty()

    
@dataclass(init=False, slots=True)
class Gen_Location():

    id: int
    name_tag: int
    tag2: int
    tag3: int
    rand_data: Gen_LocationData
    item_id: int
    owning_regions: List[int]
    is_randomized: bool = False

    def __init__(self, source: Mid_Location):
        self.id = source.get_id()
        self.name_tag = source.get_name_tag()
        self.tag2 = source.get_tag2()
        self.tag3 = source.get_tag3()
        self.rand_data = Gen_LocationData(source.get_rand_data())
        self.item_id = source.get_item_id()
        self.owning_regions = source.get_owning_regions()
        self.is_randomized = False

    
@dataclass(init=False, slots=True)
class Gen_ItemData():

    is_progression: bool
    is_useful: bool
    is_filler: bool
    is_trap: bool
    do_skip_balancing: bool
    is_deprioritized: bool
    collected_by_default: bool

    def __init__(self, source: Mid_ItemData):
        self.is_progression = source.get_is_progression()
        self.is_useful = source.get_is_useful()
        self.is_filler = source.get_is_filler()
        self.is_trap = source.get_is_trap()
        self.do_skip_balancing = source.get_do_skip_balancing()
        self.is_deprioritized = source.get_is_deprioritized()
        self.collected_by_default = source.get_collected_by_default()

    
@dataclass(init=False, slots=True)
class Gen_Item():

    id: int
    name_tag: int
    tag2: int
    tag3: int
    rand_data: Gen_ItemData
    path_reqs: Gen_ReqItem
    required_expedition: Optional[str]
    is_randomized: bool

    def __init__(self, source: Mid_Item):
        self.id = source.get_id()
        self.name_tag = source.get_name_tag()
        self.tag2 = source.get_tag2()
        self.tag3 = source.get_tag3()
        self.rand_data = Gen_ItemData(source.get_rand_data())
        self.path_reqs = Gen_ReqItem(source.get_path_reqs())
        self.required_expedition = source.get_required_expedition()
        self.is_randomized = False

    
@dataclass(init=False, slots=True)
class Gen_GameData():

    expeditions: List[Gen_ExpeditionData]
    tags: List[Gen_Tag]
    regions: List[Gen_Region]
    paths: List[Gen_Path]
    locations: List[Gen_Location]
    items: List[Gen_Item]
    floating_items: List[int]

    def __init__(self, source: Mid_GameData):
        self.expeditions    = [ Gen_ExpeditionData(x) for x in source.get_expeditions() ]
        self.tags           = [ Gen_Tag(x)            for x in source.get_tags() ]
        self.regions        = [ Gen_Region(x)         for x in source.get_regions() ]
        self.paths          = [ Gen_Path(x)           for x in source.get_paths() ]
        self.locations      = [ Gen_Location(x)       for x in source.get_locations() ]
        self.items          = [ Gen_Item(x)           for x in source.get_items() ]
        self.floating_items = source.get_floating_items() 
