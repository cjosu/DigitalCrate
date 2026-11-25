# Stem Snapshots and Blends Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give DigitalCrate's stem mixer a low-end duck on bass slots, snapshots of the mixer, and a view that plays two snapshots side by side and blends from one to the next, by hand or automatically.

**Architecture:** All new browser code lives in one new block of `digitalcrate/static/studio.js`, placed in front of the stem mixer's own block, as that file's other features are. A patch that ships with this plan creates the block and makes nine small edits to the mixer's block, so that it builds and sets its audio chains through the new one and calls its hooks. The page template does not change, so no library has to be rebuilt. Snapshots and transitions are stored inside the mixer's existing saved state, so the server changes by one dictionary entry.

**Tech Stack:** Python 3.11 (stdlib HTTP server, sqlite), vanilla JavaScript and the Web Audio API (no build step, no libraries), pytest, Playwright (Chromium).

**Spec:** `docs/plans/blend.md`. Read it before any task. Where this plan and the spec disagree, stop and ask.

## Global Constraints

- Base commit: `8872ec8a5f5da1fe33972eca7e636be967c6cde0` of `https://github.com/jaredhuling/DigitalCrate`. Work on the branch `stem-blends`.
- macOS on Apple Silicon, Python 3.11, the dependency set of `requirements.lock`. No new Python or JavaScript dependency, no build step, no `AudioWorklet`, no `ScriptProcessorNode`.
- New browser code goes only inside the stem blends block of `digitalcrate/static/studio.js`: the lines from `// ---------- 📸 stem blends` to `// ---------- end of stem blends`, which `hooks.patch` creates in Task 2 (lines 1456 to 1629 right after it). Add code before the block's last statement, `window.BLEND = BL;`. Outside the block, `studio.js` changes only through `hooks.patch`, never by hand. `digitalcrate/browser.py` does not change.
- Most lines of `studio.js` outside the block are thousands of characters long. Read the block with an offset and a limit; never read the whole file.
- The only server change is one entry in the dictionary inside `stems.log` (Task 3).
- The block calls the server through `window.CRATE.api(path, body)`, looked up at call time and never stored in a variable. It uses the page's globals `$`, `st`, `AC`, `esc`, `toast` and `url` as the rest of `studio.js` does.
- Constants, exactly: duck shelf 120 Hz, key lowpass 100 Hz, envelope smoothing 20 Hz, envelope scale 13, duck default 3 dB, duck range 0 to 12 dB; at most 8 snapshots; transition lengths 2, 4, 8, 16 bars, default 8; hold 4, 8, 16 bars, default 8; filter handoff from 20 Hz to 20 kHz, 24 dB an octave, 5% gain edges; snapshot event weight 0.6.
- Every string a person reads is in the spec's "Words on the screen" table. Use those strings exactly.
- The tests are the contract. Never change an asserted value, a selector's meaning or a timeout to make a test pass. If a test looks wrong, stop and ask.
- The `page` fixture fails a test on any uncaught page error, so no code path may throw.
- After every task both existing stem mixer tests still pass: `test_stem_mixer_deals_plays_and_learns` and `test_stem_mixer_renders_fits_and_learns`.
- Commit at the end of each task with a message in the repository's style: one plain sentence starting `Stem mixer: `.

## Review Focus

The inputs the spec implies and a person is most likely to meet, each pinned by a test in the task that owns the code:

1. A mixer saved before this feature, with no `duck`, `snaps` or `trans` keys, opens with their defaults (Task 2, `test_state_saved_before_blends_still_opens`).
2. A snapshot holds a part whose song is no longer prepared: the row says `missing`, the rest plays, nothing throws (Task 6, `test_playback_arrows_walk_the_strip`).
3. Two snapshots with different slots, roles or mutes: rows come from both, and a muted part counts as absent (Task 4, `test_blend_model`; Task 5 covers a removed part end to end).
4. The next snapshot loads slowly or fails: the arrow stays off and auto waits on the right snapshot until it is loaded (Task 6, `test_playback_waits_for_the_next_snapshot`).
5. The mixer's tempo changes after snapshots were taken: the strip plays at the new tempo with freshly rendered parts (Task 5, the last lines of `test_playback_shows_both_sets_and_blends_by_hand`).

## Files

| File | Change | Responsibility |
| --- | --- | --- |
| `digitalcrate/static/studio.js`, the stem blends block | created by `hooks.patch`, then extended | The duck, the audio chain, the blend maths, snapshots, the playback view and auto, all on `window.BLEND` |
| `digitalcrate/static/studio.js`, the stem mixer block | `hooks.patch` only | The mixer builds and sets chains through `BLEND`, saves and loads the new state, calls the hook points |
| `digitalcrate/static/studio.css` | append two blocks | The strip and the playback view |
| `digitalcrate/stems.py` | one dictionary entry | The `snap` event |
| `tests/test_ui.py`, `tests/test_units.py` | append | The tests below |
| `docs/guide.md`, `docs/plans/stems.md`, `docs/plans/blend.md`, `README.md` | edit | Task 8 |

## What ships with this plan

In `docs/superpowers/plans/2026-11-24-stem-snapshots-and-blends/`. Copy from these files; do not retype them.

| File | What it is | How it was checked |
| --- | --- | --- |
| `stemblend.seed.js` | The stem blends block as Task 2 leaves it, for reading; the patch already contains it | Parsed with `node --check`; its audio graph measured in headless Chrome by `test_blend_audio_core`, which passes |
| `hooks.patch` | The block, and the nine edits to the stem mixer block | `git apply --check` on a clean checkout of the base commit; the patched `studio.js` parses, and the block taken from it passes `test_blend_audio_core` |
| `blend.css` | The two CSS blocks, marked by task | Taken from the approved design |
| `tests_blend_ui.py` | Every new browser test, in sections marked `# === Task N` | Compiles; the Task 2 audio test was run against the seed. The others have never run: the code they test does not exist yet |
| `tests_blend_units.py` | The one new unit test | Compiles |

