# Studio performance: keeping playback on time while the page works

Audit of `digitalcrate/static/studio.js`, 25 November 2026. It was done by reading the code: nothing was run or
profiled, so the severities are judgements, and the first job of the implementation is to pin each one with a test.

## What kind of problem this is

The studio has no JavaScript on the audio thread: no `AudioWorklet`, no `ScriptProcessorNode`. Effects are native
Web Audio nodes and stretching is done by the server. So the audio cannot glitch from slow DSP code. What can go
wrong is on the main thread:

- The sketchpad and the drum lane are scheduled by a `setTimeout` loop (`skTick`, every 25 ms). Drum steps are
  scheduled 120 ms ahead. When the page blocks for longer than that, a hit is scheduled after its time has passed,
  and `drumHit` clamps it to "now": it plays late, off the grid.
- Several ordinary actions block the page for that long: redrawing the sketchpad, dragging a trim, moving the mouse
  over the galaxy, exporting stems.
- Changing the tempo asks the server to stretch every lane again, once per click, with nothing cancelled.
- Decoded audio and audio nodes are kept longer than they are needed.

## Findings and the behaviour wanted

Line numbers are `studio.js` as of this audit; the function names are the stable reference.

| # | Finding | Where | Wanted |
|---|---|---|---|
| 1 | Drum steps are scheduled only 120 ms ahead, and a late hit plays late | `drumTick` 610–618, `drumHit` 620 | A page that blocks for 190 ms does not move a hit. A step switched on just ahead of the playhead still sounds in the current pass. |
| 2 | Every redraw of the sketchpad recomputes each lane's waveform from the samples, reallocates each canvas and makes a new copy canvas | `drawSK` 902–934, `skWave` 850–862, `padWave` 726–729 | A waveform's peaks are computed once per buffer and width. Redrawing reuses them and reuses the canvases. |
| 3 | Bounce and stem export write the WAV one sample at a time through a `DataView`, then build a binary string and base64 it, all on the main thread | `wavB64` 1004–1007, callers 983, 997, 1150, 1153, 1323 | The same bytes, written through an `Int16Array` and base64-encoded off the main thread. |
| 4 | Each tempo click re-stretches and re-decodes every lane; nothing is cancelled. With Link on, a tempo change from Live does it on every 300 ms poll | `setProj` 20–21, `skReload` 522–523, `skLoad` 504, `linkPoll` 64 | A burst of changes loads each lane once, at the last tempo. A superseded request is aborted and never marks its lane as failed. |
| 5 | Each `skPlay` starts another animation loop; a stop and a play in the same frame leave both running | `skPlay` 841, `skAnim` 849, hold toggle 964, `skRestore` 800–808 | One loop, however playback is restarted. |
| 6 | The galaxy repaints every point on every mouse move and wheel event, resizes its canvas each time and spreads every taste score into `Math.min`/`Math.max` | `galDraw` 385–396, handlers 370–381 | At most one repaint a frame. The score range and the category colours are worked out once, not per repaint. |
| 7 | Dragging a trim edge or a pad's start/end line recomputes the waveform on every mouse event | lane drag 943–949, pad drag 760 | One repaint a frame while dragging. |
| 8 | Each chord playback builds a three-second noise impulse (about 290,000 `Math.random` and `Math.pow` calls) and decodes the sample again; a single-chord click leaves its nodes connected | `padReverb` 1049–1050, `chPlay` 1125, chord click 1136 | The impulse is built once per sample rate. The sample's decoded audio is reused. A single chord's nodes are disconnected when it has rung out. |
| 9 | `HOLDBUF` and `PADBUF` keep every decoded buffer for the whole session | 529, 536, 563–571 | Bounded: least recently used entries are dropped. |
| 10 | In project mode, moving through the list with the arrow keys asks the server for one stretched preview per row, and stopping a preview does not cancel its request | `kMove` 301–303, `toggle` 39–43 | In project mode the preview starts 120 ms after the last key. A preview that is stopped before it has loaded gives up its download. |
| 11 | A looping pad pattern keeps every voice it has scheduled | `padsTick` 1315 | A voice is forgotten when it ends. |
| 12 | The undo timer serialises the whole sketch twice every 300 ms | `undoTick` 813–816, `skMarkSave` 822, `skDirty` 798 | Once per tick, and not at all while the tab is hidden. |
| 13 | A `MutationObserver` on the whole document runs a selector query on every DOM change | 268 | It watches the list only. |
| 14 | The strings pad uses one vibrato oscillator for every oscillator | `padChord` 1057 | One per note. |

## Out of scope

- Rewriting `drawSK` to patch the DOM instead of rebuilding it. With finding 2 fixed the rebuild is mostly string
  work; measure again before going further.
- Sending exports as binary. That needs the server's `api/stems` and `api/bounce` to change.
- The stem mixer's block. `docs/plans/blend.md` owns it; its sliders queue automation events on every input, which
  is harmless and can wait for that work.
- A spatial index for the galaxy's hit test, and `RACK.buf` in `browser.py`.
- Baking only the loop region in `bakeLoop`: the hold plays the attack before the loop, so it needs the whole clip.

## Not audited

`studio.js` lines 1168–1275, 1328–1391 and 1407–1451; almost all of `browser.py` (the list and the sample editor);
the Python server.
