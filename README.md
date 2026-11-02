# Goosnav Frame

Create framed photo and video ads with a top caption and shop link. Launch with **Start Goosnav Frame.command** on macOS (or the matching Windows/Linux launcher).

Photos now default to PNG, with the full image centered between the title and link. Videos default to MP4. Under Layout and media placement, enable **Add image border** for a fixed color, or **Random primary colour** for red, green, blue, turquoise or orange chosen per ad. The width is adjustable. Adding a border is off by default. With it enabled, **Skip existing colored frames** detects continuous colored rectangles even with white padding outside them. This is a heuristic, not a guarantee: switch it off to force a border. Videos are checked once at the trim start. The preview and single export keep the same selected color, and each batch item gets an independent choice that stays constant across video frames; full-frame overlay, crop, scale and offsets remain available. Captions wrap at word boundaries and shrink when needed. Load **Reference ad** under Presets for the supplied example's pixelated type and gray text shadow.

## Export a folder

1. Click **Batch** on the computer running Frame.
2. Click **Choose folder…** on macOS, or paste the source folder path and click **Load path**. The first readable file appears in the preview. Each supported image or video directly in that folder produces one ad; subfolders are not scanned.
3. Leave the output field empty to save into a new **goosnav_frame_YYYY-MM-DD_HH-MM-SS** folder within the source folder, or choose another parent directory. Each run creates its own timestamped subfolder.
4. Choose **Same title for every ad** to use the Title text, or **Random line from text file**. The default file is `app/captions/Goosnav_Phrasebook_Curated.txt` (356 captions). You can replace that path with any UTF-8 text file, one caption per nonblank line, up to 400 characters per caption. Random choices are independent and may repeat.
5. Scroll to **Export** at the bottom and click **Export folder**. All files save automatically. Photos produce PNGs; videos produce MP4s using the current trim/audio settings. Batch output types are independent of the single-export format selector.

Names use a filesystem-safe caption followed by the local date and timestamp, including microseconds, e.g. `ALL-OF-THIS-CAN-BE-YOURS_20261102-143052-123456.png`. Punctuation becomes hyphens and the caption portion is limited to 80 characters. Source files remain intact. Each batch also saves a JSON report containing original captions, source/output paths and errors. Failed files do not stop the remaining files. Cancel stops queued work and the current video render; an image already rendering may finish.

Single-file exports appear under **Export** with **View** and **Download** links. Batch results show their saved paths. Refreshing the browser reconnects to its last batch while the server is still running; restarting the server does not resume interrupted work.

Existing browser settings receive the centered layout and automatic output defaults once; saved presets remain available. Direct folder access and caption-file paths are available only on the host computer.

## Development checks

```sh
uv run --project app --group dev pytest app/tests/test_core.py -q
node --check app/static/app.js
```

## Retro media looks

Choose **Single** for one file or **Batch** for several files. **Media look** applies to the preview and final export, including every batch item. Choose Early 3D dither, 1996 web GIF, CRT scanlines, four-tone handheld, photocopied zine, clean pixels, or poster color. Adjust pixel size and effect strength; Original leaves the media untouched. Output stays at the selected canvas resolution. Text and borders are processed separately.

## Updated launcher

The header shows version 0.2.2. Start scripts now reuse only a server running the same source build. If another version occupies port 8787, the updated copy opens on a free port and prints its address; existing renders are not terminated. Subsequent launches reuse the updated copy. macOS scripts find uv in Homebrew and user install locations even with Finder's limited PATH, and keep startup errors visible. These changes were exercised on macOS; Windows/Linux native binaries were not rebuilt or certified by this update. Folder chooser dialogs are available on macOS; other systems can paste paths.

## Batch uploads

The **Single** and **Batch** tabs are always visible. In Batch, use **Choose files** to select multiple images/videos, or **Choose folder…** to process a folder directly on the host. Remote browsers also have an **Upload folder** picker. Click a queued filename to preview it; × removes it from the queue. **Export batch** at the bottom automatically saves every file in a timestamped subfolder of the chosen Save to directory. With Save to left blank, uploaded batches use the application's exports directory. No download step is required. The queue survives a page refresh.

On the host, **Choose folder…** is the primary folder action; **Folder path** also accepts pasted paths. Remote connections can upload batches and use the bundled phrasebook without access to host filesystem paths.

## Settings between sessions

Settings save automatically into the application config file, including the title/link, media look, border options, layout, caption source, workflow mode and output folder. They restore after quitting and relaunching, even on a new server port or in a fresh browser. Existing browser-stored settings migrate on first opening the updated app at the same address. Changes are shared by connected browser sessions. Browser storage also retains a local copy.

Export folder names begin `goosnav_frame_` followed by local date/time (including microseconds to keep quick successive exports distinct). Filenames inside keep their caption and timestamp. The result panel shows the actual saved path; Open folder is optional. Previously saved files remain on disk after restart; interrupted renders do not resume automatically.
