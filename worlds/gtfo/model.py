from __future__ import annotations

import collections.abc
import itertools
import sys
import typing
from typing import Any, cast, ClassVar, Collection, Dict, FrozenSet, Iterable, List, Literal, Optional, Set, Tuple, \
    Type, TYPE_CHECKING, Union
from types import SimpleNamespace
import yaml

import Options

if TYPE_CHECKING:
    from .options import OptionsEvaluator

"""
The `Model` postfix is applied to classes in this file to prevent naming overlap
"""

class BaseModel:
    def __init__(self, data: Dict[str, Any]):
        pass

    def dump(self) -> Dict[str, Any]:
        return dict()

class SlotDataModel(BaseModel):
    root_seed: int
    region_whitelist: Set[int]
    region_blacklist: Set[int]
    location_whitelist: Set[int]
    location_blacklist: Set[int]
    item_whitelist: Set[int]
    item_blacklist: Set[int]
    filled_empty_locations: List[Tuple[int, int]]
    goal_item_results: List[Tuple[int, int]]
    skippable_goal_count: int

    ## Required for UT
    start_inventory_results: List[Tuple[int, int]]

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.root_seed = data['root_seed']
        self.region_whitelist = data['region_whitelist']
        self.region_blacklist = data['region_blacklist']
        self.location_whitelist = data['location_whitelist']
        self.location_blacklist = data['location_blacklist']
        self.item_whitelist = data['item_whitelist']
        self.item_blacklist = data['item_blacklist']
        self.filled_empty_locations = data['filled_empty_locations']
        self.goal_item_results = data['goal_item_results']
        self.skippable_goal_count = data['skippable_goal_count']

        ## Required for UT
        self.start_inventory_results = data['start_inventory_results']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['root_seed'] = self.root_seed
        result['region_whitelist'] = self.region_whitelist
        result['region_blacklist'] = self.region_blacklist
        result['location_whitelist'] = self.location_whitelist
        result['location_blacklist'] = self.location_blacklist
        result['item_whitelist'] = self.item_whitelist
        result['item_blacklist'] = self.item_blacklist
        result['filled_empty_locations'] = self.filled_empty_locations
        result['goal_item_results'] = self.goal_item_results
        result['skippable_goal_count'] = self.skippable_goal_count

        ## Required for UT
        result['start_inventory_results'] = self.start_inventory_results

        return result

class GameDataModel(BaseModel):
    name: Optional[str]
    version: str
    regions: List[TaggedRegionModel]
    locations: List[LocationTagModel]
    items: List[ItemTagModel]
    paths: List[PathModel]
    floating_items: List[FloatingItemModel]
    choices: List[ChoiceModel]
    options: List[OptionBaseModel]

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.name = data.get('name', None)
        self.version = data['version']
        self.regions = [ TaggedRegionModel(d) for d in data['regions'] ]
        self.locations = [ LocationTagModel(d) for d in data['locations'] ]
        self.items = [ ItemTagModel(d) for d in data['items']]
        self.paths = [ PathModel(d) for d in data['paths'] ]
        self.floating_items = [ FloatingItemModel(d) for d in data['floating_items'] ]
        self.choices = [ ChoiceModel(d) for d in data['choices'] ]
        self.options = [ OptionBaseModel.construct(d) for d in data['options'] ]

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['name'] = self.name
        result['version'] = self.version
        result['regions'] = [ m.dump() for m in self.regions ]
        result['locations'] = [ m.dump() for m in self.locations ]
        result['items'] = [ m.dump() for m in self.items ]
        result['paths'] = [ m.dump() for m in self.paths ]
        result['floating_items'] = [ m.dump() for m in self.floating_items ]
        result['choices'] = [ m.dump() for m in self.choices ]
        result['options'] = [ m.dump() for m in self.options ]
        return result

class TagModel(BaseModel):
    id: int
    name: str
    description: str
    parents: List[int]

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.id = data['id']
        self.name = data['name']
        self.description = data['description']
        self.parents = data['parents']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['id'] = self.id
        result['name'] = self.name
        result['description'] = self.description
        result['parents'] = self.parents
        return result

    def __hash__(self):
        return self.id.__hash__()

    def __eq__(self, other: Any):
        return self.id.__eq__(other.id) if isinstance(other, TagModel) else False

