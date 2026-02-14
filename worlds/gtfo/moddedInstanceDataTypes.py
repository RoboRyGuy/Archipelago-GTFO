
import numbers
from typing import Any, List, Mapping, Optional, Tuple

class Region:
    """Represents a region"""

    def __init__(self, data: Mapping[str, Any]):
        """Create a Region from json"""
        
        if not isinstance(data, dict):
            raise TypeError("Location expects a dict")

        self.name = data.get("name")
        if not isinstance(self.name, str):
            raise TypeError("'Region.name' must be a string")

    name: str
    """Unique name of the region, used to identify it"""


class Location:
    """Represents a location where an item may be found. Includes the item normally found there"""

    def __init__(self, data: Mapping[str, Any]):
        """Create a Location from json"""

        if not isinstance(data, dict):
            raise TypeError("Location expects a dict")

        self.name = str(data.get("name"))
        if not isinstance(self.name, str):
            raise TypeError("'Location.name' must be a string")
        
        self.item = str(data.get("item"))
        if not isinstance(self.item, str):
            raise TypeError("'Location.item' must be a string")

        raw_regions = data.get("regions")
        if not isinstance(self.item, list):
            raise TypeError("'Location.regions' must be a list")

        self.regions = [ int(r) if isinstance(r, numbers.Number) else None for r in raw_regions ]
        if None in self.regions:
            raise TypeError("'Location.regions' must be a list of numbers")

    name: str
    """Unique name of the location, used to identify it"""

    item: str
    """Item typically located in this location"""

    regions: List[int]
    """Regions this location can be in"""


class Path:
    """
    Represents a directed path between regions. Entrances in each region are implied.
    """

    def __init__(self, data: Mapping[str, Any]):
        """Create a Path from json"""

        if not isinstance(data, dict):
            raise TypeError("Path expects a dict")

        self.starting_region = data.get("starting_region")
        if isinstance(self.starting_region, numbers.Number):
            self.starting_region = int(self.starting_region)
        else:
            raise TypeError("'Path.starting_region' is incorrectly defined")

        self.ending_region = int(data.get("ending_region", 0))
        if isinstance(self.ending_region, numbers.Number):
            self.ending_region = int(self.ending_region)
        else:
            raise TypeError("'Path.ending_region' is incorrectly defined")

        self.required_item = data.get("required_item")
        if self.required_item is not None and not isinstance(self.required_item, str):
            raise TypeError("'Path.required_item' must be a string or null")

        self.required_item_count = data.get("required_item_count")
        if isinstance(self.required_item_count, numbers.Number):
            self.required_item_count = int(self.required_item_count)
        else:
            raise TypeError("'Path.required_item_count' is incorrectly defined")

        self.alternate_item =  data.get("alternate_item")
        if self.alternate_item is not None and not isinstance(self.alternate_item, str):
            raise TypeError("'Path.alternate_item' must be a string or null")

    """Region this path starts in"""
    starting_region: int
    
    """Region this path ends in"""
    ending_region: int
    
    """Item required to traverse this path"""
    required_item: Optional[str]
    
    """Number of required items needed to traverse this path"""
    required_item_count: int

    """
    Alternate item required to traverse this path
    - If there is no required item, this is ignored (by design)
    - The alternate item is assumed to only require one count to traverse the path
    - This is intended for door unlock events (since all zone doors can be force unlocked via an event)
    """
    alternate_item: Optional[str]


class WeightedItem:
    """Associates an item with a weight for randomization purposes"""
    
    def __init__(self, data: Mapping[str, Any]):
        """Creates a WeightedItem from json"""

        if not isinstance(data, dict):
            raise TypeError("Expedition expects a dict")

        self.name = data.get("name")
        if not isinstance(self.name, str):
            raise TypeError("'WeightedItem.name' must be a string")

        self.weight = data.get("weight")
        if isinstance(self.weight, numbers.Number):
            self.weight = float(self.weight)
        else:
            raise TypeError("'WeightedItem.weight' must be a number")

    name: str
    """Name of the item"""

    weight: float
    """Weight of the item"""


