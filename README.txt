Goosnav Frame 0.2.1

Frames an image or video into an ad: a capital Helvetica title above, the
media in the middle, an underlined Times link below. Edit the text and
effects in the browser, then export an MP4 or PNG.

OPEN THE APPLICATION
--------------------
Extract the complete ZIP. Keep every launcher beside the `app` folder.

- macOS: double-click "Start Goosnav Frame.command" in this folder.
  The header should show 0.2.1. Keep the Terminal window open while working.
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

SINGLE FILE OR FOLDER BATCH
--------------------------
Use the buttons at the top of the panel. Single opens a file picker. Batch offers Choose files and Upload folder.
Use a local folder offers a macOS chooser, or a path field and Load path. It shows a sample and counts before export. Batch output defaults
to a Goosnav Exports subfolder; you can choose a different directory.

Media look has early-3D dither, web GIF, CRT, handheld and zine presets.
The image preview updates as you adjust the look. All batch items use these
settings. Photos export as PNG; videos as MP4. Captions can be fixed or drawn
from the included phrasebook. See README.md for the complete workflow.

A start script checks the running build before reusing it. If an older copy
occupies the usual port, it opens the updated app on another port. Use the
address printed by the launcher instead of an old bookmark.
