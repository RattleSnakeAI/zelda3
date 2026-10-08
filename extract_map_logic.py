#!/usr/bin/env python3
"""Extract the structural map/logic data of Zelda 3 into a single JSON file.

Reads the original ROM directly (via the repo's own asset pipeline helpers) and
emits:

    extracted_assets/map_data.json

The JSON contains, for every dungeon, all of its rooms with
  * floor level,
  * (logical) dimensions,
  * vertical/horizontal connections (staircases & pit falls),
  * interactive elements (chests & doors),
and, for the overworld, the light/dark world dimensions plus all entrances and
holes with their destination room.

Everything is derived from real ROM tables (room headers, layer objects, chest
table, entrance tables) - nothing is hard-coded from the example schema.
"""

import json
import os
import sys

import rom_compat

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "extracted_assets")
OUT_FILE = os.path.join(OUT_DIR, "map_data.json")

NUM_ROOMS = 320          # full dungeon-room table (task only needs the first 256)
NUM_RENDER_ROOMS = 256   # rooms 0..255 get a rendered image

# "palace" index (cur_palace_index_x2) -> friendly dungeon key.
# Values come from tables.kPalaceNames: index i -> palace id (i-1)*2.
PALACE_KEY = {
    0: "church", 2: "castle", 4: "eastern_palace", 6: "desert_palace",
    8: "agahnims_tower", 10: "swamp_palace", 12: "dark_palace",
    14: "misery_mire", 16: "skull_woods", 18: "ice_palace",
    20: "tower_of_hera", 22: "thieves_town", 24: "tower_of_ganon",
    26: "ganons_tower",
}


# dungeon index (order of the in-game dungeon map layouts) -> friendly key.
# Index i corresponds to tables.kPalaceNames[i + 1].
DUNGEON_KEY = {
    0: "hyrule_castle", 1: "hyrule_castle_sewers", 2: "eastern_palace",
    3: "desert_palace", 4: "agahnims_tower", 5: "swamp_palace",
    6: "palace_of_darkness", 7: "misery_mire", 8: "skull_woods",
    9: "ice_palace", 10: "tower_of_hera", 11: "thieves_town",
    12: "turtle_rock", 13: "ganons_tower",
}



def floor_label(v):
    """Map the game's internal floor counter to a human readable label.

    The game uses 0-based floors where 0 == 1F and negative values are
    basements.
    """
    if v is None:
        return None
    if v < 0:
        return "B%d" % (-v)
    return "%dF" % (v + 1)



def stair_positions(layers):
    """Collect tile positions of every stair-like layer object."""
    out = []
    for layer in layers:
        for o in layer:
            name = o.get("n", "")
            if "stair" in name.lower():
                out.append((o["x"], o["y"]))
    return out


def pit_positions(layers):
    out = []
    for layer in layers:
        for o in layer:
            name = o.get("n", "")
            if "pit" in name.lower() or "hole" in name.lower():
                out.append((o["x"], o["y"]))
    return out


def door_entries(layers_doors):
    """Convert the raw door tuples into {direction, kind} entries."""
    out = []
    dirs = {0: "north", 1: "south", 2: "west", 3: "east"}
    for doors in layers_doors:
        for d in doors or []:
            out.append({"type": "locked_door",
                        "direction": dirs.get(d.get("dir"), "unknown"),
                        "kind": "wooden" if d.get("type", 0) < 0x80 else "bombable"})
    return out


_ENTRANCE_CACHE = {}


def get_entrance_info_safe(er, set_index):
    """Like ``extract_resources.get_entrance_info`` but skipping entries whose
    data is invalid (the German translation leaves entrances 131/132 as 0xff).
    """
    if set_index in _ENTRANCE_CACHE:
        return _ENTRANCE_CACHE[set_index]
    out = {}
    max_i = 133 if set_index == 0 else 7
    for i in range(max_i):
        try:
            room, y = er._get_entrance_info_one(i, set_index)
        except Exception:  # noqa: BLE001
            continue
        out.setdefault(room, []).append(y)
    _ENTRANCE_CACHE[set_index] = out
    return out


