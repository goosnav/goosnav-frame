"""Frame settings: defaults, schema and validation.

Settings are plain nested dicts so they travel as JSON between the GUI, presets
and the renderer. `normalize` is the single gate: it fills defaults, coerces
types and clamps every value, so the renderer never sees unchecked input.
"""
from __future__ import annotations

import copy
import re

CANVAS_PRESETS = {
    "4:5": (1080, 1350),
    "1:1": (1080, 1080),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

DEFAULTS: dict = {
    "canvas": {"preset": "4:5", "width": 1080, "height": 1350, "background": "#ffffff", "side_margin": 60,
               "layout": "overlay"},
    "title": {
        "visible": True,
        "text": "TWEAKING OFF THE\nGOOSNAV PACK",
        "uppercase": True,
        "font": "heros-bold",
        "size": 96,
        "autofit": True,
        "color": "#000000",
        "line_height": 1.12,
        "letter_spacing": 0,
        "top": 70,
        "outline": 0,
        "outline_color": "#ffffff",
    },
    "link": {
        "visible": True,
        "text": "www.goosnav.shop",
        "font": "termes-regular",
        "size": 116,
        "color": "#0000ee",
        "underline": True,
        "underline_thickness": 6,
        "bottom": 70,
        "outline": 0,
        "outline_color": "#ffffff",
    },
    "media": {
        "fit": "cover",
        "scale": 100,
        "offset_x": 0,
        "offset_y": 0,
        "gap": 36,
        "scaling": "auto",
        "trim_start": 0.0,
        "trim_duration": 0.0,
        "image_duration": 6.0,
        "keep_audio": True,
    },
    "retro": {
        "enabled": False,
        "pixel": 3,
        "aliased": True,
        "rgb_split": 0,
        "scanlines": "off",
        "scanline_strength": 35,
        "shadow": False,
        "shadow_color": "#7f7f7f",
        "jitter": False,
        "typewriter": False,
        "type_speed": 20.0,
        "type_delay": 0.2,
        "cursor": True,
    },
    "media_fx": {"mode": "none", "pixel": 3, "levels": 32},
    "export": {"format": "mp4", "fps": 0, "quality": "high", "time": 0.0},
}

# path -> (kind, constraint)
#   kind: bool | int | float | str | text | color | enum
SCHEMA: dict = {
    "canvas.preset": ("enum", list(CANVAS_PRESETS) + ["custom"]),
    "canvas.width": ("int", (64, 4096)),
    "canvas.height": ("int", (64, 4096)),
    "canvas.background": ("color", None),
    "canvas.side_margin": ("int", (0, 1000)),
    "canvas.layout": ("enum", ["overlay", "stacked"]),
    "title.visible": ("bool", None),
    "title.text": ("text", 400),
    "title.uppercase": ("bool", None),
    "title.font": ("str", 64),
    "title.size": ("int", (8, 600)),
    "title.autofit": ("bool", None),
    "title.color": ("color", None),
    "title.line_height": ("float", (0.6, 3.0)),
    "title.letter_spacing": ("int", (-40, 200)),
    "title.top": ("int", (0, 2000)),
    "title.outline": ("int", (0, 40)),
    "title.outline_color": ("color", None),
    "link.visible": ("bool", None),
    "link.text": ("text", 200),
    "link.font": ("str", 64),
    "link.size": ("int", (8, 600)),
    "link.color": ("color", None),
    "link.underline": ("bool", None),
    "link.underline_thickness": ("int", (1, 60)),
    "link.bottom": ("int", (0, 2000)),
    "link.outline": ("int", (0, 40)),
    "link.outline_color": ("color", None),
    "media.fit": ("enum", ["contain", "cover", "stretch"]),
    "media.scale": ("int", (5, 400)),
    "media.offset_x": ("int", (-4000, 4000)),
    "media.offset_y": ("int", (-4000, 4000)),
    "media.gap": ("int", (0, 1000)),
    "media.scaling": ("enum", ["auto", "crisp", "smooth"]),
    "media.trim_start": ("float", (0.0, 36000.0)),
    "media.trim_duration": ("float", (0.0, 36000.0)),
    "media.image_duration": ("float", (0.5, 120.0)),
    "media.keep_audio": ("bool", None),
    "retro.enabled": ("bool", None),
    "retro.pixel": ("int", (1, 12)),
    "retro.aliased": ("bool", None),
    "retro.rgb_split": ("int", (0, 12)),
    "retro.scanlines": ("enum", ["off", "text", "frame"]),
    "retro.scanline_strength": ("int", (0, 100)),
    "retro.shadow": ("bool", None),
    "retro.shadow_color": ("color", None),
    "retro.jitter": ("bool", None),
    "retro.typewriter": ("bool", None),
    "retro.type_speed": ("float", (1.0, 200.0)),
    "retro.type_delay": ("float", (0.0, 30.0)),
    "retro.cursor": ("bool", None),
    "media_fx.mode": ("enum", ["none", "ps1", "pixelate", "posterize"]),
    "media_fx.pixel": ("int", (1, 16)),
    "media_fx.levels": ("int", (2, 64)),
    "export.format": ("enum", ["mp4", "png"]),
    "export.fps": ("int", (0, 60)),
    "export.quality": ("enum", ["high", "medium", "small"]),
    "export.time": ("float", (0.0, 36000.0)),
}

_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _get(d: dict, path: str):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set(d: dict, path: str, value) -> None:
    parts = path.split(".")
    cur = d
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _coerce(kind: str, rule, value, default):
    try:
        if kind == "bool":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if kind in ("int", "float"):
            num = float(value)
            if num != num:  # NaN
                return default
            lo, hi = rule
            num = min(max(num, lo), hi)
            return int(round(num)) if kind == "int" else num
        if kind == "color":
            value = str(value).strip()
            if len(value) == 4 and value.startswith("#"):
                value = "#" + "".join(c * 2 for c in value[1:])
            return value.lower() if _COLOR.match(value) else default
        if kind == "enum":
            return value if value in rule else default
        if kind == "str":
            value = str(value)
            return value if re.match(r"^[A-Za-z0-9_.:-]{1,%d}$" % rule, value) else default
        if kind == "text":
            value = str(value).replace("\r\n", "\n").replace("\r", "\n")
            return "".join(ch for ch in value if ch == "\n" or ch.isprintable())[:rule]
    except (TypeError, ValueError):
        return default
    return default


def defaults() -> dict:
    return copy.deepcopy(DEFAULTS)


def normalize(raw: dict | None) -> dict:
    """Return a complete, validated copy of `raw` (unknown keys are dropped)."""
    raw = raw if isinstance(raw, dict) else {}
    out = defaults()
    for path, (kind, rule) in SCHEMA.items():
        value = _get(raw, path)
        if value is not None:
            _set(out, path, _coerce(kind, rule, value, _get(out, path)))
    preset = out["canvas"]["preset"]
    if preset in CANVAS_PRESETS:
        out["canvas"]["width"], out["canvas"]["height"] = CANVAS_PRESETS[preset]
    # even dimensions keep yuv420p encoders happy
    out["canvas"]["width"] -= out["canvas"]["width"] % 2
    out["canvas"]["height"] -= out["canvas"]["height"] % 2
    return out


def hex_rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def is_animated(s: dict) -> bool:
    """True when the text layer changes over time."""
    r = s["retro"]
    return bool(r["enabled"] and (r["jitter"] or r["typewriter"]))
