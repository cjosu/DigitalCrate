# Plan: Stem mixer (recombine drums, bass, vocals and the rest from different songs)

Status: prototype (phase 1) built; phases 2 and 3 planned.

## The idea

Four slots: **drums**, **bass**, **vocals**, **other**. Each pulls a few bars of that stem from a different song.
Everything is stretched to one tempo and shifted to one key, loops in sync, and has its own loop position and
length, pitch, volume, EQ and delay. **🎲** on a slot pulls a new part that fits what's playing; **🎲 all** deals a
whole new combination. The mixer recommends parts, and learns from what you keep, rate and throw away.

## Design

**1. A stem library.** Songs are separated once (`htdemucs_ft`) and kept as four full-length FLAC stems under
`_data/stems/t<track>/`, with what the mixer needs to know about them:
- bar lines (Beat This!), tempo and key, as mining finds them;
- per bar and stem: how active the stem is (so loops start where something plays);
- per bar: the harmony (a 12-note chroma of bass + vocals + other), so two songs can be compared bar by bar;
- per stem: a sound embedding (CLAP), for learning what you like.

Songs come from your favorites' sources plus random mined songs. Reference-only artists are never used; hip-hop
contributes vocals only (the source policy).

**2. Rendering a part.** A part is (song, stem, first bar, bars). The server cuts those bars from the stem and
stretches them to exactly that many bars at the mixer's tempo (Signalsmith; Re-Pitch when nothing needs stretching),
shifted by the slot's semitones. Drums are never pitch-shifted. Parts are cached, so a part renders once (well under
a second for 4 bars).

**3. Playing.** The browser loops each rendered part sample-accurately on one shared bar clock (as the sketchpad
does). A new part comes in at the right place in the bar, not from its start. Per slot, live in the browser: volume,
mute, solo, a 3-band EQ, and a tempo-synced delay.

**4. Harmony.** Matching keys is not enough: a bass line follows its own song's chords.
- *Key:* every pitched slot is shifted by the smallest interval that brings its song's key to the mixer's key
  (relative major and minor count as the same), plus your own offset.
- *Fit:* two parts are compared bar by bar: the cosine of their chromas after transposition, looped to a common
  length. 1.0 means the same notes in every bar. The mixer shows the fit of what's playing.
- *Picking:* a new part for a pitched slot is chosen to fit the pitched parts already playing.
- Phase 2: prefer stretches that sit on one or two chords (the pad finder's test), chord-aware alignment (try
  rotating a part by a bar or two for a better fit), and an option to keep bass and other from one song.

**5. Recommendations that learn.** Every candidate part gets a score:
- how active the stem is in those bars;
- how little it has to be stretched and shifted (drums smear beyond about ±15%; voices beyond about ±3 semitones);
- harmony fit with the pitched parts already playing;
- how close its sound is to parts you liked, minus parts you disliked (CLAP).

🎲 draws from the best-scoring parts with some randomness, so it explores. What teaches it:
- **👍 / 👎** on the whole combination (strong, every slot);
- **re-rolling** a slot within a few seconds (weak "not this");
- **keeping** a part playing for a while, and **locking** it (weak "yes").

The weights start as sensible guesses and are refitted (ridge logistic regression, pulled toward the guesses) once
there are a dozen ratings, then after each new one. The mixer says how many ratings it has learned from.

## Limits

- Separation artifacts show more in an exposed stem than in a mix (see separation grain).
- Tempo changes inside the chosen bars are averaged out (one stretch per part, not one per bar).
- A song with a wrong key or downbeat on file gives parts that clash or start mid-bar; the fit score catches the first.

## Phases

1. **Prototype (built):** library pass for ~100 songs, the four slots with 🎲, lock, loop position and length, pitch,
   volume, mute/solo, EQ, delay, harmony fit, 👍/👎 and the learning score.
2. **Smarter:** static-harmony preference, bar rotation for fit, per-bar warping, grain-aware picking, sections
   (prefer exposed sections for vocals), "more like this slot".
3. **Out of the mixer:** bounce a combination to a sample or the sketchpad; export a Live set with each stem on its
   own track, warped.

## Open questions

- Should a liked combination be saved as a sketch, a sample, or its own kind of thing?
- How much should the mixer explore (new songs) against exploit (songs whose parts you've liked)?