class TaggedRegionModel(TagModel):
    reachable: bool

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.reachable = data['reachable']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['reachable'] = self.reachable
        return result

class LocationTagModel(TagModel):
    value: Optional[LocationModel]

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        d = data.get('value', None)
        self.value = None if d is None else LocationModel(cast(Dict, d))

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['value'] = self.value
        return result

class RealLocationTagModel(LocationTagModel):
    value: LocationModel

class LocationModel(BaseModel):
    owning_regions: List[int]
    item_id: int
    priority_mode: Literal[ "Default", "Priority", "Excluded", "Trap" ]
    is_empty: bool

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.owning_regions = data['owning_regions']
        self.item_id = data['item_id']
        self.priority_mode = data['priority_mode']
        self.is_empty = data['is_empty']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['owning_regions'] = self.owning_regions
        result['item_id'] = self.item_id
        result['priority_mode'] = self.priority_mode
        result['is_empty'] = self.is_empty
        return result

class ItemTagModel(TagModel):
    value: Optional[ItemModel]

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        d = data.get('value')
        self.value = None if d is None else ItemModel(cast(Dict, d))

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['value'] = self.value.dump() if self.value is not None else None
        return result

class RealItemTagModel(LocationTagModel):
    value: ItemModel

class ItemModel(BaseModel):
    is_progression: bool
    is_useful: bool
    is_filler: bool
    is_trap: bool
    do_skip_balancing: bool
    is_deprioritized: bool
    is_collected_by_default: bool
    is_randomlike: bool

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.is_progression = data['is_progression']
        self.is_useful = data['is_useful']
        self.is_filler = data['is_filler']
        self.is_trap = data['is_trap']
        self.do_skip_balancing = data['do_skip_balancing']
        self.is_deprioritized = data['is_deprioritized']
        self.is_collected_by_default = data['is_collected_by_default']
        self.is_randomlike = data['is_randomlike']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['is_progression'] = self.is_progression
        result['is_useful'] = self.is_useful
        result['is_filler'] = self.is_filler
        result['is_trap'] = self.is_trap
        result['do_skip_balancing'] = self.do_skip_balancing
        result['is_deprioritized'] = self.is_deprioritized
        result['is_collected_by_default'] = self.is_collected_by_default
        result['is_randomlike'] = self.is_randomlike
        return result

class FloatingItemModel(BaseModel):
    region: int
    item: int

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.region = data['region']
        self.item = data['item']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['region'] = self.region
        result['item'] = self.item
        return result

class PathModel(BaseModel):
    id: int
    starting_region: int
    ending_region: int
    reqs: List[PathReqModel]
    name: Optional[str] = None

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.id = data['id']
        self.starting_region = data['starting_region']
        self.ending_region = data['ending_region']
        self.reqs = [ PathReqModel(d) for d in data['reqs'] ]
        self.name = data.get('name', None)

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['id'] = self.id
        result['starting_region'] = self.starting_region
        result['ending_region'] = self.ending_region
        result['reqs'] = [ r.dump() for r in self.reqs ]
        result['name'] = self.name
        return result

class PathReqModel(BaseModel):
    target: int
    count: int
    is_category: bool
    is_consume: bool
    is_growing: bool

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.target = data['target']
        self.count = data['count']
        self.is_category = data['is_category']
        self.is_consume = data['is_consume']
        self.is_growing = data['is_growing']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['target'] = self.target
        result['count'] = self.count
        result['is_category'] = self.is_category
        result['is_consume'] = self.is_consume
        result['is_growing'] = self.is_growing
        return result

class ChoiceModel(BaseModel):
    choice_paths: FrozenSet[int]
    regions: List[int]
    region_ranges: List[Tuple[int, int]]
    id: int = 0
    region_set: Optional[Set[int]] = None

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.choice_paths = frozenset(data['choice_paths'])
        self.regions = data['regions']
        self.region_ranges = data['region_ranges']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['choice_paths'] = list(self.choice_paths)
        result['regions'] = self.regions
        result['region_ranges'] = self.region_ranges
        return result

    def get_regions(self) -> Set[int]:
        if self.region_set is None:
            self.region_set: Set[int] = set()
            self.region_set.update(self.regions)
            self.region_set.update( r for s, e in self.region_ranges for r in range(s, e + 1) )
        return self.region_set

