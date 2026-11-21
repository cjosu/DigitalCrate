"""Back up what can't be regenerated: your ratings and listening history, favourites, sketches, drum labels and pair
votes (all in samples.sqlite), the listening-test manifests and other small state in _data, your config file and
your edits. Samples, stems and models can be re-made from the music; these can't.

Each backup is one zip named by date in BACKUP_DIR (default ~/Documents/DigitalCrate Backups, or `backup_dir` in
digitalcrate.toml); the newest KEEP are kept. The database is copied with SQLite's online backup, so it's consistent
even while the app or a mining run is writing.

    digitalcrate backup                 back up now
    digitalcrate backup --install       also back up every night at 3:30 (a launchd agent; runs on wake if asleep)
    digitalcrate backup --restore FILE  put a backup's database and files back (the current ones are kept as *.before-restore)
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from . import config as C

BACKUP_DIR = Path(os.path.expanduser(C._cfg.get("backup_dir", "~/Documents/DigitalCrate Backups")))
KEEP = int(C._cfg.get("backup_keep", 14))
SMALL = 2_000_000  # small files in _data (manifests, caches of your choices); big ones are regenerable
SKIP = {"galaxy.json", "pairing.pt", "jobs.json"}
LABEL = "com.digitalcrate.backup"


def _config_file():
    for f in (Path(os.environ.get("DIGITALCRATE_CONFIG", C.PROJECT_DIR / "digitalcrate.toml")),
              Path.home() / ".config/digitalcrate/digitalcrate.toml"):
        if f.exists():
            return f


def backup(dest=None, quiet=False):
    if not C.DB_PATH.exists():
        print(f"nothing to back up: {C.DB_PATH} isn't there (is the drive connected?)")
        return None
    dest = Path(dest or BACKUP_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"digitalcrate-{time.strftime('%Y-%m-%d_%H%M')}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "samples.sqlite"
        src = sqlite3.connect(C.DB_PATH, timeout=60)
        dst = sqlite3.connect(db)
        src.backup(dst)
        dst.close(); src.close()
        with zipfile.ZipFile(out.with_suffix(".part"), "w", zipfile.ZIP_DEFLATED) as z:
            z.write(db, "_data/samples.sqlite")
            for f in sorted(C.DATA_DIR.glob("*")):
                if f.is_file() and f.suffix in (".json", ".txt", ".csv") and f.name not in SKIP and f.stat().st_size < SMALL:
                    z.write(f, f"_data/{f.name}")
            edits = C.LIB_ROOT / "Edits"
            if edits.exists():
                for f in edits.rglob("*"):
                    if f.is_file():
                        z.write(f, f"Edits/{f.relative_to(edits)}")
            cfg = _config_file()
            if cfg:
                z.write(cfg, "digitalcrate.toml")
    out.with_suffix(".part").rename(out)
    old = sorted(dest.glob("digitalcrate-*.zip"))[:-KEEP]
    for f in old:
        f.unlink()
    if not quiet:
        print(f"backed up to {out} ({out.stat().st_size / 1e6:.0f} MB); keeping the newest {KEEP}")
    return out


def last_backup():
    zs = sorted(BACKUP_DIR.glob("digitalcrate-*.zip")) if BACKUP_DIR.exists() else []
    return dict(dir=str(BACKUP_DIR), last=zs[-1].name if zs else None,
                when=zs[-1].stat().st_mtime if zs else None, count=len(zs), installed=_plist().exists())


def _plist():
    return Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def install(hour=3, minute=30):
    """A launchd agent that runs `digitalcrate backup` nightly (macOS runs a missed one when the Mac wakes)."""
    import subprocess
    logf = BACKUP_DIR / "backup.log"
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    p = _plist()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key><array><string>{sys.executable}</string><string>-m</string><string>digitalcrate</string><string>backup</string></array>
  <key>WorkingDirectory</key><string>{C.PROJECT_DIR}</string>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>{hour}</integer><key>Minute</key><integer>{minute}</integer></dict>
  <key>StandardOutPath</key><string>{logf}</string><key>StandardErrorPath</key><string>{logf}</string>
</dict></plist>
""")
    subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
    r = subprocess.run(["launchctl", "load", str(p)], capture_output=True, text=True)
    print(f"nightly backup at {hour}:{minute:02d} installed ({p}){' — ' + r.stderr.strip() if r.returncode else ''}")


def restore(zpath):
    """Put a backup back. The current database and files are kept next to them as *.before-restore."""
    zpath = Path(zpath)
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            target = (C.PROJECT_DIR / "digitalcrate.toml") if name == "digitalcrate.toml" else C.LIB_ROOT / name
            if target.exists():
                shutil.copy2(target, target.with_name(target.name + ".before-restore"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(name) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    print(f"restored {zpath.name}; the replaced files were kept as *.before-restore")
