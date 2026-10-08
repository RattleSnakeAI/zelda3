"""ROM compatibility layer for the Zelda 3 map-extraction tools.

The upstream `assets/util.py` only accepts ROMs whose SHA1 is present in its
`ZELDA3_SHA1` table and, when `support_multilanguage` is False, only accepts the
US ROM. The German fan translation we work with
("The Legend of Zelda - Göttin der Weisheit (T + Ger 3.01).sfc") is not in that
table, but it is a text-only translation of the US ROM, so every data table
(levels, rooms, graphics, palettes) lives at the exact same (Lo)ROM offset.

This module therefore:
  * locates the ROM file (falling back to a few well-known names),
  * transparently registers its SHA1 as a US baseline so the existing
    extraction pipeline keeps working,
  * exposes a couple of tiny helpers used by our own scripts.

Nothing here modifies the ROM or the upstream repository code.
"""

import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(HERE, "assets")
if ASSETS_DIR not in sys.path:
    sys.path.insert(0, ASSETS_DIR)

# Candidate names for the ROM in the repository root, in priority order.
DEFAULT_ROM_NAMES = [
    "The Legend of Zelda - Göttin der Weisheit(T + Ger 3.01).sfc",
    "zelda3.sfc",
    "zelda3.smc",
]


def find_rom(path=None):
    """Return the absolute path of the ROM to use.

    If `path` is given it must exist. Otherwise the first existing candidate in
    the repository root is returned.
    """
    if path:
        if not os.path.isfile(path):
            raise FileNotFoundError("ROM not found: %s" % path)
        return os.path.abspath(path)
    for name in DEFAULT_ROM_NAMES:
        cand = os.path.join(HERE, name)
        if os.path.isfile(cand):
            return cand
    raise FileNotFoundError(
        "No ROM found. Place the .sfc file in %s (see README)." % HERE)


def _strip_smc_header(data):
    """Remove the optional 512-byte SMC/SNES copier header."""
    if (len(data) & 0xFFFFF) == 0x200:
        return data[0x200:]
    return data


def load_util_rom(path=None):
    """Load the ROM through `assets.util`, tolerating translated ROMs.

    Returns the `util.LoadedRom` instance; the global `util.ROM` is populated as
    a side effect so all the upstream helper functions (get_byte, get_word, ...)
    work as usual.
    """
    import util

    rom_path = find_rom(path)
    raw = open(rom_path, "rb").read()
    body = _strip_smc_header(raw)
    sha1 = hashlib.sha1(body).hexdigest().upper()

    # Register unknown ROMs as a US baseline so util.load_rom() accepts them.
    # The German translation only replaces dialogue/strings, all binary data
    # tables keep the original (US) layout.
    if sha1 not in util.ZELDA3_SHA1:
        util.ZELDA3_SHA1[sha1] = (
            "us", "unrecognised ROM treated as US baseline (translation patch)")

    return util.load_rom(rom_path)


def read_bytes(rom, addr, n):
    """Convenience wrapper returning an immutable bytes object."""
    return bytes(rom.get_bytes(addr, n))