## Stop rules

Stop and report, changing nothing further, when:
- `git apply --check` fails, or the checked-out commit is not the base commit;
- a baseline test fails in Task 1;
- a step's expected result does not appear after two honest attempts at the implementation;
- a test can pass only by changing the test.

---

### Task 1: Workspace and baseline

**Files:**
- Create: `docs/plans/blend.md`, `docs/superpowers/plans/` (copied in)

**Interfaces:**
- Consumes: nothing.
- Produces: a clone at `$HOME/src/DigitalCrate` on branch `stem-blends`, a working `.venv`, and a green baseline. Every later command runs from that folder.

- [ ] **Step 1: Clone at the base commit**

If `$HOME/src/DigitalCrate` already exists, stop and ask.

```bash
mkdir -p "$HOME/src" && git clone https://github.com/jaredhuling/DigitalCrate.git "$HOME/src/DigitalCrate"
cd "$HOME/src/DigitalCrate" && git checkout -b stem-blends 8872ec8a5f5da1fe33972eca7e636be967c6cde0
```

Expected: `git log --oneline -1` prints `8872ec8 Pause/resume background work; CI installs madmom; playable works without it`.

- [ ] **Step 2: Copy the spec, the plan and its files in**

```bash
SRC=/path/to/DigitalCrate-main
mkdir -p docs/superpowers/plans
cp "$SRC/docs/plans/blend.md" docs/plans/blend.md
cp "$SRC/docs/superpowers/plans/2026-11-24-stem-snapshots-and-blends.md" docs/superpowers/plans/
cp -R "$SRC/docs/superpowers/plans/2026-11-24-stem-snapshots-and-blends" docs/superpowers/plans/
```

Expected: `ls docs/superpowers/plans/2026-11-24-stem-snapshots-and-blends` lists the five files of the table above.

- [ ] **Step 3: Install, as the repository's CI does**

```bash
brew install ffmpeg rubberband
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python --no-deps -r requirements.lock
uv pip install --python .venv/bin/python --no-deps -e .
uv pip install --python .venv/bin/python --no-deps --no-build-isolation "madmom @ git+https://github.com/CPJKU/madmom@27f032e8947204902c675e5e341a3faf5dc86dae"
uv pip install --python .venv/bin/python pytest playwright==1.55.0
.venv/bin/python -m playwright install chromium
```

The first browser test run downloads about 1.6 GB of models and builds a throwaway library; every browser test run takes a few minutes for that reason.

- [ ] **Step 4: Baseline**

Run: `.venv/bin/python -m pytest -q tests/test_units.py -k stem`
Expected: every selected test passes (2 at the base commit).

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k "stem_mixer or sliders"`
Expected: `2 passed`.

- [ ] **Step 5: The patch applies**

Run: `git apply --check docs/superpowers/plans/2026-11-24-stem-snapshots-and-blends/hooks.patch`
Expected: no output, exit status 0.

- [ ] **Step 6: Commit**

```bash
git add docs/plans/blend.md docs/superpowers
git commit -m "Stem mixer: plan for snapshots, blends and the duck"
```

---

### Task 2: The duck, and one audio chain for both views

**Files:**
- Modify: `digitalcrate/static/studio.js` (by `hooks.patch`)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: the mixer's functions, handed over by the patch as `BLEND.init({MX, STEMS, ICON, PITCHED, DT, role, state, save, draw, sync, play, apply, ev, barLenM})`. Inside the block they are `H`, and `BLEND` is `BL`.
- Produces, all on `window.BLEND` (read their bodies in the seed):
  - constants `MAX_SNAPS`, `BARS`, `WINS`, `STYLES`, `DUCK`, `Q`, `STAGES`, `EDGE`
  - `layerPos(m, win) -> number`, `blendAt(style, p, nyq) -> {ga, gb, hp, lp}`
  - `mkXf(ctx) -> {in, out, h, l, g}`, `setXf(x, {gain, hp, lp}, t)`, `ramp(param, v, t)`
  - `duckBus(ctx) -> {in, env}`, `out(MX, ctx)` (makes `MX.master` and `MX.bus` once)
  - `mkChain(ctx, out, bus) -> chain` with `chain.drop()`, `applyChain(chain, settings, t)`, `mixOf(part, stem, {on, fx, bar, DT, duck}) -> settings`
  - `adopt(MX, saved)`, `fixTrans(MX)`, `duckOf(slotId) -> {on, db}`, `duckHTML(slotId, stem) -> string`
  - stubs `stripHTML() -> ''` and `pbDraw() -> false`, replaced in Tasks 3 and 5
  - new state: `MX.duck`, `MX.snaps`, `MX.trans`, `MX.snapSel`, `MX.bus`

- [ ] **Step 1: Append the tests**

Append the section `# === Task 2` of `tests_blend_ui.py` (from that marker to the next `# === Task` marker, without the marker lines) to the end of `tests/test_ui.py`. It adds `_mixer`, `_set`, `BLEND_AUDIO` and three tests: `test_blend_audio_core`, `test_duck_is_on_for_bass_and_remembered`, `test_state_saved_before_blends_still_opens`.

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k "blend_audio_core or duck_is_on or saved_before_blends"`
Expected: 3 failed. The first fails with a `TypeError` about reading `mkXf` of `undefined`: `window.BLEND` does not exist yet.

- [ ] **Step 3: Apply the patch**

```bash
git apply docs/superpowers/plans/2026-11-24-stem-snapshots-and-blends/hooks.patch
node --check digitalcrate/static/studio.js
grep -n -E "^// ---------- (📸 stem blends|end of stem blends)" digitalcrate/static/studio.js | cut -c1-40
```

Expected: no output from `git apply` or `node --check`; the `grep` prints lines 1456 and 1629. `git diff --stat` shows one file, `studio.js`, with 184 insertions and 14 deletions. Read lines 1456 to 1629 now: every later task adds to them.

- [ ] **Step 4: Run the new tests and the mixer's own**

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k "blend_audio_core or duck_is_on or saved_before_blends or stem_mixer or sliders"`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add digitalcrate/static/studio.js tests/test_ui.py
git commit -m "Stem mixer: bass ducks under the drums' low end; one audio chain for the mixer and what follows"
```

---

### Task 3: Snapshots in the mixer

**Files:**
- Modify: `digitalcrate/static/studio.js` (the stem blends block), `digitalcrate/static/studio.css`, `digitalcrate/stems.py`
- Test: `tests/test_ui.py`, `tests/test_units.py`

**Interfaces:**
- Consumes: `H`, `BLEND.fixTrans`, `BLEND.MAX_SNAPS` (Task 2).
- Produces on `BLEND`:
  - `LETTERS = 'ABCDEFGH'`, `STEMVAR = {drums: '--PERC', bass: '--BASS', vocals: '--VOX', other: '--KEYS'}`
  - `audible(part) -> boolean`, `sameAudio(a, b) -> boolean`
  - `diffSnaps(A, B) -> [{id, stem, a, b, kind}]`, `kind` one of `same`, `change`, `enter`, `exit`, `empty`
  - `snapNow() -> snap`, `capture() -> Promise<boolean>`, `recall(i) -> Promise<void>`, `replace(i)`, `remove(i)`
  - `stripHTML() -> string`, with ids `#snbar`, `#sncap`, `#snrep`, `#sndel`, `#snplay` and chips `button[data-sn="<index>"]`
