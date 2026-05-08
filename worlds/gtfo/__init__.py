# world/gtfo/__init__.py

import json
from typing import cast, Set, List, Optional, Mapping, override
from unicodedata import category

from BaseClasses import MultiWorld, CollectionState, Region, Entrance, Location, LocationProgressType, \
                        Item, ItemClassification, Tutorial
import rule_builder
from rule_builder.cached_world import CachedRuleBuilderWorld
from rule_builder.rules import Rule, And, Or, Has, HasGroup, CanReachRegion, HasAll 

import collections
import itertools
import logging
import Options
import rule_builder.rules
import settings
import Utils

from .options import GTFOOptions
from .mid_model import *
from .gen_model import *


class GTFORegion(Region):
    game: str = "GTFO"

class GTFOLocation(Location):
    game: str = "GTFO"

class GTFOItem(Item):
    game: str = "GTFO"

class GTFOSettings(settings.Group):
    """Settings class for GTFO (unused)"""

class GTFOWorld(CachedRuleBuilderWorld):
    """
    GTFO is a cooperative first-person shooter developed by 10 Chambers. 
    Teams of 4 players take on the role of prisoners forced to explore a vast underground complex 
     filled with terrifying creatures in a series of `Expeditions`.
    Working together, they must use stealth, teamwork, and their limited resources to fend off 
     dangerous foes, complete their objective stack, and extract alive.
    """

    game = "GTFO"
    topology_present = True;

    options_dataclass = GTFOOptions
    options: GTFOOptions

    ## Constants
    origin_region_name: str = "Menu"

    ## Required by AP
    location_name_to_id: Mapping[str, int] = dict()
    item_name_to_id: Mapping[str, int] = dict()
    item_name_groups: Mapping[str, Set[str]]
    item_mapping: Mapping[str, str] = dict()

    ## Used for generation
    logger: logging.Logger
    gen_model: Gen_GameData
    tag_model_lookup: Mapping[int, Gen_Tag]
    item_model_lookup: Mapping[int, Gen_Item]
    empty_item_model: Gen_Item

    ## Slot data
    root_seed: int
    required_expeditions: Set[str]
    whitelist_tags: Set[int]
    blacklist_tags: Set[int]
    require_secondaries: bool
    require_overloads: bool


    @override
    def generate_early(self) -> None:
        """
        Run before any general steps of the MultiWorld other than options. Useful for getting and adjusting option
        results and determining layouts for entrance rando etc. start inventory gets pushed after this step.
        """

        ## Load modded instance data
        filename = f"{self.multiworld.get_player_name(self.player)}.ini"
        filepath = f"{Utils.local_path()}/Players/{filename}"
        try:
            with open(filepath, "r") as modded_data:
                mid_model = Mid_GameData(json.load(modded_data))
        except OSError as e:
            raise Exception(
                f"Failed to find GTFO MID file for player: {self.multiworld.get_player_name(self.player)}"
                + f"\nChecked at: {filepath}"
            ) from e
        except json.JSONDecodeError as e:
            raise Exception(
                f"Failed to parse GTFO MID file for player: {self.multiworld.get_player_name(self.player)}"
            ) from e

        try:
            self.gen_model = Gen_GameData(mid_model)
        except Exception as e:
            raise Exception(
                f"Malformed GTFO MID file for player: {self.multiworld.get_player_name(self.player)}"
            ) from e

        del mid_model

        ## Some init data
        self.item_name_groups = collections.defaultdict(set) # Dictionary which auto-creates sets if needed
        self.logger = logging.getLogger(f"{self.multiworld.get_player_name(self.player)}.GTFO")
        self.root_seed = self.random.randrange(0, 2**55) ## I could do 2**63... but why?
        self.required_expeditions = self.options.required_expeditions.value
        self.require_secondaries = self.options.require_secondaries
        self.require_overloads = self.options.require_overloads

        ## Set up location and item lookup dicts for AP (because it's greedy)
        self.tag_model_lookup = { tag.id: tag for tag in self.gen_model.tags }
        
        for loc in self.gen_model.locations:
            name_tag = self.tag_model_lookup.get(loc.name_tag, None)
            if name_tag is None:
                continue ## I don't think we really care at this stage
            self.location_name_to_id[name_tag.name] = loc.id
        
        for item in self.gen_model.items:
            name_tag = self.tag_model_lookup.get(item.name_tag, None)
            if name_tag is None:
                continue ## I don't think we really care at this stage
            self.item_name_to_id[name_tag.name] = item.id

        ## Add the start_inventory setting to our options so AP finds it (it'll be empty)
        self.options.start_inventory = Options.StartInventory(dict())
        
    @override
    def create_regions(self) -> None:
        """
        For the sake of simplicity, we will do all our work in this one method
        """

        #######################################################################
        ## Tags

        tags_by_name = { tag.name: tag for tag in self.gen_model.tags }

        self.whitelist_tags = set()
        for name in itertools.chain(self.options.whitelist, ["Always"]):
            item_tag = tags_by_name.get(name, None)
            if item_tag is None: 
                if name != "Always": ## This tag normally isn't generated
                    self.logger.warn(f"Failed to find whitelist tag: {name}")
                continue
            self.whitelist_tags.add(item_tag.id)

        self.blacklist_tags = set()
        for name in itertools.chain(self.options.blacklist, ["Never"]):
            item_tag = tags_by_name.get(name, None)
            if item_tag is None:
                self.logger.warn(f"Failed to find blacklist tag: {name}")
                continue
            self.blacklist_tags.add(item_tag.id)

        ## Local variables declared separately to control the lambda
        whitelist = self.whitelist_tags 
        blacklist = self.blacklist_tags 

        def tag_matches(tag: int, tag_set: Set[int]) -> bool:
            """Check if a tag matches against a particular set, and add it (and its parents) if it does"""
            result = tag != 0 and ( tag in tag_set or tag_matches(self.tag_model_lookup[tag].parent, tag_set) )
            if result:
                tag_set.add(tag)
            return result
        def tag_listed(tag: int) -> bool:
            """Check if a tag matches the whitelist and not the blacklist"""
            return tag_matches(tag, whitelist) and not tag_matches(tag, blacklist)

        def tags_listed(*tags: int) -> bool:
            """Check if any of a set of tags is allowed"""
            return any( tag_listed(tag) for tag in tags )

        #######################################################################
        ## Regions
        
        ## Find all the regions we're working with
        expedition_lookup = { exp.name: exp for exp in self.gen_model.expeditions }
        reachable_region_ids: Set[int]

        if "All" in self.required_expeditions:
            if len(self.required_expeditions) > 1:
                self.logger.error(
                    "When using the \"All\" expedition filter, it should be the only filter."
                    + "All other entries are being ignored!"
                )
                reachable_region_ids = { r.id for r in self.gen_model.regions }

        else:
            reachable_region_ids = set()
            for exp in self.required_expeditions:
                edata = expedition_lookup.get(exp, None)
                if edata is None:
                    self.logger.warn(f"Failed to find and enable expedition: {exp}")
                    continue
            reachable_region_ids.update(edata.reachable_regions)
        
            ## We'll handle the origin region as a special case
            for r in self.gen_model.regions:
                if r.name == self.origin_region_name:
                    reachable_region_ids.add(r.id)
                    break
            else:
                self.logger.error("Failed to find origin region ID")

        ## Create the regions!
        region_lookup = { 
            r.id: GTFORegion(r.name, self.player, self.multiworld)  
                for r in self.gen_model.regions if r.id in reachable_region_ids
        }
        if any( i not in region_lookup for i in reachable_region_ids ):
            self.logger.error("Failed to find all expected regions during creation!")
        self.multiworld.regions += region_lookup.values()
            
        #######################################################################
        ## Locations and Items Init

        ## Init item lookup
        self.item_model_lookup = { i.id: i for i in self.gen_model.items }

        ## Find the empty item - this is needed to create filler when items are moved to starting items
        empty_id = self.item_name_to_id.get("Empty", None)
        if empty_id is None:
            self.logger.error("Failed to find empty item ID!")
        else:
            self.empty_item_model = self.item_model_lookup.get(empty_id, None)
            if self.empty_item_model is None:
                self.logger.error("Failed to find empty item model!")

        ## Fetch and set randomization on relevant locations
        reachable_locations = [ 
            loc for loc in self.gen_model.locations 
                if all( r in reachable_region_ids for r in loc.owning_regions ) 
        ]
        for loc in reachable_locations: 
            loc.is_randomized = tags_listed(loc.name_tag, loc.tag2, loc.tag3)

        ## Set randomization on relevant items - we won't really be referencing the relevant item set after this
        relevant_item_ids = { loc.item_id for loc in reachable_locations if loc.item_id != 0 }
        relevant_item_ids.update(self.gen_model.floating_items)
        for item_id in relevant_item_ids:
            gen_item = self.item_model_lookup.get(item_id, None)
            if gen_item is None:
                self.logger.error(f"Failed to look up item by ID: {item_id}")
                continue
            gen_item.is_randomized = \
                (gen_item.required_expedition is None or gen_item.required_expedition in self.required_expeditions) \
                and tags_listed(gen_item.name_tag, gen_item.tag2, gen_item.tag3)

        #######################################################################
        ## FLoating Item Distribution

        floating_items: List[int]
        def distribute(empty_locations: List[Gen_Location]) -> None:
            """Helper to distribute currently queued floating items into available empty locations"""
            if not floating_items: ## Must have at least one floating item to distribute
                return

            step: float
            if len(floating_items) >= len(empty_locations):
                step = 1.0 ## Fill all locations
            else:
                step = len(floating_items) / len(empty_locations)
            count: float = 0.2 ## Starts at .2 to avoid rounding issues

            for i in range(len(empty_locations)):
                count += step
                if count >= 1.0:
                    index: int = (i + abs(self.root_seed)) % len(empty_locations)
                    if empty_locations[index].item_id != 0:
                        raise Exception("Overwriting floating item ID. I messed up somewhere!")
                    empty_locations[index].item_id = floating_items.pop(0)
                    count -= 1.0

        
        ## Round 1: Progression items into priority locations
        floating_items = [ 
            i for i in self.gen_model.floating_items 
                if self.item_model_lookup[i].is_randomized 
                and self.item_model_lookup[i].rand_data.is_progression
        ]
        seen_items = { f for f in floating_items }
        distribute([
            l for l in reachable_locations 
                if l.is_randomized 
                and l.item_id == 0 
                and l.rand_data.priority_mode == "Priority" 
        ])

        ## Round 2: Progression items in all locations
        distribute([
            l for l in reachable_locations 
                if l.is_randomized 
                and l.item_id == 0 
                and l.rand_data.priority_mode != "Excluded" 
        ])

        ## Round 3: All items into all locations
        floating_items.extend(
            i for i in self.gen_model.floating_items 
                if self.item_model_lookup[i].is_randomized 
                and not i in seen_items
        )
        distribute([
            l for l in reachable_locations 
                if l.is_randomized 
                and l.item_id == 0 
        ])

        ## Round 4: All remaining items are given
        for i in floating_items:
            name = self.tag_model_lookup[self.item_model_lookup[i].name_tag].name
            self.logger.warn(f"Not enough empty locations. Adding starting item: {name}")
            self.push_precollected(self.create_item_by_id(i))
        
        #######################################################################
        ## Item Creation and Submission
        
        rand_items: List[Gen_Item] = []
        for gen_location in reachable_locations:
            ## Any location still empty is ignored!
            if gen_location.item_id == 0:
                continue
            
            ## Identify the name
            name_tag = self.tag_model_lookup.get(gen_location.name_tag, None)
            if name_tag is None:
                self.logger.error(f"Name tag for location {gen_location.id} not found!")
                continue

            ## Identify the main region
            if not gen_location.owning_regions:
                self.logger.error(f"Location not contained in any regions: {name_tag.name}")
                continue
            main_region = region_lookup.get(gen_location.owning_regions[0], None)
            if main_region is None:
                self.logger.error(f"Location's main region could not be found: {name_tag.name}")
                continue

            ## Build the location and item pair
            location = GTFOLocation(self.player, name_tag.name, gen_location.id, main_region)
            main_region.locations.append(location)

            ## Add the access rule (if needed)
            if len(gen_location.owning_regions) > 1:
                rule = And(*( CanReachRegion(region_lookup[r].name) for r in gen_location.owning_regions[1:] ))
                self.set_rule(location, rule)

            ## Either pair them together or randomize them!
            gen_item = self.item_model_lookup[gen_location.item_id]
            if gen_location.is_randomized and gen_item.is_randomized:
                rand_items.append(gen_item)
                item_tag = self.tag_model_lookup[gen_item.name_tag]
                self.logger.debug(f"Randomized: {location.name} - {item_tag.name}")
            else:
                item = self.create_item_by_model(gen_item)
                location.place_locked_item(item)
                self.logger.debug(f"Locked: {location.name} - {item.name}")
        
        #######################################################################
        ## Early and Start Items

        ## Starting items
        for tag, count in self.options.start_items.items():

            ## Collect matching items
            gen_tag = tags_by_name.get(tag, None)
            if gen_tag is None:
                self.logger.warn(f"Failed to find starting item tag: {tag}")
                continue
            whitelist = { gen_tag.id }
            blacklist = set()

            matches = [ (1 if tags_listed(gi.name_tag, gi.tag2, gi.tag3) else 0) for gi in rand_items ]
            match_count = sum(matches)

            ## Filter/warn by count
            if match_count < count:
                self.logger.warn(f"Requested {count} start items matching {tag}, only found {match_count}")

            ## Select our items and apply!
            sample = self.random.sample(range(len(rand_items)), count, counts=matches)
            for i in reversed(sample):
                gen_item = rand_items.pop(i)
                item = self.create_item_by_model(gen_item)
                self.multiworld.push_precollected(item)
                self.multiworld.itempool.append(self.create_filler()) ## To keep it balanced
                self.logger.info(f"Added {item.name} as a starting item")

        ## Similar process for the early items
        for tag, count in self.options.early_items.items():
            
            ## Collect matching items
            gen_tag = tags_by_name.get(tag, None)
            if gen_tag is None:
                self.logger.warn(f"Failed to find early item tag: {tag}")
                continue
            whitelist = { gen_tag.id }
            blacklist = set()

            matches = [ (1 if tags_listed(gi.name_tag, gi.tag2, gi.tag3) else 0) for gi in rand_items ]
            match_count = sum(matches)

            ## Filter/warn by count
            if match_count < count:
                self.logger.warn(f"Requested {count} early items matching {tag}, only found {match_count}")

            ## Get or create our early item dictionary
            early_dict = self.multiworld.early_items.get(self.player, None)
            if early_dict is None:
                early_dict = dict()
                self.multiworld.early_items[self.player] = early_dict

            ## Select our items and apply!
            sample = self.random.sample(range(len(rand_items)), count, counts=matches)
            for i in reversed(sample):
                gen_item = rand_items.pop(i)
                item = self.create_item_by_model(gen_item)
                self.multiworld.itempool.append(item)
                early_dict[item.name] = early_dict.get(item.name, 0) + 1
                self.logger.info(f"Added {item.name} as an early item")

        ## Finally, we simply add any remaining randomized items to the pool
        self.multiworld.itempool.extend(self.create_item_by_model(m) for m in rand_items)
        
        #######################################################################
        ## Paths - Added after items to ensure item_name_groups is valid

        for gen_path in self.gen_model.paths:

            ## Get the regions, check if path exists
            starting_region = region_lookup.get(gen_path.starting_region, None)
            ending_region = region_lookup.get(gen_path.ending_region, None)
            if starting_region is None or ending_region is None:
                continue
            path_name = f"{starting_region.name} -> {ending_region.name}" \
                if gen_path.name is None else gen_path.name

            ## Build the rule
            rule: Rule = None
            if gen_path.req_item.type != "None":
                target_tag = self.tag_model_lookup.get(gen_path.req_item.target, None)
                if target_tag is None:
                    self.logger.error(f"Failed to create accurate path reqs for path: {path_name}")
                    target_tag = tags_by_name["Never"]

                if gen_path.req_item.type == "Item":
                    rule = Has(target_tag.name, gen_path.req_count)
                elif gen_path.req_item.type == "Category":
                    rule = HasGroup(target_tag.name, gen_path.req_count)
                else:
                    raise Exception(f"Unknown path req type: {gen_path.req_item.type}")

                if gen_path.alt_item.type != "None":
                    target_tag = self.tag_model_lookup.get(gen_path.alt_item.target, None)
                    if target_tag is None:
                        self.logger.error(f"Failed to create accurate path reqs for path: {path_name}")
                        target_tag = tags_by_name["Never"]
                        
                    if gen_path.alt_item.type == "Item":
                        rule = Or(rule, Has(target_tag.name, 1))
                    elif gen_path.alt_item.type == "Category":
                        rule = Or(rule, HasGroup(target_tag.name, 1))
                    else:
                        raise Exception(f"Unknown path alt type: {gen_path.alt_item.type}")

            ## Create the path!
            starting_region.connect(ending_region, path_name, rule)
            self.logger.debug(f"Path {starting_region.name} -> {ending_region.name} | Requires { gen_path.req_count }x { self.tag_model_lookup.get(gen_path.req_item.target, type("temp", (), { "name": "None" })).name }")

        #######################################################################
        ## Win Condition

        ## Set the tags so we can filter by tag for relevant goal items
        whitelist = { tags_by_name["Goal Items"].id } ## By default, all goal items
        blacklist = { ## Blacklist all goal items for expeditions we're not completing
            tags_by_name[f"{exp.name} Goal Items"].id for exp in self.gen_model.expeditions 
                if exp.name not in self.required_expeditions 
        }

        if not self.options.require_secondaries:
            blacklist.update( tags_by_name[f"{exp} (Secondary) Sector Clear"] for exp in self.required_expeditions )
        if not self.options.require_overloads:
            blacklist.update( tags_by_name[f"{exp} (Overload) Sector Clear"] for exp in self.required_expeditions )

        ## Check each item ID that is *actually* spawned (including if it's spawned multiple times)
        all_item_ids = itertools.chain( 
            ( loc.item_id for loc in reachable_locations if loc.item_id != 0 ),
            self.gen_model.floating_items
        )
        win_items: List[str] = [ ]

        for item_id in all_item_ids:
            gen_item = self.item_model_lookup.get(item_id, None)
            if gen_item is None:
                self.logger.warn(f"Failed to look up potential goal item with ID: {item_id}")
                continue

            if (gen_item.required_expedition is None or gen_item.required_expedition in self.required_expeditions) \
                and tags_listed(gen_item.name_tag, gen_item.tag2, gen_item.tag3):

                name_tag = self.tag_model_lookup.get(gen_item.name_tag, None)
                if name_tag is None:
                    self.logger.error(f"Failed to find name tag for win item: {item_id}")
                else:
                    win_items.append(name_tag.name)

        rule = HasAll( *win_items )
        self.set_completion_rule(rule)


    @override
    def create_item(self, item_name: str) -> GTFOItem:
        """
        Create an item for this world type and player.
        Warning: this may be called with self.world = None, for example by MultiServer
        """
        if item_name == "Empty":
            return self.create_filler()
        else:
            item_id = self.item_name_to_id.get(item_name, None)
            if item_id is None:
                self.logger.warn(f"Failed to look up item by name: {item_name}, using filler instead")
                return self.create_filler()
            return self.create_item_by_id(item_id)
    

    def create_item_by_id(self, item_id: int) -> GTFOItem:
        
        gen_item = self.item_model_lookup.get(item_id, None)
        if gen_item is None:
            self.logger.error(f"Failed to create item by id: {item_id}, using filler instead")
            return self.create_filler()
        
        return self.create_item_by_model(gen_item)

    def create_item_by_model(self, gen_item: Gen_Item) -> GTFOItem:

        ## Create classification data
        classification: ItemClassification = cast(ItemClassification, 0)
        if gen_item.rand_data.is_progression:
            classification |= ItemClassification.progression
        if gen_item.rand_data.is_useful:
            classification |= ItemClassification.useful
        if gen_item.rand_data.is_filler:
            classification |= ItemClassification.filler
        if gen_item.rand_data.is_trap:
            classification |= ItemClassification.trap
        if gen_item.rand_data.do_skip_balancing:
            classification |= ItemClassification.skip_balancing
        if gen_item.rand_data.is_deprioritized:
            classification |= ItemClassification.deprioritized

        ## Create the item itself and add custom proprties
        name_tag = self.tag_model_lookup.get(gen_item.name_tag, None)
        if name_tag is None:
            self.logger.error(f"Failed to find name tag for item with id: {gen_item.id}")
            return self.create_filler()
        item = GTFOItem(name_tag.name, classification, gen_item.id, self.player)

        ## Evaluate path reqs and add as category if needed
        if gen_item.path_reqs.type == "Category":
            category_tag = self.tag_model_lookup.get(gen_item.path_reqs.target, None)
            if category_tag is None:
                self.logger.warn(f"Failed to find and set category for item: {item.name}")
            else:
                self.item_mapping[item.name] = category_tag.name
                self.item_name_groups[category_tag.name].add(item.name)

        return item


    @override
    def get_filler_item_name(self):
        return "Empty"
    

    @override
    def create_filler(self) -> GTFOItem:
        """
        Create a random filler item, which may be a trap item
        """
        return self.create_item_by_model(self.empty_item_model)


    @override
    def fill_slot_data(self) -> Mapping[str, Any]:  # json of WebHostLib.models.Slot
        """
        What is returned from this function will be in the `slot_data` field
        in the `Connected` network package.
        It should be a `dict` with `str` keys, and should be serializable with json.

        This is a way the generator can give custom data to the client.
        The client will receive this as JSON in the `Connected` response.

        The generation does not wait for `generate_output` to complete before calling this.
        `threading.Event` can be used if you need to wait for something from `generate_output`.
        """

        return {
            "RootSeed": self.root_seed,
            "ExpeditionNames": self.required_expeditions,
            "WhitelistTags": self.whitelist_tags,
            "BlacklistTags": self.blacklist_tags,
            "RequiresSecondaries": self.require_secondaries,
            "RequiresOverloads": self.require_overloads,
        }

