# Plan: Mashup to Ableton Live

Status: step 1 (the Arrangement export, dry) built. Steps 2 and 3 next. Recreating the effects with Live's devices
(step 4) is planned here, not built.

## How a mashup maps onto a Live set

| Mashup | Live |
| --- | --- |
| a slot | a track |
| the strip of snapshots, in order | sections of the Arrangement, with a locator at each (A, B, C…) |
| a snapshot | also a scene in Session View (step 2) |
| a part (n bars of a stem) | an audio clip of exactly n bars at the set's tempo, looping for its section |
| a one-shot slot | step 1: its pattern as a looping audio clip · step 3: a Simpler on a MIDI track, the hits as a MIDI clip |
| tempo · volume · mute | the set's tempo · track faders (a snapshot's own level as clip gain) · no clip where a slot is muted |

Parts are already rendered to the tempo and key, so a clip needs no warping to be in time; it is marked warped 1:1
so it still follows if you change the tempo in Live.

## Steps

1. **Arrangement, dry (built).** One audio track per slot, the snapshots laid end to end (8 bars each by default)
   with locators; a mashup without snapshots is one section. Dry: no EQ, delay, reverb, harmonics or duck.
2. **Session scenes.** Each snapshot a scene, each part a clip in its track's slot, so snapshots can be launched.
3. **One-shots as Simpler + MIDI**, so hits stay editable in Live (the Simpler preset and MIDI writers exist).
4. **The effects, with Live's devices** (below).

## Step 4: recreating the effects in Live

The mixer's effects are simple and fully specified, so each has a close counterpart. Device XML would be taken from
the installed Live's own default presets and edited (as the Simpler and Drum Rack writers do), never stored here, so
it matches your Live version.

| Mashup effect | What it is | In Live | How close | Work |
| --- | --- | --- | --- | --- |
| **EQ** | low shelf 200 Hz, bell 1 kHz (Q 0.8), high shelf 5 kHz, ±12 dB | **EQ Eight** on the track: band 1 low shelf 200 Hz, band 4 bell 1 kHz Q 0.8, band 8 high shelf 5 kHz, the same gains; device off when the slot's EQ is off | very close (same filter types; slopes differ slightly near the corner) | medium |
| **Delay** | a send after the fader into a delay of one note value, 35% feedback, 4.5 kHz low-pass in the loop | a **return track per note value used** (at most four) with **Delay**: sync on, that note value, feedback 35%, filter on (low-pass about 4.5 kHz), 100% wet; the slot's amount as the track's **send** | close (Live's delay filter is a band-pass with width; set wide) | medium |
| **Reverb** | one shared convolution reverb, impulse response made by DigitalCrate (room / plate / hall + decay), 180 Hz high-pass in, 9 kHz low-pass out | a **return track** with **Hybrid Reverb** in convolution mode loading the *same impulse response*, exported as a WAV next to the set, with EQ Eight before it (high-pass 180 Hz); sends = each slot's reverb amount. Without Suite: **Reverb** with the decay time, pre-delay and damping set to match | identical in principle with Hybrid Reverb (same IR); approximate with Reverb | medium (Hybrid Reverb's reference to a user IR must be checked in Live) |
| **Harmonics** | a copy of the part driven through a soft clipper (tanh, +15.5 dB in), high-passed at 110 Hz, mixed in at −9 dB | a **return track** "Harmonics": **Saturator** (Analog Clip or Soft Sine, drive about +15 dB) then **EQ Eight** high-pass 110 Hz 24 dB/oct, return level −9 dB; the slot's send at 0 dB when on | approximate (Saturator's curves are not exactly tanh) | medium |
| **Duck** | the drums' lows (below 100 Hz) push a low shelf (120 Hz) on the bass down 3 to 12 dB | **Multiband Dynamics** on the bass, low band up to 120 Hz, sidechained from the drums track (its sidechain EQ low-passed at 100 Hz), set for the same depth | approximate (a compressor band, not a keyed shelf) | hard |
| **Blends between snapshots** | per layer: equal-power crossfade, or a filter handoff (one cutoff sweeping 20 Hz to 20 kHz, high-passing the outgoing part and low-passing the incoming at 24 dB/oct) | **automation** in the Arrangement over the transition's bars: track volume for a crossfade; an **Auto Filter** pair (24 dB) with the cutoff automated for a handoff | close | hard (automation envelopes) |

**Order within step 4:** returns and sends (delay, reverb, harmonics) first: they are the most audible and share
one mechanism (a return with devices, a send per track). Then EQ Eight per track. Then the duck. Blend automation
last.

**How we'd know it matches:** Live can't be driven from here, so each effect would be checked two ways. A printed
reference of the mashup "as heard" in the browser (rendered offline through the same chain) goes into the set on a
muted track, level-matched, to A/B by ear. And for the linear effects (EQ, reverb with the shared IR), the browser's
output for a test signal can be compared with a bounce from Live that you make once.

**Risks:** device XML differs between Live versions (hence taking it from the installed Live); Hybrid Reverb needs
Suite; a send's dB scale is not the mixer's linear amount (mapped as 20·log10 of the amount).

## Not exported

Ratings, the recommendations, slot history and locks stay in DigitalCrate. The snapshot strip's transition settings
come with step 4's blend automation.