## Options API ####################################################################################

class Repeat(collections.abc.Collection[int]):
    """A simple alternative to itertools.repeat() which defines *something* for its length"""
    value: int

    def __init__(self, value: int):
        self.value = value

    def __len__(self):
        return 1

    def __iter__(self):
        return itertools.repeat(self.value)

    def __contains__(self, item):
        return item == self.value

def gtfo_zip(*args: Collection[int]) -> Collection[Tuple[int, ...]]:
    """
    A variation of zip which uses collections; if the size of all collections is calculated
    to be 1, then it returns only 1 element (to account for our infinite Repeat collection)
    """
    if all(len(arg) == 1 for arg in args):
        return ( tuple(next(iter(arg)) for arg in args), )
    else:
        return tuple(*zip(*args))

def gtfo_iter(arg: Collection[int]) -> Iterable[int]:
    """
    If the collection's length is 1, returns the first element of the iterable only.
    This is to account for our special Repeat collection
    """
    if len(arg) == 1:
        return (next(iter(arg)), )
    else:
        return arg

class OptionParameterModel(BaseModel):
    type: Literal[ "Constant", "RegionID", "LocationID", "ItemID", "OptionID" ]
    value: int

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.type = data['type']
        self.value = data['value']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['type'] = self.type
        result['value'] = self.value
        return result

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        """Shortcut to get the value of this parameter"""
        if self.type == "OptionID":
            return oe.get_output(self.value)
        else:
            return Repeat(self.value)

class OptionBaseModel(BaseModel):
    id: int
    type: str

    registered_options: ClassVar[Dict[str, Type[OptionBaseModel]]] = dict()

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.id = data['id']
        self.type = data['type']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['id'] = self.id
        result['type'] = self.type
        return result

    @staticmethod
    def construct(data: Dict[str, Any]) -> OptionBaseModel:
        typ = OptionBaseModel.registered_options.get(data['type'])
        if typ is None:
            raise Exception(f"Failed to create option model for option type: {data['type']}")
        return typ(data)

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        """Evaluate this option and return the resulting value"""
        raise NotImplementedError

def gtfo_option(cls: Type[OptionBaseModel]):
    """Registers an option with OptionBaseModel so it can dynamically use it during JSON parsing"""
    OptionBaseModel.registered_options[cls.type] = cls
    return cls

class OptionInputModel(OptionBaseModel):
    display_name: str
    description: str
    category: str
    category_sort: List[int]
    default_value: int
    condition: int

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.display_name = data['display_name']
        self.description = data['description']
        self.category = data['category']
        self.category_sort = data['category_sort']
        self.default_value = data['default_value']
        self.condition = data['condition']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['display_name'] = self.display_name
        result['description'] = self.description
        result['category'] = self.category
        result['category_sort'] = self.category_sort
        result['default_value'] = self.default_value
        result['condition'] = self.condition
        return result

    def create_namespace(self) -> Dict[str, Any]:
        """Creates the namespace for the options class"""
        namespace = SimpleNamespace()
        namespace: Type[Options.Option]
        namespace.display_name = self.display_name
        namespace.__doc__ = self.description
        namespace.default = self.default_value
        return namespace.__dict__

    def get_base_class(self) -> Type[Options.Option]:
        """Virtual method to get the base option class used by this input"""
        return Options.Option

    def create_class(self, world_name: Optional[str]) -> Type[Options.Option]:
        """Creates the class definition for the options class"""
        namespace = self.create_namespace()
        base = self.get_base_class()
        if world_name is None:
            return type(base)(f"{self.display_name} (GTFO Option)", (base,), namespace)
        else:
            return type(base)(f"{self.display_name} (GTFO-{world_name} Option)", (base,), namespace)

    def get_class_instance(self, oe: OptionsEvaluator) -> Options.Option:
        """The option's instance from the options class in the world"""
        instance = getattr(oe.options, self.display_name)
        if instance is None:
            msg = f"Failed to find option input: {self.display_name}"
            oe.options.logger.error(msg)
            raise Exception(msg)
        elif not isinstance(instance, self.get_base_class()):
            msg = f"Option found input but it was the wrong type: {self.display_name}"
            oe.options.logger.error(msg)
            raise Exception(msg)
        instance: Options.Option
        return instance

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        ## Evaluate the result. If it's iterable, return that; if not, loop it
        instance = self.get_class_instance(oe)
        try:
            iter(instance.value)
            len(instance.value)
            return instance.value
        except TypeError:
            return Repeat(instance.value)