def read_room(er, tables, room_index):
    """Read one dungeon room's structure directly from the ROM.

    This mirrors ``assets/extract_resources.print_room`` but deliberately skips
    the enemy-sprite table: that table is relocated in the German translation
    (its offsets lack the 0x8000 page bit) and the sprites are not needed for
    the map metadata anyway. Everything else is read exactly like upstream.
    """
    get_byte, get_word = er.get_byte, er.get_word
    p = 0x1f8000 + room_index * 3
    room_addr = get_byte(p) | get_byte(p + 1) << 8 | get_byte(p + 2) << 16
    p = 0x40000 | get_word(0x4f502 + room_index * 2)
    if p == 0x4FFEF:
        p = 0x82EDC5
    floor, layout = get_byte(room_addr), get_byte(room_addr + 1)
    flags = get_byte(p + 0)
    p7, p8 = get_byte(p + 7), get_byte(p + 8)

    header = {
        "floor1": floor & 0xf,
        "floor2": floor >> 4,
        "layout": layout >> 2,
        "start_quadrant": layout & 3,
        "bg2": tables.kBg2[flags >> 5],
        "collision": tables.kCollisionNames[flags >> 2 & 7],
        "lights_out": flags & 1,
        "palette": get_byte(p + 1),
        "blockset": get_byte(p + 2),
        "enemyblk": get_byte(p + 3),
        "hole0_dest": [get_byte(p + 9), p7 & 3],
        "stair0_dest": [get_byte(p + 10), p7 >> 2 & 3],
        "stair1_dest": [get_byte(p + 11), p7 >> 4 & 3],
        "stair2_dest": [get_byte(p + 12), p7 >> 6 & 3],
        "stair3_dest": [get_byte(p + 13), p8 & 3],
        "pits_hurt_player": room_index in er.pits_hurt_player(),
    }

    layers = []
    q = room_addr + 2
    for _ in range(3):
        q, objs, doors = er.decode_room_objects(q)
        layers.append((objs, doors))

    chests = []
    for data, big in er.get_chest_info().get(room_index, []):
        chests.append("%d!" % data if big else data)

    entrances = [dict(e, room=room_index) for e in get_entrance_info_safe(er, 0).get(room_index, [])]
    starting = [dict(e, room=room_index) for e in get_entrance_info_safe(er, 1).get(room_index, [])]

    return {
        "Header": header,
        "Layer1": layers[0][0], "Layer1.doors": layers[0][1],
        "Layer2": layers[1][0], "Layer2.doors": layers[1][1],
        "Layer3": layers[2][0], "Layer3.doors": layers[2][1],
        "Chests": chests,
        "Entrances": entrances,
        "StartingPoints": starting,
    }

    return out