- A snap is `{order, roles, slots, duck}`, each in the shape `save()` writes to `localStorage['dcStems']`.

- [ ] **Step 1: Append the tests**

Append the section `# === Task 3` of `tests_blend_ui.py` to `tests/test_ui.py` (`_roll`, `test_snapshots_capture_recall_replace_delete`) and the whole of `tests_blend_units.py` below its marker line to `tests/test_units.py` (`test_stem_snapshot_counts_as_a_weak_yes`).

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest -q tests/test_units.py -k snapshot_counts`
Expected: 1 failed with `KeyError: 'snap'`.

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k snapshots_capture`
Expected: 1 failed: it times out waiting for `#snplay`, which does not exist yet.

- [ ] **Step 3: The `snap` event in `digitalcrate/stems.py`**

In `log()`, add `"snap": (1, 0.6)` to the dictionary of kinds, after `"remove": (0, 0.6)`, and add to its docstring: `snap: a snapshot was taken with this part in it (weak yes).`

Run: `.venv/bin/python -m pytest -q tests/test_units.py -k "stem"`
Expected: all pass (3).

- [ ] **Step 4: The model, in the stem blends block**

Implement, replacing nothing yet:

- `audible(p)`: `p` exists, `p.track != null` and `p.mute` is not true.
- `sameAudio(a, b)`: both audible and equal in `stem`, `track`, `bar0`, `n`, `k || 1` and `off || 0`. Volume, EQ, delay and lock do not count.
- `diffSnaps(A, B)`: one row per slot id, in `A.order` followed by the ids of `B.order` not in it. `a` is `A.slots[id]` when audible, else `null`; `b` likewise. `kind` is `same` or `change` when both exist, `enter` when only `b`, `exit` when only `a`, `empty` when neither. `stem` is `b.stem`, else `a.stem`, else `B.roles[id]`, else `A.roles[id]`, else `id`.
- `snapNow()`: call `H.save()`, parse `localStorage['dcStems']`, return its `order`, `roles`, `slots` and `duck || {}`.

- [ ] **Step 5: `capture`, `recall`, `replace`, `remove`**

`capture()`, in this order:
1. 8 snapshots already: `toast('8 snapshots at most: delete one first')`, return `false`.
2. No audible slot in the mixer: `toast('nothing to snapshot yet: 🎲 a part first')`, return `false`.
3. `MX.key` is `''` and `MX.info.key` exists: set `MX.key = MX.info.key` (the auto key is frozen).
4. Take `snapNow()`, push it, `fixTrans(MX)`, set `MX.snapSel` to its index.
5. Call `H.ev('snap', id)` for every audible slot when it is the first snapshot; otherwise for every row of `diffSnaps(previous, new)` whose `kind` is `change` or `enter`.
6. `H.save()`, `H.draw()`, return `true`.

`recall(i)` mirrors the mixer's own "open a saved one": if `MX.on`, `H.play(false)`; set `MX.order`, `MX.roles`, `MX.slots` and `MX.duck` to deep copies of the snapshot's; `MX.info = null`; `MX.snapSel = i`; `await H.sync()`; `MX.order.forEach(H.apply)`; play again if it was playing.

`replace(i)`: `MX.snaps[i] = snapNow()`, then `H.save()` and `H.draw()`.

`remove(i)`:

```js
MX.snaps.splice(i, 1);
MX.trans.splice(Math.min(i, MX.trans.length - 1), 1);
if (i > 0 && i < MX.snaps.length) MX.trans[i - 1] = { bars: 8, layers: {} };   // its two neighbours are a new pair
BL.fixTrans(MX); MX.snapSel = null; H.save(); H.draw();
```

