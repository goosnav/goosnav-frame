"use strict";
// Goosnav Frame GUI. All rendering happens on the server; this page edits the
// settings object, asks for exact preview frames, and drives exports.

const TOKEN = document.querySelector('meta[name="frame-token"]').content;
const $ = (id) => document.getElementById(id);
const STORE = "goosnav-frame/v2";

let DEFAULTS = null;
let settings = null;
let mediaId = null;
let mediaItems = [];
let plan = { duration: 0, fps: 24 };

// ------------------------------------------------------------------ field schema
const FIELDS = {
  "f-title": [
    ["title.visible", "check", "Show title"],
    ["title.text", "textarea", "Text"],
    ["title.uppercase", "check", "All capitals"],
    ["title.font", "font", "Font"],
    ["title.size", "range", "Size", 12, 300, 1],
    ["title.autofit", "check", "Shrink to fit"],
    ["title.color", "color", "Colour"],
    ["title.line_height", "range", "Line height", 0.7, 2, 0.01],
    ["title.letter_spacing", "range", "Letter spacing", -20, 60, 1],
    ["title.top", "range", "Top margin", 0, 600, 1],
    ["title.outline", "range", "Outline", 0, 20, 1],
    ["title.outline_color", "color", "Outline colour"],
  ],
  "f-link": [
    ["link.visible", "check", "Show link"],
    ["link.text", "text", "Text"],
    ["link.font", "font", "Font"],
    ["link.size", "range", "Size", 12, 300, 1],
    ["link.color", "color", "Colour"],
    ["link.underline", "check", "Underline"],
    ["link.underline_thickness", "range", "Line weight", 1, 30, 1],
    ["link.bottom", "range", "Bottom margin", 0, 600, 1],
    ["link.outline", "range", "Outline", 0, 20, 1],
    ["link.outline_color", "color", "Outline colour"],
  ],
  "f-retro": [
    ["retro.enabled", "check", "Retro text on"],
    ["retro.pixel", "range", "Pixel size", 1, 10, 1],
    ["retro.aliased", "check", "Hard edges"],
    ["retro.rgb_split", "range", "RGB split", 0, 10, 1],
    ["retro.scanlines", "select", "Scanlines", [["off", "Off"], ["text", "Text only"], ["frame", "Whole frame"]]],
    ["retro.scanline_strength", "range", "Scanline depth", 0, 100, 1],
    ["retro.shadow", "check", "Hard shadow"],
    ["retro.shadow_color", "color", "Shadow colour"],
    ["retro.jitter", "check", "Jitter (video)"],
    ["retro.typewriter", "check", "Type on"],
    ["retro.type_speed", "range", "Letters / sec", 2, 80, 1],
    ["retro.type_delay", "range", "Type delay (s)", 0, 5, 0.1],
    ["retro.cursor", "check", "Blinking cursor"],
  ],
  "f-media": [
    ["canvas.layout", "select", "Layout", [["overlay", "Text over full-frame media"], ["stacked", "Title / media / link stacked"]]],
    ["media.fit", "select", "Fit", [["contain", "Fit inside"], ["cover", "Fill and crop"], ["stretch", "Stretch"]]],
    ["media.scale", "range", "Scale %", 10, 300, 1],
    ["media.offset_x", "range", "Move left/right", -800, 800, 1],
    ["media.offset_y", "range", "Move up/down", -800, 800, 1],
    ["media.gap", "range", "Gap to text (stacked)", 0, 300, 1],
    ["media.scaling", "select", "Resampling", [["auto", "Auto"], ["crisp", "Crisp pixels"], ["smooth", "Smooth"]]],
    ["media.trim_start", "number", "Start at (s)", 0, 36000, 0.1],
    ["media.trim_duration", "number", "Length (s, 0 = all)", 0, 36000, 0.1],
    ["media.image_duration", "number", "Image video length (s)", 0.5, 120, 0.5],
    ["media.keep_audio", "check", "Keep audio"],
  ],
  "f-mediafx": [
    ["media_fx.mode", "select", "Effect", [["none", "None"], ["ps1", "PS1 dither"], ["pixelate", "Pixelate"], ["posterize", "Posterize"]]],
    ["media_fx.pixel", "range", "Pixel size", 1, 12, 1],
    ["media_fx.levels", "range", "Colour levels", 2, 64, 1],
  ],
  "f-canvas": [
    ["canvas.preset", "select", "Shape", [["4:5", "4:5 portrait 1080×1350"], ["1:1", "1:1 square 1080×1080"], ["9:16", "9:16 story 1080×1920"], ["16:9", "16:9 wide 1920×1080"], ["custom", "Custom"]]],
    ["canvas.width", "number", "Width", 64, 4096, 2],
    ["canvas.height", "number", "Height", 64, 4096, 2],
    ["canvas.background", "color", "Background"],
    ["canvas.side_margin", "range", "Side margin", 0, 400, 1],
  ],
  "f-export": [
    ["export.format", "select", "Format", [["mp4", "MP4 video"], ["png", "PNG still (current time)"]]],
    ["export.quality", "select", "Quality", [["high", "High"], ["medium", "Medium"], ["small", "Small file"]]],
    ["export.fps", "number", "Frame rate (0 = source)", 0, 60, 1],
  ],
};

