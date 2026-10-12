"""Layout, text layer and frame compositing.

One function, `compose`, produces every pixel the user sees: the GUI preview,
the PNG export and each frame of the MP4 export all come from it.
"""
from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageDraw

from . import fonts
from .settings import hex_rgb

BAYER4 = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) + 0.5) / 16.0


# ------------------------------------------------------------------ layout
def _line_width(font, text: str, spacing: int) -> float:
    if not text:
        return 0.0
    if spacing == 0:
        return font.getlength(text)
    return sum(font.getlength(ch) for ch in text) + spacing * (len(text) - 1)


def title_lines(s: dict) -> list[str]:
    t = s["title"]["text"]
    if s["title"]["uppercase"]:
        t = t.upper()
    return t.split("\n")


def layout(s: dict) -> dict:
    W, H = s["canvas"]["width"], s["canvas"]["height"]
    side = min(s["canvas"]["side_margin"], W // 3)
    out = {"W": W, "H": H, "side": side, "title": None, "link": None}

    top_edge = 0
    if s["title"]["visible"] and s["title"]["text"].strip():
        ts = s["title"]
        lines = title_lines(s)
        size = ts["size"]
        if ts["autofit"]:
            avail = W - 2 * side
            widest = max(_line_width(fonts.get(ts["font"], size), ln, ts["letter_spacing"]) for ln in lines)
            if widest > avail:
                size = max(8, int(size * avail / widest))
        font = fonts.get(ts["font"], size)
        cap = -font.getbbox("H", anchor="ls")[1]
        lh = size * ts["line_height"]
        rows = []
        for i, ln in enumerate(lines):
            w = _line_width(font, ln, ts["letter_spacing"])
            rows.append({"text": ln, "x": (W - w) / 2, "baseline": ts["top"] + cap + i * lh, "width": w})
        bottom = ts["top"] + cap + (len(lines) - 1) * lh + size * 0.08
        out["title"] = {"size": size, "rows": rows, "cap": cap, "bottom": bottom}
        top_edge = bottom

    bottom_edge = H
    if s["link"]["visible"] and s["link"]["text"].strip():
        ls = s["link"]
        font = fonts.get(ls["font"], ls["size"])
        text = ls["text"]
        w = font.getlength(text)
        bbox = font.getbbox(text, anchor="ls")
        ul_off = ls["size"] * 0.13
        thick = ls["underline_thickness"]
        low = max(bbox[3], ul_off + thick if ls["underline"] else 0)
        baseline = H - ls["bottom"] - low
        out["link"] = {"text": text, "x": (W - w) / 2, "baseline": baseline, "width": w,
                       "ul_off": ul_off, "thick": thick, "top": baseline + bbox[1]}
        bottom_edge = baseline + bbox[1]

    if s["canvas"]["layout"] == "overlay":  # media is the whole frame; text sits on top
        out["box"] = (0, 0, W, H)
        return out
    gap = s["media"]["gap"]
    y0 = top_edge + gap if out["title"] else gap
    y1 = bottom_edge - gap if out["link"] else H - gap
    if y1 - y0 < 32:
        y0, y1 = H * 0.25, H * 0.75
    out["box"] = (side, int(round(y0)), W - side, int(round(y1)))
    return out


def media_rect(s: dict, lay: dict, mw: int, mh: int) -> tuple[int, int, int, int]:
    """Where the media lands on the canvas: (x, y, w, h); may extend past the box."""
    bx0, by0, bx1, by1 = lay["box"]
    bw, bh = bx1 - bx0, by1 - by0
    fit = s["media"]["fit"]
    if fit == "stretch":
        w, h = bw, bh
    else:
        k = min(bw / mw, bh / mh) if fit == "contain" else max(bw / mw, bh / mh)
        w, h = mw * k, mh * k
    k = s["media"]["scale"] / 100.0
    w, h = max(1, int(round(w * k))), max(1, int(round(h * k)))
    x = int(round(bx0 + (bw - w) / 2 + s["media"]["offset_x"]))
    y = int(round(by0 + (bh - h) / 2 + s["media"]["offset_y"]))
    return x, y, w, h


# ------------------------------------------------------------------ text layer
def _elements(s: dict, lay: dict) -> list[dict]:
    """Text runs in reading order (title rows, then the link)."""
    els = []
    if lay["title"]:
        ts = s["title"]
        for row in lay["title"]["rows"]:
            els.append(dict(text=row["text"], x=row["x"], base=row["baseline"], font=ts["font"],
                            size=lay["title"]["size"], color=ts["color"], spacing=ts["letter_spacing"],
                            underline=False, cursor_h=lay["title"]["cap"],
                            outline=ts["outline"], outline_color=ts["outline_color"]))
    if lay["link"]:
        ls = s["link"]
        font = fonts.get(ls["font"], ls["size"])
        els.append(dict(text=lay["link"]["text"], x=lay["link"]["x"], base=lay["link"]["baseline"],
                        font=ls["font"], size=ls["size"], color=ls["color"], spacing=0,
                        underline=ls["underline"], cursor_h=-font.getbbox("x", anchor="ls")[1] * 1.35,
                        outline=ls["outline"], outline_color=ls["outline_color"]))
    return els


def _draw_text(d: ImageDraw.ImageDraw, xy, text, font, fill, spacing, stroke=0, stroke_fill=None):
    x, y = xy
    kw = {"stroke_width": stroke, "stroke_fill": stroke_fill} if stroke else {}
    if spacing == 0:
        d.text((x, y), text, font=font, fill=fill, anchor="ls", **kw)
        return
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill, anchor="ls", **kw)
        x += font.getlength(ch) + spacing