- [ ] **Step 6: The strip**

Replace the `stripHTML` stub with:

```js
BL.stripHTML = () => {
  const MX = H.MX, n = MX.snaps.length, sel = MX.snapSel, L = BL.LETTERS;
  const label = i => {
    if (!i) return '<span class="sub">start</span>';
    const d = BL.diffSnaps(MX.snaps[i - 1], MX.snaps[i]).filter(r => r.kind !== 'same' && r.kind !== 'empty');
    return d.length ? d.map(r => `<span class="sndot" style="--c:var(${BL.STEMVAR[r.stem] || '--mute'})"></span>${r.stem}`).join('') : '<span class="sub">same</span>';
  };
  return `<div class="snbar" id="snbar"><span class="snlab">snapshots</span>${MX.snaps.map((s, i) =>
    `${i ? '<span class="snsep">›</span>' : ''}<button class="snchip${sel === i ? ' on' : ''}" data-sn="${i}" title="bring snapshot ${L[i]} back into the mixer"><b>${L[i]}</b>${label(i)}</button>`).join('')}
   ${sel != null && sel < n ? `<button class="tbtn" id="snrep" title="write what is playing now over snapshot ${L[sel]}">↻ replace ${L[sel]}</button><button class="tbtn" id="sndel" title="delete snapshot ${L[sel]}">🗑</button>` : ''}
   <button class="tbtn" id="sncap" title="keep every slot as it is now, as the next snapshot">📸 snapshot</button><span style="flex:1"></span>
   ${n ? '<span class="sub">tempo and key belong to the strip</span>' : ''}<button class="pill" id="snplay" title="play the snapshots side by side and move from one to the next" ${n < 2 ? 'disabled' : ''}>▶ play strip</button></div>`;
};
```

In the click listener that `BL.init` adds, handle `#sncap` (`BL.capture()`), `[data-sn]` (`BL.recall(+ds.sn)`), `#snrep` (`BL.replace(MX.snapSel)`) and `#sndel` (`BL.remove(MX.snapSel)`). Find the button with `e.target.closest('button')`, as the existing branch does.

Append the block marked `=== Task 3` of `blend.css` to `digitalcrate/static/studio.css`, without its marker line.

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k "snapshots_capture or duck_is_on or stem_mixer"`
Expected: `3 passed`.

- [ ] **Step 8: Commit**

```bash
git add digitalcrate/static/studio.js digitalcrate/static/studio.css digitalcrate/stems.py tests/test_ui.py tests/test_units.py
git commit -m "Stem mixer: snapshots in a strip above the slots"
```

---

### Task 4: The transition model

**Files:**
- Modify: `digitalcrate/static/studio.js` (the stem blends block)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `diffSnaps` (Task 3), `layerPos`, `BARS`, `STYLES`, `WINS` (Task 2).
- Produces on `BLEND`, all pure (they never write to `MX`):
  - `transFor(MX, i, rows?) -> {bars, layers: {slotId: {style, win}}}`
  - `rowPos(row, m, T, hand) -> number`
  - `lerpMix(a, b, m) -> {db, eq, dly, dt, eqOn: true, dlyOn: true, mute: false}`

- [ ] **Step 1: Append the test**

Append the section `# === Task 4` of `tests_blend_ui.py` to `tests/test_ui.py` (`test_blend_model`).

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k blend_model`
Expected: 1 failed with `TypeError: B.transFor is not a function`.

- [ ] **Step 3: Implement the three functions**

- `transFor(MX, i, rows)`: `rows` defaults to `diffSnaps(MX.snaps[i], MX.snaps[i + 1])`. `bars` is `MX.trans[i].bars` when it is one of `BARS`, else 8. For every row whose `kind` is `change`, `enter` or `exit`, `layers[id]` is the first stored entry found in `MX.trans[j].layers[id]` for `j = i, i - 1, …, 0`, with a `style` not in `STYLES` read as `filter` and a `win` not in `WINS` read as `all`; with no stored entry it is `{style: 'filter', win: 'all'}`. Only stored entries are inherited, never a default.
- `rowPos(row, m, T, hand)`: `m` for a `same` or `empty` row; else `hand[row.id]` when it is not `null` or `undefined`; else `layerPos(m, T.layers[row.id].win)`.
- `lerpMix(a, b, m)`: every number goes linearly from `a`'s to `b`'s. `db` from `db || 0`. `eq` from each side's `eq`, read as `[0, 0, 0]` when that side's `eqOn` is `false`. `dly` from each side's `dly`, read as 0 when its `dlyOn` is `false`. `dt` is `a.dt` below `m = 0.5` and `b.dt` from there on, `'1/8'` when missing.

- [ ] **Step 4: Run the test**

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k blend_model`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add digitalcrate/static/studio.js tests/test_ui.py
git commit -m "Stem mixer: the transition model between two snapshots"
```

---

### Task 5: Playing the strip by hand

**Files:**
- Modify: `digitalcrate/static/studio.js` (the stem blends block), `digitalcrate/static/studio.css`
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: everything from Tasks 2 to 4.
- Produces `BLEND.pb`, also at `window.CRATE.PB`:

```js
PB = {
  on: false, playing: false, ready: false, nextReady: true,
  i: 0,            // the left snapshot's index; the right one is i + 1
  m: 0,            // the master, 0..1
  hand: {},        // slot id -> position, for layers ridden by hand
  auto: false, hold: 8,
  rows: [],        // diffSnaps of the pair; each row also carries .va and .vb, its voices (the same object on a `same` row)
  T: null,         // transFor(MX, i, rows)
  info: [{}, {}],  // the server's api/stems/info answer for each side
  missing: {},     // 'a:<slot>' or 'b:<slot>' -> true
  t0: 0,           // the audio-clock time of bar 0
  open(i), close(), play(on), setMaster(m), setHand(id, p), setStyle(id, style), setWin(id, win), setBars(n),
  pos(id) -> number | null, atEnd(side) -> boolean, voice(id, side) -> voice | null
}
voice = { id, key, buf, xf, chain, src, g, t, set: {gain, hp, lp} }   // t: when its source started; set: what it was last told
```

- `BLEND.pbDraw(L) -> boolean`: `false` when `PB.on` is false; otherwise it fills `L` and returns `true`.
- DOM: root `#pb`; `#pbback`, `#pbplay`, `#pbauto`, `#pbhold`, `#pbprev`, `#pbnext`, `#pbm`, `#pbbars`, `#pbstat`; rows `.pb3[data-pbrow="<slot>"]`; slot cards `[data-pbside="a"|"b"]`; waveforms `[data-pbwave="<side>:<slot>"]`; per layer `select[data-pbstyle]`, `select[data-pbwin]`, `input[data-pbpos]`.
- In this task the arrows are drawn but always disabled, and `#pbauto` and `#pbhold` are drawn but do nothing. Tasks 6 and 7 bring them to life.