let FONTS = [];

function get(obj, path) { return path.split(".").reduce((o, k) => (o ? o[k] : undefined), obj); }
function set(obj, path, v) {
  const ks = path.split("."); let o = obj;
  for (const k of ks.slice(0, -1)) o = o[k] = o[k] || {};
  o[ks[ks.length - 1]] = v;
}
function clone(o) { return JSON.parse(JSON.stringify(o)); }
function merge(base, over) {
  const out = clone(base);
  for (const [k, v] of Object.entries(over || {})) {
    if (v && typeof v === "object" && !Array.isArray(v) && typeof out[k] === "object") out[k] = merge(out[k], v);
    else if (k in out) out[k] = v;
  }
  return out;
}

// ------------------------------------------------------------------ api
async function api(path, opts = {}) {
  const headers = Object.assign({ "X-Frame-Token": TOKEN }, opts.headers || {});
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const res = await fetch(path, { method: opts.method || "GET", headers, body: opts.body, signal: opts.signal });
  if (!res.ok) {
    let msg = res.status + " " + res.statusText;
    try { const j = await res.json(); msg = j.error.message; } catch (e) { /* not json */ }
    throw new Error(msg);
  }
  return opts.raw ? res : res.json();
}

function status(msg, err = false) {
  const el = $("status"); el.textContent = msg || ""; el.classList.toggle("err", !!err);
}

// ------------------------------------------------------------------ form
function buildForm() {
  for (const [boxId, fields] of Object.entries(FIELDS)) {
    const box = $(boxId); box.innerHTML = "";
    for (const [path, type, label, a, b, c] of fields) {
      const row = document.createElement("label");
      row.className = "field" + (type === "textarea" ? " wide" : "") + (type === "check" ? " check" : "");
      const cap = document.createElement("span"); cap.textContent = label; row.appendChild(cap);
      let input;
      if (type === "textarea") {
        input = document.createElement("textarea"); input.rows = 3;
      } else if (type === "select" || type === "font") {
        input = document.createElement("select");
        const opts = type === "font" ? FONTS.map((f) => [f.id, f.label]) : a;
        for (const [v, t] of opts) { const o = document.createElement("option"); o.value = v; o.textContent = t; input.appendChild(o); }
      } else if (type === "range") {
        const pair = document.createElement("div"); pair.className = "pair";
        const r = document.createElement("input"); r.type = "range"; r.min = a; r.max = b; r.step = c;
        const n = document.createElement("input"); n.type = "number"; n.min = a; n.max = b; n.step = c;
        r.dataset.path = n.dataset.path = path; r.dataset.kind = n.dataset.kind = "num";
        r.addEventListener("input", () => { n.value = r.value; onField(path, +r.value); });
        n.addEventListener("change", () => { r.value = n.value; onField(path, +n.value); });
        pair.append(r, n); row.appendChild(pair); box.appendChild(row);
        continue;
      } else {
        input = document.createElement("input");
        input.type = type === "check" ? "checkbox" : type === "number" ? "number" : type === "color" ? "color" : "text";
        if (type === "number") { input.min = a; input.max = b; input.step = c; }
      }
      input.dataset.path = path;
      input.dataset.kind = type === "check" ? "bool" : type === "number" ? "num" : "str";
      const ev = type === "text" || type === "textarea" || type === "color" ? "input" : "change";
      input.addEventListener(ev, () => {
        const v = input.dataset.kind === "bool" ? input.checked : input.dataset.kind === "num" ? +input.value : input.value;
        onField(path, v);
      });
      row.appendChild(input); box.appendChild(row);
    }
  }
}