@gtfo_option
class OptionToggleModel(OptionInputModel):
    type: Literal["Toggle"] = "Toggle"

    def get_base_class(self) -> Type[Options.Option]:
        return Options.Toggle if self.default_value == 0 else Options.DefaultOnToggle

@gtfo_option
class OptionChoiceModel(OptionInputModel):
    type: Literal["Choice"] = "Choice"
    choice_names: List[str]
    choice_values: List[int]

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.choice_names = data['choice_names']
        self.choice_values = data['choice_values']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['choice_names'] = self.choice_names
        result['choice_values'] = self.choice_values
        return result

    def get_base_class(self) -> Type[Options.Option]:
        return Options.Choice

    def create_class(self, world_name: str) -> Type[Options.Option]:
        klass = super().create_class(world_name)
        klass: Type[Options.Choice]

        assert len(self.choice_names) > 0, \
            "Choice option does not have any choices!"
        assert len(self.choice_names) == len(self.choice_values), \
            "Choice option does not have equal number of choice names and values!"

        defined_values: Set[int] = set()
        for name, value in zip(self.choice_names, self.choice_values):
            klass.options.setdefault(name, value)
            if value not in defined_values:
                ## Issue: name_lookup is considered an instance variable, but it's actually a class variable
                klass.name_lookup.setdefault(value, name) # type: ignore
            else:
                klass.aliases.setdefault(name, value)
            klass.options.setdefault(name.lower(), value)
            klass.aliases.setdefault(name.lower(), value)

        return klass

@gtfo_option
class OptionRangeModel(OptionInputModel):
    type: Literal["Range"] = "Range"
    min: float
    max: float

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.min = data['min']
        self.max = data['max']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['min'] = self.min
        result['max'] = self.max
        return result

    def create_namespace(self) -> Dict[str, Any]:
        namespace = super().create_namespace()
        namespace = SimpleNamespace(**namespace)
        namespace: Type[Options.Range]
        namespace.range_start = self.min
        namespace.range_end = self.max
        return namespace.__dict__

    def get_base_class(self) -> Type[Options.Option]:
        return Options.Range