- [ ] **Step 1: Append the test**

Append the section `# === Task 5` of `tests_blend_ui.py` to `tests/test_ui.py` (`_strip`, `_voice`, `test_playback_shows_both_sets_and_blends_by_hand`).

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k playback_shows_both`
Expected: 1 failed: the wait for `CRATE.PB.on` times out or throws on `CRATE.PB`.

- [ ] **Step 3: Loading a pair**

`PB.load(i)` makes `snaps[i]` and `snaps[i + 1]` the pair that plays:

1. `PB.ready = false`. Ask the server about each side: `window.CRATE.api('api/stems/info', {state: {bpm: MX.bpm, key: MX.key || null, slots}})`, where `slots` holds `{stem, track, bar0, n, k, off}` for every audible part of that snapshot. Keep both answers in `PB.info`.
2. An audible part whose slot id is missing from its answer's `slots` belongs to a song that is no longer prepared. Record it in `PB.missing` and leave it out of the copy of the snapshot used in the next step.
3. `PB.rows = diffSnaps(leftCopy, rightCopy)`; `PB.T = transFor(MX, i, PB.rows)`.
4. For every part in the rows get its buffer. Its key is `[track, stem, bar0, n, k || 1, MX.bpm, semis].join('|')`, with `semis` from the answer in step 1. A buffer comes from `PB.cache` (a `Map` of key to promise) or from `api/stems/render` with `{track, stem, bar0, n, k, bpm: MX.bpm, semis}`, then `fetch(url(r.url))`, then `AC.decodeAudioData`. A part whose render fails is treated as missing: recompute steps 2 and 3 without it.
5. A voice's identity is `slotId + '|' + key`. Keep voices that the new rows still need: they keep playing. Stop and `chain.drop()` the others. Create the missing ones: `xf = BLEND.mkXf(AC)`, `chain = BLEND.mkChain(AC, MX.master, MX.bus)` after `BLEND.out(MX, AC)`, `xf.out` into `chain.in`. On a `same` row `va` and `vb` are one voice.
6. `PB.ready = true`, apply everything (Step 4), start any voice that is not running if `PB.playing`, then `H.draw()`.

A voice starts as the mixer's own sources do, so every loop sits on one bar clock:

```js
const when = AC.currentTime + 0.03, src = AC.createBufferSource(), g = AC.createGain(), d = v.buf.duration;
src.buffer = v.buf; src.loop = true; src.connect(g); g.connect(v.xf.in);
g.gain.setValueAtTime(0, when); g.gain.linearRampToValueAtTime(1, when + 0.012);
src.start(when, (((when - PB.t0) % d) + d) % d);
v.src = src; v.g = g; v.t = when;
```

It stops with `v.g.gain.setTargetAtTime(0, t, 0.006)` and `v.src.stop(t + 0.05)`. `PB.play(true)` calls `AC.resume()`, sets `PB.t0 = AC.currentTime + 0.05` and starts every voice; called while already playing it does nothing. `PB.play(false)` stops them all.

- [ ] **Step 4: Applying a position**

`PB.pos(id)` is `rowPos(row, PB.m, PB.T, PB.hand)`, or `null` for an unknown id. `PB.atEnd(side)` is true when every `change`, `enter` and `exit` row is at exactly `side` (0 or 1). One function applies the whole state and is called by `setMaster`, `setHand`, `setStyle`, `setWin`, `setBars` and `load`:

```js
const t = AC.currentTime, nyq = AC.sampleRate / 2, MX = H.MX, A = MX.snaps[PB.i], B = MX.snaps[PB.i + 1];
const o = { on: true, fx: MX.fx !== false, bar: H.barLenM(), DT: H.DT };
for (const r of PB.rows) {
  if (r.kind === 'empty') continue;
  const set = (v, x, part, duck) => { v.set = x; BL.setXf(v.xf, x, t); BL.applyChain(v.chain, BL.mixOf(part, r.stem, { ...o, duck }), t); };
  if (r.kind === 'same') { set(r.va, { gain: 1, hp: 0, lp: nyq }, BL.lerpMix(r.a, r.b, PB.m), ((PB.m < 0.5 ? A : B).duck || {})[r.id]); continue; }
  const b = BL.blendAt(PB.T.layers[r.id].style, PB.pos(r.id), nyq);
  if (r.va) set(r.va, { gain: b.ga, hp: b.hp, lp: nyq }, r.a, (A.duck || {})[r.id]);
  if (r.vb) set(r.vb, { gain: b.gb, hp: 0, lp: b.lp }, r.b, (B.duck || {})[r.id]);
}
```

`setStyle`, `setWin` and `setBars` write to `MX.trans[PB.i]` (a layer's entry is always the complete `{style, win}`), then `H.save()`, recompute `PB.T`, apply, and `H.draw()`. `setMaster` and `setHand` apply and then call `PB.paint()`; they never redraw, because a redraw would destroy the slider being dragged.

`PB.paint()` updates the open view in place: every `[data-pbpos]` and `#pbm` gets its value (`Math.round(position * 100)`) and its fill (`style.setProperty('--a', 0)` and `'--b'` the position, as the sliders block at the end of the file does); a left card gets class `off` when its row is at 1 and a right card when its row is at 0; the two side labels, the two letters' `idle` class, the two arrows and `#pbstat` get their current state. It does nothing when `#pb` is not on the page.

