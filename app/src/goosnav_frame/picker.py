"""Native host file chooser; no user text is interpreted as commands."""
import subprocess
import sys
from .services import ServiceError


def choose_path(kind: str) -> str:
    if kind not in ("folder", "file"):
        raise ServiceError(400, "BAD_KIND", "Choose a folder or text file")
    if sys.platform != "darwin":
        raise ServiceError(400, "PASTE_PATH", "Paste the folder or file path in the field on this computer")
    noun = "folder" if kind == "folder" else "file"
    script = f'POSIX path of (choose {noun} with prompt "Goosnav Frame: choose a {noun}")'
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise ServiceError(408, "PICKER_TIMEOUT", "Folder chooser timed out; try again or paste a path") from exc
    if result.returncode:
        if "(-128)" in result.stderr:
            return ""
        raise ServiceError(400, "PICKER_FAILED", "Could not open the chooser; paste a path instead")
    return result.stdout.strip()
