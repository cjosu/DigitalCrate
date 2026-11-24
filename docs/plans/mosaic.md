# Plan: Mosaic (rebuild a sound from your library)

Status: planned, not started. Inspired by Samplebrain (Aphex Twin and Dave Griffiths) and the FluCoMa tools.

## The idea

Pick a **target** (a drum loop, a vocal line, your sketch, a song you drop in) and a **brain** (the part of your
library to build from: favorites, a collection, one artist, one category). DigitalCrate cuts the brain into small
units and rebuilds the target from the closest-sounding ones. The result follows the target's rhythm, dynamics and
(optionally) pitch, made entirely of your library's sounds. It's saved as a new sample you can rate, edit and use.

## Design

**1. Units.** Two kinds, chosen by the target:
- *Hits* (rhythmic targets): segments between onsets, 40–500 ms, so transients stay intact.
- *Grains* (textures, vocals, pads): fixed 40–200 ms windows, 50% overlap, overlap-added.

**2. What a unit "sounds like".** CLAP works on 10 s windows and is too slow for hundreds of thousands of units, so
units use classic short-time descriptors: 13 MFCCs (mean and change), loudness, spectral centroid, flatness, and
pitch with confidence (tonal units only). These are standardized and reduced to about 12 dimensions.

**3. Brains.** Building from the whole library (about 40 hours of audio, millions of grains) is slow and sounds
generic. A chosen scope is better and more musical: favorites, a collection, an artist, a category or a single
sample. Descriptors are computed once per sample and cached (`_data/units/`), so a new brain is quick to assemble.

**4. Matching.** For each target frame, the nearest 8 units by weighted distance, using three weights the user
sets: timbre, loudness and pitch. Then a Viterbi pass over those candidates adds two terms:
- **Stickiness:** continuing the same source unit is cheaper, so longer stretches of one recording survive
  (recognizable, less grainy).
- **Variety:** reusing a unit recently used costs more.

**5. Synthesis.** Windowed overlap-add.
- Each unit is gained to the target's loudness envelope (an amount slider).
- Tonal units can be re-pitched to the target's pitch, using the stretch engines that won your blind tests.
- The brain is conformed to the project key first.
- A dry/wet blend with the target is available.

**6. Where it lives.**
- **🧩 mosaic** in the sample panel, with this sample as the target.
- In the sketchpad, with the sketch bounce as the target.
- A dropped-in file, analyzed and deleted like *fits my track*.

The panel has a brain picker, the three weights, unit size, stickiness and variety. It renders in a few seconds;
**save** makes it a sample in `Edits/` with its recipe as provenance.

**7. Learning.** Mosaics are rated 👍/👎 like suggested edits, so the taste model learns which brains and settings
you like.

## Performance

- **Descriptors:** about 20 ms per sample, cached. A 500-sample brain takes about 10 s the first time.
- **Matching:** brute force over 200k units for 2,000 target frames is too slow, so it uses a PCA-12 ball tree
  (scikit-learn) with k = 8, then Viterbi over 8 × 8 transitions per frame. Target: under 3 s for a 10 s target.

## How we'd know it's good

- **Objective:** descriptor distance between target and result, onset alignment for rhythmic targets, and seam
  smoothness (the spectral-jump measure used for sustain loops).
- **Subjective:** a blind listening round like the stretch shootout. Three presets (grainy, balanced, sticky) on
  six targets from your music; pick favorites; the defaults follow.

## Phases

1. **Prototype (command line):** `digitalcrate mosaic TARGET --brain favorites`, fixed settings, both unit kinds,
   listening round.
2. **Panel** in the sample editor, with presets from round 1, saving, and provenance.
3. **Sketchpad and dropped files** as targets, plus taste learning.

## Open questions for you

- Which targets matter most: your own drum loops, vocals, whole sketches, or other songs?
- How recognizable should sources be? Sticky (phrases you can place) or granular (abstract texture)? This sets the
  default stickiness.
- Should mosaics also export as stems (one per source sample), so you can rebalance them in Live?
