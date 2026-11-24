"""Lazy-loaded ML models: Demucs (stem separation) and CLAP (audio/text embeddings)."""
import warnings
import numpy as np
import torch

from .config import DEMUCS_MODEL, CLAP_MODEL, SR, MODELS_DIR, ROFORMER_MODELS, DATA_DIR

warnings.filterwarnings("ignore")
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
import os as _os
if _os.environ.get("DC_THREADS"):  # background jobs (serve.start_job) share the machine with the app
    torch.set_num_threads(int(_os.environ["DC_THREADS"]))

_demucs = None
_clap = None


def separate(y, model=None):
    """y: (2, n) float32 @44.1k -> dict of stems (2, n): drums, bass, other, vocals."""
    global _demucs
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    name = model or DEMUCS_MODEL
    if _demucs is None or getattr(_demucs, "_dc_name", None) != name:
        _demucs = get_model(name).eval().to(DEVICE)
        _demucs._dc_name = name
    x = torch.from_numpy(y)
    ref = x.mean(0)
    mu, sd = ref.mean(), ref.std() + 1e-8
    x = (x - mu) / sd
    with torch.no_grad():
        out = apply_model(_demucs, x[None], device=DEVICE, shifts=0, split=True,
                          overlap=0.25, progress=False)[0]
    out = (out * sd + mu).cpu().numpy().astype(np.float32)
    return {name: out[i] for i, name in enumerate(_demucs.sources)}


_rof = {}


def roformer_vocals(path, n_samples, engine="roformer"):
    """High-quality vocal stem via MelBand RoFormer (audio-separator). Returns (2, n) @44.1k."""
    import logging, shutil, soundfile as sf
    from audio_separator.separator import Separator
    tmp = DATA_DIR / "tmp_sep"
    tmp.mkdir(parents=True, exist_ok=True)
    if engine not in _rof:
        sep = Separator(model_file_dir=str(MODELS_DIR), output_dir=str(tmp), output_single_stem="Vocals",
                        output_format="WAV", log_level=logging.WARNING, sample_rate=SR)
        sep.load_model(ROFORMER_MODELS[engine])
        _rof[engine] = sep
    outs = _rof[engine].separate(str(path))
    try:
        v, sr = sf.read(str(tmp / outs[0]), dtype="float32", always_2d=True)
    finally:
        for o in outs:
            (tmp / o).unlink(missing_ok=True)
    v = v.T
    if v.shape[0] == 1:
        v = np.repeat(v, 2, 0)
    if sr != SR:
        from scipy.signal import resample_poly
        v = resample_poly(v, SR, sr, axis=1).astype(np.float32)
    out = np.zeros((2, n_samples), np.float32)
    m = min(n_samples, v.shape[1])
    out[:, :m] = v[:, :m]
    return out


class Clap:
    def __init__(self):
        from transformers import ClapModel, ClapProcessor
        self.model = ClapModel.from_pretrained(CLAP_MODEL).eval().to(DEVICE)
        self.proc = ClapProcessor.from_pretrained(CLAP_MODEL)
        self._text_cache = {}

    @staticmethod
    def _vec(out):
        if isinstance(out, torch.Tensor):
            return out
        return getattr(out, "pooler_output", None) if getattr(out, "pooler_output", None) is not None else out[0]

    def embed_audio(self, clips48):
        """clips48: list of mono float32 arrays at 48 kHz (<=10 s used). Returns (n, d) unit vectors."""
        embs = []
        for i in range(0, len(clips48), 16):
            batch = clips48[i:i + 16]
            inp = self.proc(audio=batch, sampling_rate=48000, return_tensors="pt")
            inp = {k: v.to(DEVICE) for k, v in inp.items()}
            with torch.no_grad():
                e = self._vec(self.model.get_audio_features(**inp))
            embs.append(torch.nn.functional.normalize(e, dim=-1).float().cpu().numpy())
        return np.concatenate(embs) if embs else np.zeros((0, 512), np.float32)

    def embed_text(self, texts):
        key = tuple(texts)
        if key not in self._text_cache:
            inp = self.proc(text=list(texts), return_tensors="pt", padding=True)
            inp = {k: v.to(DEVICE) for k, v in inp.items()}
            with torch.no_grad():
                e = self._vec(self.model.get_text_features(**inp))
            self._text_cache[key] = torch.nn.functional.normalize(e, dim=-1).float().cpu().numpy()
        return self._text_cache[key]


def clap():
    global _clap
    if _clap is None:
        _clap = Clap()
    return _clap
