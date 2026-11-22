# Models

Weights are not part of the repo. Most download themselves on first use.

| Model | Used for | How it arrives | License |
|---|---|---|---|
| Demucs `htdemucs` | drums / bass / other / vocals stems | automatic (torch hub cache) | MIT |
| MelBand RoFormer (Kim) `vocals_mel_band_roformer.ckpt`, `mel_band_roformer_kim_ft2_bleedless_unwa.ckpt` | cleaner vocals (`--vocals roformer|bleedless`) | automatic via audio-separator into `models/` | see model card |
| MDX23C DrumSep `MDX23C-DrumSep-aufr33-jarredou.ckpt` | labeling drum hits (kick/snare/hats…) | automatic via audio-separator into `models/` | see model card |
| LAION CLAP `larger_clap_music_and_speech` | every sound/text embedding: search, galaxy, taste, compatibility | automatic (Hugging Face cache) | Apache-2.0 |
| Spotify basic-pitch | audio → MIDI | ships with the package | Apache-2.0 |
| Essentia Discogs-EffNet `discogs-effnet-bsdynamic-1.onnx` | 400 Discogs styles per song, related music, guided scouting | automatic into `models/discogs/` (essentia.upf.edu) | **CC BY-NC-SA 4.0** (non-commercial) |
| Whisper large-v3-turbo (`mlx-community/whisper-large-v3-turbo`) | words in vocal samples | automatic (Hugging Face cache) | MIT |
| Beat This! `final0` | beats and downbeats for cutting loops | automatic (torch hub cache) | MIT |
| MERT-v1-95M (tested, not used) | compared with CLAP for taste; not used by the app | automatic (Hugging Face cache), loaded as plain HuBERT (no remote code) | CC BY-NC 4.0 |
| OpenVPI PC-NSF-HiFiGAN 44.1k (2025.02) | neural vocoder in the stretch shootout | manual, see below | **CC BY-NC-SA 4.0** (non-commercial) |

Neural vocoder (optional, only for `python -m digitalcrate shootout`):

```bash
mkdir -p models/pcnsf && cd models/pcnsf
curl -LO https://github.com/openvpi/vocoders/releases/download/pc-nsf-hifigan-44.1k-hop512-128bin-2025.02/pc_nsf_hifigan_44.1k_hop512_128bin_2025.02.oudep
unzip pc_nsf_hifigan_44.1k_hop512_128bin_2025.02.oudep && rm *.oudep
```