function fillForm() {
  document.querySelectorAll("[data-path]").forEach((el) => {
    const v = get(settings, el.dataset.path);
    if (el.type === "checkbox") el.checked = !!v; else el.value = v;
  });
  const custom = settings.canvas.preset === "custom";
  document.querySelectorAll('[data-path="canvas.width"],[data-path="canvas.height"]').forEach((el) => (el.disabled = !custom));
}

const PRESETS = { "4:5": [1080, 1350], "1:1": [1080, 1080], "9:16": [1080, 1920], "16:9": [1920, 1080] };

function onField(path, value) {
  set(settings, path, value);
  if (path === "canvas.preset" && PRESETS[value]) { settings.canvas.width = PRESETS[value][0]; settings.canvas.height = PRESETS[value][1]; fillForm(); }
  if (path === "canvas.preset") fillForm();
  if (path.startsWith("media.trim") || path === "media.image_duration" || path === "export.fps") refreshPlan();
  save(); schedulePreview();
}

function save() { localStorage.setItem(STORE, JSON.stringify({ settings, mediaId })); }

// ------------------------------------------------------------------ preview
let pvTimer = null, pvBusy = false, pvAgain = false, pvUrl = null;
function schedulePreview(delay = 120) { clearTimeout(pvTimer); pvTimer = setTimeout(renderPreview, delay); }

async function renderPreview() {
  if (pvBusy) { pvAgain = true; return; }
  pvBusy = true; $("busy").hidden = false;
  settings.export.time = +$("time").value;
  try {
    const res = await api("/api/preview", { method: "POST", json: { settings, media_id: mediaId, t: +$("time").value }, raw: true });
    const blob = await res.blob();
    if (pvUrl) URL.revokeObjectURL(pvUrl);
    pvUrl = URL.createObjectURL(blob);
    $("preview").src = pvUrl;
    if (!$("status").classList.contains("err") || $("status").dataset.src === "preview") status("");
  } catch (e) {
    status("Preview failed: " + e.message, true); $("status").dataset.src = "preview";
  } finally {
    pvBusy = false; $("busy").hidden = true;
    if (pvAgain) { pvAgain = false; renderPreview(); }
  }
}

async function refreshPlan() {
  try {
    plan = await api("/api/plan", { method: "POST", json: { settings, media_id: mediaId } });
    const t = $("time"); t.max = Math.max(0.01, plan.duration - 1 / plan.fps).toFixed(2);
    if (+t.value > +t.max) t.value = t.max;
    $("tlabel").textContent = (+t.value).toFixed(2) + " s";
    const item = mediaItems.find((m) => m.id === mediaId);
    const what = !item ? "No media: text only" : item.info.kind === "image" ? "Image" : "Video";
    $("planInfo").textContent = `${what} · MP4 will be ${plan.duration.toFixed(2)} s at ${+plan.fps.toFixed(2)} fps (${plan.frames} frames), ${settings.canvas.width}×${settings.canvas.height}`;
  } catch (e) { status(e.message, true); }
}

