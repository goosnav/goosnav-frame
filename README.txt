Goosnav Frame

Frames an image or video into an ad: a capital Helvetica title above, the
media in the middle, an underlined Times link below. Edit the text and
effects in the browser, then export an MP4 or PNG.

OPEN THE APPLICATION
--------------------
Extract the complete ZIP. Keep every launcher beside the `app` folder.

- macOS (Intel or Apple Silicon): double-click "Open Goosnav Frame — macOS.app".
- Windows x64: double-click "Open Goosnav Frame — Windows x64.exe".
- Linux x86_64: double-click "Open Goosnav Frame — Linux x86_64.AppImage".
- Linux ARM64: double-click "Open Goosnav Frame — Linux ARM64.AppImage".

Windows on ARM is not supported yet (the bundled video encoder has no ARM
build).

Or run a start script yourself (same app, same data):
- Linux / macOS terminal: ./"Start Goosnav Frame.sh"
  (add --no-browser on a headless server, --port 9000 for another port,
  --local to keep it off the network). Ctrl+C stops it.
- macOS: double-click "Start Goosnav Frame.command".
- Windows: double-click "Start Goosnav Frame.bat".

A setup page opens in your browser. The first launch downloads Python and
the locked libraries (about 100 MB) and needs a network connection. Later
launches start in about a second. Nothing else needs to be installed.

USE IT FROM YOUR PHONE OR ANOTHER COMPUTER
------------------------------------------
While it runs, the top of the page shows "Other devices: http://...:8787".
Open that address on any device on the same network. If it does not load,
allow incoming connections for Goosnav Frame in this computer's firewall.
Anyone on your network can use it while it runs; quit it from this
computer when you are done (the Quit button, top right).

LINUX FIRST LAUNCH
------------------
If double-clicking the AppImage does nothing, open its Properties >
Permissions, turn on "Allow executing file as program", and try again.

SECURITY PROMPTS
----------------
These launchers are not signed yet.
- macOS: if it says the app cannot be opened, Control-click the app, choose
  Open, then Open again.
- Windows: if SmartScreen appears, choose "More info", then "Run anyway".

WHERE YOUR FILES ARE
--------------------
Uploads, exports, presets and logs are kept in:
- macOS:   ~/Library/Application Support/GoosnavFrame
- Windows: %LOCALAPPDATA%\GoosnavFrame
- Linux:   ~/.local/share/GoosnavFrame
Exports are in the `data/exports` folder there, and can be downloaded from
the Export panel on any device.

RECOVERY
--------
If setup fails, the setup page shows an error code, a Retry button when
retrying is safe, and the log location. Do not move a launcher away from
the `app` folder. Deleting the `runtimes` folder above forces a clean
reinstall on the next launch; your uploads and exports are not affected.
