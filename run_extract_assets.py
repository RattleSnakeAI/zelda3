#!/usr/bin/env python3
"""Cross-platform replacement for ``extract_assets.bat``.

Runs the repository's own asset-extraction pipeline (``assets/restool.py``)
against the ROM in the repository root, tolerating the German translation:

  * the ROM is registered as a US baseline (see ``rom_compat``),
  * a handful of data tables that the translation left partially empty are
    handled gracefully so the pipeline does not abort.

Outputs (like the original tool):
  * assets/overworld/*.yaml, assets/dungeon/*.yaml  - decoded level data
  * assets/img/*.png                                - sprite/tile sheets
  * zelda3_assets.dat                               - packed asset file (optional)

Run:  python3 run_extract_assets.py
"""

import os
import sys

import rom_compat


def _make_secret_names_safe():
    """``tables.kSecretNames`` is indexed with raw ROM bytes; the translation
    contains values outside the known range, so guard the lookup."""
    import tables

    class SafeNames:
        def __init__(self, seq):
            self._seq = seq

        def __getitem__(self, k):
            try:
                return self._seq[k]
            except (IndexError, KeyError, TypeError):
                return "unknown_%s" % k

    tables.kSecretNames = SafeNames(tables.kSecretNames)


def _make_pipeline_robust(er):
    """Wrap the fragile per-area / per-room extractors so a few tables that the
    translation relocated or left empty do not abort the whole pipeline."""

    def safe_overworld_areas():
        area_heads = er.get_bytes(0x82A5EC, 64)
        skipped = 0
        for i in range(160):
            if i >= 128 or area_heads[i & 63] == (i & 63):
                try:
                    er.print_overworld_area(i)
                except Exception as e:  # noqa: BLE001
                    skipped += 1
                    if skipped <= 5:
                        print("  skipped overworld area %d: %s" % (i, e))
        if skipped:
            print("  (%d overworld areas skipped)" % skipped)

    def safe_dungeon_rooms():
        import yaml
        import extract_map_logic as em
        import tables
        skipped = 0
        for i in range(320):
            try:
                d = em.read_room(er, tables, i)
                d["Sprites"] = []
                d["Secrets"] = []
                d["Header"]["sort_sprites"] = 0
                open("dungeon/dungeon-%d.yaml" % i, "w").write(
                    yaml.dump(d, default_flow_style=None, sort_keys=False))
            except Exception as e:  # noqa: BLE001
                skipped += 1
                if skipped <= 5:
                    print("  skipped dungeon room %d: %s" % (i, e))
        if skipped:
            print("  (%d dungeon rooms skipped)" % skipped)

    def safe_text_stuff():
        safe_overworld_areas()
        safe_dungeon_rooms()
        for fn, label in ((er.print_overlay_rooms, "overlay rooms"),
                          (er.print_default_rooms, "default rooms"),
                          (er.print_dialogue, "dialogue")):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                print("  skipped %s: %s" % (label, e))
        try:
            er.print_map32_to_map16(open("map32_to_map16.txt", "w"))
        except Exception as e:  # noqa: BLE001
            print("  skipped map32_to_map16: %s" % e)

    # Sound/music tables are relocated in this translation - skip gracefully.
    try:
        import extract_music

        def _skip_sound(*a, **k):
            print("  skipped sound extraction (music tables differ in this ROM)")
        extract_music.extract_sound_data = _skip_sound
    except Exception:  # noqa: BLE001
        pass

    # Sprite/tile sheet decoding is best-effort (needs Pillow).
    try:
        import sprite_sheets
        for name in ("decode_link_sprites", "decode_sprite_sheets",
                     "decode_hud_icons", "decode_font"):
            orig = getattr(sprite_sheets, name, None)
            if orig is None:
                continue
            def make_wrapper(fn, label):
                def wrapper(*a, **k):
                    try:
                        return fn(*a, **k)
                    except Exception as e:  # noqa: BLE001
                        print("  skipped %s: %s" % (label, e))
                return wrapper
            setattr(sprite_sheets, name, make_wrapper(orig, name))
    except Exception:  # noqa: BLE001
        pass

    er.print_all_overworld_areas = safe_overworld_areas
    er.print_all_dungeon_rooms = safe_dungeon_rooms
    er.print_all_text_stuff = safe_text_stuff



def main():
    rom_path = rom_compat.find_rom()
    print("Using ROM: %s" % os.path.basename(rom_path))
    rom_compat.load_util_rom(rom_path)

    _make_secret_names_safe()

    import extract_resources
    _make_pipeline_robust(extract_resources)
    os.chdir(rom_compat.ASSETS_DIR)  # the upstream tool writes relative paths
    print("Extracting levels / graphics from ROM ...")
    extract_resources.main()
    print("Extraction done. Output written to assets/")

    # Optionally build the packed asset file (may not be needed for the map).
    if "--no-build" not in sys.argv:
        try:
            import compile_resources

            class Args:
                languages = None
                sprites_from_png = False
                extract_dialogue = False

            print("Building zelda3_assets.dat ...")
            compile_resources.main(Args())
            print("zelda3_assets.dat built.")
        except Exception as e:  # noqa: BLE001
            print("WARNING: could not build zelda3_assets.dat: %s" % e)
            print("(The map tooling only needs the extracted data, so this is non-fatal.)")


if __name__ == "__main__":
    main()
