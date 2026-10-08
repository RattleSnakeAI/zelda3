#!/usr/bin/env python3
"""Validate the extracted map data and the rendered images.

Checks performed:
  1. every room id 0..255 has a rendered PNG,
  2. all connection targets point to existing rooms,
  3. staircase connections are (mostly) bidirectional,
  4. there are no out-of-range / orphan tile coordinates,
  5. every overworld entrance points to an existing dungeon room.

Prints a human readable report and exits non-zero when hard errors are found.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(HERE, "extracted_assets", "map_data.json")
IMG_DIR = os.path.join(HERE, "extracted_assets", "images")
NUM_RENDER_ROOMS = 256
ROOM_SIZE_TILES = 64  # a room is 64x64 logical tiles


def main():
    errors = []
    warnings = []

    if not os.path.exists(DATA_FILE):
        print("ERROR: %s missing - run extract_map_logic.py first" % DATA_FILE)
        return 1
    data = json.load(open(DATA_FILE, encoding="utf8"))

    # ---- 1. room images ---------------------------------------------------
    missing_images = [i for i in range(NUM_RENDER_ROOMS)
                      if not os.path.exists(os.path.join(IMG_DIR, "room_%03d.png" % i))]
    if missing_images:
        errors.append("missing room images: %s" % missing_images[:10])
    print("[1] room images: %d/%d present" % (NUM_RENDER_ROOMS - len(missing_images), NUM_RENDER_ROOMS))

    # ---- collect all rooms -------------------------------------------------
    rooms = {}
    for dkey, dungeon in data["dungeons"].items():
        for r in dungeon["rooms"]:
            rooms[r["room_id"]] = (dkey, r)
    print("[ ] dungeon rooms indexed: %d" % len(rooms))

    # ---- 2/3. connections --------------------------------------------------
    stair_links = {}
    target_errors = []
    bidir_missing = []
    for rid, (dkey, r) in rooms.items():
        conn = r.get("connections", {})
        for st in conn.get("staircases", []):
            tgt = st.get("target_room_id")
            if tgt not in rooms:
                target_errors.append("room %d staircase -> unknown room %s" % (rid, tgt))
            else:
                stair_links.setdefault(rid, set()).add(tgt)
        for pf in conn.get("pit_falls", []):
            tgt = pf.get("target_room_id")
            if tgt not in rooms:
                target_errors.append("room %d pit -> unknown room %s" % (rid, tgt))

    for src, tgts in stair_links.items():
        for t in tgts:
            if src not in stair_links.get(t, set()):
                bidir_missing.append((src, t))

    if target_errors:
        errors.extend(target_errors[:20])
    print("[2] connection targets: %d invalid" % len(target_errors))
    pct = 100.0 * (1 - len(bidir_missing) / max(1, sum(len(v) for v in stair_links.values())))
    print("[3] staircases bidirectional: %.1f%% (%d one-way of %d links)"
          % (pct, len(bidir_missing), sum(len(v) for v in stair_links.values())))
    if bidir_missing:
        warnings.append("%d one-way staircase links (expected: some stairs are one-directional)" % len(bidir_missing))

    # ---- 4. orphan / out-of-range coordinates ------------------------------
    orphan = []
    for rid, (dkey, r) in rooms.items():
        for kind in ("staircases", "pit_falls"):
            for c in r.get("connections", {}).get(kind, []):
                x, y = c.get("tile_x"), c.get("tile_y")
                if x is None and y is None:
                    continue  # position simply unknown, not an error
                if x is None or y is None or not (0 <= x < ROOM_SIZE_TILES and 0 <= y < ROOM_SIZE_TILES):
                    orphan.append("room %d %s at (%s,%s)" % (rid, kind, x, y))
        for el in r.get("interactive_elements", []):
            x, y = el.get("tile_x"), el.get("tile_y")
            if x is None or y is None:
                continue
            if not (0 <= x < ROOM_SIZE_TILES and 0 <= y < ROOM_SIZE_TILES):
                orphan.append("room %d %s at (%s,%s)" % (rid, el.get("type"), x, y))
    if orphan:
        errors.extend(orphan[:20])
    print("[4] orphan coordinates: %d" % len(orphan))

    # ---- 5. overworld entrances -------------------------------------------
    ow_bad = []
    for world in ("light_world", "dark_world"):
        for e in data["overworld"][world]["entrances"]:
            rid = e.get("leads_to_room_id")
            if rid is not None and rid not in rooms:
                ow_bad.append("%s entrance -> unknown room %s" % (world, rid))
    if ow_bad:
        warnings.append("%d overworld entrances point outside the known dungeons" % len(ow_bad))
    print("[5] overworld entrances: %d unresolved" % len(ow_bad))

    # ---- summary -----------------------------------------------------------
    print()
    for w in warnings:
        print("WARNING: %s" % w)
    if errors:
        print()
        for e in errors:
            print("ERROR: %s" % e)
        print("\nValidation FAILED with %d error(s)." % len(errors))
        return 1
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
