"""Paths and tunable parameters for the sample miner.

Paths come from `digitalcrate.toml` in the project root (copy `digitalcrate.example.toml`), overridable with environment
variables DIGITALCRATE_MUSIC, DIGITALCRATE_LIBRARY, DIGITALCRATE_FOUND, DIGITALCRATE_ABLETON_SAMPLES.
"""
import os
import tomllib
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
_cfg = {}
CONFIG_FILE = Path.home() / ".config/digitalcrate/digitalcrate.toml"  # where the setup page saves, unless one below exists
for _f in (Path(os.environ.get("DIGITALCRATE_CONFIG", PROJECT_DIR / "digitalcrate.toml")), CONFIG_FILE):
    if _f.exists():
        _cfg = tomllib.loads(_f.read_text())
        CONFIG_FILE = _f
        break
else:
    if os.environ.get("DIGITALCRATE_CONFIG"):
        CONFIG_FILE = Path(os.environ["DIGITALCRATE_CONFIG"])


def _path(key, env, default):
    return Path(os.environ.get(env) or _cfg.get(key) or default).expanduser()


MUSIC_ROOT = _path("music", "DIGITALCRATE_MUSIC", "~/Music")                       # your record collection (read-only)
LIB_ROOT = _path("library", "DIGITALCRATE_LIBRARY", "~/SampleLibrary")             # where samples + database are written
FOUND_DIR = _path("found_sounds", "DIGITALCRATE_FOUND", LIB_ROOT.parent / "Found Sounds")  # downloads / references
ABLETON_SAMPLES = _path("ableton_samples", "DIGITALCRATE_ABLETON_SAMPLES",
                        "~/Music/Ableton/User Library/Samples/DigitalCrate")  # export destination
DATA_DIR = LIB_ROOT / "_data"
DB_PATH = DATA_DIR / "samples.sqlite"

AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aif", ".aiff", ".m4a", ".ogg", ".aac"}

SR = 44100            # render / separation sample rate
SR_F = 22050          # analysis sample rate
N_FFT = 2048
HOP = 1024            # ~46 ms analysis frames
FPS = SR_F / HOP

DEMUCS_MODEL = "htdemucs"
MODELS_DIR = PROJECT_DIR / "models"
ROFORMER_MODELS = {  # --vocals choices -> audio-separator checkpoints
    "roformer": "vocals_mel_band_roformer.ckpt",                       # Kim MelBand RoFormer, SDR ~12.6
    "bleedless": "mel_band_roformer_kim_ft2_bleedless_unwa.ckpt",      # tuned for minimal instrument bleed
}
CLAP_MODEL = "laion/larger_clap_music_and_speech"

# --- detection thresholds (dB are relative frame powers) ---
ACTIVE_BELOW_P95_DB = 28      # a source is "active" if within this many dB of its own loud level
ABS_FLOOR_DB = -62            # ...and above this absolute floor
DRUMS_REL_DB = -20            # drums stem louder than (mix + this) => drums present
BASS_REL_DB = -10             # bass stem louder than (mix + this) => bass present
NEGLIGIBLE_REL_DB = -24       # other stems below this rel. to mix => render from the clean mix
MIX_PRATIO_DRUMS = 0.30       # (no stems) percussive ratio above this => drums present
OTHER_PRATIO_MAX = 0.40       # 'other' stem frames more percussive than this are excluded

# --- output caps per track ---
MAX_PER_TRACK = {
    "vocal_phrase": 10,
    "vocal_chop": 8,
    "vocal_atmos": 4,
    "long": 8,      # pads / chords / melodies / textures loops+free
    "oneshot": 6,
    "pad": 4,       # loops that hold 1-2 chords (pads.find)
}
MIN_QUALITY = 0.40
LOOP_MAX_SECONDS = 32
FREE_WINDOW_SECONDS = 12
