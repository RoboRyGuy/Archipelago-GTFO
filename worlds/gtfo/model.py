from __future__ import annotations

import Options
from pydantic import BaseModel, Field
from typing import Annotated, Dict, List, Iterable, Literal, Optional, Set, Tuple, Type, Union
from . import options as gtfo_options

"""
The `Model` postfix is applied to classes in this file to prevent naming overlap
"""

class GameDataModel(BaseModel):
    name: Optional[str]
    expeditions: List[ExpeditionDataModel]
    tags: List[TagModel]
    regions: List[RegionModel]
    paths: List[PathModel]
    locations: List[LocationModel]
    items: List[ItemModel]
    floating_items: List[int]
    options: List[OptionTypes]

class ExpeditionDataModel(BaseModel):
    name: str
    reachable_regions: List[int]

class TagModel(BaseModel):
    id: int
    name: str
    description: str
    parent: int

class RegionModel(BaseModel):
    id: int
    name: str

class ReqItemModel(BaseModel):
    type: str
    target: int

class PathModel(BaseModel):
    id: int
    name: Optional[str]
    starting_region: int
    ending_region: int
    req_item: ReqItemModel
    req_count: int
    alt_item: ReqItemModel

class LocationDataModel(BaseModel):
    priority_mode: str
    is_empty: bool

class LocationModel(BaseModel):
    id: int
    name_tag: int
    tag2: int
    tag3: int
    rand_data: LocationDataModel
    item_id: int
    owning_regions: List[int]
    is_in_required_expeditions: bool = False
    is_whitelisted: bool = False
    is_blacklisted: bool = False

    def tags(self) -> Iterable[int]:
        return self.name_tag, self.tag2, self.tag3

    def should_be_randomized(self):
        return self.is_in_required_expeditions and self.is_whitelisted and not self.is_blacklisted

    def __hash__(self):
        return hash(f"Location {self.id}")

class ItemDataModel(BaseModel):
    is_progression: bool
    is_useful: bool
    is_filler: bool
    is_trap: bool
    do_skip_balancing: bool
    is_deprioritized: bool
    is_collected_by_default: bool
    is_randomlike: bool

class ItemModel(BaseModel):
    id: int
    name_tag: int
    tag2: int
    tag3: int
    rand_data: ItemDataModel
    path_reqs: ReqItemModel
    required_expedition: Optional[str]
    is_in_required_expeditions: bool = False
    is_whitelisted: bool = False
    is_blacklisted: bool = False

    def tags(self) -> Iterable[int]:
        return self.name_tag, self.tag2, self.tag3

    def should_be_randomized(self):
        return self.is_in_required_expeditions and self.is_whitelisted and not self.is_blacklisted

    def __hash__(self):
        return hash(f"Item {self.id}")

class OptionBaseModel(BaseModel):
    type: str
    id: int
    output: float = 0

    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        """Evaluate this option, updating its output value"""
        raise NotImplementedError

class OptionParameterModel(BaseModel):
    type: Literal["Constant", "Option"]
    value: int

    def get(self, state: gtfo_options.OptionEvaluationState) -> float:
        """Get the value represented by this parameter"""
        if self.type == "Constant":
            return self.value
        elif self.type == "Option":
            return state.get_output(self.value)
        else:
            raise Exception(f"Attempted to evaluate option parameter of unknown type: \"{self.type}\"")

class OptionInputModel(OptionBaseModel):
    type: Literal["Toggle", "Choice", "Range"]
    display_name: str
    description: str
    category: str
    default_value: int
    condition: int

    def check_condition(self, state: gtfo_options.OptionEvaluationState) -> bool:
        """Returns true if this input should be visible and false otherwise"""
        if self.condition == 0:
            return True
        return state.get_output(self.condition) != 0

    def get_name(self):
        """Get the pythonic name of this option"""
        return self.display_name.lower().replace(' ', '_')

    def get_class(self) -> Tuple[Type[Options.Option], Dict]:
        """
        Get the class and namespace for this option.
        To be overridden in derived classes to add more relevant values to specific input types.
        """
        namespace = dict()
        namespace["display_name"] = self.display_name
        namespace["rich_text_doc"] = True
        namespace["__doc__"] = self.description
        namespace["default"] = self.default_value
        return Options.Option, namespace

    def get_option(self, state: gtfo_options.OptionEvaluationState) -> Optional[Options.Option]:
        """Get the options instance from the world during evaluation"""
        return getattr(state.world.options, self.get_name())

