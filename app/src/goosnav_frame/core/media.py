"""Media probing and decoding (Pillow for stills, bundled ffmpeg for video)."""
from __future__ import annotations

import functools
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageOps

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".gif"}
MEDIA_EXT = IMAGE_EXT | VIDEO_EXT


class MediaError(Exception):
    """A file could not be read as an image or video."""


@dataclass
class Info:
    kind: str  # "image" | "video"
    width: int
    height: int
    duration: float
    fps: float
    has_audio: bool

    def to_dict(self) -> dict:
        return asdict(self)


def ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _hidden() -> dict:
    """Keep ffmpeg from flashing a console window on Windows."""
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


@functools.lru_cache(maxsize=256)
def _probe(path: str, mtime: float) -> Info:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        try:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im)
                return Info("image", im.width, im.height, 0.0, 0.0, False)
        except Exception as exc:
            raise MediaError(f"Could not read image: {exc}") from exc
    if ext not in VIDEO_EXT:
        raise MediaError("Unsupported file type")
    proc = subprocess.run([ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True,
                          errors="replace", timeout=60, **_hidden())
    err = proc.stderr
    m = re.search(r"Stream #.*?Video:.*?(\d{2,5})x(\d{2,5})", err)
    if not m:
        raise MediaError("No video stream found")
    w, h = int(m.group(1)), int(m.group(2))
    rot = re.search(r"rotate\s*:\s*(-?\d+)|rotation of (-?[\d.]+) degrees", err)
    if rot:
        deg = abs(int(float(rot.group(1) or rot.group(2)))) % 180
        if deg == 90:
            w, h = h, w
    fps_m = re.search(r"(\d+(?:\.\d+)?) fps", err) or re.search(r"(\d+(?:\.\d+)?) tbr", err)
    fps = float(fps_m.group(1)) if fps_m else 24.0
    dur_m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
    dur = int(dur_m.group(1)) * 3600 + int(dur_m.group(2)) * 60 + float(dur_m.group(3)) if dur_m else 0.0
    if dur <= 0:
        dur = 1.0 / fps
    has_audio = bool(re.search(r"Stream #.*?Audio:", err))
    return Info("video", w, h, dur, fps, has_audio)


def probe(path: str | Path) -> Info:
    p = Path(path)
    return _probe(str(p), p.stat().st_mtime)


@functools.lru_cache(maxsize=8)
def _image(path: str, mtime: float) -> np.ndarray:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im)
        return np.asarray(im.convert("RGB")).copy()


def load_image(path: str | Path) -> np.ndarray:
    p = Path(path)
    return _image(str(p), p.stat().st_mtime)


def _decode_cmd(path: str, info: Info, start: float, duration: float | None, fps: float | None) -> list[str]:
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin"]
    if start > 0:
        cmd += ["-ss", f"{start:.4f}"]
    cmd += ["-i", path]
    if duration:
        cmd += ["-t", f"{duration:.4f}"]
    vf = ["format=rgb24"]
    if fps:
        vf.insert(0, f"fps={fps}")
    cmd += ["-an", "-sn", "-vf", ",".join(vf), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    return cmd


@functools.lru_cache(maxsize=48)
def _frame_at(path: str, mtime: float, t: float) -> np.ndarray:
    info = probe(path)
    t = max(0.0, min(t, max(0.0, info.duration - 0.5 / max(info.fps, 1))))
    proc = subprocess.run(_decode_cmd(path, info, t, None, None)[:-1] + ["-frames:v", "1", "-"],
                          capture_output=True, timeout=60, **_hidden())
    size = info.width * info.height * 3
    if len(proc.stdout) < size:
        if t > 0:
            return _frame_at(path, mtime, 0.0)
        raise MediaError("Could not decode a frame")
    return np.frombuffer(proc.stdout[:size], np.uint8).reshape(info.height, info.width, 3).copy()


def frame_at(path: str | Path, t: float) -> np.ndarray:
    """One RGB frame of any media at time t (images ignore t)."""
    p = Path(path)
    info = probe(p)
    if info.kind == "image":
        return load_image(p)
    return _frame_at(str(p), p.stat().st_mtime, round(float(t), 3))


def iter_frames(path: str | Path, start: float, duration: float, fps: float):
    """Yield RGB frames at `fps` from `start` for `duration` seconds."""
    info = probe(path)
    cmd = _decode_cmd(str(path), info, start, duration, fps)
    size = info.width * info.height * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_hidden())
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(info.height, info.width, 3)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def thumbnail(path: str | Path, out: Path, edge: int = 320) -> Path:
    info = probe(path)
    arr = frame_at(path, min(1.0, info.duration / 3) if info.kind == "video" else 0)
    im = Image.fromarray(arr)
    im.thumbnail((edge, edge))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, "JPEG", quality=82)
    return out


__all__ = ["Info", "MediaError", "MEDIA_EXT", "IMAGE_EXT", "VIDEO_EXT", "probe", "frame_at",
           "iter_frames", "load_image", "thumbnail", "ffmpeg"]