@gtfo_option
class OptionMultiChoiceModel(OptionChoiceModel):
    type: Literal["MultiChoice"] = "MultiChoice"

    class MultiChoiceOption(Options.OptionSet):
        value: Set[str]
        random_choices: Optional[List[str]]
        random_weights: Optional[List[int]]
        random_count: Union[int, Tuple[int, int]]

        def __init__(self,
                     value: Iterable[str],
                     random_choices: Optional[List[str]] = None,
                     random_weights: Optional[List[int]] = None,
                     random_count: Union[int, Tuple[int, int]] = 1):
            self.random_choices = random_choices
            self.random_weights = random_weights
            self.random_count = random_count
            super().__init__(value, None)

        @classmethod
        def from_any(cls, data: typing.Any):
            try:
                count_raw = data.get('random', 1)
                del data['random']
                count_raw: str
                keys = [ k for k, v in data.items() if v > 0 ]
                values = [ v for v in data.values() if v > 0 ]
                try:
                    count = int(count_raw)
                    if count == -1:
                        count = len(keys)
                    elif count < -1:
                        raise Exception("Cannot parse option; desired random count is less than -1")
                    elif count > len(keys):
                        raise Exception(
                            "Cannot parse option; desired random count is greater than number of available choices."
                            + "\nUse -1 as the value for `random` if you wish to select all choices."
                        )
                except ValueError:
                    low, high = count_raw.split("-", 1)
                    low, high = int(low), int(high)
                    if low == -1: low = len(keys)
                    if high == -1: high = len(keys)
                    if low > high:
                        low, high = high, low
                    count = (low, high)
                return OptionMultiChoiceModel.MultiChoiceOption({ "random" }, keys, values, count)
            except: ## If we fail, simply ignore it
                return super(OptionMultiChoiceModel.MultiChoiceOption, cls).from_any(data)

    class ThisDefaultValue(dict):
        """
        This class exists purely to let me format this option correctly when generating templates.
        We register a YAML representer for this class below OptionMuiltiChoiceModel's definition.
        """

        @staticmethod
        def representer(dumper, obj):
            return dumper.represent_mapping('tag:yaml.org,2002:map', obj.items())


    def create_namespace(self) -> Dict[str, Any]:
        namespace = super().create_namespace()
        namespace = SimpleNamespace(**namespace)
        namespace: Type[Options.OptionSet]
        namespace.supports_weighting = False
        namespace.valid_keys = itertools.chain((key.casefold() for key in self.choice_names), ("random", ))
        namespace.valid_keys_casefold = True

        ## Collect the defaults
        defaults: Set[str] = set()
        d = self.default_value
        x = 0
        while d > 0:
            if d & 1 != 0:
                defaults.add(self.choice_names[x])
            x = x + 1
            d = d >> 1

        ## We have to format our option differently if we're being used by OptionsCreator
        if getattr(sys.modules['__main__'], "__file__", "").endswith("OptionsCreator.py"):
            namespace.default = defaults
        elif defaults:
            namespace.default = OptionMultiChoiceModel.ThisDefaultValue()
            namespace.default["random"] = -1
            namespace.default.update({k: 0 for k in self.choice_names})
            for d in defaults:
                namespace.default[d] = 50
        else:
            namespace.default = OptionMultiChoiceModel.ThisDefaultValue()
            namespace.default["random"] = 0
            namespace.default.update({k: 50 for k in self.choice_names})
        namespace.supports_weighting = False

        namespace.__doc__ = ("" if namespace.__doc__ is None else namespace.__doc__) \
            + "\n\nYou may either provide a list of values or a mapping of `name: weight` pairs." \
            + "\nIf using a mapping, you may choose how many options to select using the special value" \
            + "\n'random'. For example, `random: 3` selects 3 options. `random: 2-5` selects 2 to 5 options." \
            + "\n`random: -1` will select all values with a weight greater than 0."
        return namespace.__dict__

    def get_base_class(self) -> Type[Options.Option]:
        return OptionMultiChoiceModel.MultiChoiceOption

    def create_class(self, world_name: str) -> Type[Options.Option]:
        return super(OptionChoiceModel, self).create_class(world_name)
        klass = super().create_class(world_name)
        klass: Type[Options.OptionSet]
        ## We're simply adding 'random' as a special option, at the front, so it populates when generating templates
        klass.options = {
            'random': NotImplemented,
            **klass.options
        }
        ## Issue: name_lookup is considered an instance variable, but it's actually a class variable
        klass.name_lookup = { # type: ignore
            NotImplemented: 'random',
            **klass.name_lookup # type: ignore
        }
        return klass

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        instance = self.get_class_instance(oe)
        instance: OptionMultiChoiceModel.MultiChoiceOption
        if instance.value == { "random" }:
            assert instance.random_choices is not None and instance.random_weights is not None, \
                f"Error parsing option {self.display_name}; expected random, got None!"
            options = list(instance.random_choices)
            weights = list(instance.random_weights)
            count = instance.random_count
            try:
                low, high = count
                count = oe.options.random.randrange(low, high + 1)
            except TypeError:
                pass
            count: int
            original_count = count
            values: Set[str] = set()
            while count > 0:
                assert any(w > 0 for w in weights), \
                    f"Cannot randomly sample item from option {self.display_name}; all remaining weights are zero!" \
                    + f"\nAttempted to sample {original_count} items, failed on item {original_count - count + 1}"
                sample = oe.options.random.sample(range(len(options)), 1, counts=weights)[0]
                values.add(options.pop(sample))
                weights.pop(sample)
                count -= 1
        else:
            values = instance.value
        lookup = { name: value for name, value in zip(self.choice_names, self.choice_values) }
        return [ lookup[value] for value in values if value != 'random' ]

yaml.add_representer(OptionMultiChoiceModel.ThisDefaultValue, OptionMultiChoiceModel.ThisDefaultValue.representer)

class OptionOperationModel(OptionBaseModel):
    pass

