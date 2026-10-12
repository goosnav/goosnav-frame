"""Render a framed PNG or MP4 from settings + media."""
from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from . import media as M
from .render import compose, layout, text_layer
from .settings import is_animated

CRF = {"high": 16, "medium": 21, "small": 27}


class Cancelled(Exception):
    pass


def plan(s: dict, info: M.Info | None) -> dict:
    """Timing for an export: start, duration, fps, frame count."""
    if info is None or info.kind == "image":
        dur = s["media"]["image_duration"]
        fps = s["export"]["fps"] or 24
        start = 0.0
    else:
        start = min(s["media"]["trim_start"], max(0.0, info.duration - 0.05))
        dur = info.duration - start
        if s["media"]["trim_duration"] > 0:
            dur = min(dur, s["media"]["trim_duration"])
        fps = s["export"]["fps"] or info.fps or 24
    fps = float(min(max(fps, 1), 60))
    frames = max(1, int(round(dur * fps)))
    return {"start": start, "duration": frames / fps, "fps": fps, "frames": frames}


def render_still(s: dict, path: str | None, t: float) -> np.ndarray:
    lay = layout(s)
    frame = None
    if path:
        info = M.probe(path)
        tt = t + (s["media"]["trim_start"] if info.kind == "video" else 0)
        frame = M.frame_at(path, tt)
    return compose(s, lay, frame, t, int(t * 24))


def export_png(s: dict, path: str | None, out: Path) -> Path:
    Image.fromarray(render_still(s, path, s["export"]["time"])).save(out, "PNG", optimize=False)
    return out


def export_mp4(s: dict, path: str | None, out: Path, progress: Callable[[float], None] | None = None,
               cancel: threading.Event | None = None, half: bool = False) -> Path:
    info = M.probe(path) if path else None
    pl = plan(s, info)
    lay = layout(s)
    W, H = lay["W"], lay["H"]
    ow, oh = (W // 4 * 2, H // 4 * 2) if half else (W, H)
    animated = is_animated(s)
    static_layer = None if animated else text_layer(s, lay, 0.0, 0)
    tmp = out.with_suffix(".video.mp4")
    crf = CRF[s["export"]["quality"]] + (6 if half else 0)
    cmd = [M.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", f"{pl['fps']}", "-i", "-"]
    if half:
        cmd += ["-vf", f"scale={ow}:{oh}:flags=neighbor"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast" if half else "medium", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, **M._hidden())

    def frames():
        if info is None or info.kind == "image":
            still = M.load_image(path) if path else None
            for _ in range(pl["frames"]):
                yield still
        else:
            last = None
            n = 0
            for fr in M.iter_frames(path, pl["start"], pl["duration"], pl["fps"]):
                last = fr
                n += 1
                yield fr
            while n < pl["frames"] and last is not None:  # pad a short decode with the last frame
                n += 1
                yield last

    cached = None
    try:
        for i, fr in enumerate(frames()):
            if i >= pl["frames"]:
                break
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            t = i / pl["fps"]
            if not animated and (info is None or info.kind == "image"):
                if cached is None:
                    cached = compose(s, lay, fr, t, i, static_layer)
                out_frame = cached
            else:
                out_frame = compose(s, lay, fr, t, i, static_layer)
            enc.stdin.write(out_frame.tobytes())
            if progress:
                progress((i + 1) / pl["frames"] * (0.97 if not half else 1.0))
        enc.stdin.close()
        err = enc.stderr.read().decode("utf-8", "replace")
        if enc.wait() != 0:
            raise RuntimeError("Video encoder failed: " + err.strip()[-400:])
    except BaseException:
        enc.kill()
        enc.wait()
        tmp.unlink(missing_ok=True)
        raise

    use_audio = (info is not None and info.kind == "video" and info.has_audio
                 and s["media"]["keep_audio"] and not half)
    if use_audio:
        mux = [M.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(tmp),
               "-ss", f"{pl['start']:.4f}", "-t", f"{pl['duration']:.4f}", "-i", str(path),
               "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-shortest", "-movflags", "+faststart", str(out)]
        res = subprocess.run(mux, capture_output=True, timeout=600, **M._hidden())
        if res.returncode == 0:
            tmp.unlink(missing_ok=True)
        else:
            os.replace(tmp, out)
    else:
        os.replace(tmp, out)
    if progress:
        progress(1.0)
    return out
