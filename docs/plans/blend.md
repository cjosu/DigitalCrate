# Plan: Snapshots and blends in the stem mixer, and a low-end duck

Status: built (pull request #1, by cjosu); not yet listened to. It builds on the stem mixer ([stems.md](stems.md)).

## The idea

You arrive at a combination you like and take a **📸 snapshot**. You change a layer and take another. **▶ play strip**
then shows two snapshots side by side and moves the sound from the left one to the right one: by hand, with a master
slider and a slider per layer, or by itself. Once you are fully on the right snapshot, an arrow moves the view on: B
goes to the left and C comes in on the right.

Separately, bass slots **duck**: the drums' low end pushes the bass's low end down a little, so a kick and a bass
line from different songs don't pile up.

## Design

**1. The duck.** Every bass slot has a DUCK switch (on by default) and an amount (3 dB by default, 0 to 12).
- The low end of every drum slot (after its volume, so muted drums duck nothing) is summed, lowpassed at 100 Hz,
  rectified, smoothed at 20 Hz, scaled by 13 and limited to 0..1. That envelope, times minus the amount, drives the
  gain of a low shelf at 120 Hz on the bass. Only the bass's low end moves.
- Native Web Audio nodes only. The browser's compressor has no sidechain input; the technique (an envelope fed into a
  gain parameter at audio rate) is the one the `soundbank-dipper` package uses, here without its ScriptProcessor.
- Measured in Chrome with a kick on every beat at the loudness the server gives every part: at 3 dB the bass's 55 Hz
  drops 2.8 dB under the kick and is back between kicks, and its 440 Hz moves by less than 0.05 dB.
- The FX switch does not turn it off: it is a mix fix, not an effect.

**2. Snapshots.** A snapshot is every slot as it is now (the part, its bars, pitch, volume, EQ, delay, duck), in the
shape the mixer already saves.
- They sit in an ordered strip above the slots, lettered A to H (8 at most), and are saved with the mixer (in the
  browser and by 💾).
- **📸 snapshot** adds one at the end. Clicking one brings it back into the mixer, as opening a saved combination
  does. **↻ replace** writes what is playing over the selected one; **🗑** deletes it.
- Tempo and key belong to the strip, not to a snapshot: they are the mixer's own. The first snapshot freezes an
  *auto* key to the key it resolved to, so changing one layer later cannot re-pitch the others.
- A snapshot's chip names the layers that differ from the snapshot before it.
- A snapshot is a weak yes for the recommendations (0.6, like 🔒): for every slot on the first one, afterwards only
  for the slots whose part changed.

**3. Playing the strip.** The view is the mixer at half width, twice: the left snapshot's slots stacked on the left,
the right snapshot's on the right, every slot of both always visible, and the transition controls in a column
between them. It only plays; snapshots are changed in the mixer. The mixer stops while the strip plays. It always
starts with A on the left.
- Rows are matched by slot. A row is **same** (the same audio on both sides: one voice keeps looping, and its volume,
  EQ and delay glide with the master), **change**, **enter** (only on the right), **exit** (only on the left) or
  **empty**.
- The same audio means the same song, stem, first bar, length, half/double time and pitch offset. A muted or empty
  slot, or a part whose song is no longer prepared ("missing"), counts as absent.

**4. Transitions.** Every layer that differs has a style, the bars it changes over, and its own slider.
- **Filter handoff** (the default): one cutoff sweeps from 20 Hz to 20 kHz. The outgoing part is highpassed at it and
  the incoming part lowpassed at it (24 dB an octave), so every band comes from one part at a time and two low ends
  never sound together. Over the first and last 5% the incoming and outgoing part's gain opens and closes.
- **Crossfade:** equal power (cosine out, sine in).
- **When:** the whole transition, its first half, its second half, or a cut at its midpoint.
- **Length:** 2, 4, 8 or 16 bars for each transition, 8 to begin with.
- Settings belong to a transition. A layer with none yet takes them from the nearest earlier transition that set that
  slot, else filter handoff over the whole transition.
- The **master** moves every layer through its own bars. Grabbing a layer's own slider takes it off the master until
  the view moves on.

**5. Arrows.** ▶ works only when every differing layer is fully on the right and the next snapshot is loaded; ◀ only
when every one is fully on the left. The next snapshot's parts are loaded while the current pair plays. The parts of
the snapshot that stays keep playing: there is no gap.

**6. Auto.** Hold the left snapshot (4, 8 or 16 bars, 8 to begin with, one setting for the strip), move the master
across over the transition's own bars, move the view on, and again. It stops on the last snapshot. A hand on any
slider or arrow switches it off where it stands; switched on halfway, it carries on from where the master is. Its
position comes from the audio clock and it starts on a bar line.

**7. What is stored**, in the mixer's saved state:

```
duck:  { slot: { on, db } }                       absent = on, 3 dB
snaps: [ { order, roles, slots, duck } ]          the saved shapes of those four
trans: [ { bars, layers: { slot: { style, win } } } ]     trans[i] is between snaps[i] and snaps[i + 1]
         style: "filter" | "xfade"        win: "all" | "first" | "second" | "cut"
```

## Words on the screen

| Where | Text |
| --- | --- |
| bass row | `DUCK` (switch), `lows` (slider label) |
| strip | `snapshots`, `📸 snapshot`, `↻ replace A`, `🗑`, `▶ play strip`, `tempo and key belong to the strip` |
| chip | the letter, then `start` on the first, the differing layers' names after, or `same` |
| toasts | `8 snapshots at most: delete one first` · `nothing to snapshot yet: 🎲 a part first` |
| playback head | `◂ mixer`, `playing the strip`, `▶ play` / `■ stop`, `100 bpm · Am`, `auto on` / `auto off`, `hold`, `4 bars` `8 bars` `16 bars` |
| sides | left: `going out`, `silent` or `playing`; right: `coming in`, `playing` or `next` |
| arrows | `◀` or `◀ A · B`; `B · C ▶` or `B is last` |
| transition column | `transition`, `filter handoff`, `crossfade`, `bars 1–8`, `bars 1–4`, `bars 5–8`, `cut at bar 5`, `by hand`, `same in both`, `empty in both`, `master`, `over` |
| slot | `empty`, `muted`, `missing` |
| status | `holding A · bar 3 of 8` · `moving to B · bar 2 of 8` |

## Limits

- Two bass lines playing different notes still clash in a crossfade. The filter handoff or a cut is for that.
- The duck follows the drums' low end, whatever is in it: a low tom ducks the bass too.
- Parts are rendered again at whatever the mixer's tempo is. Far from the tempo they were chosen at, they stretch badly.
- Playback only: a strip cannot be bounced or exported yet.

## Left for later

A bounce and a Live set of a strip (the audio graph and the maths already take the audio context as a parameter),
tempo or key changes inside a strip, reordering snapshots, rules per role, stepping-stone parts pulled from the
library, filter resonance and sweep direction, curve shapes.
