"""Goosnav Frame: frame images and videos into Goosnav ads."""
from pathlib import Path
import hashlib

__version__ = "0.2.1"
APP_ID = "com.goosnav.frame"

def _build_id():
    root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256(str(root).encode())
    for directory in (root / "src", root / "static"):
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix in (".py", ".js", ".css", ".html"):
                digest.update(str(path.relative_to(root)).encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()[:16]

BUILD_ID = _build_id()
