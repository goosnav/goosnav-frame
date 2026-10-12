#!/bin/sh
# macOS: double-click to start Goosnav Frame in Terminal. Close the window or press Ctrl+C to stop.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec /bin/sh "$DIR/Start Goosnav Frame.sh" "$@"
