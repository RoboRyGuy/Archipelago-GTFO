from typing import override
from rules.rule_builder import *
from worlds.gtfo import GTFOWorld

class CanGoal(Rule[GTFOWorld], game="My Game"):

    def __init__(self):
        pass

    @override
    def _instantiate(self, world: GTFOWorld) -> Rule.Resolved:
        # caching_enabled only needs to be passed in when your world inherits from CachedRuleBuilderWorld
        return self.Resolved(world.required_mcguffins, player=world.player, caching_enabled=True)

    class Resolved(Rule.Resolved):
        goal: int

        @override
        def _evaluate(self, state: CollectionState) -> bool:
            return state.has("McGuffin", self.player, count=self.goal)

        @override
        def item_dependencies(self) -> dict[str, set[int]]:
            # this function is only required if you have caching enabled
            return {"McGuffin": {id(self)}}

        @override
        def explain_json(self, state: CollectionState | None = None) -> list[JSONMessagePart]:
            # this method can be overridden to display custom explanations
            return [
                {"type": "text", "text": "Goal with "},
                {"type": "color", "color": "green" if state and self(state) else "salmon", "text": str(self.goal)},
                {"type": "text", "text": " McGuffins"},
            ]
        
        @override
        def item_dependencies(self) -> dict[str, set[int]]:
            return {self.item_name: {id(self)}}