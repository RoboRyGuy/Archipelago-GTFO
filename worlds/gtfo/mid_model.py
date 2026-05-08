
from typing import Any, List, Mapping, Optional, Union, Type, TypeVar, get_origin, get_args

T = TypeVar("T")
"""Type variable used for conversions"""

"""
Mid model is just a lightweight wrapper for dicts so I can readily import json data.
The prefix `MID_` is added to classes in this file to prevent naming conflicts
"""

class LazyObject:
    """Base class which is just a dict with some helper accessors."""
    __slots__ = ( "source" )

    def __init__(self, source: Mapping[str, Any]):
        if not isinstance(source, Mapping):
            raise TypeError(f"LazyObject source must be a Mapping, got {type(source)}")
        self.source = source

    @staticmethod
    def convert(typ: Type[T], value: Any) -> Type[T]:
        """
        Helper to try and convert one value into another
        """
        allow_fail = False
        if get_origin(typ) is Union:
            typ = get_args(typ)[0]
            allow_fail = True

        if typ is Any:
            return value
        elif isinstance(typ, type) and issubclass(typ, LazyObject):
            return typ(value)
        elif allow_fail and value is None:
            return None
        try:
            return typ(value)
        except Exception as exc:
            raise TypeError(
                f"Failed to convert value {value!r} to type {typ}: {exc}"
            ) from exc

    def get_value(self, typ: Type[T], *keys: str) -> Optional[Type[T]]:
        """
        Look up the first matching key in `source`, then convert the value to `typ`.
        Returns None if no key is found.
        """
        for key in keys:
            if key in self.source:
                return LazyObject.convert(typ, self.source[key])
        else:
            raise KeyError(f"Failed to find key(s): {keys}")
            return None

    def get_list(self, typ: Type[T], *keys: str) -> List[Type[T]]:
        """
        Look up the first matching key in `source`, then convert the value to `typ`.
        Returns an empty list if no key is found.
        """
        values = None
        for key in keys:
            if key in self.source:
                values = self.source[key]
                break
        else:
            raise KeyError(f"Failed to find key(s): {keys}")
            return []

        result = []
        for value in values:
            result.append(LazyObject.convert(typ, value))
        return result
    

class Mid_ExpeditionData(LazyObject):
    """Wraps data about a particular expedition"""
    __slots__ = LazyObject.__slots__

    def get_name(self) -> str:
        return self.get_value(str, "Name")

    def get_reachable_regions(self) -> List[int]:
        return self.get_list(int, "ReachableRegions")


class Mid_Tag(LazyObject):
    """Wraps an imported Randomization Tag"""
    __slots__ = LazyObject.__slots__

    def get_id(self) -> int:
        return self.get_value(int, "ID")

    def get_name(self) -> str:
        return self.get_value(str, "Name")

    def get_description(self) -> str:
        return self.get_value(str, "Description")

    def get_parent(self) -> int:
        return self.get_value(int, "Parent")


class Mid_Region(LazyObject):
    """Wraps an imported region"""
    __slots__ = LazyObject.__slots__

    def get_id(self) -> int:
        return self.get_value(int, "ID")

    def get_name(self) -> str:
        return self.get_value(str, "Name")


class Mid_ReqItem(LazyObject):
    """
    Wraps an imported path requirement.
    This represents the item tag that is needed 
     and if it's a category or item tag
    """
    __slots__ = LazyObject.__slots__

    def get_type(self) -> str:
        """Currently one of 'Item', 'Category', or 'None'"""
        return self.get_value(str, "Type")

    def get_target(self) -> int:
        return self.get_value(int, "Target")


class Mid_Path(LazyObject):
    """Wraps an imported path"""
    __slots__ = LazyObject.__slots__

    def get_id(self) -> int:
        return self.get_value(int, "ID")

    def get_name(self) -> Optional[str]:
        return self.get_value(Optional[str], "Name")

    def get_starting_region(self) -> int:
        return self.get_value(int, "StartingRegion")

    def get_ending_region(self) -> int:
        return self.get_value(int, "EndingRegion")

    def get_req_item(self) -> Mid_ReqItem:
        return self.get_value(Mid_ReqItem, "ReqItem")

    def get_req_count(self) -> int:
        return self.get_value(int, "ReqCount")

    def get_alt_item(self) -> Mid_ReqItem:
        return self.get_value(Mid_ReqItem, "AlternateItem")