class OptionToggleModel(OptionInputModel):
    type: Literal["Toggle"]

    def get_class(self) -> Tuple[Type[Options.Option], Dict]:
        namespace = super().get_class()[1]
        return Options.Toggle, namespace

    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        instance = self.get_option(state)
        instance: Options.Toggle
        self.output = 1 if instance.value else 0

class OptionChoiceModel(OptionInputModel):
    type: Literal["Choice"]
    choice_names: List[str]
    choice_values: List[int]

    def get_class(self) -> Tuple[Type[Options.Option], Dict]:
        namespace = super().get_class()[1]

        ## Define the choices
        if len(self.choice_names) != len(self.choice_values):
            raise Exception("Choice option has different name and values counts!")

        defined_values: Set[int] = set()
        for i in range(len(self.choice_names)):
            name, value = self.choice_names[i], self.choice_values[i]
            if value in defined_values:
                namespace[f"alias_{name}"] = value
            else:
                namespace[f"option_{name}"] = value
            defined_values.add(value)

        return Options.Choice, namespace

    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        instance = self.get_option(state)
        instance: Options.Choice
        self.output = instance.value

class OptionRangeModel(OptionInputModel):
    type: Literal["Range"]
    min: int
    max: int

    def get_class(self) -> Tuple[Type[Options.Option], Dict]:
        namespace = super().get_class()[1]

        ## Define the range
        namespace["range_start "] = self.min
        namespace["range_end "] = self.max

        return Options.Range, namespace

    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        instance = self.get_option(state)
        instance: Options.Range
        self.output = instance.value

class OptionOperationModel(OptionBaseModel):
    pass

class OptionUnaryOperationModel(OptionOperationModel):
    param: OptionParameterModel

    def get_params(self, state: gtfo_options.OptionEvaluationState) -> float:
        return self.param.get(state)

