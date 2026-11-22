"""DigitalCrate as a Mac app: the DigitalCrate.app launcher, its window, and the first-run setup.

    digitalcrate app        make ~/Applications/DigitalCrate.app (the installer does this)
    digitalcrate open       what the app runs: start the server if it isn't running, then open the window
    digitalcrate firstrun   what the setup page runs: scan your music, find promising songs, mine a first batch

The window is Chrome, Edge or Brave in app mode when one is installed (its own window, no tabs or address bar, and Web
MIDI works there), otherwise your default browser. The server keeps running when the window closes; the ⏻ button in
the page stops it, and opening the app again starts it.
"""
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import config as C

PORT = 8765
URL = f"http://localhost:{PORT}/"
LOG = Path.home() / "Library/Logs/DigitalCrate.log"
BREW_BIN = ["/opt/homebrew/bin", "/usr/local/bin"]
APP_BROWSERS = ["Google Chrome", "Microsoft Edge", "Brave Browser", "Chromium", "Vivaldi"]


# ---------------- setup state ----------------

def configured():
    """True once you've told DigitalCrate where your music is (a config file or the environment variables)."""
    return bool(C._cfg.get("music")) or bool(os.environ.get("DIGITALCRATE_MUSIC"))


def tool(name):
    return shutil.which(name) or next((f"{d}/{name}" for d in BREW_BIN if Path(f"{d}/{name}").exists()), None)


def state():
    lib = C.LIB_ROOT
    tracks = 0
    if (C.DB_PATH).exists():
        try:
            from .db import connect
            tracks = connect().execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        except Exception:
            pass
    free = shutil.disk_usage(lib if lib.exists() else lib.parent if lib.parent.exists() else Path.home()).free
    return dict(configured=configured(), music=str(C.MUSIC_ROOT), library=str(lib),
                has_library=(lib / "Browser.html").exists(), tracks=tracks, free_gb=round(free / 1e9),
                tools={t: bool(tool(t)) for t in ("ffmpeg", "rubberband")})


def choose_folder(prompt, start=None):
    """The Mac folder picker, in front of the window. Returns a path, or None if cancelled."""
    loc = f' default location (POSIX file "{start}")' if start and Path(start).exists() else ""
    script = (f'tell application (path to frontmost application as text) to '
              f'POSIX path of (choose folder with prompt "{prompt}"{loc})')
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return r.stdout.strip().rstrip("/") or None


def count_audio(path, seconds=6.0):
    """How many audio files a folder holds (stops counting after a few seconds on a huge or slow drive)."""
    n, t0 = 0, time.time()
    for dp, dn, fn in os.walk(Path(path).expanduser()):
        dn[:] = [d for d in dn if not d.startswith(".")]
        n += sum(1 for f in fn if not f.startswith("._") and Path(f).suffix.lower() in C.AUDIO_EXTS)
        if time.time() - t0 > seconds:
            return dict(n=n, more=True)
    return dict(n=n, more=False)


def save_config(music, library):
    music, library = Path(music).expanduser(), Path(library).expanduser()
    if not music.is_dir():
        raise ValueError(f"{music} isn't a folder")
    if library == music or music in library.parents:
        raise ValueError("put the sample library outside your music folder")
    library.mkdir(parents=True, exist_ok=True)
    q = lambda p: '"' + str(p).replace("\\", "\\\\").replace('"', '\\"') + '"'
    C.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    old = C.CONFIG_FILE.read_text() if C.CONFIG_FILE.exists() else ""
    for key, val in (("music", music), ("library", library)):
        line = f"{key} = {q(val)}"
        old = re.sub(rf"(?m)^{key}\s*=.*$", line, old, count=1) if re.search(rf"(?m)^{key}\s*=", old) \
            else line + "\n" + old
    C.CONFIG_FILE.write_text(old)
    return dict(music=str(music), library=str(library))


def first_run(n_scout=400, n_mine=25):
    """Scan → scout a random sample of songs → mine the most promising → build the page."""
    from .scan import scan
    from .scout import scout, RANK_SQL
    from .process import run
    from .build import build
    print("STEP 1/4 Reading your music folder", flush=True)
    scan()
    print(f"STEP 2/4 Listening to {n_scout} songs for the most promising ones", flush=True)
    scout(limit=n_scout, shuffle=True)
    print(f"STEP 3/4 Mining the {n_mine} most promising songs", flush=True)
    w, order = RANK_SQL["vocals"]
    run(f"scout_done=1 AND {w}", (), limit=n_mine, order_by=order)
    print("STEP 4/4 Building your library", flush=True)
    print("BUILDING the browser page…", flush=True)
    build()
    print("BUILD DONE", flush=True)