def extract():
    import extract_resources as er
    import tables

    room_data = {}
    for i in range(NUM_ROOMS):
        try:
            room_data[i] = read_room(er, tables, i)
        except Exception as e:  # noqa: BLE001 - keep going, record the failure
            room_data[i] = {"error": str(e)}

    # ---- build entrance_index -> room, plus palace & floor per room ------
    ent_map = {}
    palace_of_room = {}
    floor_of_room = {}
    for room_idx in range(NUM_ROOMS):
        d = room_data[room_idx]
        if "error" in d:
            continue
        for e in d.get("Entrances", []):
            ent_map[e["entrance_index"]] = room_idx
            if e.get("palace") is not None:
                palace_of_room.setdefault(room_idx, e.get("palace"))
            if e.get("floor") is not None:
                floor_of_room.setdefault(room_idx, e["floor"])
        for e in d.get("StartingPoints", []):
            if e.get("floor") is not None:
                floor_of_room.setdefault(room_idx, e["floor"])

    def palace_index(name):
        try:
            i = tables.kPalaceNames.index(name)
        except ValueError:
            return None
        return None if i == 0 else (i - 1) * 2

    palace_of_room = {k: palace_index(v) for k, v in palace_of_room.items()}

    # ---- authoritative room -> dungeon mapping --------------------------
    # The game stores, for every dungeon, a per-floor 5x5 layout of the room
    # indices it contains ("kDungMap_FloorLayout"). Reading that table gives us
    # the exact dungeon membership and the floor (layout row) of every room.
    k_dungmap_sizes = [75, 125, 50, 75, 175, 75, 50, 75, 50, 200, 150, 75, 100, 200]
    dungeon_rooms = {}
    room_floor = {}
    for d_idx in range(14):
        addr = 0xa0000 + er.get_word(0x8AF605 + d_idx * 2)
        blob = bytes(er.get_bytes(addr, k_dungmap_sizes[d_idx]))
        n_floors = k_dungmap_sizes[d_idx] // 25
        rooms = []
        for row in range(n_floors):
            for v in blob[row * 25:(row + 1) * 25]:
                if v == 0xf or v >= NUM_ROOMS:
                    continue
                rooms.append(v)
                # Layout row 0 is the top floor; the bottom row is 1F.
                room_floor.setdefault(v, (n_floors - 1) - row)
        dungeon_rooms[d_idx] = sorted(set(rooms))


    # ---- assemble the dungeon output ------------------------------------
    dungeons = {}
    for d_idx, rooms in dungeon_rooms.items():
        dungeon_name = tables.kPalaceNames[d_idx + 1]
        key = DUNGEON_KEY.get(d_idx, "dungeon_%d" % d_idx)
        entry = {"dungeon_id": d_idx, "palace_id": d_idx * 2,
                 "name": dungeon_name, "rooms": []}
        for room_idx in sorted(rooms):
            d = room_data[room_idx]
            if "error" in d:
                continue
            h = d.get("Header", {})
            layers = [d.get("Layer1", []), d.get("Layer2", []), d.get("Layer3", [])]
            stairs = stair_positions(layers)
            pits = pit_positions(layers)

            staircases = []
            stair_dests = [h.get("stair%d_dest" % n) for n in range(4)]
            for pos_i, (tx, ty) in enumerate(stairs):
                if pos_i < len(stair_dests) and stair_dests[pos_i]:
                    tgt = stair_dests[pos_i][0]
                    if 0 <= tgt < NUM_ROOMS:
                        staircases.append({
                            "tile_x": tx, "tile_y": ty,
                            "target_room_id": tgt,
                            "target_floor": floor_label(room_floor.get(tgt, 0)),
                        })

            pit_falls = []
            hole = h.get("hole0_dest")
            if hole and isinstance(hole, list) and 0 <= hole[0] < NUM_ROOMS:
                tgt = hole[0]
                tx, ty = pits[0] if pits else (None, None)
                pit_falls.append({
                    "tile_x": tx, "tile_y": ty,
                    "target_room_id": tgt,
                    "target_floor": floor_label(room_floor.get(tgt, 0)),
                })

            chest_objs = [(o["x"], o["y"]) for layer in layers for o in layer
                          if "chest" in o.get("n", "").lower()]
            interactive = []
            for ci, chest in enumerate(d.get("Chests", [])):
                big = isinstance(chest, str) and chest.endswith("!")
                cx, cy = chest_objs[ci] if ci < len(chest_objs) else (None, None)
                interactive.append({
                    "type": "chest",
                    "item_id": int(chest[:-1]) if big else chest,
                    "big_chest": big,
                    "tile_x": cx, "tile_y": cy,
                })
            interactive += door_entries([d.get("Layer1.doors"), d.get("Layer2.doors"), d.get("Layer3.doors")])

            room_name = "%s - Room 0x%02X" % (key.replace("_", " ").title(), room_idx)
            if d.get("Entrances"):
                room_name = d["Entrances"][0].get("name", room_name)

            # Floor label from the authoritative dungeon-map layout row
            # (row 0 = top floor, bottom row = 1F).
            fl = room_floor.get(room_idx, 0)
            entry["rooms"].append({
                "room_id": room_idx,
                "name": room_name,
                "floor_level": floor_label(fl),
                "layout_row": room_floor.get(room_idx),
                "num_floors": k_dungmap_sizes[d_idx] // 25,
                "dimensions": {"width": 512, "height": 512},
                "connections": {"staircases": staircases, "pit_falls": pit_falls},
                "interactive_elements": interactive,
            })

        if entry["rooms"]:
            dungeons[key] = entry


    # ---- overworld -------------------------------------------------------
    ow_entrances = er.get_ow_entrance_info()
    hole_infos = er.get_hole_infos()
    area_names = tables.kAreaNames

    def area_grid_pos(area):
        """Approximate pixel position/size of an overworld area on the map."""
        light = area < 64
        a = area & 63
        return (a % 8) * 512, (a // 8) * 512, light

    overworld = {
        "light_world": {"dimensions": {"width": 4096, "height": 4096}, "entrances": [], "areas": []},
        "dark_world": {"dimensions": {"width": 4096, "height": 4096}, "entrances": [], "areas": []},
    }

    for area in range(160):
        base_x, base_y, light = area_grid_pos(area)
        world = "light_world" if light else "dark_world"
        area_obj = {
            "area_id": area,
            "name": area_names[area] if area < len(area_names) else str(area),
            "entrances": [], "holes": [],
        }
        for e in ow_entrances.get(area, []):
            area_obj["entrances"].append({
                "x": e["x"] * 8, "y": e["y"] * 8,
                "entrance_id": e["entrance_id"],
                "leads_to_room_id": ent_map.get(e["entrance_id"]),
            })
        for hole in hole_infos.get(area, []):
            area_obj["holes"].append({
                "x": hole["x"] * 8, "y": hole["y"] * 8,
                "entrance_id": hole["entrance_id"],
                "leads_to_room_id": ent_map.get(hole["entrance_id"]),
            })
        overworld[world]["areas"].append(area_obj)
        for e in area_obj["entrances"]:
            overworld[world]["entrances"].append({
                "name": area_obj["name"] + " entrance",
                "x": base_x + e["x"], "y": base_y + e["y"],
                "leads_to_room_id": e["leads_to_room_id"],
            })

    return {
        "meta": {
            "game": "The Legend of Zelda: A Link to the Past",
            "source_rom": os.path.basename(rom_compat.find_rom()),
            "num_dungeon_rooms": NUM_ROOMS,
            "num_rendered_rooms": NUM_RENDER_ROOMS,
            "palace_keys": {str(k): v for k, v in PALACE_KEY.items()},
        },
        "dungeons": dungeons,
        "overworld": overworld,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rom_compat.load_util_rom()
    data = extract()
    with open(OUT_FILE, "w", encoding="utf8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    n_rooms = sum(len(v["rooms"]) for v in data["dungeons"].values())
    print("Wrote %s" % OUT_FILE)
    print("  dungeons: %d, dungeon rooms: %d" % (len(data["dungeons"]), n_rooms))
    print("  light world entrances: %d" % len(data["overworld"]["light_world"]["entrances"]))
    print("  dark world entrances: %d" % len(data["overworld"]["dark_world"]["entrances"]))


if __name__ == "__main__":
    main()