- [ ] **Step 5: Opening, closing and the view**

`PB.open(i)`: stop the mixer if `MX.on` (`H.play(false)`); `PB.on = true`, `PB.i = i`, `PB.m = 0`, `PB.hand = {}`; `H.draw()`; `await PB.load(i)`; `PB.play(true)`. `PB.close()`: stop and drop every voice, clear `PB.cache`, `PB.on = false`, `PB.auto = false`, `H.draw()`.

`pbDraw(L)` fills `L` with this structure. The strings come from the spec; `LT` is `BLEND.LETTERS`.

```html
<div class="mx" id="pb">
 <div class="mxtop pbhead">
  <button id="pbback">◂ mixer</button><span class="snlab">playing the strip</span>
  <!-- one per snapshot, `on` for i and i + 1, `›` between them -->
  <button class="snchip on" data-pbsn="0"><b>A</b></button><span class="snsep">›</span><button class="snchip on" data-pbsn="1"><b>B</b></button>
  <button id="pbplay" class="on">■ stop</button><span class="sub">100 bpm · Am</span><span style="flex:1"></span>
  <button id="pbauto">auto off</button>
  <label class="sub">hold <select id="pbhold"><option value="4">4 bars</option><option value="8" selected>8 bars</option><option value="16">16 bars</option></select></label>
 </div>
 <div class="pbscroll"><div class="pbgrid">
  <div class="pb3" style="margin-bottom:6px">
   <div class="pbside"><button class="tbtn" id="pbprev" disabled>◀</button><b class="pbletter">A</b><span class="sub">going out</span></div>
   <div class="snlab" style="text-align:center;align-self:center">transition</div>
   <div class="pbside r"><span class="sub">coming in</span><b class="pbletter">B</b><button class="tbtn" id="pbnext" disabled>B is last</button></div>
  </div>
  <!-- one .pb3 per row of PB.rows -->
  <div class="pb3" data-pbrow="drums">
   <div class="pbslot" data-pbside="a" data-pbslot="drums"><div class="mxname">🥁 drums</div>
    <div class="mxsrc" title="artist — title"><b>artist</b> — title<br><span class="sub">bars 9–12 · from 96.4 bpm</span></div>
    <div class="mxwave" data-pbwave="a:drums"><canvas></canvas><i></i></div></div>
   <div class="pbx"><div class="pbxrow">
     <select data-pbstyle="drums"><option value="filter">filter handoff</option><option value="xfade">crossfade</option></select>
     <select data-pbwin="drums"><option value="all">bars 1–8</option><option value="first">bars 1–4</option><option value="second">bars 5–8</option><option value="cut">cut at bar 5</option></select></div>
    <label class="pbab"><span>A</span><input type="range" min="0" max="100" step="1" value="0" data-pbpos="drums"><span>B</span></label></div>
   <div class="pbslot" data-pbside="b" data-pbslot="drums">…the same card for the right snapshot's part…</div>
  </div>
  <div class="pb3">
   <div class="sub" style="align-self:center;text-align:right">moves every layer at once</div>
   <div class="pbx pbmaster"><div class="pbxrow" style="justify-content:space-between"><b>master</b>
     <label class="sub">over <select id="pbbars" style="flex:none"><option value="2">2 bars</option><option value="4">4 bars</option><option value="8" selected>8 bars</option><option value="16">16 bars</option></select></label></div>
    <label class="pbab"><span>A</span><input type="range" id="pbm" min="0" max="100" step="1" value="0"><span>B</span></label></div>
   <div class="sub" id="pbstat" style="align-self:center"></div>
  </div>
 </div></div>
</div>
```

Rules for what varies:
- A card with no part shows `<div class="mxsrc"><span class="sub">…</span></div>` and no waveform: `missing` when `PB.missing` has it, `muted` when the snapshot has a muted part there, else `empty`.
- A card's second line is the mixer's own: `bars <first>–<last> · from <src_bpm> bpm`, and for bass, vocals and other ` · <key>` and the shift when it is not 0. `src_bpm`, `key` and `semis` come from `PB.info`.
- The middle cell of a `same` row is `<div class="pbsame">same in both</div>`, with a second line `volume glides −2 → −4 dB` when the two sides' `db` differ; of an `empty` row `<div class="pbsame">empty in both</div>`.
- A layer in `PB.hand` shows `<span class="tag hot">by hand</span>` in place of its `data-pbwin` select.
- The window options use the transition's length `T.bars`: `bars 1–T`, `bars 1–T/2`, `bars T/2+1–T`, `cut at bar T/2+1`. Selects show the layer's current style and window and the transition's length.
- The side labels follow `PB.atEnd`: fully on the left (`atEnd(0)`) the left says `playing` and the right `next`; fully on the right (`atEnd(1)`) the left says `silent` and the right `playing`; anywhere between, `going out` and `coming in`. The letter of the side that is not sounding (`next` or `silent`) has class `pbletter idle`.
- The head shows the mixer's tempo and key (`100 bpm · Am`); `#pbplay` reads `■ stop` with class `on` while playing and `▶ play` otherwise; `#pbhold` shows `PB.hold`.
- `pbDraw` can run before the first `load` has finished (the mixer redraws when its own work ends): with `PB.ready` false it draws the head and the column heads only, and never throws.
- Escape every artist and title with `esc`.