class Mid_LocationData(LazyObject):
    """Location data, which describes how a location is randomized"""
    __slots__ = LazyObject.__slots__

    def get_priority_mode(self) -> str:
        """Currently one of 'Default', 'Priority', 'Excluded', or 'Trap'"""
        return self.get_value(str, "PriorityMode")


class Mid_Location(LazyObject):
    """Wraps an imported location"""
    __slots__ = LazyObject.__slots__

    def get_id(self) -> int:
        return self.get_value(int, "ID")

    def get_name_tag(self) -> int:
        return self.get_value(int, "NameTag")

    def get_tag2(self) -> int:
        return self.get_value(int, "Tag2")

    def get_tag3(self) -> int:
        return self.get_value(int, "Tag3")

    def get_rand_data(self) -> Mid_LocationData:
        return self.get_value(Mid_LocationData, "RandData")

    def get_item_id(self) -> int:
        return self.get_value(int, "ItemID")

    def get_owning_regions(self) -> List[int]:
        return self.get_list(int, "OwningRegionIds")


class Mid_ItemData(LazyObject):
    """Item data, which describes how an item is randomized"""
    __slots__ = LazyObject.__slots__

    def get_is_progression(self) -> bool:
        return self.get_value(bool, "IsProgression")

    def get_is_useful(self) -> bool:
        return self.get_value(bool, "IsUseful")

    def get_is_filler(self) -> bool:
        return self.get_value(bool, "IsFiller")

    def get_is_trap(self) -> bool:
        return self.get_value(bool, "IsTrap")

    def get_do_skip_balancing(self) -> bool:
        return self.get_value(bool, "DoSkipBalancing")

    def get_is_deprioritized(self) -> bool:
        return self.get_value(bool, "IsDeprioritized")


class Mid_Item(LazyObject):
    """Wraps an imported item"""
    __slots__ = LazyObject.__slots__

    def get_id(self) -> int:
        return self.get_value(int, "ID")

    def get_name_tag(self) -> int:
        return self.get_value(int, "NameTag")

    def get_tag2(self) -> int:
        return self.get_value(int, "Tag2")

    def get_tag3(self) -> int:
        return self.get_value(int, "Tag3")

    def get_rand_data(self) -> Mid_ItemData:
        return self.get_value(Mid_ItemData, "RandData")

    def get_path_reqs(self) -> Mid_ReqItem:
        """
        Which pathing requirements this is meant to fulfill.
        Typically ignored unless the type is 'Category'
        """
        return self.get_value(Mid_ReqItem, "PathReqs")

    def get_required_expedition(self) -> Optional[str]:
        """
        Ties this item to a particular expedition.
        Prevents it from entering the pool unless that expedition is selected.
        """
        return self.get_value(Optional[str], "RequiredExpeditionName")


class Mid_GameData(LazyObject):
    """Wraps all data imported from GTFO"""
    __slots__ = LazyObject.__slots__

    def get_expeditions(self) -> List[Mid_ExpeditionData]: 
        return self.get_list(Mid_ExpeditionData, "Expeditions")
        
    def get_tags(self) -> List[Mid_Tag]:
        return self.get_list(Mid_Tag, "Tags")

    def get_regions(self) -> List[Mid_Region]:
        return self.get_list(Mid_Region, "Regions")

    def get_paths(self) -> List[Mid_Path]:
        return self.get_list(Mid_Path, "Paths")

    def get_locations(self) -> List[Mid_Location]:
        return self.get_list(Mid_Location, "Locations")

    def get_items(self) -> List[Mid_Item]:
        return self.get_list(Mid_Item, "Items")

    def get_floating_items(self) -> List[int]:
        return self.get_list(int, "FloatingItems")
    


