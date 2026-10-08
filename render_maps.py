#!/usr/bin/env python3
"""Render the extracted map data to PNG images.

Outputs (all inside extracted_assets/images/):
  * overworld_light.png / overworld_dark.png  - the full Hyrule world map
    (real graphics taken straight from the ROM's Mode-7 world map)
  * room_000.png .. room_255.png              - one image per dungeon room,
    drawn from the real room layout objects (floors, walls, stairs, pits,
    chests, doors, ...)

The world maps use the genuine ROM tile graphics + palette. The dungeon rooms
are rendered as clean, colour-coded schematics because faithfully re-drawing a
dungeon room background would require re-implementing the game's full tileset
decompressor (3bpp->4bpp, blocksets, ...); the schematic keeps every real
object position and type.
"""

import json
import os

import rom_compat

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(HERE, "extracted_assets", "images")
DATA_FILE = os.path.join(HERE, "extracted_assets", "map_data.json")

# SNES ROM locations of the world-map assets (identical in every regional ROM).
MAP_GFX_ADDR = 0x18C000     # 256 x 8bpp 8x8 tiles (char-major)
LIGHT_TILEMAP_ADDR = 0xAC727  # 4096 bytes = 4 blocks of 32x32 tile indices
DARK_TILEMAP_ADDR = 0xAD727   # 1024 bytes overlay for the dark world
MAP_PALETTE_ADDR = 0x8ADB27   # 256 BGR555 colours


def _to_rgb(c):
    return ((c & 31) * 255 // 31, ((c >> 5) & 31) * 255 // 31, ((c >> 10) & 31) * 255 // 31)


def render_world_map(rom, dark, scale):
    """Return a PIL.Image of the whole light (dark=False) or dark world map."""
    from PIL import Image

    gfx = bytes(rom.get_bytes(MAP_GFX_ADDR, 0x4000))
    tm = bytes(rom.get_bytes(LIGHT_TILEMAP_ADDR, 4096))
    pal_raw = rom.get_words(MAP_PALETTE_ADDR, 256)

    pal_off = 0x80 if dark else 0
    palette = [0] * 768
    for i in range(128):
        r, g, b = _to_rgb(pal_raw[pal_off + i])
        palette[i * 3:i * 3 + 3] = [r, g, b]

    # 256 tiles of 8x8 pixels, stored char-major (64 bytes per tile).
    tiles = [[[gfx[c * 64 + y * 8 + x] & 0x7F for x in range(8)] for y in range(8)]
             for c in range(256)]

    # The 4096 bytes are four 32x32 blocks placed in the four quadrants.
    W = H = 64
    grid = [[0] * W for _ in range(H)]
    for blk in range(4):
        for row in range(32):
            for col in range(32):
                grid[(blk >> 1) * 32 + row][(blk & 1) * 32 + col] = tm[blk * 1024 + row * 32 + col]

    img = Image.new("P", (W * 8, H * 8))
    img.putpalette(palette)
    for y in range(H):
        for x in range(W):
            t = tiles[grid[y][x]]
            for yy in range(8):
                for xx in range(8):
                    img.putpixel((x * 8 + xx, y * 8 + yy), t[yy][xx])
    if scale != 1:
        img = img.resize((W * 8 * scale, H * 8 * scale), Image.NEAREST)
    return img.convert("RGB")

# ---------------------------------------------------------------------------
# Dungeon room rendering (clean, colour-coded schematic of the real layout)
# ---------------------------------------------------------------------------

# Keyword -> colour used to classify the ROM's object names.
OBJECT_CATEGORIES = [
    (("stair",), (255, 205, 60)),
    (("pit", "hole"), (5, 5, 8)),
    (("water", "waterfall", "fountain"), (54, 116, 214)),
    (("chest",), (242, 196, 66)),
    (("door",), (74, 200, 122)),
    (("wall",), (104, 114, 136)),
    (("floor",), (38, 48, 68)),
    (("torch", "lamp", "fire"), (250, 148, 52)),
    (("table", "pot", "block", "statue", "gravestone", "rock", "skull"), (150, 150, 156)),
    (("grass", "bush", "tree"), (70, 150, 80)),
    (("water",), (54, 116, 214)),
]
DEFAULT_COLOR = (96, 106, 128)


def object_color(name):
    low = name.lower()
    for keys, color in OBJECT_CATEGORIES:
        if any(k in low for k in keys):
            return color
    return DEFAULT_COLOR


def _parse_size(s):
    """Parse a 'W*H' size string, returning (w, h) in 0..3."""
    if not s:
        return 0, 0
    try:
        w, h = s.split("*")
        return int(w), int(h)
    except ValueError:
        return 0, 0


def render_room(room_index, room, floor_level):
    """Render one dungeon room to a PIL.Image (512x512)."""
    from PIL import Image, ImageDraw

    S = 512
    img = Image.new("RGB", (S, S), (22, 28, 44))
    d = ImageDraw.Draw(img)

    # subtle 4-tile grid
    for i in range(0, S + 1, 32):
        d.line([(i, 0), (i, S)], fill=(32, 40, 62))
        d.line([(0, i), (S, i)], fill=(32, 40, 62))

    layers = [room.get("Layer1", []), room.get("Layer2", []), room.get("Layer3", [])]
    # Draw background layers first, walls on top.
    order = sorted(range(len(layers)), key=lambda li: len(layers[li]), reverse=True)
    for li in order:
        for o in layers[li]:
            w, h = _parse_size(o.get("s"))
            x0, y0 = o["x"] * 8, o["y"] * 8
            wpx, hpx = (w + 1) * 16, (h + 1) * 16
            color = object_color(o.get("n", ""))
            d.rectangle([x0, y0, min(x0 + wpx - 1, S - 1), min(y0 + hpx - 1, S - 1)], fill=color)

    # chests (gold diamond markers on top)
    for o in layers[0] + layers[1] + layers[2]:
        if "chest" in o.get("n", "").lower():
            cx, cy = o["x"] * 8 + 4, o["y"] * 8 + 4
            d.polygon([(cx, cy - 6), (cx + 6, cy), (cx, cy + 6), (cx - 6, cy)], fill=(255, 235, 120))

    # doors as coloured bars along the room edges
    for doors in (room.get("Layer1.doors"), room.get("Layer2.doors"), room.get("Layer3.doors")):
        for door in doors or []:
            pos, dr = door.get("pos", 0), door.get("dir", 0)
            color = (74, 200, 122) if door.get("type", 0) < 0x80 else (220, 90, 90)
            off = pos * 32 + 4
            if dr == 0:      # north
                d.rectangle([off, 0, off + 24, 6], fill=color)
            elif dr == 1:    # south
                d.rectangle([off, S - 7, off + 24, S - 1], fill=color)
            elif dr == 2:    # west
                d.rectangle([0, off, 6, off + 24], fill=color)
            else:            # east
                d.rectangle([S - 7, off, S - 1, off + 24], fill=color)

    d.rectangle([0, 0, S - 1, S - 1], outline=(80, 92, 120))
    return img


def render_missing_room(room_index):
    from PIL import Image, ImageDraw
    S = 512
    img = Image.new("RGB", (S, S), (14, 18, 30))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, S - 1, S - 1], outline=(60, 70, 96))
    d.line([(0, 0), (S, S)], fill=(60, 70, 96))
    d.line([(S, 0), (0, S)], fill=(60, 70, 96))
    return img



