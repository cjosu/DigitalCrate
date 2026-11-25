# Plan: Mashup tracks (the whole song under every loop, effects you drag, Tops and a vocal duck)

Status: built (tracks, the loop, pitch, the row of effects, harmonics as an amount, Tops and the vocal duck).

## The idea

A slot becomes a **track**, read the way Simpler reads in Live (Classic mode, Loop on): the whole song's stem as one
waveform, the bars that loop lit, the rest gray. You drag the loop where you want it and its end snaps to a bar line.
Pitch is two numbers you drag, and so is every effect, in one slim row under the waveform. Drums split in two:
**Drums** (kick, snare, the rest of the kit) and **Tops** (hats and cymbals), each from its own song. And the vocals
**duck** Tops and Other.

## Why

- A slot shows only the bars that loop. Where they sit in the song can't be seen, and moving them is ◀ ▶ and a length
  menu. The person this is for works in Live and wanted to see the whole song and grab the loop.
- A slot's controls are two rows of labelled sliders beside its waveform, and every new effect (reverb, harmonics, a
  second duck) makes them longer. Numbers you drag hold more in less room, and every track's settings stay in view.
- A drum part's hats come with its kick. Being able to take the hats from another song is most of what makes a
  recombined beat sound new.

## Goals

- See the whole song under every loop, and change the loop by dragging it.
- A track is no taller than a slot is today (about 122 px), so the screen holds as much as it does now.
- Nothing Mashup does today is lost. Every control keeps a place.
- Everything saved before still opens.

## Not goals

- Hearing the song outside the loop, or scrubbing. The browser gets a picture of the whole song, not its audio.
- Loop lengths that aren't whole bars.
- A new look for the play-strip view. It keeps working and keeps its look.
- Changing how parts are scored and picked, beyond adding Tops as a role.

## What must not happen

- A control that is drawn but can't be reached, or one that does nothing. Nothing may need sideways scrolling at
  1280 px wide. (The play-strip's ▶ arrow was once drawn off the right edge. Tests passed because the test browser
  scrolls to what it clicks.)
- Loops drifting apart, or a click at the loop point. Parts stay rendered by the server to exact bars and looped on
  the one bar clock.
- A saved combination or snapshot that opens and sounds different from how it was saved (see 8).

## What stays as it is

The top bar and everything in it, the snapshot strip and the play-strip view, ＋ add slot, the learning line, the list
of prepared songs, saving and reverting, the one reverb for the whole mixer, slot history, duplicating a slot, the
dice's next part being fetched ahead of time, and a one-shot slot's step grid, waveform lane and trim. The words
"slot" and "track" mean the same thing below; the screen says nothing either way.

## Design

**1. A track.** A header line, the waveform, and under it a row of effects.

```
● Drums   Birds ov Paradise - Fog · 120 bpm        bars 105–112 · 8 bars   pitch [ 0 st][ 0 ct]   ⚄ ↶ ↷   S M   ──●──  ⋯
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░▕██████▏░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
● EQ [lo 0.0 dB][mid 0.0 dB][hi +1.5 dB]   ○ DELAY [time 1/8][feedback 35 %][amount 0 %]   ○ REVERB [amount 0 %]   HARMONICS [0 %]
```

Left to right in the header:
- a dot in the stem's colour and what the track plays, as a word (Drums, Tops, Bass, Vocals, Other, One-shot). No
  emoji anywhere on a track;
- the song, then what the row says today after it (source tempo, key and the shift to the key, half- or
  double-time, take 2/5, the sub-bass note). It is the part that shortens when the window is narrow; the full text
  and "why this part" stay in its tooltip;
- the loop in the song's own bars: `bars 105–112 · 8 bars`, or `bar 44 · 1 bar`;
- pitch: two numbers (3);
- a new part (a drawn die), back ↶ and forward ↷ through the parts the track has held;
- S and M, and the volume slider (double-click for 0 dB);
- **⋯**: choose the song, other takes of this song (⇄ today), keep on "all" (🔒 today), duplicate this track (⧉
  today), empty this track, what it plays (the role menu today), remove the track.

An empty track shows its name, "empty", the die and ⋯. A part that is loading or failed says so where the song is
named, as today.

A **one-shot** track has the same header: its sample where the song is, its cycle length and how often it plays
where a stem track shows its bars, and ▶ (play it once) beside the die. Under the header it keeps its step grid and
the waveform lane under it, as they are on main, and has the row of effects under those. Its pitch is by playback
speed, as now.

