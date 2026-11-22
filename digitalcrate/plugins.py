"""Your own audio plugins (AU and VST3) inside DigitalCrate, through Spotify's Pedalboard: on a sample in the edit
panel, and as one of the "space" stages variations can draw (Valhalla Supermassive if installed).

Plugins are found in /Library/Audio/Plug-Ins and ~/Library/Audio/Plug-Ins; a plugin is loaded only when used.
Instruments, and effects that won't load outside a DAW, are skipped. Where a plugin exists as both, VST3 is used.
"""
import threading
from pathlib import Path

import numpy as np

_lock = threading.Lock()  # a plugin instance isn't safe to run from two server threads at once

DIRS = [Path("/Library/Audio/Plug-Ins"), Path.home() / "Library/Audio/Plug-Ins"]
HIDE = ("reserved", "bypass", "clear", "midi", "program")
_loaded = {}


def scan():
    """[{name, path, format}] of installed plugins, VST3 preferred over AU for the same name."""
    out = {}
    for d in DIRS:
        for fmt, sub, ext in (("AU", "Components", ".component"), ("VST3", "VST3", ".vst3")):
            for f in sorted((d / sub).glob(f"*{ext}")) if (d / sub).exists() else []:
                name = f.stem
                if name not in out or fmt == "VST3":
                    out[name] = dict(name=name, path=str(f), format=fmt)
    return sorted(out.values(), key=lambda x: x["name"].lower())


def load(path):
    if path not in _loaded:
        import pedalboard
        p = pedalboard.load_plugin(path)
        if getattr(p, "is_instrument", False):
            raise ValueError(f"{Path(path).stem} is an instrument, not an effect")
        _loaded[path] = p
    return _loaded[path]


def params(path):
    """The plugin's controls: [{key, name, kind, min, max, step, choices, value}] (housekeeping ones hidden)."""
    p = load(path)
    out = []
    for k, v in p.parameters.items():
        if any(h in k.lower() for h in HIDE):
            continue
        d = dict(key=k, name=v.name, value=getattr(p, k))
        if v.type is bool or isinstance(d["value"], bool):
            d.update(kind="bool")
        elif isinstance(d["value"], str):
            d.update(kind="choice", choices=list(v.valid_values))
        else:
            lo, hi, st = v.range
            d.update(kind="float", min=lo, max=hi, step=st or (hi - lo) / 200, label=v.label or "")
            d["value"] = float(d["value"])
        out.append(d)
    return out


def apply(y, sr, chain, tail=0.0):
    """y: (channels, n) float32. chain: [{path, params: {key: value}}]. tail: seconds of silence added first so
    reverbs and delays can ring out."""
    if not chain:
        return y
    with _lock:
        return _apply(y, sr, chain, tail)


def _apply(y, sr, chain, tail):
    if tail > 0:
        y = np.concatenate([y, np.zeros((y.shape[0], int(tail * sr)), np.float32)], 1)
    for step in chain:
        p = load(step["path"])
        p.reset()
        for k, v in (step.get("params") or {}).items():
            try:
                setattr(p, k, v)
            except Exception as e:  # a value out of range or a renamed control: skip that one, say so
                print(f"  {Path(step['path']).stem}: {k}={v!r} not set ({e})")
        y = p(y.astype(np.float32), sr, reset=True)
    if tail > 0:  # trim the silence that stayed silent
        env = np.abs(y).max(0)
        last = np.flatnonzero(env > 10 ** (-70 / 20))
        y = y[:, : (last[-1] + 1 if len(last) else y.shape[1])]
    return y.astype(np.float32)


def find(name):
    """Path of an installed plugin by (part of) its name, or None."""
    n = name.lower()
    return next((x["path"] for x in scan() if n in x["name"].lower()), None)