def main():
    os.makedirs(IMG_DIR, exist_ok=True)
    rom = rom_compat.load_util_rom()

    import extract_map_logic as em
    import extract_resources as er
    import tables

    # ---- world maps -------------------------------------------------------
    for dark, name in ((False, "overworld_light"), (True, "overworld_dark")):
        img = render_world_map(rom, dark, scale=8)
        img.save(os.path.join(IMG_DIR, name + ".png"))
        img.resize((512, 512)).save(os.path.join(IMG_DIR, name + "_small.png"))
        print("wrote %s.png (%dx%d)" % (name, img.width, img.height))

    # ---- room -> floor lookup (from map_data.json) ------------------------
    floor_of_room = {}
    if os.path.exists(DATA_FILE):
        data = json.load(open(DATA_FILE, encoding="utf8"))
        for dungeon in data["dungeons"].values():
            for r in dungeon["rooms"]:
                floor_of_room[r["room_id"]] = r["floor_level"]

    # ---- individual rooms -------------------------------------------------
    num = 256
    for i in range(num):
        try:
            room = em.read_room(er, tables, i)
            has_data = bool(room.get("Layer1") or room.get("Layer2") or room.get("Layer3"))
        except Exception:  # noqa: BLE001
            has_data = False
        if has_data:
            img = render_room(i, room, floor_of_room.get(i))
        else:
            img = render_missing_room(i)
        img.save(os.path.join(IMG_DIR, "room_%03d.png" % i))
    print("wrote %d room images to %s" % (num, IMG_DIR))


if __name__ == "__main__":
    main()

