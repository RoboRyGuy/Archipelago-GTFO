from __future__ import annotations

import dataclasses
import itertools
from typing import Any, cast, ClassVar, FrozenSet, override, TYPE_CHECKING

from NetUtils import JSONMessagePart
from rule_builder.rules import FieldResolver, Has, resolve_field, Rule, TWorld
from worlds.AutoWorld import CollectionState

if TYPE_CHECKING:
    from . import GTFOWorld

@dataclasses.dataclass()
class GTFOHas(Rule[TWorld], game="GTFO"):
    """A rule that checks if the player has at least `count` of a given item in a particular state"""

    state: int | FieldResolver
    """The state in which to search for the item"""

    item_name: str | FieldResolver
    """The item to check for"""

    count: int | FieldResolver = 1
    """The count the player is required to have"""

    @override
    def _instantiate(self, world: TWorld) -> Rule.Resolved:
        item_name = resolve_field(self.item_name, world, str)
        return GTFOHas.Resolved(
            item_name=item_name,
            item_state_name=f"C#{resolve_field(self.state, world, int)} {item_name}",
            count=resolve_field(self.count, world, int),
            player=world.player,
            caching_enabled=getattr(world, "rule_caching_enabled", False),
        )

    @override
    def __str__(self) -> str:
        count = f", count={self.count}" if isinstance(self.count, FieldResolver) or self.count > 1 else ""
        options = f", options={self.options}" if self.options else ""
        return f"{self.__class__.__name__}({self.item_name}{count}{options})"

    class Resolved(Rule.Resolved):
        item_name: str
        item_state_name: str
        count: int = 1
        skip_cache: ClassVar[bool] = True

        @override
        def _evaluate(self, state: CollectionState) -> bool:
            # implementation based on Has.Resolved._evaluate
            counts = state.prog_items[self.player]
            return (counts[self.item_name] + counts[self.item_state_name]) >= self.count

        @override
        def item_dependencies(self) -> dict[str, set[int]]:
            return {
                self.item_name: { id(self) },
                self.item_state_name: { id(self) },
            }

        @override
        def explain_json(self, state: CollectionState | None = None) -> list[JSONMessagePart]:
            verb = "Missing " if state and not self(state) else "Has "
            messages: list[JSONMessagePart] = [{"type": "text", "text": verb}]
            if self.count > 1:
                messages.append({"type": "color", "color": "cyan", "text": str(self.count)})
                messages.append({"type": "text", "text": "x "})
            if state:
                color = "green" if self(state) else "salmon"
                messages.append({"type": "color", "color": color, "text": self.item_name})
            else:
                messages.append({"type": "item_name", "flags": 0b001, "text": self.item_name, "player": self.player})
            return messages

        @override
        def explain_str(self, state: CollectionState | None = None) -> str:
            if state is None:
                return str(self)
            prefix = "Has" if self(state) else "Missing"
            count = f"{self.count}x " if self.count > 1 else ""
            return f"{prefix} {count}{self.item_name}"

        @override
        def __str__(self) -> str:
            count = f"{self.count}x " if self.count > 1 else ""
            return f"Has {count}{self.item_name}"

@dataclasses.dataclass()
class GTFOHasGroup(Rule[TWorld], game="GTFO"):
    """A rule that checks if the player has at least `count` of the items present in the specified item group"""

    state: int | FieldResolver
    """The state in which to search for the item"""

    item_group_name: str | FieldResolver
    """The name of the item group containing the items"""

    count: int | FieldResolver = 1
    """The number of items the player needs to have"""

    @override
    def _instantiate(self, world: GTFOWorld) -> Rule.Resolved:
        item_group_name = resolve_field(self.item_group_name, world, str)
        return self.Resolved(
            item_group_name=item_group_name,
            item_group=world.get_item_group(item_group_name, None),
            item_state_group=world.get_item_group(item_group_name, resolve_field(self.state, world, int)),
            count=resolve_field(self.count, world, int),
            player=world.player,
            caching_enabled=getattr(world, "rule_caching_enabled", False),
        )

    @override
    def __str__(self) -> str:
        count = f", count={self.count}" if isinstance(self.count, FieldResolver) or self.count > 1 else ""
        options = f", options={self.options}" if self.options else ""
        return f"{self.__class__.__name__}({self.item_group_name}{count}{options})"

    class Resolved(Rule.Resolved):
        item_group_name: str
        item_group: FrozenSet[str]
        item_state_group: FrozenSet[str]
        count: int = 1

        @override
        def _evaluate(self, state: CollectionState) -> bool:
            # implementation based on state.has_group
            found = 0
            player_prog_items = state.prog_items[self.player]
            for item_name in itertools.chain(self.item_group, self.item_state_group):
                found += player_prog_items[item_name]
                if found >= self.count:
                    return True
            return False

        @override
        def item_dependencies(self) -> dict[str, set[int]]:
            return {item: {id(self)} for item in itertools.chain(self.item_group, self.item_state_group)}

        @override
        def explain_json(self, state: CollectionState | None = None) -> list[JSONMessagePart]:
            messages: list[JSONMessagePart] = [{"type": "text", "text": "Has "}]
            if state is None:
                messages.append({"type": "color", "color": "cyan", "text": str(self.count)})
            else:
                count = sum(
                    state.prog_items[self.player][item_name]
                    for item_name in itertools.chain(self.item_group, self.item_state_group)
                )
                color = "green" if count >= self.count else "salmon"
                messages.append({"type": "color", "color": color, "text": f"{count}/{self.count}"})
            messages.append({"type": "text", "text": " items from "})
            messages.append({"type": "color", "color": "cyan", "text": self.item_group_name})
            return messages

        @override
        def explain_str(self, state: CollectionState | None = None) -> str:
            if state is None:
                return str(self)
            count = sum(
                state.prog_items[self.player][item_name]
                for item_name in itertools.chain(self.item_group, self.item_state_group)
            )
            return f"Has {count}/{self.count} items from {self.item_group_name}"

        @override
        def __str__(self) -> str:
            count = f"{self.count}x items" if self.count > 1 else "an item"
            return f"Has {count} from {self.item_group_name}"