After filling `L`, draw each waveform on its canvas the way `waves()` in the stem mixer block does (bars in the stem's colour from `BLEND.STEMVAR`, a white line at 28% for each bar), and run a `requestAnimationFrame` loop while `PB.playing` and `st.tab === 'M'` that moves each `<i>` play line with `((AC.currentTime - PB.t0) % d + d) % d / d` and sets its `display` to `block`.

- [ ] **Step 6: Wiring**

In the listeners of `BL.init`, all behind the existing `st.tab !== 'M'` guard:

| Event | Target | Action |
| --- | --- | --- |
| click | `#snplay` | `PB.open(0)` |
| click | `#pbback` | `PB.close()` |
| click | `#pbplay` | `PB.play(!PB.playing)`, then `H.draw()` |
| input | `#pbm` | `PB.setMaster(value / 100)` |
| input | `[data-pbpos]` | `PB.setHand(id, value / 100)` |
| change | `[data-pbpos]` | `H.draw()` (the `by hand` tag appears) |
| change | `[data-pbstyle]`, `[data-pbwin]`, `#pbbars` | `PB.setStyle`, `PB.setWin`, `PB.setBars(+value)` |

Add `window.CRATE.PB = BL.pb = PB` in `BL.init`. Append the block marked `=== Task 5` of `blend.css` to `digitalcrate/static/studio.css`, without its marker line.

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k "playback_shows_both or snapshots_capture or stem_mixer"`
Expected: `3 passed`.

- [ ] **Step 8: Commit**

```bash
git add digitalcrate/static/studio.js digitalcrate/static/studio.css tests/test_ui.py
git commit -m "Stem mixer: play two snapshots side by side and blend between them by hand"
```

---

### Task 6: Arrows, loading ahead, missing songs

**Files:**
- Modify: `digitalcrate/static/studio.js` (the stem blends block)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `PB.load`, `PB.atEnd`, `PB.cache`, `PB.paint`, `pbDraw` (Task 5).
- Produces: `PB.advance(dir) -> Promise<boolean>` (`dir` is `1` or `-1`), `PB.prefetch() -> Promise<void>`, and a truthful `PB.nextReady`.

- [ ] **Step 1: Append the tests**

Append the section `# === Task 6` of `tests_blend_ui.py` to `tests/test_ui.py` (`test_playback_arrows_walk_the_strip`, `test_playback_waits_for_the_next_snapshot`).

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k "playback_arrows or playback_waits"`
Expected: 2 failed: in the first `#pbnext` never becomes enabled; the second finds `CRATE.PB.nextReady` already true.

- [ ] **Step 3: Implement**

- `PB.prefetch()`: at the end of every `load`, set `PB.nextReady` to `false` when `snaps[i + 2]` exists, else `true`. When it exists, fetch the buffers of its audible parts into `PB.cache` as `load` does (one `api/stems/info` call for their `semis`, skipping parts the server does not answer for), then set `PB.nextReady = true` and call `PB.paint()`. If `PB.i` changed meanwhile, do nothing. A failed render counts as loaded: that part will show as missing.
- Arrow state, set by both `pbDraw` and `paint`:
  - `#pbnext` is enabled when `PB.atEnd(1)`, `snaps[i + 2]` exists and `PB.nextReady`. Enabled, its class is `pill` and its text `B · C ▶`; otherwise class `tbtn`, with `B · C ▶` when a next snapshot exists and `B is last` when not.
  - `#pbprev` is enabled when `PB.atEnd(0)` and `i > 0`, with text `◀ Z · A` (the pair before); at `i = 0` its text is `◀`.
- `PB.advance(1)`: only when `#pbnext` would be enabled. `PB.i += 1`, `PB.m = 0`, `PB.hand = {}`, `await PB.load(PB.i)`. `PB.advance(-1)`: only when `#pbprev` would be enabled. `PB.i -= 1`, `PB.m = 1`, `PB.hand = {}`, `await PB.load(PB.i)`. Both return whether they moved. Because `load` keeps voices by identity, the snapshot that stays never stops sounding.
- After a `load`, delete from `PB.cache` every key that no part of `snaps[i - 1]` to `snaps[i + 2]` uses.
- Clicks on `#pbnext` and `#pbprev` call `PB.advance(1)` and `PB.advance(-1)`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k "playback_arrows or playback_waits or playback_shows_both"`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add digitalcrate/static/studio.js tests/test_ui.py
git commit -m "Stem mixer: arrows walk the strip, the next snapshot loads ahead"
```

---

### Task 7: Auto

**Files:**
- Modify: `digitalcrate/static/studio.js` (the stem blends block)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `PB.advance`, `PB.nextReady`, `PB.setMaster`, `PB.paint` (Tasks 5 and 6).
- Produces: `PB.setAuto(on)`, `PB.setHold(bars)` (any positive number; the menu offers 4, 8 and 16), `PB.ph` (`null`, or `{kind: 'hold' | 'move', from, m0}` with `from` an audio-clock time on a bar line).

- [ ] **Step 1: Append the test**

Append the section `# === Task 7` of `tests_blend_ui.py` to `tests/test_ui.py` (`test_auto_walks_the_strip_and_hands_back_control`).

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k auto_walks`
Expected: 1 failed with `TypeError: CRATE.PB.setHold is not a function`.

- [ ] **Step 3: Implement**

With `L = H.barLenM()` and `nextBar() = PB.t0 + Math.ceil((AC.currentTime - PB.t0) / L - 1e-6) * L`:

- `PB.setAuto(true)`: start playing if stopped; `PB.hand = {}`; `PB.auto = true`. Then:
  - master at exactly 1: if a next snapshot exists and is loaded, `await PB.advance(1)` and hold; if none exists, `PB.auto = false`;
  - master at 0: `PB.ph = {kind: 'hold', from: nextBar()}`;
  - anywhere between: `PB.ph = {kind: 'move', from: nextBar(), m0: PB.m}`.
  Start a `setInterval` of 25 ms that runs the tick below. `PB.setAuto(false)` clears it and sets `PB.ph = null`. Both end with `H.draw()`.
- The tick, with `now = AC.currentTime`:
  - `hold`: when `now >= from + PB.hold * L`, become `{kind: 'move', from: from + PB.hold * L, m0: 0}`.
  - `move`: `dur = (1 - m0) * PB.T.bars * L` and `x = (now - from) / dur`. Below 1, set the master to `m0 + (1 - m0) * x`. At 1 or more, set the master to exactly `1`; then, if no next snapshot exists, `PB.setAuto(false)`; if it exists and `PB.nextReady`, `await PB.advance(1)` and become `{kind: 'hold', from: from + dur}`; if it exists and is not loaded, do nothing and try again next tick.
  - Guard the tick against running twice at once while it awaits `advance`.
  - The tick moves the master through an internal setter that does not switch auto off.
- A hand switches auto off first: the `input` handlers of `#pbm` and `[data-pbpos]` and the clicks on `#pbprev` and `#pbnext` call `PB.setAuto(false)` before their own action, when `PB.auto` is true. `PB.close()` does the same, so no timer outlives the view.
- `#pbauto` click: `PB.setAuto(!PB.auto)`. It reads `auto on` with class `on`, or `auto off`. `#pbhold` change: `PB.setHold(+value)`.
- `#pbstat`, kept current by `paint`: `holding A · bar 3 of 8` while holding (the bar is `Math.floor((now - from) / L) + 1`), `moving to B · bar 2 of 8` while moving (out of the transition's length), empty otherwise.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py -k "auto_walks or playback_arrows or playback_waits or playback_shows_both"`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add digitalcrate/static/studio.js tests/test_ui.py
git commit -m "Stem mixer: auto holds each snapshot, blends to the next and moves on"
```

---

### Task 8: Guide, plan status, full run

**Files:**
- Modify: `docs/guide.md`, `docs/plans/stems.md`, `docs/plans/blend.md`, `README.md`

**Interfaces:**
- Consumes: the finished feature.
- Produces: documentation that matches it, and a full green run.

- [ ] **Step 1: The guide**

In `docs/guide.md`, section `## Stem mixer`, add these three bullets after the whole bullet that begins `- **Per slot:**` (it runs over several lines):

```markdown
- **DUCK** on bass slots (on to begin with): the drums' low end pushes the bass's low end down a few dB, so a kick and
  a bass line from different songs don't pile up. The slider is how many dB at most.
- **📸 snapshot** keeps the mixer as it is, in a strip above the slots (A, B, C… up to 8). Click one to bring it back;
  **↻** replaces it, **🗑** deletes it. Tempo and key belong to the strip, and 💾 saves the strip too.
- **▶ play strip** shows two snapshots side by side, every slot of both, with the transition between them: for each
  layer that differs a style (filter handoff or crossfade), the bars it changes over, and its own slider. The
  **master** moves them all. Fully on the right snapshot, the arrow moves the view on. **auto** holds each snapshot,
  makes the transition over its bars and moves on by itself. The design is in [docs/plans/blend.md](plans/blend.md).
```

- [ ] **Step 2: The plans and the README**

- `docs/plans/blend.md`: change the first words of its status line from `Status: designed, not built.` to `Status: built.`
- `docs/plans/stems.md`: add a line after its status paragraph: `Snapshots, blends between them and the low-end duck: [blend.md](blend.md).`
- `README.md`: in the bullet that begins `- **🎛 Stems** (prototype)`, replace `and learns which combinations you like.` with `learns which combinations you like, and blends from one snapshot of a combination to the next.`

- [ ] **Step 3: The full run**

Run: `.venv/bin/python -m pytest -q`
Expected: no failures.

Run: `.venv/bin/python -m pytest -q --ui tests/test_ui.py`
Expected: no failures. Tests that need Ableton Live are skipped on a machine without it, as before.

- [ ] **Step 4: Listen to it**

Tests cannot hear. Run `digitalcrate build && digitalcrate serve` on a library with prepared songs (`digitalcrate stems`), and report in plain words what you heard for each of: the duck at 3 dB and at 12 dB with a kick-heavy drum part; a filter handoff and a crossfade between two drum parts; a cut; auto across three snapshots. If you cannot listen, say so; do not describe sound you did not hear.

- [ ] **Step 5: Commit**

```bash
git add docs/guide.md docs/plans/stems.md docs/plans/blend.md README.md
git commit -m "Stem mixer: guide and plans for snapshots, blends and the duck"
```