class OptionUnaryOperationModel(OptionOperationModel):
    param: OptionParameterModel

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.param = OptionParameterModel(data['param'])

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['param'] = self.param.dump()
        return result

    def get_param(self, oe: OptionsEvaluator) -> Collection[Tuple[int]]:
        """Shortcut to evaluate parameter"""
        result = gtfo_zip(self.param.evaluate(oe))
        result: Collection[Tuple[int]]
        return result

@gtfo_option
class OptionToBoolOperationModel(OptionUnaryOperationModel):
    type: Literal["ToBool"] = "ToBool"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int]) -> int:
            return 0 if x[0] == 0 else 1
        return tuple(map(trans, self.get_param(oe)))

@gtfo_option
class OptionNotOperationModel(OptionUnaryOperationModel):
    type: Literal["Not"] = "Not"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int]) -> int:
            return 1 if x[0] == 0 else 0
        return tuple(map(trans, self.get_param(oe)))

@gtfo_option
class OptionNegateOperationModel(OptionUnaryOperationModel):
    type: Literal["Negate"] = "Negate"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int]) -> int:
            return -x[0]
        return tuple(map(trans, self.get_param(oe)))

@gtfo_option
class OptionReciprocalOperationModel(OptionUnaryOperationModel):
    type: Literal["Reciprocal"] = "Reciprocal"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int]) -> int:
            return int(1.0 // x[0])
        return tuple(map(trans, self.get_param(oe)))

class OptionBinaryOperationModel(OptionOperationModel):
    l_param: OptionParameterModel
    r_param: OptionParameterModel

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.l_param = OptionParameterModel(data['l_param'])
        self.r_param = OptionParameterModel(data['r_param'])

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['l_param'] = self.l_param.dump()
        result['r_param'] = self.r_param.dump()
        return result

    def get_params(self, oe: OptionsEvaluator) -> Collection[Tuple[int, int]]:
        """Shortcut to evaluate parameters"""
        result = gtfo_zip(self.l_param.evaluate(oe), self.r_param.evaluate(oe))
        result: Collection[Tuple[int, int]]
        return result

@gtfo_option
class OptionOrOperationModel(OptionBinaryOperationModel):
    type: Literal["Or"] = "Or"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return x[0] if x[0] != 0 else x[1]
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class OptionAndOperationModel(OptionBinaryOperationModel):
    type: Literal["And"] = "And"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return x[0] if x[0] == 0 else x[1]
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class OptionEqualsOperationModel(OptionBinaryOperationModel):
    type: Literal["Equals"] = "Equals"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return int(x[0] == x[1])
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class DoesNotEqualOperationModel(OptionBinaryOperationModel):
    type: Literal["DoesNotEqual"] = "DoesNotEqual"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return int(x[0] != x[1])
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class OptionLessThanOperationModel(OptionBinaryOperationModel):
    type: Literal["LessThan"] = "LessThan"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return int(x[0] < x[1])
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class OptionLessThanOrEqualOperationModel(OptionBinaryOperationModel):
    type: Literal["LessThanOrEqual"] = "LessThanOrEqual"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return int(x[0] <= x[1])
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class OptionGreaterThanOperationModel(OptionBinaryOperationModel):
    type: Literal["GreaterThan"] = "GreaterThan"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return int(x[0] > x[1])
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class OptionGreaterThanOrEqualOperationModel(OptionBinaryOperationModel):
    type: Literal["GreaterThanOrEqual"] = "GreaterThanOrEqual"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return int(x[0] >= x[1])
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class OptionAddOperationModel(OptionBinaryOperationModel):
    type: Literal["Add"] = "Add"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return x[0] + x[1]
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class OptionSubtractOperationModel(OptionBinaryOperationModel):
    type: Literal["Subtract"] = "Subtract"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return x[0] - x[1]
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class OptionMultiplyOperationModel(OptionBinaryOperationModel):
    type: Literal["Multiply"] = "Multiply"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return x[0] * x[1]
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class OptionDivideOperationModel(OptionBinaryOperationModel):
    type: Literal["Divide"] = "Divide"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return int(x[0] // x[1])
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class OptionGetBitOperationModel(OptionBinaryOperationModel):
    type: Literal["GetBit"] = "GetBit"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int]) -> int:
            return (x[0] >> x[1]) & 1
        return tuple(map(trans, self.get_params(oe)))