class Expedition:
    """Bundles regions, paths, and items together for one expedition"""

    def __init__(self, data: Mapping[str, Any]):
        """Creates an expedition from json"""

        if not isinstance(data, dict):
            raise TypeError("Expedition expects a dict")

        self.name = data.get("name")
        if not isinstance(self.name, str):
            raise TypeError("'Expedition.name' must be a string")

        raw_regions = data.get("regions")
        if not isinstance(raw_regions, list):
            raise TypeError("'Expedition.regions' must be a list")
        self.regions = [ Region(r) for r in raw_regions ]

        raw_locations = data.get("locations")
        if not isinstance(raw_locations, list):
            raise TypeError("'Expedition.locations' must be a list")
        self.locations = [ Location(l) for l in raw_locations ]

        raw_paths = data.get("paths")
        if not isinstance(raw_paths, list):
            raise TypeError("'Expedition.paths' must be a list")
        self.paths = [ Path(p) for p in raw_paths ]

        self.start_region = data.get("start_region")
        if isinstance(self.start_region, numbers.Number):
            self.start_region = int(self.start_region)
        else:
            raise TypeError("'Expedition.start_region' must be a number")

        self.num_sectors = data.get("num_sectors")
        if isinstance(self.num_sectors, numbers.Number):
            self.num_sectors = int(self.num_sectors)
        else:
            raise TypeError("'Expedition.num_sectors' must be a number")

    name: str
    """Short or 'common' name of the expedition, ie R1A1"""

    regions: List[Region]
    """Regions found in this expedition"""

    locations: List[Location]
    """Locations found in this expedition"""

    paths: List[Path]
    """Paths found in this expedition"""

    start_region: int
    """Starting region for this expedition, linked to the menu"""

    num_sectors: int
    """Count of sectors (main, secondary, overload) in this expedition"""


class ModdedInstanceData:
    """Contains and formats modded instance data so it can be easily serialized / deserialized"""

    def __init__(self, data: Mapping[str, Any]):
        """Creates a ModdedInstanceData from json"""

        if not isinstance(data, dict):
            raise TypeError("ModdedInstanceData expects a dict")

        self.plugin_version = data.get("plugin_version")
        if not isinstance(self.plugin_version, str):
            raise TypeError("'ModdedInstanceData.plugin_version' must be a string")

        if self.plugin_version != "1.0.0":
            raise ValueError("Unsupported plugin version: %r" % (self.plugin_version,))

        raw_expeditions = data.get("expeditions")
        if not isinstance(raw_expeditions, list):
            raise TypeError("'ModdedInstanceData.expeditions' must be a list")
        self.expeditions = [ Expedition(e) for e in raw_expeditions ]

        raw_optional_items = data.get("optional_items")
        if not isinstance(raw_optional_items, list):
            raise TypeError("'ModdedInstanceData.optional_items' must be a list")

        def make_optional_category(item: Mapping[str, Any]) -> Tuple[str, List[str]]:
            if not isinstance(item, dict):
                raise TypeError("ModdedInstanceData.optional_items.item expects a dict")

            category_name = item.get("Item1")
            if not isinstance(category_name, str):
                raise TypeError("ModdedInstanceData.optional_items.item.Item1 must be a string")

            raw_items = item.get("Item2")
            if not isinstance(raw_items, list):
                raise TypeError("ModdedInstanceData.optional_items.item.Item2 must be a list")

            items = [ str(i) if isinstance(i, str) else None for i in raw_items ]
            if None in items:
                raise TypeError("ModdedInstanceData.optional_items.item.Item2 must be a list of strings")

        self.optional_items = [ make_optional_category(i) for i in raw_optional_items ]

        raw_filler_items = data.get("filler_items")
        if not isinstance(raw_filler_items, list):
            raise TypeError("'ModdedInstanceData.filler_items' must be a list")
        self.filler_items = [ WeightedItem(fi) for fi in raw_filler_items ]

        raw_trap_items = data.get("trap_items")
        if not isinstance(raw_trap_items, list):
            raise TypeError("'ModdedInstanceData.trap_items' must be a list")
        self.trap_items = [ WeightedItem(ti) for ti in raw_trap_items ]

    plugin_version: str
    """Version of the plugin which generated the ModdedInstanceData, for compatibility checking"""

    expeditions: List[Expedition]
    """List of expeditions declared by the data"""

    optional_items: List[Tuple[str, List[str]]]
    """List of optional item categories and the optional items in those categories"""

    filler_items: List[WeightedItem]
    """List of filler items supported by the plugin, weighted by how common they are (higher is more common)"""

    trap_items: List[WeightedItem]
    """List of trap items supported by the plugin, weighted by how bad they are (higher is worse)"""