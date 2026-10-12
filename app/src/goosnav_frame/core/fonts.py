"""Font registry: bundled metric clones, known system fonts, and user uploads."""
from __future__ import annotations

import functools
import os
import re
from pathlib import Path

from PIL import ImageFont

STATIC = Path(__file__).resolve().parents[3] / "static"

BUNDLED = {
    "heros-bold": ("Helvetica Bold (TeX Gyre Heros)", STATIC / "fonts" / "texgyreheros-bold.otf", 0),
    "heros-regular": ("Helvetica (TeX Gyre Heros)", STATIC / "fonts" / "texgyreheros-regular.otf", 0),
    "termes-regular": ("Times (TeX Gyre Termes)", STATIC / "fonts" / "texgyretermes-regular.otf", 0),
    "termes-bold": ("Times Bold (TeX Gyre Termes)", STATIC / "fonts" / "texgyretermes-bold.otf", 0),
}

# Real system faces, used when present on the machine running the server.
SYSTEM_CANDIDATES = [
    ("sys-helvetica-bold", "Helvetica Bold (system)", "/System/Library/Fonts/Helvetica.ttc", 1),
    ("sys-helvetica", "Helvetica (system)", "/System/Library/Fonts/Helvetica.ttc", 0),
    ("sys-times", "Times New Roman (system)", "/System/Library/Fonts/Supplemental/Times New Roman.ttf", 0),
    ("sys-times", "Times New Roman (system)", r"C:\Windows\Fonts\times.ttf", 0),
    ("sys-arial-bold", "Arial Bold (system)", r"C:\Windows\Fonts\arialbd.ttf", 0),
    ("sys-arial-bold", "Arial Bold (system)", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
    ("sys-nimbus-sans-bold", "Nimbus Sans Bold (system)", "/usr/share/fonts/opentype/urw-base35/NimbusSans-Bold.otf", 0),
    ("sys-nimbus-roman", "Nimbus Roman (system)", "/usr/share/fonts/opentype/urw-base35/NimbusRoman-Regular.otf", 0),
    ("sys-dejavu-mono-bold", "DejaVu Sans Mono Bold (system)", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 0),
    ("sys-courier-bold", "Courier New Bold (system)", r"C:\Windows\Fonts\courbd.ttf", 0),
    ("sys-courier-bold", "Courier New Bold (system)", "/System/Library/Fonts/Supplemental/Courier New Bold.ttf", 0),
]

_user_dir: Path | None = None


def set_user_dir(path: Path) -> None:
    global _user_dir
    _user_dir = path
    path.mkdir(parents=True, exist_ok=True)
    available.cache_clear()


@functools.lru_cache(maxsize=1)
def available() -> dict[str, tuple[str, str, int]]:
    """id -> (label, path, face index)."""
    out = {k: (label, str(p), idx) for k, (label, p, idx) in BUNDLED.items()}
    for fid, label, p, idx in SYSTEM_CANDIDATES:
        if fid not in out and os.path.isfile(p):
            out[fid] = (label, p, idx)
    if _user_dir and _user_dir.is_dir():
        for f in sorted(_user_dir.iterdir()):
            if f.suffix.lower() in (".ttf", ".otf", ".ttc"):
                out["user-" + f.stem] = (f.stem + " (uploaded)", str(f), 0)
    return out


def refresh() -> None:
    available.cache_clear()
    _font.cache_clear()


def safe_font_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(name).stem).strip("-")[:48]
    return stem or "font"


@functools.lru_cache(maxsize=256)
def _font(path: str, idx: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size, index=idx)


def get(font_id: str, size: int) -> ImageFont.FreeTypeFont:
    fonts = available()
    label, path, idx = fonts.get(font_id) or fonts["heros-bold"]
    return _font(path, idx, max(1, int(size)))


def listing() -> list[dict]:
    return [{"id": k, "label": v[0]} for k, v in available().items()]


__all__ = ["available", "get", "listing", "refresh", "set_user_dir", "safe_font_name"]
