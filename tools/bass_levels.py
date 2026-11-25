"""Compare raw and Even bass on each prepared song's busiest four bars."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from digitalcrate import basscond, config


def levels(y, sr):
    rms = float(np.sqrt(np.mean(y ** 2)))
    peak = float(np.abs(y).max())
    db = lambda value: 20 * np.log10(max(value, 1e-12))
    return db(rms), db(basscond.heard(y.mean(axis=0), sr)), db(peak) - db(rms), peak


def report(stems):
    before, after = [], []
    for path in sorted(stems.glob("t*/meta.json")):
        meta = json.loads(path.read_text())
        bars = meta["bars"]
        if "bass" not in meta["stems"] or len(bars) < 5:
            continue
        first = int(np.argmax(np.convolve(meta["act"]["bass"], np.ones(4), "valid")))
        source = path.with_name("bass.flac")
        with sf.SoundFile(source) as audio:
            sr = audio.samplerate
            start, end = int(bars[first] * sr), int(bars[first + 4] * sr)
            audio.seek(start)
            y = audio.read(end - start, dtype="float32", always_2d=True).T
        if not y.size:
            continue
        rms = float(np.sqrt(np.mean(y ** 2) + 1e-12))
        gain = min(0.08 / rms, 0.9 / (np.abs(y).max() + 1e-9), 60.0)
        before.append(levels(y * gain, sr))
        after.append(levels(basscond.condition(y, sr), sr))

    if not before:
        raise SystemExit(f"No prepared four-bar bass parts in {stems}")
    print(f"{len(before)} bass parts (each song's busiest four bars)")
    print(f"{'Measure':<28} {'Plain':>19} {'Even':>19}")
    print(f"{'RMS dBFS (5th–95th)':<28}", end="")
    for data in (before, after):
        lo, hi = np.percentile(np.asarray(data)[:, 0], [5, 95])
        print(f" {lo:8.2f} to {hi:6.2f}", end="")
    print()
    print(f"{'B-weighted dBFS (5th–95th)':<28}", end="")
    for data in (before, after):
        lo, hi = np.percentile(np.asarray(data)[:, 1], [5, 95])
        print(f" {lo:8.2f} to {hi:6.2f}", end="")
    print()
    print(f"{'Crest dB (median / 95th)':<28}", end="")
    for data in (before, after):
        median, high = np.percentile(np.asarray(data)[:, 2], [50, 95])
        print(f" {median:8.2f}  / {high:6.2f}", end="")
    print()
    print(f"{'Highest peak':<28} {max(row[-1] for row in before):19.3f} {max(row[-1] for row in after):19.3f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stems", nargs="?", type=Path, default=config.DATA_DIR / "stems",
                        help="directory of prepared songs (defaults to the configured library's stems)")
    report(parser.parse_args().stems)