class OptionTernaryOperationModel(OptionOperationModel):
    a_param: OptionParameterModel
    b_param: OptionParameterModel
    c_param: OptionParameterModel

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.a_param = OptionParameterModel(data['a_param'])
        self.b_param = OptionParameterModel(data['b_param'])
        self.c_param = OptionParameterModel(data['c_param'])

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['a_param'] = self.a_param.dump()
        result['b_param'] = self.b_param.dump()
        result['c_param'] = self.c_param.dump()
        return result

    def get_params(self, oe: OptionsEvaluator) -> Collection[Tuple[int, int, int]]:
        """Shortcut to evaluate parameters"""
        result = gtfo_zip(self.a_param.evaluate(oe), self.b_param.evaluate(oe), self.c_param.evaluate(oe))
        result: Collection[Tuple[int, int, int]]
        return result

@gtfo_option
class OptionConditionalOperationModel(OptionTernaryOperationModel):
    type: Literal["Conditional"] = "Conditional"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int, int]) -> int:
            return x[2] if x[0] == 0 else x[1]
        return tuple(map(trans, self.get_params(oe)))

@gtfo_option
class OptionLinearMapOperationModel(OptionTernaryOperationModel):
    type: Literal["LinearMap"] = "LinearMap"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        def trans(x: Tuple[int, int, int]) -> int:
            return x[0] * x[1] + x[2]
        return tuple(map(trans, self.get_params(oe)))

OptionSetTarget = Literal[
    "RegionWhitelist",
    "RegionBlacklist",
    "LocationWhitelist",
    "LocationBlacklist",
    "ItemWhitelist",
    "ItemBlacklist",
]

OptionDictTarget = Literal[
    "GoalItems",
    "StartInventory",
    "StartVouchers",
    "EarlyItems",
    "LocalItems",
    "NonLocalItems",
    "ItemHints",
    "LocationHints",
    "PriorityLocations",
    "ExcludeLocations",
]

class OptionEffectModel(OptionBaseModel):
    condition: int

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.condition = data['condition']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['condition'] = self.condition
        return result

    def check_condition(self, oe: OptionsEvaluator) -> bool:
        """Checks the condition set by the option and returns True if met, False otherwise"""
        if self.condition == 0:
            return True
        else:
            return all( o != 0 for o in gtfo_iter(oe.get_output(self.condition)) )

@gtfo_option
class OptionAddToSetModel(OptionEffectModel):
    type: Literal["AddToSet"] = "AddToSet"
    target: OptionSetTarget
    tag: OptionParameterModel

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.target = data['target']
        self.tag = OptionParameterModel(data['tag'])

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['target'] = self.target
        result['tag'] = self.tag.dump()
        return result

    def evaluate(self, oe: OptionsEvaluator) -> int:
        if self.check_condition(oe):
            target = oe.get_set_target(self.target)
            for tag in gtfo_iter(self.tag.evaluate(oe)):
                if tag != 0:
                    target.add(tag)
            return 1
        else:
            return 0

@gtfo_option
class OptionAddCountModel(OptionEffectModel):
    type: Literal["AddCountToDict"] = "AddCountToDict"
    target: OptionDictTarget
    tag: OptionParameterModel
    count: OptionParameterModel

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.target = data['target']
        self.tag = OptionParameterModel(data['tag'])
        self.count = OptionParameterModel(data['count'])

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['target'] = self.target
        result['tag'] = self.tag.dump()
        result['count'] = self.count.dump()
        return result

    def evaluate(self, oe: OptionsEvaluator) -> int:
        if self.check_condition(oe):
            target = oe.get_dict_target(self.target)
            for t, c in gtfo_zip(self.tag.evaluate(oe), self.count.evaluate(oe)):
                if t == 0:
                    continue
                if c < -1:
                    raise ValueError(f"Cannot AddCount of {c}; it is less than -1")
                if t in target:
                    if target[t] >= 0:
                        if c >= 0:
                            target[t] += c
                        elif c == -1:
                            target[t] = c
                else:
                    target[t] = c
            return 1
        else:
            return 0

