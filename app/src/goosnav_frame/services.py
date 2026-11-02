"""Application services: media library, uploads, presets, exports and jobs.

The HTTP layer calls only this module; it holds no rendering logic itself.
"""
from __future__ import annotations

import copy
import random
from datetime import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .core import export as X
from .core import fonts
from .core import media as M
from .core import settings as S

ID_RE = re.compile(r"^(up|lib)-[a-f0-9]{8,40}$")
EXPORT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,120}\.(mp4|png)$")
PRIMARY_COLORS = ("#ff0000", "#0000ff", "#ffff00")

DEFAULT_CAPTIONS = Path(__file__).resolve().parents[2] / "captions" / "Goosnav_Phrasebook_Curated.txt"

def export_name(caption: str, fmt: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", caption).strip("-")[:80] or "ad"
    return f"{base}_{datetime.now().astimezone():%Y%m%d-%H%M%S-%f}.{fmt}"


MAX_UPLOAD = 4 * 1024**3
MAX_FONT = 30 * 1024**2


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class Job:
    id: str
    kind: str
    name: str
    state: str = "queued"  # queued | running | done | failed | cancelled
    progress: float = 0.0
    error: str = ""
    output: str = ""
    results: list = field(default_factory=list)
    total: int = 0
    destination: str = ""
    started: float = field(default_factory=time.time)
    cancel: threading.Event = field(default_factory=threading.Event)

    def public(self) -> dict:
        return {"id": self.id, "kind": self.kind, "name": self.name, "state": self.state,
                "results": list(self.results), "total": self.total, "destination": self.destination,
                "progress": round(self.progress, 4), "error": self.error, "output": self.output}


class App:
    def __init__(self, data_dir: Path, config_dir: Path, default_roots: list[str] | None = None):
        self.data = data_dir
        self.config_dir = config_dir
        self.uploads = data_dir / "uploads"
        self.exports = data_dir / "exports"
        self.thumbs = data_dir / "thumbs"
        self.font_dir = data_dir / "fonts"
        for d in (self.uploads, self.exports, self.thumbs, self.font_dir, config_dir):
            d.mkdir(parents=True, exist_ok=True)
        fonts.set_user_dir(self.font_dir)
        self.config_path = config_dir / "config.json"
        self.lock = threading.RLock()
        self.config = self._load_config(default_roots or [])
        self.jobs: dict[str, Job] = {}
        self.border_colors = {}
        self.queue_lock = threading.Lock()  # one render at a time
        self._library: dict[str, Path] = {}
        self._selected: dict[str, Path] = {}
        self._library_at = 0.0

    # ------------------------------------------------------------ config
    def _load_config(self, default_roots: list[str]) -> dict:
        cfg = {"library_roots": default_roots, "presets": {}}
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
            if isinstance(raw.get("library_roots"), list):
                cfg["library_roots"] = [str(r) for r in raw["library_roots"]][:20]
            if isinstance(raw.get("presets"), dict):
                cfg["presets"] = {str(k)[:60]: S.normalize(v) for k, v in raw["presets"].items()}
        except (OSError, ValueError, AttributeError):
            pass
        cfg["presets"].setdefault("Reference ad", S.normalize({
            "title": {"text": "ALL OF THIS\nCAN BE YOURS"},
            "retro": {"enabled": True, "pixel": 3, "shadow": True},
            "media": {"border_enabled": True},
        }))
        return cfg

    def _save_config(self) -> None:
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.config, indent=1), encoding="utf-8")
        os.replace(tmp, self.config_path)

    # ------------------------------------------------------------ media
    def _scan_library(self, force: bool = False) -> dict[str, Path]:
        with self.lock:
            if not force and time.time() - self._library_at < 20:
                return self._library
            found: dict[str, Path] = {}
            for root in self.config["library_roots"]:
                rp = Path(root).expanduser()
                if not rp.is_dir():
                    continue
                for dirpath, dirnames, filenames in os.walk(rp):
                    depth = len(Path(dirpath).relative_to(rp).parts)
                    dirnames[:] = [d for d in dirnames if not d.startswith(".")] if depth < 4 else []
                    for fn in filenames:
                        if Path(fn).suffix.lower() in M.MEDIA_EXT and not fn.startswith("."):
                            p = Path(dirpath) / fn
                            found["lib-" + hashlib.sha1(str(p).encode()).hexdigest()[:16]] = p
                    if len(found) > 2000:
                        break
            self._library, self._library_at = found, time.time()
            return found

    def resolve(self, media_id: str | None) -> Path | None:
        if not media_id:
            return None
        if not ID_RE.match(media_id):
            raise ServiceError(400, "BAD_MEDIA", "Unknown media id")
        if media_id.startswith("up-"):
            hits = [h for h in self.uploads.glob(media_id + ".*") if h.suffix.lower() in M.MEDIA_EXT]
            if hits:
                return hits[0]
        else:
            p = self._selected.get(media_id) or self._scan_library().get(media_id) or self._scan_library(force=True).get(media_id)
            if p and p.is_file():
                return p
        raise ServiceError(404, "NO_MEDIA", "That media is no longer available")

    def _item(self, mid: str, p: Path, source: str) -> dict | None:
        try:
            info = M.probe(p)
        except (M.MediaError, OSError, Exception):
            return None
        name = p.name
        if source == "upload":
            meta = p.with_suffix(p.suffix + ".name")
            if meta.exists():
                name = meta.read_text(encoding="utf-8")[:200]
        return {"id": mid, "name": name, "source": source, "info": info.to_dict(),
                "folder": p.parent.name if source == "library" else "", "mtime": p.stat().st_mtime}

    def list_media(self, refresh: bool = False) -> list[dict]:
        items = []
        for p in sorted(self.uploads.iterdir(), key=lambda q: q.stat().st_mtime, reverse=True):
            if p.suffix.lower() in M.MEDIA_EXT and ID_RE.match(p.stem):
                it = self._item(p.stem, p, "upload")
                if it:
                    items.append(it)
        lib = sorted(self._scan_library(refresh).items(), key=lambda kv: kv[1].stat().st_mtime, reverse=True)
        for mid, p in lib:
            it = self._item(mid, p, "library")
            if it:
                items.append(it)
        known = {item["id"] for item in items}
        for mid, p in list(self._selected.items()):
            if mid not in known and p.is_file():
                item = self._item(mid, p, "folder")
                if item:
                    items.append(item)
        return items

    def inspect_folder(self, folder: str) -> dict:
        source = Path(folder).expanduser().resolve() if folder.strip() else None
        if source is None or not source.is_dir():
            raise ServiceError(400, "BAD_FOLDER", "Choose an existing source folder")
        paths = sorted(p for p in source.iterdir() if p.is_file() and not p.name.startswith(".")
                       and p.suffix.lower() in M.MEDIA_EXT)
        sample = None
        for path in paths[:30]:
            mid = "lib-" + hashlib.sha1(str(path).encode()).hexdigest()[:16]
            sample = self._item(mid, path, "folder")
            if sample:
                self._selected[mid] = path
                break
        return {"folder": str(source), "count": len(paths), "sample": sample,
                "images": sum(p.suffix.lower() in M.IMAGE_EXT for p in paths),
                "videos": sum(p.suffix.lower() in M.VIDEO_EXT for p in paths)}

    def save_upload(self, filename: str, stream, length: int) -> dict:
        ext = Path(filename).suffix.lower()
        if ext not in M.MEDIA_EXT:
            raise ServiceError(415, "BAD_TYPE", "Use an image (PNG, JPG, WebP) or a video (MP4, MOV, WebM, GIF)")
        if length <= 0 or length > MAX_UPLOAD:
            raise ServiceError(413, "TOO_BIG", "Files must be under 4 GB")
        mid = "up-" + uuid.uuid4().hex[:16]
        dest = self.uploads / (mid + ext)
        part = dest.with_suffix(ext + ".part")
        remaining = length
        try:
            with open(part, "wb") as f:
                while remaining > 0:
                    chunk = stream.read(min(1 << 20, remaining))
                    if not chunk:
                        raise ServiceError(400, "SHORT_UPLOAD", "The upload was interrupted")
                    f.write(chunk)
                    remaining -= len(chunk)
            os.replace(part, dest)
        finally:
            part.unlink(missing_ok=True)
        dest.with_suffix(ext + ".name").write_text(Path(filename).name[:200], encoding="utf-8")
        item = self._item(mid, dest, "upload")
        if item is None:
            self.delete_upload(mid)
            raise ServiceError(415, "UNREADABLE", "That file could not be read as an image or video")
        return item

    def delete_upload(self, mid: str) -> None:
        if not ID_RE.match(mid) or not mid.startswith("up-"):
            raise ServiceError(400, "BAD_MEDIA", "Only uploads can be deleted")
        for p in self.uploads.glob(mid + ".*"):
            p.unlink(missing_ok=True)
        for p in self.thumbs.glob(mid + ".*"):
            p.unlink(missing_ok=True)

    def thumb(self, mid: str) -> Path:
        p = self.resolve(mid)
        out = self.thumbs / f"{mid}.{int(p.stat().st_mtime)}.jpg"
        if not out.exists():
            M.thumbnail(p, out)
        return out

    # ------------------------------------------------------------ fonts
    def save_font(self, filename: str, stream, length: int) -> dict:
        ext = Path(filename).suffix.lower()
        if ext not in (".ttf", ".otf", ".ttc"):
            raise ServiceError(415, "BAD_FONT", "Fonts must be .ttf, .otf or .ttc")
        if length <= 0 or length > MAX_FONT:
            raise ServiceError(413, "TOO_BIG", "Fonts must be under 30 MB")
        stem = fonts.safe_font_name(filename)
        dest = self.font_dir / (stem + ext)
        data = stream.read(length)
        tmp = dest.with_suffix(ext + ".part")
        tmp.write_bytes(data)
        try:
            from PIL import ImageFont
            ImageFont.truetype(str(tmp), 20)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            raise ServiceError(415, "BAD_FONT", "That font file could not be opened") from exc
        os.replace(tmp, dest)
        fonts.refresh()
        return {"id": "user-" + stem, "label": stem + " (uploaded)"}

    # ------------------------------------------------------------ presets / library roots
    def presets(self) -> dict:
        return self.config["presets"]

    def save_preset(self, name: str, settings: dict) -> None:
        name = re.sub(r"\s+", " ", str(name)).strip()[:60]
        if not name:
            raise ServiceError(400, "BAD_NAME", "Give the preset a name")
        with self.lock:
            self.config["presets"][name] = S.normalize(settings)
            self._save_config()

    def delete_preset(self, name: str) -> None:
        with self.lock:
            self.config["presets"].pop(name, None)
            self._save_config()

    def set_roots(self, roots: list[str]) -> list[str]:
        clean = []
        for r in roots[:20]:
            r = str(r).strip()
            if r and Path(r).expanduser().is_dir():
                clean.append(str(Path(r).expanduser().resolve()))
        with self.lock:
            self.config["library_roots"] = clean
            self._save_config()
            self._library_at = 0
        return clean

    # ------------------------------------------------------------ render
    def _border_settings(self, s: dict, media_id: str | None) -> dict:
        # Keep the preview and export identical; never randomize individual video frames.
        if s["media"]["border_enabled"] and s["media"]["border_random"]:
            key = (media_id, s["title"]["text"])
            with self.lock:
                if key not in self.border_colors:
                    if len(self.border_colors) >= 1000:
                        self.border_colors.clear()
                    self.border_colors[key] = random.choice(PRIMARY_COLORS)
                s["media"]["border_color"] = self.border_colors[key]
        return s

    def preview_png(self, settings: dict, media_id: str | None, t: float) -> bytes:
        import io

        from PIL import Image
        s = self._border_settings(S.normalize(settings), media_id)
        path = self.resolve(media_id)
        arr = X.render_still(s, str(path) if path else None, max(0.0, float(t)))
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, "PNG", compress_level=1)
        return buf.getvalue()

    def plan(self, settings: dict, media_id: str | None) -> dict:
        s = self._border_settings(S.normalize(settings), media_id)
        path = self.resolve(media_id)
        return X.plan(s, M.probe(path) if path else None)

    def start_export(self, settings: dict, media_id: str | None, quick: bool = False) -> Job:
        s = self._border_settings(S.normalize(settings), media_id)
        path = self.resolve(media_id)
        fmt = "mp4" if quick else s["export"]["format"]
        if fmt == "auto":
            fmt = "mp4" if path and M.probe(path).kind == "video" else "png"
        name = export_name(s["title"]["text"], fmt)
        job = Job(id=secrets.token_hex(8), kind="preview" if quick else "export", name=name)
        self.jobs[job.id] = job
        for old in sorted((j for j in self.jobs.values() if j.state in ("done", "failed", "cancelled")), key=lambda j: j.started)[:-40]:
            self.jobs.pop(old.id, None)

        def run():
            with self.queue_lock:
                if job.cancel.is_set():
                    job.state = "cancelled"
                    return
                job.state = "running"
                out = (self.data / "previews" if quick else self.exports) / name
                try:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    if fmt == "png":
                        X.export_png(s, str(path) if path else None, out)
                    else:
                        X.export_mp4(s, str(path) if path else None, out,
                                     progress=lambda f: setattr(job, "progress", f), cancel=job.cancel, half=quick)
                    job.output = name
                    job.progress = 1.0
                    job.state = "done"
                    if quick:
                        self._prune_previews()
                except X.Cancelled:
                    job.state = "cancelled"
                except Exception as exc:  # surfaced to the GUI, details in the log
                    job.state = "failed"
                    job.error = str(exc)[:300] or exc.__class__.__name__
                    import traceback
                    traceback.print_exc()

        threading.Thread(target=run, daemon=True, name="render-" + job.id).start()
        return job

    def start_batch(self, settings: dict, folder: str, output: str = "",
                    caption_mode: str = "fixed", caption_file: str = "") -> Job:
        source = Path(folder).expanduser().resolve() if folder.strip() else None
        if source is None or not source.is_dir():
            raise ServiceError(400, "BAD_FOLDER", "Enter an existing source folder")
        destination = Path(output).expanduser().resolve() if output.strip() else source / "Goosnav Exports"
        if destination == source:
            raise ServiceError(400, "BAD_OUTPUT", "Choose a subfolder or a separate output folder")
        files = sorted(p for p in source.iterdir() if p.is_file() and not p.name.startswith(".")
                       and p.suffix.lower() in M.MEDIA_EXT)
        if not files:
            raise ServiceError(400, "EMPTY_FOLDER", "No supported images or videos in that folder")
        captions = []
        if caption_mode not in ("fixed", "random"):
            raise ServiceError(400, "BAD_CAPTIONS", "Choose fixed or random captions")
        if caption_mode == "random":
            try:
                captions = [line.strip() for line in Path(caption_file or DEFAULT_CAPTIONS).expanduser()
                            .read_text(encoding="utf-8-sig").splitlines() if line.strip()]
            except (OSError, UnicodeError) as exc:
                raise ServiceError(400, "BAD_CAPTIONS", f"Could not read caption file: {exc}") from exc
            if not captions or any(len(line) > 400 for line in captions):
                raise ServiceError(400, "BAD_CAPTIONS", "Use nonblank captions of at most 400 characters per line")
        s = S.normalize(settings)
        job = Job(id=secrets.token_hex(8), kind="batch", name="Folder batch",
                  total=len(files), destination=str(destination))
        self.jobs[job.id] = job

        def run():
            with self.queue_lock:
                try:
                    if job.cancel.is_set():
                        raise X.Cancelled()
                    destination.mkdir(parents=True, exist_ok=True)
                    job.state = "running"
                    for i, path in enumerate(files):
                        if job.cancel.is_set():
                            raise X.Cancelled()
                        item = copy.deepcopy(s)
                        if captions:
                            item["title"]["text"] = random.choice(captions)
                        if item["media"]["border_enabled"] and item["media"]["border_random"]:
                            item["media"]["border_color"] = random.choice(PRIMARY_COLORS)
                        caption = item["title"]["text"]
                        out = None
                        try:
                            info = M.probe(path)
                            fmt = "png" if info.kind == "image" else "mp4"
                            out = destination / export_name(caption, fmt)
                            if fmt == "png":
                                X.export_png(item, str(path), out)
                            else:
                                X.export_mp4(item, str(path), out, cancel=job.cancel,
                                    progress=lambda f: setattr(job, "progress", (i + f) / len(files)))
                            job.results.append({"source": str(path), "caption": caption, "border_color": item["media"]["border_color"] if item["media"]["border_enabled"] else None, "output": str(out), "error": ""})
                        except X.Cancelled:
                            if out:
                                out.unlink(missing_ok=True)
                            raise
                        except Exception as exc:
                            if out:
                                out.unlink(missing_ok=True)
                            job.results.append({"source": str(path), "caption": caption, "output": "", "error": str(exc)})
                        job.progress = (i + 1) / len(files)
                    failures = sum(bool(r["error"]) for r in job.results)
                    job.state = "done" if not failures else "failed"
                    job.error = f"{failures} of {len(files)} files failed; see results" if failures else ""
                except X.Cancelled:
                    job.state = "cancelled"
                except Exception as exc:
                    job.state, job.error = "failed", str(exc)
                finally:
                    if destination.is_dir():
                        report = destination / ("batch-" + job.id + ".json")
                        report.write_text(json.dumps(job.public(), indent=2), encoding="utf-8")

        threading.Thread(target=run, daemon=True, name="batch-" + job.id).start()
        return job

    def _prune_previews(self) -> None:
        files = sorted((self.data / "previews").glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        for p in files[:-6]:
            p.unlink(missing_ok=True)

    def job(self, jid: str) -> Job:
        j = self.jobs.get(jid)
        if not j:
            raise ServiceError(404, "NO_JOB", "Unknown job")
        return j

    def list_exports(self) -> list[dict]:
        out = []
        for p in sorted(self.exports.iterdir(), key=lambda q: q.stat().st_mtime, reverse=True):
            if EXPORT_RE.match(p.name):
                out.append({"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime})
        return out

    def export_path(self, name: str, preview: bool = False) -> Path:
        if not EXPORT_RE.match(name):
            raise ServiceError(400, "BAD_NAME", "Bad file name")
        p = (self.data / "previews" if preview else self.exports) / name
        if not p.is_file():
            raise ServiceError(404, "NO_FILE", "That export no longer exists")
        return p

    def delete_export(self, name: str) -> None:
        self.export_path(name).unlink(missing_ok=True)

    def clear_previews(self) -> None:
        shutil.rmtree(self.data / "previews", ignore_errors=True)
