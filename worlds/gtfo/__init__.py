# world/gtfo/__init__.py

import math
import os
import json
import itertools as itertools
from collections.abc import Sequence
from sqlite3 import SQLITE_DBCONFIG_LEGACY_FILE_FORMAT
from tarfile import _Bz2ReadableFileobj
from typing import cast, Any, Callable, Dict, Set, List, Optional, TextIO, Union, Mapping

from BaseClasses import CollectionState, MultiWorld, Region, Item, Location, LocationProgressType, Entrance, \
                        Tutorial, ItemClassification

from worlds.AutoWorld import World
from worlds.generic import Rules
import settings
import Utils

from .options import GTFOOptions, gtfo_option_groups
from .mid_model import *


class GTFOItem(Item):
    game: str = "GTFO"

class GTFOLocation(Location):
    game: str = "GTFO"

class GTFORegion(Region):
    game: str = "GTFO"

class GTFOSettings(settings.Group):
    """Settings class for GTFO (unused)"""

def id_to_index(id: int) -> int:
    """Convert an ID to an index. Here in case I change the implementation later"""
    return id - 1

class GTFOWorld(World):
    """
    GTFO is a cooperative first-person shooter developed by 10 Chambers. 
    Teams of 4 players take on the role of prisoners forced to explore a vast underground complex 
     filled with terrifying creatures in a series of `Expeditions`.
    Working together, they must use stealth, teamwork, and their limited resources to fend off 
     dangerous foes, complete their objective stack, and extract alive.
    """

    game = "GTFO"
    options_dataclass = GTFOOptions
    options: GTFOOptions
    topology_present = True; ## Show paths to relevant location checks in spoiler

    origin_region_name: str = "Menu" ## Set to match client
    item_name_to_id: Mapping[GTFOItem, int] = {}
    location_name_to_id: Mapping[GTFOLocation, int] = {}
    item_name_groups: Mapping[str, Set[str]] = {}

    mid_model: Mid_GameData

    #@classmethod
    #def stage_assert_generate(cls, multiworld: "MultiWorld") -> None:
    #    """
    #    Checks that a game is capable of generating, such as checking for some base file like a ROM.
    #    This gets called once per present world type. Not run for unittests since they don't produce output.
    #    """

    def generate_early(self) -> None:
        """
        Run before any general steps of the MultiWorld other than options. Useful for getting and adjusting option
        results and determining layouts for entrance rando etc. start inventory gets pushed after this step.
        """

        ## Load modded instance data
        filename = f"{self.multiworld.get_player_name(self.player)}.mid"
        filepath = f"{Utils.local_path()}/Players/{filename}"
        try:
            print("Trying to find mid file at path: " + filepath)
            with open(filepath, "r") as modded_data:
                self.mid_model = Mid_GameData(json.load(modded_data))
        except:
            raise

    def create_regions(self) -> None:
        """
        Method for creating and connecting regions for the World.
        """

        ## Fetch regions and paths
        mid_regions = self.mid_model.get_regions()

        ## Menu region (usually first item)
        menu_region = None
        for r in mid_regions:
            if r.get_name() == self.origin_region_name:
                menu_region = r
                break
        else:
            raise
        menu_region: Mid_Region

        ## Set of all reachable regions
        expeditions = [ 
            exp for exp in self.mid_model.get_expeditions() if exp.get_name() in self.options.required_expeditions 
        ]
        reachable_region_ids = { i for exp in expeditions for i in exp.get_reachable_regions() }
        reachable_region_ids.add(menu_region.get_id())

        ## Create the region and add them to AP
        regions = { 
            i: GTFORegion(mid_regions[id_to_index(i)].get_name(), self.player, self.multiworld) 
                for i in reachable_region_ids 
        }
        self.multiworld.regions.extend(regions.values)

        ## Create paths between regions
        mid_tags = self.mid_model.get_tags()
        mid_paths = self.mid_model.get_paths()
        for mid_path in mid_paths:
            start_id = mid_path.get_starting_region()
            if not start_id in reachable_region_ids: continue

            end_id = mid_path.get_ending_region()
            if not end_id in reachable_region_ids: continue

            start_region = regions[id_to_index(start_id)]
            end_region = regions[id_to_index(end_id)]

            entrance = start_region.connect(end_region)

            reqs = mid_path.get_req_item()
            req_type = reqs.get_type()
            if req_type == "None":
                pass
            elif req_type == "Item":
                mid_tag = mid_tags[id_to_index(reqs.get_target())]
                Rules.set_rule(entrance, lambda state, item=mid_tag.get_name(): state.has(item, mid_path.get_req_count()))
            elif req_type == "Category":
                mid_tag = mid_tags[id_to_index(reqs.get_target())]
                Rules.set_rule(entrance, lambda state: state.has(mid_tag.get_name(), mid_path.get_req_count()))





        ## TODO: Paths, locations, items, completion condtion
                
    def create_item(self, item_name: str) -> GTFOItem:
        """
        Create an item for this world type and player.
        Warning: this may be called with self.world = None, for example by MultiServer
        """


        return GTFOItem(item_name, classification, None, self.player)

    def create_filler(self) -> GTFOItem:
        """
        Create a random filler item, which may be a trap item
        """

        ran: float = self.random.random()
        if ran < self.trap_percent:
            choice = self.random.choices(self.mid_model.traps, cum_weights=self.trap_weights, k=1)[0]
            return GTFOItem(choice.name, ItemClassification.trap, None, self.player)
        else:
            choice = self.random.choices(self.mid_model.fillers, cum_weights=self.trap_weights, k=1)[0]
            return GTFOItem(choice.name, ItemClassification.filler, None, self.player)

    def create_items(self) -> None:
        """
        Method for creating and submitting items to the itempool. Items and Regions must *not* be created and submitted
        to the MultiWorld after this step. If items need to be placed during pre_fill use `get_pre_fill_items`.
        """


    #def set_rules(self) -> None:
    #    """Method for setting the rules on the World's regions and locations."""
    #    pass

    #def connect_entrances(self) -> None:
    #    """Method to finalize the source and target regions of the World's entrances"""
    #    pass

    #def generate_basic(self) -> None:
    #    """
    #    Useful for randomizing things that don't affect logic but are better to be determined before the output stage.
    #    i.e. checking what the player has marked as priority or randomizing enemies
    #    """
    #    pass

    #def pre_fill(self) -> None:
    #    """Optional method that is supposed to be used for special fill stages. This is run *after* plando."""
    #    pass

    #def fill_hook(self,
    #              progitempool: List["Item"],
    #              usefulitempool: List["Item"],
    #              filleritempool: List["Item"],
    #              fill_locations: List["Location"]) -> None:
    #    """Special method that gets called as part of distribute_items_restrictive (main fill)."""
    #    pass

    #def post_fill(self) -> None:
    #    """
    #    Optional Method that is called after regular fill. Can be used to do adjustments before output generation.
    #    This happens before progression balancing, so the items may not be in their final locations yet.
    #    """
    #    pass

    #def generate_output(self, output_directory: str) -> None:
    #    """
    #    This method gets called from a threadpool, do not use multiworld.random here.
    #    If you need any last-second randomization, use self.random instead.
    #    """
    #    pass

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
        # The reason for the `Mapping` type annotation, rather than `dict`
        # is so that type checkers won't worry about the mutability of `dict`,
        # so you can have more specific typing in your world implementation.

        return {
            "required_expeditions": [ exp.name for exp in self.required_expeditions ],
            "lock_expeditions": self.options.lock_expeditions.value,
            "lock_gear": self.options.lock_gear.value,
            "lock_player_slots": self.options.lock_player_slots.value,
        }

    #def extend_hint_information(self, hint_data: Dict[int, Dict[int, str]]):
    #    """
    #    Fill in additional entrance information text into locations, which is displayed when hinted.
    #    structure is {player_id: {location_id: text}} You will need to insert your own player_id.
    #    """
    #    pass

    #def modify_multidata(self, multidata: "MultiData") -> None:
    #    """For deeper modification of server multidata."""
    #    pass

    # Spoiler writing is optional, these may not get called.
    #def write_spoiler_header(self, spoiler_handle: TextIO) -> None:
    #    """
    #    Write to the spoiler header. If individual it's right at the end of that player's options,
    #    if as stage it's right under the common header before per-player options.
    #    """
    #    pass

    #def write_spoiler(self, spoiler_handle: TextIO) -> None:
    #    """
    #    Write to the spoiler "middle", this is after the per-player options and before locations,
    #    meant for useful or interesting info.
    #    """
    #    pass

    #def write_spoiler_end(self, spoiler_handle: TextIO) -> None:
    #    """Write to the end of the spoiler"""
    #    pass