**2. The waveform and the loop.**
- The picture is the whole stem, start to end. Inside the loop it is in the stem's colour on a slightly lighter
  ground; outside it is gray. A bar across the top joins the loop's two edges, and each edge has a small flag.
- **Drag the right edge** to change the length, **the left edge** to change the start (the end stays), **inside** to
  move the loop. **Click the gray** and the loop goes there, same length. While you drag, a tag at the edge says the
  length.
- Edges snap so the loop is a whole number of the mixer's bars, 1 to 16: to every bar line of the song; for a
  half-time part (two of the song's bars to one of the mixer's) to every second line from the loop's start; a
  double-time part is two mixer bars for each of the song's.
- With the waveform focused, ← → move the loop a bar, ⇧← ⇧→ make it a bar shorter or longer. This replaces ◀ ▶ and
  the length menu.
- **Zoom:** pinch (or ⌘ / ctrl + scroll) zooms around the pointer, from the whole song down to two bars; a sideways
  swipe pans, and so does dragging the gray once zoomed in. Two small buttons appear on a waveform under the pointer,
  *loop* (the loop with two bars either side) and *whole song*; a switch in the top bar does the same for every
  track. Bar lines show once they are 5 px apart, bar numbers once they are 34 px apart. A new part keeps the track's
  zoom and centres on its loop.
- A white line shows where the loop is playing.
- **The sound follows when you let go.** Nothing is asked of the server during a drag. On release the new bars are
  rendered as a new part is today; the old loop keeps sounding until the new one is in and then joins at the right
  place in the bar. If that takes longer than about 150 ms the loop's edges say the sound is catching up.
- A waveform is as tall as a slot's is today (58 px).

**3. Pitch.** Two numbers on every track: semitones (−12 to +12) and cents (−50 to +50). Drag up or down (160 px
is the whole range, shift for a quarter of that speed), arrow keys when focused, double-click for 0. The sound
follows on release. They add to the shift to the key. Drums and Tops are still never shifted to the key, but they
take your own semitones and cents (today a drum part can't be pitched at all). A one-shot's are playback speed.

**4. Effects.** A slim row under every track's waveform holds its effects, as numbers you drag, each with its label
inside it. Every track's settings are in view at once; there is nothing to select or open.
- Each effect's name has a dot beside it: lit when the effect is on, a click switches it (the settings are kept).
  An effect that is off, or all of them with FX off, is dimmed.
- **EQ:** lo, mid and hi, the three bands there are today (200 Hz, 1 kHz, 5 kHz), −12 to +12 dB.
- **Delay:** time (1/4, 1/8, 3/16, 1/16), feedback (0 to 90%, starting at the 35% it is fixed at today), amount.
- **Reverb:** how much of the track goes to the mixer's one reverb. The reverb's type and decay stay in the top bar,
  as they belong to every track.
- **Harmonics:** an amount from 0 to 100%, where there is a switch today. At 0 there are none; at 100% they are as
  strong as the switch makes them now, and they come in evenly in between. As they come in, the track is turned down
  to match, so turning them up changes the tone and not how loud the track is: its level, measured, stays where it
  was at 0. For a pure sub-bass it still sets itself, to 100%.
- **Duck**, on the tracks that duck: Bass under the drums' low end (today's), Tops and Other under the vocals (6).
  An amount, 0 to 12 dB, and its switch.
- Every number drags as the pitch numbers do (3), and its sound follows as you drag: these are live settings, not a
  new render.
- The **FX** switch in the top bar still turns EQ, delay, reverb and harmonics off at once (and with harmonics, the
  turning-down that goes with them); the ducks are not effects.
- A one-shot track's row has EQ, delay and reverb, and its **trim** (the small waveform it has in its controls
  today).

**5. Tops.**
- Tops are the hi-hat, ride and crash that the drum-separation model finds in a song's drums stem. It is the model
  `percussion.py` already uses to label drum hits (MDX23C DrumSep, through `audio-separator`); it downloads itself
  the first time it is used.
- Each prepared song gains one file, `tops.flac`, beside its other stems. **Drums are the drums stem minus Tops**:
  taken away when a part is rendered, so the kick, the snare and every other piece of percussion stay in Drums, and
  the two always add back up to the stem. Drums-without-tops is not stored.
