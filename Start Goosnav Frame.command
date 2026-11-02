#!/bin/sh
# Double-click in Finder. Keep setup failures visible instead of closing the window.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
/bin/sh "$DIR/Start Goosnav Frame.sh" "$@"
RESULT=$?
if [ "$RESULT" -ne 0 ]; then
  echo "Goosnav Frame could not start (exit $RESULT). Copy the error above for troubleshooting."
  if [ -t 0 ]; then printf 'Press Return to close...'; read -r REPLY; fi
fi
exit "$RESULT"
