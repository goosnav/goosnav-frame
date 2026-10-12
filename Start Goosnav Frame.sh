#!/bin/sh
# Start Goosnav Frame from a terminal (Linux or macOS). Works on headless servers.
#
#   ./"Start Goosnav Frame.sh"                 start on port 8787, open a browser if there is a desktop
#   ./"Start Goosnav Frame.sh" --no-browser    never open a browser
#   ./"Start Goosnav Frame.sh" --port 9000     use another port
#   ./"Start Goosnav Frame.sh" --local         only this computer, not the network
#
# The first run downloads Python and the locked libraries (about 100 MB). Press Ctrl+C to stop.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP="$ROOT/app"
[ -f "$APP/launcher/bootstrap.py" ] || { echo "Cannot find the app folder next to this script: $APP" >&2; exit 1; }

case "$(uname -s)" in
  Darwin) OS=macos; DATA="$HOME/Library/Application Support/GoosnavFrame" ;;
  Linux)  OS=linux; DATA="${XDG_DATA_HOME:-$HOME/.local/share}/GoosnavFrame" ;;
  *) echo "Unsupported system: $(uname -s). On Windows use 'Start Goosnav Frame.bat'." >&2; exit 1 ;;
esac
case "$(uname -m)" in
  x86_64|amd64)  ARCH=x64 ;;
  arm64|aarch64) ARCH=arm64 ;;
  *) echo "Unsupported processor: $(uname -m)" >&2; exit 1 ;;
esac

# Prefer the bundled, checksum-pinned uv; fall back to one on PATH.
UV="$APP/launcher/tools/$OS-$ARCH/uv"
if [ -x "$UV" ]; then
  WANT=$(grep " launcher/tools/$OS-$ARCH/uv\$" "$APP/launcher/checksums.sha256" | cut -d' ' -f1)
  if command -v sha256sum >/dev/null 2>&1; then HAVE=$(sha256sum "$UV" | cut -d' ' -f1)
  else HAVE=$(shasum -a 256 "$UV" | cut -d' ' -f1); fi
  [ "$WANT" = "$HAVE" ] || { echo "The bundled setup tool is damaged: $UV" >&2; exit 1; }
elif command -v uv >/dev/null 2>&1; then
  UV=$(command -v uv)
else
  echo "No setup tool found. Extract the complete ZIP so app/launcher/tools is present." >&2; exit 1
fi

mkdir -p "$DATA/data" "$DATA/config" "$DATA/logs"
export UV_PROJECT_ENVIRONMENT="$DATA/runtimes/manual"
export UV_PYTHON_INSTALL_DIR="$DATA/python"
export UV_CACHE_DIR="$DATA/cache/uv"

echo "Preparing Goosnav Frame (first run downloads about 100 MB)..."
"$UV" sync --project "$APP" --locked --no-dev --managed-python --quiet

unset PYTHONPATH
export GOOSNAV_APP_ROOT="$APP" GOOSNAV_APP_DATA="$DATA" GOOSNAV_DATA_DIR="$DATA/data" GOOSNAV_CONFIG_DIR="$DATA/config"
export GOOSNAV_PORT_PREFERENCE="${GOOSNAV_PORT_PREFERENCE:-8787}"
exec "$UV_PROJECT_ENVIRONMENT/bin/python" "$APP/launcher/bootstrap.py" --open "$@"