- **How loud.** Every part is brought to one loudness today, each by itself. Drums and Tops are not: both get the
  gain the whole kit would get for those bars. So hats sit against a kick as they did in their own song, a Tops part
  is as quiet as hats are, and Drums and Tops of one song at the same volume add back up to the kit as it is
  rendered today (exactly at the song's own tempo, very nearly once stretched). A new Tops track starts at the
  volume a Drums track does.
- A song that has no `tops.flac` yet plays its whole drums stem and offers no Tops.
- `digitalcrate stems` makes Tops for new songs as part of preparing them, and first tops up the songs prepared
  before (a line of progress each, pausable like the rest). Before running it over the library, time one song and
  say how long the whole pass will take: this has not been measured. It adds about 15 to 20 MB a song.
- A song's meta gains Tops' activity per bar, its level and its sound embedding, and its Drums' activity and level
  are worked out again without the tops. Tops that are all but silent in a song are not offered, by the rule that
  drops silent stems today.
- In the mixer Tops is a role like any other: it follows the tempo within the limits drums do, is never shifted to
  the key, is scored as drums are, and has its own colour. A new mixer starts with five tracks: Drums, Tops, Bass,
  Vocals, Other. 🎲 all deals Tops straight after Drums. The song list gets a Tops button.
- Songs that give only their vocals (the source policy) give no Tops.
- The bass still ducks under Drums alone.

**6. The vocal duck.** The louder the vocals, the more Tops and Other drop. Tops drop across the whole range.
Other drops in six bands, each according to how loud the voice is there.
- Other keeps its lows and its top. The whole-track dip reaches hats above the voice.
- Every Vocals track, after its volume, feeds one more bus (so a muted vocal ducks nothing). Its level, smoothed,
  turns Tops and Other down by up to the amount set on each: 3 dB to begin with, on.
- It sits in the row of effects of Tops and Other as **Duck**, like the bass's own, and is built the same way.
- One-shots neither duck nor are ducked.
- Measure it in the browser as the bass's duck was: with a vocal at the loudness the server gives every part, Tops
  under it should drop by close to the amount and be back between phrases.

**7. Snapshots keep up.** A snapshot already stores a slot whole, so it keeps the new settings. What has to follow:
- the "has changed since" marks on the strip and on save count cents, the delay's feedback and the new ducks;
- "the same audio" (what lets a layer play on from one snapshot to the next) counts cents;
- the play-strip view renders parts with cents and with the Drums / Tops split, glides the delay's feedback and the
  harmonics for a layer that stays, and ducks under the vocals. Its look does not change.

**8. What is stored, and what was saved before.** A slot gains cents and the delay's feedback;
Tops and Other gain a duck entry; the saved state gains a version.

A Drums part from before had its tops in it. It keeps them, on a track of their own:
- When a mixer, a saved combination or a snapshot from before is opened, every Drums part in it is split: a Tops
  track appears directly under its Drums track, holding the same song, bars, half- or double-time and pitch, with the
  Drums track's volume, mute, lock, EQ, delay and reverb. The two together sound as the part did (5, "how loud").
- That Tops track is the same track in the mixer and in every snapshot of the state (its id comes from its Drums
  track's), so the strip's rows still line up. The eight-track limit does not stop it.
- If the song's tops are not made yet, the part plays whole, as any such song's drums do, and is split once they are.
- In a state from before, the vocal duck is off on Other and on the Tops tracks the split made.
- In a state from before, a track with harmonics on has them at 100%, and its volume is raised by what the
  turning-down now takes off, once its part has loaded.
- Opening and splitting is not a change: nothing is marked unsaved or "changed since" because of it.

So an old combination or snapshot sounds as it did.

**9. The server.**
- `api/stems/peaks` (track, stem): a picture of the whole stem, at least 400 points a second, a byte each, made the
  first time it is asked for (about a tenth of a second) and kept beside the stem. About 120 KB for five minutes.
  The browser keeps it for the session. Drums' picture is of Drums without their tops.
- Rendering takes fractions of a semitone, renders Tops, and renders Drums with their tops taken away whenever the
  song has them. Parts rendered before are not reused for Drums.
- The library call lists Tops among a song's stems.

## Approaches considered

- **Getting the song to the browser.** (a) A picture of the whole song and audio for the loop only, rendered on
  demand: chosen. Measured: a five-minute stem is 14 MB on disk and 110 MB once decoded; its picture is 63 KB at 200
  points a second; a 4-bar loop renders in 0.04 s. (b) The whole stem stretched once to the tempo and key and held
  in the browser: 110 MB a track, about 3 s a track on every tempo or key change, and bars would need warping one by
  one to stay on the grid. (c) The raw stem in the browser, stretched live by Signalsmith's browser build: everything
  instant, but a new playback engine, the same memory, and four live stretchers to keep in step. The view is the same
  for all three, so (c) can replace the audio underneath later.
- **Rendering the neighbouring loops ahead of time** was part of (a) as first described. At 0.04 s a loop it would
  save almost nothing, so it is left out. (The dice's next part is still fetched ahead, as on main: that saves a
  pick as well as a render.)
- **A track's layout.** One waveform you zoom: chosen. The alternative was a thin strip of the whole song with a
  close-up of the loop under it: no zooming needed, but twice the pictures and a taller track.
- **Where the effects go.** A row of numbers you drag under every track: chosen, because every track's settings
  stay in view and nothing has to be selected. The alternatives were the same row with a small drawn EQ, and one
  rack at the bottom for a selected track, with a large drawn EQ and knobs.
- **Making Tops.** From the drum-separation model, on the stems already separated: chosen. Filtering the drums stem
  above about 3 kHz needs no model and no new files, but it splits by frequency, not by instrument: the snare's
  crack would go to Tops and the snare left in Drums would be dull.
- **Drums saved before Tops existed.** Split onto a Tops track of their own when opened: chosen. Letting them lose
  their hats was simpler but changes saved work. Marking them as whole kits that keep their hats until replaced
  would have to follow a part through every loop edit, take, history step and snapshot.

## Order to build

1. The tracks, the loop, pitch and the row of effects (with everything that exists today in it).
2. Tops.
3. The vocal duck.

Each leaves Mashup working. The work starts from `main`.

## Tests

- With five tracks: no sideways scrolling at 1512 or at 1280 wide, every track's header and row of effects are
  inside the window's width, and a track is no taller than a slot is today. Checked by where things are, not by
  clicking them.
- Dragging an edge snaps and changes the part; a click on the gray moves it; a half-time part snaps to every second
  line.
- A pitch drag asks for a render with the fraction; a drum part takes it.
- An EQ number changes its band's gain; the delay's feedback reaches the delay.
- Drums and Tops of one song, same bars and volume, add up to the kit as it is rendered today: exactly at the song's
  own tempo, within a small tolerance when stretched.
- The vocal duck, measured.
- A state saved before opens with a Tops track under its Drums, same song and bars; the pair adds up to the old
  part; its Other is not ducked; nothing is marked as changed; its snapshots are split the same way and their rows
  still line up in the play-strip view.
- Harmonics: at 100% the overtones are as strong as the switch made them; at every position the track's
  level is within a decibel of its level at 0.

## Limits

- You hear only the loop. To hear another place in the song, move the loop there.
- Loops of different lengths come round at different times: three bars against four line up every twelve.
- Tops are as good as the model. Some snare can bleed into them, and whatever it doesn't call a hat or a cymbal
  stays in Drums.
- A Drums waveform drawn before a song's Tops were made stays until the page is reloaded.
- Zoomed all the way out on a long song, a one-bar loop is a few pixels wide.
- The vocal duck follows how loud the vocal is, breaths and held notes included.
- In the offline browser test at 0.08 RMS, Tops drops 3.0 dB or 12.0 dB at those settings, and at 12 dB Other drops about 8 dB near 250 and 500 Hz and less than 1.5 dB at 60 Hz, 4 kHz and 8 kHz. Both recover between phrases.

## Left for later

Loop lengths off the bar lines; hearing the whole song (approach (c)); the play-strip view in this look; a drawn EQ
with a frequency for each band; one-shots in the play-strip view; a duck's attack and release.

## Left to the builder

What the stored fields and the CSS are called; the picture file's format; the drawn icons; whether ⋯ is a menu or a
row that opens under the header; how a loop says the sound is catching up; the duck's constants (measure them); how
the turning-down that goes with harmonics is worked out for a part; how far the top bar's own buttons are redrawn to
match (the die on "all" at least).

## The mockup

`.superpowers/brainstorm/31859-1795616386/content/effects.html` on the machine this was designed on (not in the
repository), option 1, "strip of numbers". It was made before `main` moved: it has no snapshot strip, a shorter top
bar, no ↶ ↷, taller waveforms, a decay on each track's reverb, no delay feedback and no harmonics. Where it and this
page differ, this page is right.