def text_layer(s: dict, lay: dict, t: float = 0.0, frame: int = 0) -> np.ndarray:
    """RGBA uint8 (H, W, 4) holding the title, link and retro text effects."""
    W, H = lay["W"], lay["H"]
    r = s["retro"]
    retro = r["enabled"]
    p = r["pixel"] if retro else 1
    lw, lh = math.ceil(W / p), math.ceil(H / p)
    img = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.fontmode = "1" if (retro and r["aliased"]) else "L"
    rng = random.Random(frame * 7919 + 13)
    els = _elements(s, lay)

    typing = retro and r["typewriter"]
    budget = int(max(0.0, t - r["type_delay"]) * r["type_speed"]) if typing else None
    cursor = None
    for i, e in enumerate(els):
        text = e["text"]
        if typing:
            take = min(budget, len(text))
            budget -= take
            text = text[:take]
            if cursor is None and (take < len(e["text"]) or i == len(els) - 1):
                cursor = (e, _line_width(fonts.get(e["font"], e["size"]), text, e["spacing"]))
        if not text:
            continue
        font = fonts.get(e["font"], max(4, round(e["size"] / p)))
        jx, jy = (rng.choice((-1, 0, 0, 1)), rng.choice((-1, 0, 0, 1))) if retro and r["jitter"] else (0, 0)
        lx, ly = e["x"] / p + jx, e["base"] / p + jy
        width = _line_width(fonts.get(e["font"], e["size"]), text, e["spacing"])
        layers = [(0, hex_rgb(e["color"]))]
        if retro and r["shadow"]:
            sh = max(1, round(e["size"] / p / 24))
            layers.insert(0, (sh, hex_rgb(r["shadow_color"])))
        ow = round(e["outline"] / p) if e["outline"] else 0
        oc = hex_rgb(e["outline_color"]) + (255,)
        for off, col in layers:
            ul, th = (lay["link"]["ul_off"], lay["link"]["thick"]) if e["underline"] else (0, 0)
            if ow and off == 0 and e["underline"]:
                d.rectangle([lx - ow, ly + ul / p - ow, lx + width / p + ow, ly + (ul + th) / p - 1 + ow], fill=oc)
            _draw_text(d, (lx + off, ly + off), text, font, col + (255,), e["spacing"] / p,
                       ow if off == 0 else 0, oc)
            if e["underline"]:
                d.rectangle([lx + off, ly + off + ul / p, lx + off + width / p,
                             ly + off + (ul + th) / p - 1], fill=col + (255,))
    if typing and r["cursor"] and cursor and int(t * 2.5) % 2 == 0:
        e, w = cursor
        cx = e["x"] + w + (e["size"] * 0.06 if w else 0)
        d.rectangle([cx / p, (e["base"] - e["cursor_h"]) / p, (cx + e["size"] * 0.5) / p, e["base"] / p - 1],
                    fill=hex_rgb(e["color"]) + (255,))

    if p > 1:
        img = img.resize((lw * p, lh * p), Image.NEAREST)
    arr = np.asarray(img, dtype=np.uint8)[:H, :W].copy()
    if retro and r["scanlines"] == "text":
        rows = (np.arange(H) // max(p, 1)) % 2 == 1
        a = arr[..., 3].astype(np.float32)
        a[rows] *= 1 - r["scanline_strength"] / 100.0
        arr[..., 3] = a.astype(np.uint8)
    return arr


# ------------------------------------------------------------------ media
def _resize(img: Image.Image, w: int, h: int, mode: str) -> Image.Image:
    if mode == "crisp" or (mode == "auto" and w >= img.width and h >= img.height):
        return img.resize((w, h), Image.NEAREST)
    return img.resize((w, h), Image.LANCZOS)


def media_fx(arr: np.ndarray, s: dict) -> np.ndarray:
    fx = s["media_fx"]
    mode = fx["mode"]
    if mode == "none":
        return arr
    h, w = arr.shape[:2]
    if mode in ("ps1", "pixelate") and fx["pixel"] > 1:
        p = fx["pixel"]
        small = Image.fromarray(arr).resize((max(1, w // p), max(1, h // p)), Image.BOX)
        a = np.asarray(small, dtype=np.float32) / 255.0
    else:
        p = 1
        a = arr.astype(np.float32) / 255.0
    if mode == "ps1":
        hh, ww = a.shape[:2]
        thr = np.tile(BAYER4, (hh // 4 + 1, ww // 4 + 1))[:hh, :ww][..., None]
        a = np.clip(np.floor(a * 31 + thr) / 31, 0, 1)
    elif mode == "posterize":
        lv = fx["levels"] - 1
        a = np.round(a * lv) / lv
    out = (a * 255 + 0.5).astype(np.uint8)
    if p > 1:
        out = np.asarray(Image.fromarray(out).resize((w, h), Image.NEAREST))
    return out


def place_media(canvas: np.ndarray, frame: np.ndarray, rect, s: dict) -> None:
    x, y, w, h = rect
    H, W = canvas.shape[:2]
    if x >= W or y >= H or x + w <= 0 or y + h <= 0:
        return
    img = Image.fromarray(frame)
    if img.mode != "RGB":
        img = img.convert("RGB")
    arr = np.asarray(_resize(img, w, h, s["media"]["scaling"]))
    arr = media_fx(arr, s)
    sx0, sy0 = max(0, -x), max(0, -y)
    dx0, dy0 = max(0, x), max(0, y)
    cw, ch = min(w - sx0, W - dx0), min(h - sy0, H - dy0)
    canvas[dy0:dy0 + ch, dx0:dx0 + cw] = arr[sy0:sy0 + ch, sx0:sx0 + cw, :3]


# ------------------------------------------------------------------ compose
def _shift(a: np.ndarray, dx: int) -> np.ndarray:
    if dx == 0:
        return a
    out = np.zeros_like(a)
    if dx > 0:
        out[:, dx:] = a[:, :-dx]
    else:
        out[:, :dx] = a[:, -dx:]
    return out


def composite_text(canvas: np.ndarray, layer: np.ndarray, s: dict) -> np.ndarray:
    r = s["retro"]
    split = r["rgb_split"] if r["enabled"] else 0
    out = canvas.astype(np.float32)
    rgb = layer[..., :3].astype(np.float32)
    alpha = layer[..., 3].astype(np.float32) / 255.0
    for c, dx in enumerate((-split, 0, split)):
        a = _shift(alpha, dx)
        col = _shift(rgb[..., c], dx)
        out[..., c] = out[..., c] * (1 - a) + col * a
    return out


def compose(s: dict, lay: dict, frame: np.ndarray | None, t: float = 0.0, index: int = 0,
            layer: np.ndarray | None = None) -> np.ndarray:
    """Final RGB uint8 frame (H, W, 3)."""
    W, H = lay["W"], lay["H"]
    canvas = np.empty((H, W, 3), np.uint8)
    canvas[:] = hex_rgb(s["canvas"]["background"])
    if frame is not None:
        place_media(canvas, frame, media_rect(s, lay, frame.shape[1], frame.shape[0]), s)
    if layer is None:
        layer = text_layer(s, lay, t, index)
    out = composite_text(canvas, layer, s)
    r = s["retro"]
    if r["enabled"] and r["scanlines"] == "frame":
        p = max(1, r["pixel"])
        rows = (np.arange(H) // p) % 2 == 1
        out[rows] *= 1 - r["scanline_strength"] / 200.0
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)