$("time").addEventListener("input", () => { $("tlabel").textContent = (+$("time").value).toFixed(2) + " s"; schedulePreview(60); });

// ------------------------------------------------------------------ jobs
async function runJob(quick, bar, onDone) {
  const job = await api("/api/export", { method: "POST", json: { settings, media_id: mediaId, quick } });
  bar.hidden = false; const fill = bar.querySelector("span"); fill.style.width = "0";
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const j = await api("/api/jobs/" + job.id);
        fill.style.width = Math.round(j.progress * 100) + "%";
        if (j.state === "done") { bar.hidden = true; onDone(j); resolve(j); return; }
        if (j.state === "failed") { bar.hidden = true; reject(new Error(j.error || "Render failed")); return; }
        if (j.state === "cancelled") { bar.hidden = true; reject(new Error("Cancelled")); return; }
        setTimeout(tick, 400);
      } catch (e) { bar.hidden = true; reject(e); }
    };
    tick();
    currentJob = job.id;
  });
}
let currentJob = null;

$("quick").addEventListener("click", async () => {
  $("quick").disabled = true; status("Rendering a quick half-size preview video…");
  try {
    await runJob(true, $("exportBar"), (j) => {
      const v = $("pvideo"); v.src = "/api/previews/" + encodeURIComponent(j.output) + "?inline=1";
      v.hidden = false; $("preview").hidden = true; $("backToFrame").hidden = false; v.play().catch(() => {});
      status("Preview video (half size). Export makes the full-quality file.");
    });
  } catch (e) { status(e.message, true); }
  $("quick").disabled = false;
});
$("backToFrame").addEventListener("click", () => {
  const v = $("pvideo"); v.pause(); v.hidden = true; $("preview").hidden = false; $("backToFrame").hidden = true;
});

$("exportBtn").addEventListener("click", async () => {
  $("exportBtn").disabled = true; $("cancelBtn").hidden = false; status("Exporting…");
  settings.export.time = +$("time").value;
  try {
    await runJob(false, $("exportBar"), async (j) => {
      await loadExports(); status("Exported " + j.output);
    });
  } catch (e) { status(e.message, e.message !== "Cancelled"); }
  $("exportBtn").disabled = false; $("cancelBtn").hidden = true;
});
$("cancelBtn").addEventListener("click", () => { if (currentJob) api("/api/jobs/" + currentJob + "/cancel", { method: "POST", json: {} }); });

async function loadExports() {
  const { items } = await api("/api/exports");
  const ul = $("exports"); ul.innerHTML = "";
  for (const it of items.slice(0, 30)) {
    const li = document.createElement("li");
    const name = document.createElement("span"); name.className = "name"; name.textContent = it.name; name.title = it.name;
    const size = document.createElement("span"); size.className = "muted"; size.textContent = (it.size / 1048576).toFixed(1) + " MB";
    const view = document.createElement("a"); view.href = "/api/exports/" + encodeURIComponent(it.name) + "?inline=1"; view.target = "_blank"; view.textContent = "View";
    const dl = document.createElement("a"); dl.href = "/api/exports/" + encodeURIComponent(it.name); dl.textContent = "Download"; dl.setAttribute("download", it.name);
    const del = document.createElement("button"); del.className = "ghost"; del.textContent = "×"; del.title = "Delete";
    del.addEventListener("click", async () => { if (confirm("Delete " + it.name + "?")) { await api("/api/exports/" + encodeURIComponent(it.name), { method: "DELETE" }); loadExports(); } });
    li.append(name, size, view, dl, del); ul.appendChild(li);
  }
  if (!items.length) ul.innerHTML = '<li class="muted">No exports yet.</li>';
}

// ------------------------------------------------------------------ media
async function loadMedia(refresh = false) {
  const { items } = await api("/api/media" + (refresh ? "?refresh=1" : ""));
  mediaItems = items; drawMedia();
}