class OptionToBoolOperationModel(OptionUnaryOperationModel):
    type: Literal["ToBool"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x = self.get_params(state)
        self.output = 0 if x == 0 else 1

class OptionNotOperationModel(OptionUnaryOperationModel):
    type: Literal["Not"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x = self.get_params(state)
        self.output = 1 if x == 0 else 0

class OptionNegateOperationModel(OptionUnaryOperationModel):
    type: Literal["Negate"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x = self.get_params(state)
        self.output = -x

class OptionReciprocalOperationModel(OptionUnaryOperationModel):
    type: Literal["Reciprocal"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x = self.get_params(state)
        self.output = float(1) / float(x)

class OptionBinaryOperationModel(OptionOperationModel):
    l_param: OptionParameterModel
    r_param: OptionParameterModel

    def get_params(self, state: gtfo_options.OptionEvaluationState) -> Tuple[float, float]:
        return self.l_param.get(state), self.r_param.get(state)

class OptionOrOperation(OptionBinaryOperationModel):
    type: Literal["Or"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x, y = self.get_params(state)
        self.output = x or y

class OptionAndOperation(OptionBinaryOperationModel):
    type: Literal["And"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x, y = self.get_params(state)
        self.output = x and y

class OptionEqualsOperation(OptionBinaryOperationModel):
    type: Literal["Equals"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x, y = self.get_params(state)
        self.output = x == y

class OptionDoesNotEqualOperation(OptionBinaryOperationModel):
    type: Literal["DoesNotEqual"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x, y = self.get_params(state)
        self.output = x != y

class OptionLessThanOperation(OptionBinaryOperationModel):
    type: Literal["LessThan"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x, y = self.get_params(state)
        self.output = x < y

class OptionLessThanOrEqualOperation(OptionBinaryOperationModel):
    type: Literal["LessThanOrEqual"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x, y = self.get_params(state)
        self.output = x <= y

class OptionGreaterThanOperation(OptionBinaryOperationModel):
    type: Literal["GreaterThan"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x, y = self.get_params(state)
        self.output = x > y

class OptionGreaterThanOrEqualOperation(OptionBinaryOperationModel):
    type: Literal["GreaterThanOrEqual"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x, y = self.get_params(state)
        self.output = x >= y

class OptionAddOperation(OptionBinaryOperationModel):
    type: Literal["Add"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x, y = self.get_params(state)
        self.output = x + y

class OptionSubtractOperation(OptionBinaryOperationModel):
    type: Literal["Subtract"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x, y = self.get_params(state)
        self.output = x - y

class OptionMultiplyOperation(OptionBinaryOperationModel):
    type: Literal["Multiply"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x, y = self.get_params(state)
        self.output = x * y

class OptionDivideOperation(OptionBinaryOperationModel):
    type: Literal["Divide"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        x, y = self.get_params(state)
        self.output = float(x) / float(y)

class OptionTernaryOperationModel(OptionOperationModel):
    a_param: OptionParameterModel
    b_param: OptionParameterModel
    c_param: OptionParameterModel

    def get_params(self, state: gtfo_options.OptionEvaluationState) -> Tuple[float, float, float]:
        return self.a_param.get(state), self.b_param.get(state), self.c_param.get(state)

class OptionConditionalOperation(OptionTernaryOperationModel):
    type: Literal["Conditional"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        a, b, c = self.get_params(state)
        self.output = c if a == 0 else b

class OptionLinearMapOperation(OptionTernaryOperationModel):
    type: Literal["LinearMap"]
    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        a, b, c = self.get_params(state)
        self.output = a * b + c

class OptionEffectModel(OptionBaseModel):
    type: Literal["AddToSet", "AddCount"]
    condition: int

    def check_condition(self, state: gtfo_options.OptionEvaluationState) -> bool:
        """Returns true if this effect should apply, and false otherwise"""
        if self.condition == 0:
            return True
        return state.get_output(self.condition) != 0

OptionEffectTargets = Literal[
    "Whitelist", "Blacklist", "StartInventory", "StartVouchers", "EarlyItems", "LocalItems", "NonLocalItems",
    "StartHints", "CustomExcludeLocations", "CustomPriorityLocations", "GoalBlacklist",
]

class OptionAddToSetEffectModel(OptionEffectModel):
    type: Literal["AddToSet"]
    target: OptionEffectTargets
    tag: OptionParameterModel

    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        if not self.check_condition(state): return
        target = state.get_target(self.target)
        tag = int(self.tag.get(state))
        if tag != 0:
            target.add(tag)


class OptionAddCountEffectModel(OptionEffectModel):
    type: Literal["AddCount"]
    target: OptionEffectTargets
    tag: OptionParameterModel
    count: OptionParameterModel

    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        if not self.check_condition(state): return
        target = state.get_target(self.target)
        tag = int(self.tag.get(state))
        count = int(self.count.get(state))
        if tag != 0:
            target[tag] = target.get(tag, 0) + count

class OptionWhiteOrBlacklist(OptionInputModel):
    type: Literal["WhiteOrBlacklist"]
    tag: OptionParameterModel

    def get_class(self) -> Tuple[Type[Options.Option], Dict]:
        namespace = super().get_class()[1]

        ## Define the choices
        namespace["option_whitelist"] = 0
        namespace["option_none"] = 1
        namespace["option_blacklist"] = 2

        return Options.Choice, namespace

    def evaluate(self, state: gtfo_options.OptionEvaluationState):
        instance = self.get_option(state)
        instance: Options.Choice
        self.output = instance.value

        if not self.check_condition(state): return
        tag = int(self.tag.get(state))
        if tag != 0:
            if self.output == 0:
                state.world.whitelist_tags.add(tag)
            elif self.output == 2:
                state.world.blacklist_tags.add(tag)

OptionTypes = Annotated[
    Union[
        OptionToggleModel,
        OptionChoiceModel,
        OptionRangeModel,
        OptionToBoolOperationModel,
        OptionNotOperationModel,
        OptionNegateOperationModel,
        OptionReciprocalOperationModel,
        OptionOrOperation,
        OptionAndOperation,
        OptionEqualsOperation,
        OptionDoesNotEqualOperation,
        OptionLessThanOperation,
        OptionLessThanOrEqualOperation,
        OptionGreaterThanOperation,
        OptionGreaterThanOrEqualOperation,
        OptionAddOperation,
        OptionSubtractOperation,
        OptionMultiplyOperation,
        OptionDivideOperation,
        OptionConditionalOperation,
        OptionLinearMapOperation,
        OptionAddToSetEffectModel,
        OptionAddCountEffectModel,
        OptionWhiteOrBlacklist,
    ],
    Field(discriminator="type")
]