# ---------------- the window ----------------

def running(timeout=0.5):
    try:
        with urllib.request.urlopen(URL + "api/ping", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def start_server():
    """Start the server in the background (it outlives the window), and wait until it answers."""
    if running():
        return True
    LOG.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PATH=":".join(BREW_BIN + [os.environ.get("PATH", "/usr/bin:/bin")]))
    subprocess.Popen([sys.executable, "-m", "digitalcrate", "serve", "--no-browser"], cwd=str(C.PROJECT_DIR),
                     stdout=open(LOG, "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     start_new_session=True, env=env)
    for _ in range(120):
        if running():
            return True
        time.sleep(0.25)
    return False


def open_window(url=URL):
    for name in APP_BROWSERS:
        exe = Path(f"/Applications/{name}.app/Contents/MacOS/{name}")
        if not exe.exists():
            exe = Path.home() / f"Applications/{name}.app/Contents/MacOS/{name}"
        if exe.exists():
            subprocess.Popen([str(exe), f"--app={url}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return name
    subprocess.run(["open", url])
    return "default browser"


def open_app():
    if not start_server():
        subprocess.run(["osascript", "-e", f'display alert "DigitalCrate didn\'t start" message '
                                           f'"The log is in {LOG}"'])
        sys.exit(1)
    open_window()


# ---------------- the .app ----------------

PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>DigitalCrate</string>
  <key>CFBundleDisplayName</key><string>DigitalCrate</string>
  <key>CFBundleIdentifier</key><string>local.digitalcrate</string>
  <key>CFBundleExecutable</key><string>DigitalCrate</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>{version}</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
"""

LAUNCHER = """#!/bin/bash
# DigitalCrate launcher: starts the local server if needed and opens the window.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd {repo}
exec {python} -m digitalcrate open
"""


def icon_png(path, size=1024):
    """The app icon: a record in a crate, drawn here so the repo needs no binary art."""
    from PIL import Image, ImageDraw
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    m = int(s * 0.09)
    d.rounded_rectangle([m, m, s - m, s - m], radius=int(s * 0.2), fill=(20, 23, 28))
    cx, cy, r = s // 2, int(s * 0.44), int(s * 0.27)  # the record, half out of the crate
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(10, 11, 13))
    for k in range(1, 6):
        rr = r - k * int(r * 0.12)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(42, 46, 54), width=max(2, s // 300))
    lr = int(r * 0.33)
    d.ellipse([cx - lr, cy - lr, cx + lr, cy + lr], fill=(224, 164, 88))
    hr = max(4, int(r * 0.05))
    d.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], fill=(20, 23, 28))
    top = int(s * 0.56)  # the crate front, with slats
    d.rounded_rectangle([int(s * 0.2), top, int(s * 0.8), int(s * 0.82)], radius=int(s * 0.03), fill=(224, 164, 88))
    for y in (0.64, 0.73):
        d.rectangle([int(s * 0.2), int(s * y), int(s * 0.8), int(s * y) + max(3, s // 110)], fill=(170, 118, 56))
    im.save(path)


def make_app(dest=Path.home() / "Applications"):
    from importlib.metadata import version
    app = Path(dest) / "DigitalCrate.app"
    if app.exists():
        shutil.rmtree(app)
    (app / "Contents/MacOS").mkdir(parents=True)
    (app / "Contents/Resources").mkdir()
    try:
        v = version("digitalcrate")
    except Exception:
        v = "0"
    (app / "Contents/Info.plist").write_text(PLIST.format(version=v))
    q = lambda p: "'" + str(p).replace("'", "'\\''") + "'"
    exe = app / "Contents/MacOS/DigitalCrate"
    exe.write_text(LAUNCHER.format(repo=q(C.PROJECT_DIR), python=q(sys.executable)))
    exe.chmod(0o755)
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        iconset = Path(t) / "AppIcon.iconset"
        iconset.mkdir()
        big = Path(t) / "icon.png"
        icon_png(big)
        for px in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                name = f"icon_{px}x{px}{'@2x' if scale == 2 else ''}.png"
                subprocess.run(["sips", "-z", str(px * scale), str(px * scale), str(big), "--out", str(iconset / name)],
                               capture_output=True, check=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(app / "Contents/Resources/AppIcon.icns")],
                       check=True)
    subprocess.run(["touch", str(app)])  # so Finder picks up the icon
    return app