function drawMedia() {
  const grid = $("mediaGrid"); grid.innerHTML = "";
  const f = $("mediaFilter").value.trim().toLowerCase();
  for (const it of mediaItems) {
    if (f && !(it.name + " " + it.folder).toLowerCase().includes(f)) continue;
    const b = document.createElement("button"); b.className = "tile" + (it.id === mediaId ? " on" : ""); b.type = "button";
    b.title = it.folder ? it.folder + " / " + it.name : it.name;
    const img = document.createElement("img"); img.loading = "lazy"; img.alt = ""; img.src = "/api/media/" + it.id + "/thumb";
    const cap = document.createElement("span"); cap.className = "cap"; cap.textContent = it.name;
    const kind = document.createElement("span"); kind.className = "kind";
    kind.textContent = it.info.kind === "video" ? it.info.duration.toFixed(1) + "s" : "IMG";
    b.append(img, cap, kind);
    if (it.source === "upload") {
      const del = document.createElement("span"); del.className = "del button"; del.textContent = "×"; del.title = "Remove upload";
      del.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        if (!confirm("Remove " + it.name + " from uploads?")) return;
        await api("/api/media/" + it.id, { method: "DELETE" });
        if (mediaId === it.id) selectMedia(null);
        loadMedia();
      });
      b.appendChild(del);
    }
    b.addEventListener("click", () => selectMedia(it.id));
    grid.appendChild(b);
  }
  if (!grid.children.length) grid.innerHTML = '<p class="muted small">Nothing here yet. Upload an image or video.</p>';
  const cur = mediaItems.find((m) => m.id === mediaId);
  $("mediaInfo").textContent = cur
    ? `${cur.name} · ${cur.info.width}×${cur.info.height}` + (cur.info.kind === "video" ? ` · ${cur.info.duration.toFixed(2)} s · ${cur.info.fps} fps${cur.info.has_audio ? " · audio" : ""}` : "")
    : "No media selected: the export will be text only.";
}

function selectMedia(id) {
  mediaId = id; $("time").value = 0; $("tlabel").textContent = "0.00 s";
  save(); drawMedia(); refreshPlan(); schedulePreview(0);
}

function upload(file) {
  if (!file) return;
  const bar = $("uploadBar"); const fill = bar.querySelector("span"); bar.hidden = false; fill.style.width = "0";
  status("Uploading " + file.name + "…");
  const xhr = new XMLHttpRequest();
  xhr.open("PUT", "/api/upload?name=" + encodeURIComponent(file.name));
  xhr.setRequestHeader("X-Frame-Token", TOKEN);
  xhr.setRequestHeader("Content-Type", "application/octet-stream");
  xhr.upload.onprogress = (e) => { if (e.lengthComputable) fill.style.width = Math.round((e.loaded / e.total) * 100) + "%"; };
  xhr.onload = async () => {
    bar.hidden = true;
    if (xhr.status !== 200) {
      let msg = "Upload failed"; try { msg = JSON.parse(xhr.responseText).error.message; } catch (e) { /* keep */ }
      status(msg, true); return;
    }
    const item = JSON.parse(xhr.responseText);
    await loadMedia(); selectMedia(item.id); status("Uploaded " + file.name);
  };
  xhr.onerror = () => { bar.hidden = true; status("Upload failed: connection lost", true); };
  xhr.send(file);
}

$("file").addEventListener("change", (e) => { upload(e.target.files[0]); e.target.value = ""; });
$("noMedia").addEventListener("click", () => selectMedia(null));
$("refreshMedia").addEventListener("click", () => loadMedia(true));
$("mediaFilter").addEventListener("input", drawMedia);

let dragDepth = 0;
window.addEventListener("dragenter", (e) => { e.preventDefault(); dragDepth++; $("dropHint").hidden = false; });
window.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; $("dropHint").hidden = true; } });
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
  e.preventDefault(); dragDepth = 0; $("dropHint").hidden = true;
  const f = e.dataTransfer.files[0];
  if (!f) return;
  if (/\.(ttf|otf|ttc)$/i.test(f.name)) uploadFont(f); else upload(f);
});

