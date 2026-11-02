"""Conservative detection of rectangular colored frames, including inset borders."""
from __future__ import annotations

import numpy as np
from PIL import Image


def has_colored_frame(frame: np.ndarray) -> bool:
    image = Image.fromarray(frame).convert("RGB")
    image.thumbnail((256, 256))
    pixels = np.asarray(image).astype(np.int16)
    h, w = pixels.shape[:2]
    if min(h, w) < 24:
        return False
    colorful = (pixels.max(axis=2) - pixels.min(axis=2) >= 65) & (pixels.max(axis=2) >= 90)
    bins = pixels // 48
    codes = bins[..., 0] * 36 + bins[..., 1] * 6 + bins[..., 2]
    colors, counts = np.unique(codes[colorful], return_counts=True)

    def longest_run(row):
        edges = np.diff(np.r_[False, row, False].astype(int))
        starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
        if not len(starts):
            return (0, 0)
        i = np.argmax(ends - starts)
        return int(starts[i]), int(ends[i])

    for color in colors[np.argsort(counts)[-16:]]:
        selected = colorful & (codes == color)
        representative = np.median(pixels[selected], axis=0)
        # Tolerance includes compression and antialiasing around the solid band.
        mask = colorful & (np.max(np.abs(pixels - representative), axis=2) < 60)
        runs = [longest_run(row) for row in mask]
        rows = [y for y, (left, right) in enumerate(runs) if right-left >= w * .4]
        if not rows:
            continue
        top, bottom = rows[0], rows[-1]
        if top > h * .35 or bottom < h * .65 or bottom-top < h * .4:
            continue
        left = max(runs[top][0], runs[bottom][0])
        right = min(runs[top][1], runs[bottom][1])
        if left > w * .35 or right < w * .65 or right-left < w * .4:
            continue
        # Both vertical sides must be nearly continuous, not just four colored corners.
        left_band = mask[top:bottom+1, max(0, left-2):left+3]
        right_band = mask[top:bottom+1, max(0, right-3):min(w, right+2)]
        if not (left_band.any(axis=1).mean() >= .85 and right_band.any(axis=1).mean() >= .85):
            continue
        inset = max(3, int(min(bottom-top, right-left) * .12))
        interior = mask[top+inset:bottom-inset, left+inset:right-inset]
        # A filled colored photo/background is not a frame.
        if interior.size and interior.mean() < .45:
            return True
    return False


def prepare(s: dict, frame: np.ndarray | None) -> dict:
    if (frame is not None and s["media"]["border_enabled"]
            and s["media"]["border_auto_skip"] and has_colored_frame(frame)):
        import copy
        s = copy.deepcopy(s)
        s["media"]["border_enabled"] = False
    return s
