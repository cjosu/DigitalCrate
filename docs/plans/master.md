# Plan: a mastering chain on the stem mixer, and what the sidechain and the chain cost

The stem mixer gets a fixed, light mastering chain on its mix: a gentle trim of the very bottom and the top, a glue
compressor and a limiter. This note also answers whether that, together with the low-end duck of `blend.md`, is too
much processing for a browser. It is not: measured, the whole thing costs about 1.5% of real time.

## What it costs (measured 25 November 2026)

Sixty seconds of four looping stems rendered offline in headless Chromium 140 on this Mac (Apple Silicon), median of
three runs. An offline render runs the same node code as live playback on one thread, so the time it takes over the
length rendered is the share of one core the audio thread needs. `docs/superpowers/plans/2026-11-25-master-chain/
audiobench.py` repeats it.

| What is running | ms to render 60 s | Share of real time |
|---|---|---|
| Four sources only | 23 | 0.04% |
| The mixer as it is (three EQ bands, volume and a feedback delay on each stem) | 565 | 0.94% |
| The same without the four feedback delays | 319 | 0.53% |
| Mixer and the duck of `blend.md` | 721 | 1.20% |
| Mixer, duck and the chain below (the browser's compressor as the limiter) | 879 | 1.46% |
| The same with a 4× oversampled soft clipper after it | 1,262 | 2.10% |
| Mixer, duck, EQ, glue and a hand-written limiter in an AudioWorklet | 944 | 1.57% |

So the duck adds about 0.26%, the mastering chain about 0.26%, and the largest single cost is the four delay loops
(0.41%), which run even when a stem's delay is at zero.

## Use what the browser already has

Every stage but one is a node the browser ships, written in C++ and already optimized. Nothing here should be
written by hand or pulled from a library; a library such as Tone.js wraps these same nodes.

| Stage | Node | Settings |
|---|---|---|
| Bottom | `BiquadFilterNode` highpass | 30 Hz, Q 0.707 |
| Top | `BiquadFilterNode` highshelf | 12 kHz, −1.5 dB |
| Glue | `DynamicsCompressorNode` | threshold −18 dB, knee 12 dB, ratio 2, attack 30 ms, release 250 ms |
| Limiter | `DynamicsCompressorNode` | threshold −3 dB, knee 0, ratio 20, attack 1 ms, release 100 ms |

Three things the browser's compressor does that the chain has to allow for:

- **It has no sidechain input.** The duck stays what `blend.md` describes: an envelope built from native nodes that
  drives a gain.
- **It adds make-up gain by itself**, a fixed amount worked out from its threshold, knee and ratio. Left alone, the
  "light" glue would make the mix several dB louder. The chain has no make-up gain (owner, 25 November 2026): each
  compressor is followed by a gain that takes its make-up back out, and nothing else in the chain adds level. The amount is measured once, by rendering a quiet tone through a compressor with the same
  settings, so it is right in every browser.
- **It is not a brickwall.** In the benchmark, with its threshold at −1 dB, peaks still reached +0.1 dBFS. With the
  threshold at −3 dB and the make-up taken out there is about 2 dB of room. A true ceiling needs a limiter with
  lookahead, which means an AudioWorklet (see below).

## How it behaves

- One switch on the mixer, `MASTER`, on by default, kept with the mixer's saved state (`master: { on }`; absent = on).
- Beside it, the glue's gain reduction in dB while the mixer plays (`-1.8 dB`), read from the compressor's own
  `reduction` value. No analyser node.
- Off is a true bypass: the mix goes straight to the output and the chain's nodes process nothing.
- The chain is built once and never rebuilt. Nothing in it is a control in this version.
- Unity for quiet material: with the switch on, a signal below the glue's threshold comes out at the level it went in.
- The two compressors look ahead by about 6 ms each, so the mix is about 12 ms later with the chain on. For playback
  that is inaudible.

## Delay sends

A stem's delay loop is connected only while its delay amount is above zero, and for 4 seconds after it returns to
zero, so the echoes die away. With every delay at zero the mixer costs 0.53% instead of 0.94%.

## Out of scope

- **A true-peak limiter in an AudioWorklet.** It is cheap (0.1% more than the browser's compressor) and held its
  ceiling in the benchmark (peak 0.894 for a ceiling of 0.891). But on every fresh page its first offline render
  never finished; the second did. That was in headless Chromium 140 and the cause is not known. Until it is, the
  limiter is the browser's compressor. `blend.md` also rules out AudioWorklet for the mixer.
- Controls for the chain (amounts, thresholds), loudness metering, and the chain on the sketchpad or on exports.
- A soft clipper: 4× oversampling costs more than the rest of the chain together and overshot in the benchmark.