// ------------------------------------------------------------------ fonts
async function uploadFont(file) {
  try {
    const res = await api("/api/fonts?name=" + encodeURIComponent(file.name), { method: "PUT", body: file, headers: { "Content-Type": "application/octet-stream" } });
    FONTS = res.fonts; buildForm(); fillForm(); status("Added font " + res.font.label);
  } catch (e) { status(e.message, true); }
}
$("fontFile").addEventListener("change", (e) => { uploadFont(e.target.files[0]); e.target.value = ""; });

// ------------------------------------------------------------------ presets
let PRESET_DATA = {};
function drawPresets() {
  const sel = $("presetSelect"); sel.innerHTML = '<option value="">Saved presets…</option>';
  for (const name of Object.keys(PRESET_DATA).sort()) { const o = document.createElement("option"); o.value = o.textContent = name; sel.appendChild(o); }
}
$("presetSave").addEventListener("click", async () => {
  const name = $("presetName").value.trim(); if (!name) { status("Name the preset first", true); return; }
  PRESET_DATA = (await api("/api/presets", { method: "POST", json: { name, settings } })).presets;
  drawPresets(); $("presetSelect").value = name; status("Saved preset " + name);
});
$("presetLoad").addEventListener("click", () => {
  const p = PRESET_DATA[$("presetSelect").value]; if (!p) return;
  settings = merge(DEFAULTS, p); fillForm(); save(); refreshPlan(); schedulePreview(0); status("Loaded preset");
});
$("presetDelete").addEventListener("click", async () => {
  const name = $("presetSelect").value; if (!name || !confirm("Delete preset " + name + "?")) return;
  PRESET_DATA = (await api("/api/presets/" + encodeURIComponent(name), { method: "DELETE" })).presets; drawPresets();
});
$("resetAll").addEventListener("click", () => {
  if (!confirm("Reset every setting to the defaults?")) return;
  settings = clone(DEFAULTS); fillForm(); save(); refreshPlan(); schedulePreview(0);
});

// ------------------------------------------------------------------ host-only
$("quit").addEventListener("click", async () => {
  if (!confirm("Stop Goosnav Frame? Other devices will lose access too.")) return;
  await api("/api/quit", { method: "POST", json: {} }).catch(() => {});
  document.body.innerHTML = "<p style='padding:24px'>Goosnav Frame has stopped. You can close this tab.</p>";
});
$("rootsSave").addEventListener("click", async () => {
  const roots = $("roots").value.split("\n").map((s) => s.trim()).filter(Boolean);
  const res = await api("/api/library", { method: "POST", json: { roots } });
  $("roots").value = res.roots.join("\n"); await loadMedia(true); status("Library folders saved (" + res.roots.length + ")");
});

// ------------------------------------------------------------------ boot
(async function boot() {
  try {
    const st = await api("/api/state");
    DEFAULTS = st.defaults; FONTS = st.fonts; PRESET_DATA = st.presets;
    let saved = {}; try { saved = JSON.parse(localStorage.getItem(STORE) || "{}"); } catch (e) { saved = {}; }
    settings = merge(DEFAULTS, saved.settings || {});
    mediaId = saved.mediaId || null;
    if (st.lan.length) $("lan").textContent = "Other devices: " + st.lan.join("  ");
    if (st.local) { $("quit").hidden = false; $("libraryBox").hidden = false; $("roots").value = (st.library_roots || []).join("\n"); }
    buildForm(); fillForm(); drawPresets();
    await loadMedia();
    if (mediaId && !mediaItems.some((m) => m.id === mediaId)) mediaId = null;
    drawMedia(); await refreshPlan(); renderPreview(); loadExports();
  } catch (e) { status("Could not start: " + e.message, true); }
})();
