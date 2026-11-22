"""MERT (m-a-p/MERT-v1-95M), a self-supervised music model: embeddings that capture timbre, pitch, rhythm and
harmony, where CLAP captures what a sound "is" in words.

MERT's repository ships its own model code (trust_remote_code). With its CQT option off, as in v1-95M, that code is
plain HuBERT, so the weights are loaded into transformers' own HubertModel instead: no downloaded code runs, and
torch.load uses weights_only.
"""
import numpy as np

REPO = "m-a-p/MERT-v1-95M"
SR = 24000
_m = None


def model():
    global _m
    if _m is None:
        import json
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import HubertConfig, HubertModel
        from .models import DEVICE
        cfg = json.load(open(hf_hub_download(REPO, "config.json")))
        hc = HubertConfig(**{k: v for k, v in cfg.items() if k in HubertConfig().to_dict()
                             and k not in ("architectures", "model_type", "auto_map", "_name_or_path", "transformers_version")})
        m = HubertModel(hc).eval()
        sd = torch.load(hf_hub_download(REPO, "pytorch_model.bin"), map_location="cpu", weights_only=True)
        r = m.load_state_dict(sd, strict=False)
        assert not r.missing_keys, r.missing_keys[:5]
        _m = m.to(DEVICE)
    return _m


def embed(y24, layers="all"):
    """mono 24 kHz -> time-averaged hidden states: (13, 768) for layers='all', else the mean over layers (768,)."""
    import torch
    from .models import DEVICE
    x = (y24 - y24.mean()) / (y24.std() + 1e-7)  # what MERT's feature extractor does
    with torch.no_grad():
        o = model()(torch.from_numpy(x[None].astype(np.float32)).to(DEVICE), output_hidden_states=True, return_dict=True)
        h = torch.stack(o.hidden_states)[:, 0].mean(1).float().cpu().numpy()
    return h if layers == "all" else h.mean(0)


def load(path, max_s=10.0):
    import soundfile as sf
    from scipy.signal import resample_poly
    y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    m = y.mean(1)
    if len(m) > sr * max_s:  # the middle, like the CLAP embeddings
        mid = len(m) // 2
        m = m[mid - int(sr * max_s / 2): mid + int(sr * max_s / 2)]
    m = resample_poly(m, SR, sr).astype(np.float32) if sr != SR else m
    if len(m) < SR // 2:
        m = np.pad(m, (0, SR // 2 - len(m)))
    return m


def embed_files(files, layers="all"):
    from tqdm import tqdm
    return np.stack([embed(load(f), layers) for f in tqdm(files, desc="mert", mininterval=5)])
