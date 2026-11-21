"""Export samples into Ableton's User Library, organised for use.

    python -m digitalcrate export --favorites --name "Night Session"
    python -m digitalcrate export --kit Kit003_05A-Cm_136bpm_eerie
    python -m digitalcrate export --ids ab12cd ef34gh --name "Chops"

Destination: ~/Music/Ableton/User Library/Samples/DigitalCrate/<name>/<Category>/<Subtype>/
(the User Library shows up in Live's browser automatically). Files keep their key/tempo names; an _info.csv
next to them records key, tempo, length, source track and provenance.
"""
import csv
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

from . import config as C
from .db import connect

ABLETON_SAMPLES = C.ABLETON_SAMPLES


def _safe(s):
    return re.sub(r'[/:\\\\*?"<>|]+', "-", s).strip() or "Export"


def export(paths, name=None, reveal=True, rack=False, key=None, bpm=None, midi=False, chop=False):
    """paths: library-relative file paths (samples, variations or edits).
    key/bpm: conform copies to a project key / tempo.  midi: add basic-pitch .mid files next to tonal samples.
    rack: build an Ableton Drum Rack of everything exported.  chop: per sample, slice into syllable chops + a rack."""
    con = connect()
    pkey, pbpm = key, bpm
    name = _safe(name or f"Export {date.today().isoformat()}")
    dest = ABLETON_SAMPLES / name
    rows, pads, extra = [], [], []
    for rel in paths:
        src = C.LIB_ROOT / rel
        if not src.exists():
            continue
        r = con.execute("""SELECT s.*, t.artist, t.title FROM samples s JOIN tracks t ON t.id=s.track_id
                           WHERE s.path=?""", (rel,)).fetchone()
        parts = Path(rel).parts
        if r is None and parts[0] == "Variations":  # inherit musical metadata from the source sample
            r = con.execute("""SELECT s.*, t.artist, t.title FROM variants v JOIN samples s ON s.id=v.sample_id
                               JOIN tracks t ON t.id=s.track_id WHERE v.path=?""", (rel,)).fetchone()
            var = True
        else:
            var = False
        if var:
            sub = Path("Variations") / parts[1] / parts[2]
        elif r is not None:
            sub = Path(r["category"]) / r["subtype"]
        else:
            sub = Path(parts[0])
        out = dest / sub / src.name
        out.parent.mkdir(parents=True, exist_ok=True)
        cinfo = None
        if pkey or pbpm:
            from .conform import render, conformed_name
            csrc, cinfo = render(rel, pkey, pbpm)
            out = dest / sub / conformed_name(rel, cinfo)
            if not out.exists():
                shutil.copy2(csrc, out)
        elif not out.exists():
            shutil.copy2(src, out)
        tag = (r["subtype"] if r else parts[0]) + (f" {r['camelot']}" if r and r["key_from"] != "none" else "")
        pads.append((out, f"{len(pads) + 1:02d} {tag}"))
        if midi and r is not None and r["category"] != "Percussion" and r["key_from"] != "none" and not cinfo:
            try:
                from .midi import transcribe
                mr = transcribe(rel, r["bpm"] if r["kind"] == "loop" else None)
                if mr["notes"]:
                    shutil.copy2(C.LIB_ROOT / mr["midi"], out.with_suffix(".mid"))
                    extra.append(str(out.with_suffix(".mid").relative_to(dest)))
            except Exception as e:
                print("midi failed:", e)
        if chop:
            from .ableton import chops, drum_rack
            import soundfile as sf
            cdir = dest / "Chops" / out.stem
            cdir.mkdir(parents=True, exist_ok=True)
            cp = []
            for k, (z, t0) in enumerate(chops(rel)):
                f = cdir / f"{out.stem[:60]}_chop{k + 1:02d}.wav"
                sf.write(str(f), z.T, C.SR, subtype="PCM_24")
                cp.append((f, f"{k + 1:02d} @{t0:.2f}s"))
            drum_rack(cp, f"{out.stem[:40]} chops", dest / f"{out.stem[:60]} chops.adg")
            extra.append(f"{out.stem[:60]} chops.adg")
        key = ""
        if r and r["key_from"] != "none":
            from .audio import PITCHES, camelot
            shift = 0
            if var:  # pitched variations: shift the key by the variation's pitch amount
                ch = con.execute("SELECT chain FROM variants WHERE path=?", (rel,)).fetchone()
                m = re.search(r"(?:pitch|tape|vari)([+-]\d+)", ch["chain"] if ch else "")
                shift = int(m.group(1)) if m else 0
            pc = (PITCHES.index(r["key"]) + shift + (cinfo or {}).get("semis", 0)) % 12
            key = f"{camelot(pc, r['scale'])} {PITCHES[pc]}{'m' if r['scale'] == 'minor' else ''}"
        rows.append(dict(file=str(out.relative_to(dest)), category=r["category"] if r else "",
                         subtype=r["subtype"] if r else "", key=key,
                         bpm=(cinfo.get("bpm") if cinfo and cinfo.get("bpm") else (round(r["bpm"]) if r and r["bpm"] else "")), bars=r["bars"] if r else "",
                         seconds=(round(__import__("soundfile").info(str(out)).duration, 2) if cinfo else round(r["dur"], 2)) if r else "", source=f"{r['artist']} — {r['title']}" if r else "",
                         at=f"{int(r['start'] // 60)}:{int(r['start'] % 60):02d}" if r else "",
                         id=r["id"] if r else "", edited_from=(f"variation of {r['id']}" if var else (r["parent_id"] or "")) if r else "",
                         library_path=rel))
    if rows:
        info = dest / "_info.csv"
        new = not info.exists()
        with open(info, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            if new:
                w.writeheader()
            w.writerows(rows)
        if rack and pads:
            from .ableton import drum_rack
            drum_rack(pads, name, dest / f"{name}.adg")
            extra.append(f"{name}.adg")
        if reveal:
            subprocess.run(["open", str(dest)])
    return dict(dest=str(dest), count=len(rows), extra=extra)


def favorites_paths():
    con = connect()
    return [r["path"] for r in con.execute("SELECT path FROM favorites ORDER BY added_at")]


def kit_paths(kit_name):
    d = C.LIB_ROOT / "Kits" / kit_name
    con = connect()
    names = {p.name for p in d.glob("*.wav")}
    return [r["path"] for r in con.execute("SELECT path FROM samples") if Path(r["path"]).name in names]