@gtfo_option
class OptionAddAll(OptionEffectModel):
    type: Literal["AddAllToDict"] = "AddAllToDict"
    target: OptionDictTarget
    tag: OptionParameterModel

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.target = data['target']
        self.tag = OptionParameterModel(data['tag'])

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['target'] = self.target
        result['tag'] = self.tag.dump()
        return result

    def evaluate(self, oe: OptionsEvaluator) -> int:
        if self.check_condition(oe):
            target = oe.get_dict_target(self.target)
            for tag in gtfo_iter(self.tag.evaluate(oe)):
                if tag != 0:
                    target[tag] = -1
            return 1
        else:
            return 0

@gtfo_option
class OptionRaiseError(OptionEffectModel):
    type: Literal["RaiseError"] = "RaiseError"
    message: str

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.message = data['message']

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['message'] = self.message
        return result

    def evaluate(self, oe: OptionsEvaluator) -> int:
        if self.check_condition(oe):
            raise Exception(self.message)
        return 0

@gtfo_option
class OptionIsFakeGenerationModel(OptionBaseModel):
    type: Literal["IsFakeGeneration"] = "IsFakeGeneration"

    def evaluate(self, oe: OptionsEvaluator) -> Collection[int]:
        is_fake = oe.world_instance is not None and getattr(oe.world_instance.multiworld, "generation_is_fake", False)
        return Repeat(1 if is_fake else 0)

class OptionTagOptionModel(OptionInputModel):
    tag: OptionParameterModel

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self.tag = OptionParameterModel(data['tag'])

    def dump(self) -> Dict[str, Any]:
        result = super().dump()
        result['tag'] = self.tag.dump()
        return result

    check_condition = OptionEffectModel.check_condition

    def get_whitelist(self, oe: OptionsEvaluator) -> Set[int]:
        """Get the whitelist for this option"""
        raise NotImplementedError()

    def get_blacklist(self, oe: OptionsEvaluator) -> Set[int]:
        """Get the blacklist for this option"""
        raise NotImplementedError()

    def get_base_class(self) -> Type[Options.Option]:
        return Options.Choice

    def create_class(self, world_name: str) -> Type[Options.Option]:
        klass = super().create_class(world_name)

        options = ( ("None", 1), ("Whitelist", 0), ("Blacklist", 2) )
        for name, value in options:
            klass.options[name] = value
            klass.options[name.lower()] = value
            klass.aliases[name.lower()] = value ## Not sure if this is necessary
            ## Issue: name_lookup is considered an instance variable, but it's actually a class variable
            klass.name_lookup[value] = name  # type: ignore

        return klass

    def evaluate(self, oe: OptionsEvaluator) -> int:
        if self.check_condition(oe):
            value = self.get_class_instance(oe).value
            if value == 0:
                whitelist = self.get_whitelist(oe)
                for tag in gtfo_iter(self.tag.evaluate(oe)):
                    whitelist.add(tag)
            elif value == 2:
                blacklist = self.get_blacklist(oe)
                for tag in gtfo_iter(self.tag.evaluate(oe)):
                    blacklist.add(tag)
            return value
        else:
            return -1

@gtfo_option
class OptionRegionTagOptionModel(OptionTagOptionModel):
    type: Literal["RegionTagOption"] = "RegionTagOption"

    def get_whitelist(self, oe: OptionsEvaluator) -> Set[int]:
        return oe.options.region_whitelist

    def get_blacklist(self, oe: OptionsEvaluator) -> Set[int]:
        return oe.options.region_blacklist

@gtfo_option
class OptionLocationTagOptionModel(OptionTagOptionModel):
    type: Literal["LocationTagOption"] = "LocationTagOption"

    def get_whitelist(self, oe: OptionsEvaluator) -> Set[int]:
        return oe.options.location_whitelist

    def get_blacklist(self, oe: OptionsEvaluator) -> Set[int]:
        return oe.options.location_blacklist

@gtfo_option
class OptionItemTagOptionModel(OptionTagOptionModel):
    type: Literal["ItemTagOption"] = "ItemTagOption"

    def get_whitelist(self, oe: OptionsEvaluator) -> Set[int]:
        return oe.options.item_whitelist

    def get_blacklist(self, oe: OptionsEvaluator) -> Set[int]:
        return oe.options.item_blacklist
