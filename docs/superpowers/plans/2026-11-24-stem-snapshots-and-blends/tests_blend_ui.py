# The browser tests of the stem mixer's duck, snapshots and blends. Each task of the plan appends its own section to
# the end of tests/test_ui.py, in order. Sections are delimited by "# === Task N" lines; copy them whole.

# === Task 2: append to tests/test_ui.py ===


# ---------------------------------------------------------------------------------------------------- stem blends
def _mixer(site, page, bpm=100):
    """🎛 Stems on the three prepared test songs, with a part dealt into each of the four slots and playing."""
    r = subprocess.run([sys.executable, "-c", STEM_SONGS], env=site["env"], capture_output=True, text=True)
    assert "STEMS OK" in r.stdout, r.stderr[-2000:]
    page.click("#tabM")
    page.wait_for_selector("#mxall")
    page.fill("#mxbpm", str(bpm))
    page.dispatch_event("#mxbpm", "change")
    page.click("#mxall")
    page.wait_for_function("CRATE.MX.on&&['drums','bass','vocals','other'].every(s=>CRATE.MX.slots[s]&&CRATE.MX.slots[s].buf)", timeout=90000)


def _set(page, sel, value, events=("input",)):
    """Set a slider or a number field the way a hand does: the value, then the events the app listens for."""
    page.evaluate("([sel,v,evs])=>{const e=document.querySelector(sel);e.value=v;evs.forEach(n=>e.dispatchEvent(new Event(n,{bubbles:true})))}",
                  [sel, str(value), list(events)])


BLEND_AUDIO = r"""async () => {
  const BL = window.BLEND, SR = 44100, N = 4 * SR, out = {};
  const db = x => 20 * Math.log10(Math.max(x, 1e-12));
  const rms = (d, a, b) => { let s = 0; for (let i = a; i < b; i++) s += d[i] * d[i]; return Math.sqrt(s / (b - a)); };
  const play = (ctx, buf) => { const s = ctx.createBufferSource(); s.buffer = buf; s.start(0); return s; };
  const noise = (ctx, secs, seed) => { const b = ctx.createBuffer(1, secs * SR, SR), d = b.getChannelData(0); let s = seed;
    for (let i = 0; i < d.length; i++) { s = (s * 16807) % 2147483647; d[i] = (s / 2147483647) * 2 - 1; } return b; };
  // the level of one band of a signal: three bandpasses in a row, rendered offline
  const band = async (data, f0, q) => { const c = new OfflineAudioContext(1, data.length, SR), b = c.createBuffer(1, data.length, SR);
    b.copyToChannel(data, 0); let n = play(c, b);
    for (let i = 0; i < 3; i++) { const f = c.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = f0; f.Q.value = q; n.connect(f); n = f; }
    n.connect(c.destination); return (await c.startRendering()).getChannelData(0); };

  // 1. a parked blend filter passes everything, to the sample
  { const c = new OfflineAudioContext(1, SR, SR), nb = noise(c, 1, 7), x = BL.mkXf(c); play(c, nb).connect(x.in); x.out.connect(c.destination);
    const y = (await c.startRendering()).getChannelData(0), d = nb.getChannelData(0); let mx = 0;
    for (let i = 0; i < d.length; i++) mx = Math.max(mx, Math.abs(y[i] - d[i])); out.parked_max_diff = mx; }

  // 2. halfway through a filter handoff (cutoff 632 Hz): what is left of each side two octaves the wrong way, in dB
  out.handoff = {};
  for (const side of ['a', 'b']) { const c = new OfflineAudioContext(1, 2 * SR, SR), nb = noise(c, 2, side === 'a' ? 11 : 13), x = BL.mkXf(c), o = BL.blendAt('filter', 0.5, SR / 2);
    BL.setXf(x, side === 'a' ? { gain: o.ga, hp: o.hp, lp: SR / 2 } : { gain: o.gb, hp: 0, lp: o.lp }, 0);
    play(c, nb).connect(x.in); x.out.connect(c.destination); const y = (await c.startRendering()).getChannelData(0), d = nb.getChannelData(0);
    for (const f of [158, 2528]) out.handoff[side + '_' + f] = db(rms(await band(y, f, 4), SR, 2 * SR)) - db(rms(await band(d, f, 4), SR, 2 * SR)); }

  // 3. the duck: a kick on every beat at 120 bpm, at the loudness the server gives every part (RMS 0.08), over a bass of 55 Hz + 440 Hz
  const kick = ctx => { const b = ctx.createBuffer(1, N, SR), d = b.getChannelData(0);
    for (let beat = 0; beat < 8; beat++) { let ph = 0; const i0 = Math.round(beat * 0.5 * SR);
      for (let i = 0; i < 0.4 * SR; i++) { const t = i / SR; ph += 2 * Math.PI * (50 + 100 * Math.exp(-t / 0.03)) / SR; d[i0 + i] += Math.sin(ph) * Math.exp(-t / 0.12); } }
    const g = Math.min(0.08 / rms(d, 0, N), 0.9 / d.reduce((m, v) => Math.max(m, Math.abs(v)), 0)); for (let i = 0; i < N; i++) d[i] *= g; return b; };
  const bass = ctx => { const b = ctx.createBuffer(1, N, SR), d = b.getChannelData(0);
    for (let i = 0; i < N; i++) d[i] = 0.2 * Math.sin(2 * Math.PI * 55 * i / SR) + 0.1 * Math.sin(2 * Math.PI * 440 * i / SR); return b; };
  const O = { fx: true, bar: 2, DT: { '1/8': 1 / 8 } };
  const run = async (duck, drumsOn) => { const c = new OfflineAudioContext(2, N, SR), merge = c.createChannelMerger(2); merge.connect(c.destination);
    const MX = {}; BL.out(MX, c); MX.master.disconnect();                       // the bus without the speakers: each chain to its own channel
    const outB = c.createGain(), outK = c.createGain(); outB.connect(merge, 0, 0); outK.connect(merge, 0, 1);
    const cb = BL.mkChain(c, outB, MX.bus), ck = BL.mkChain(c, outK, MX.bus);
    BL.applyChain(cb, BL.mixOf({ db: 0 }, 'bass', { ...O, on: true, duck }), 0);
    BL.applyChain(ck, BL.mixOf({ db: 0 }, 'drums', { ...O, on: drumsOn }), 0);
    play(c, bass(c)).connect(cb.in); play(c, kick(c)).connect(ck.in); return (await c.startRendering()).getChannelData(0); };
  const ref = await run({ on: false }, true), lo0 = await band(ref, 55, 3), hi0 = await band(ref, 440, 6);
  const dip = async (duck, drumsOn) => { const y = await run(duck, drumsOn), lo = await band(y, 55, 3), hi = await band(y, 440, 6), w = Math.round(0.02 * SR), dips = [];
    for (let k = 0; k < 25; k++) { const a = 2 * SR + k * w; dips.push(db(rms(lo, a, a + w)) - db(rms(lo0, a, a + w))); }   // one beat, in 20 ms steps
    return { deepest: Math.min(...dips), shallowest: Math.max(...dips), high: db(rms(hi, 2 * SR, 3 * SR)) - db(rms(hi0, 2 * SR, 3 * SR)) }; };
  out.duck3 = await dip(undefined, true);            // no setting yet: on, 3 dB
  out.duck12 = await dip({ on: true, db: 12 }, true);
  out.muted = await dip({ on: true, db: 12 }, false); // muted drums duck nothing
  out.off = await dip({ on: false, db: 12 }, true);
  return out;
}"""


def test_blend_audio_core(page):
    """The stem blends audio graph, measured offline: a parked blend filter changes nothing, a filter handoff splits the
    spectrum between the two parts, and the duck takes a few dB off the bass's low end only, only under the kick."""
    o = page.evaluate(BLEND_AUDIO)
    assert o["parked_max_diff"] < 1e-6
    h = o["handoff"]
    assert h["a_158"] < -40 and h["b_2528"] < -40            # the outgoing part has no lows left, the incoming one no highs yet
    assert abs(h["a_2528"]) < 0.5 and abs(h["b_158"]) < 0.5  # and each keeps its own side whole
    assert -3.5 < o["duck3"]["deepest"] < -2.0 and o["duck3"]["shallowest"] > -0.5   # down under the kick, back between kicks
    assert abs(o["duck3"]["high"]) < 0.2                     # 440 Hz is left alone
    assert -13.0 < o["duck12"]["deepest"] < -9.0
    assert o["muted"]["deepest"] > -0.1 and o["off"]["deepest"] > -0.1


def test_duck_is_on_for_bass_and_remembered(site, page):
    """DUCK: on by default at 3 dB, on bass rows only; the switch and the amount are kept across a reload."""
    _mixer(site, page)
    assert page.locator("[data-mxduckon]").count() == 1 and page.locator('[data-mxduckon="bass"]').count() == 1
    assert page.input_value('[data-mxduck="bass"]') == "3"
    page.wait_for_function("CRATE.MX.slots.bass._c&&CRATE.MX.slots.bass._c.ducked===true&&CRATE.MX.slots.drums._c.ducked===false")
    _set(page, '[data-mxduck="bass"]', 6, ("input", "change"))
    assert page.evaluate("CRATE.MX.duck.bass.db") == 6
    page.click('[data-mxduckon="bass"]')
    page.wait_for_function("CRATE.MX.slots.bass._c.ducked===false&&CRATE.MX.duck.bass.on===false")
    assert page.evaluate("JSON.parse(localStorage.getItem('dcStems')).duck.bass") == {"on": False, "db": 6}
    page.reload()
    page.wait_for_function("typeof st!=='undefined'&&st.tab==='M'&&CRATE.MX.duck.bass&&CRATE.MX.duck.bass.on===false", timeout=30000)


def test_state_saved_before_blends_still_opens(site, page):
    """A mixer saved before snapshots and the duck existed (no duck, snaps or trans keys) opens with their defaults."""
    r = subprocess.run([sys.executable, "-c", STEM_SONGS], env=site["env"], capture_output=True, text=True)
    assert "STEMS OK" in r.stdout, r.stderr[-2000:]
    page.evaluate("""localStorage.setItem('dcStems',JSON.stringify({bpm:100,key:'',name:'',fx:true,order:['drums','bass','vocals','other'],
      roles:{drums:'drums',bass:'bass',vocals:'vocals',other:'other'},slots:{bass:{stem:'bass',track:901,bar0:0,n:4,k:1,off:0,bars:16,
      artist:'Stem Artist 901',title:'Song',db:-2,mute:false,lock:false,eq:[0,0,0],dly:0,dt:'1/8',eqOn:true,dlyOn:true}}}));localStorage.setItem('dcTab','M')""")
    page.reload()
    page.wait_for_function("typeof st!=='undefined'&&st.tab==='M'&&CRATE.MX.slots.bass&&CRATE.MX.slots.bass.buf", timeout=60000)
    assert page.evaluate("[CRATE.MX.snaps.length,CRATE.MX.trans.length,Object.keys(CRATE.MX.duck).length]") == [0, 0, 0]
    assert page.input_value('[data-mxduck="bass"]') == "3"


# === Task 3: append to tests/test_ui.py ===


def _roll(page, slot, track):
    """Put this prepared song's best-fitting bars into a slot, and wait until they are loaded."""
    page.evaluate(f"CRATE.mxRoll('{slot}', true, {track})")
    page.wait_for_function(f"CRATE.MX.slots['{slot}']&&CRATE.MX.slots['{slot}'].track==={track}&&CRATE.MX.slots['{slot}'].buf&&!CRATE.MX.slots['{slot}']._loading", timeout=60000)


def test_snapshots_capture_recall_replace_delete(site, page):
    """📸 keeps the mixer as it is; a snapshot comes back with a click, can be replaced and deleted, survives a reload,
    freezes an auto key, and teaches the recommendations."""
    _mixer(site, page)
    assert page.evaluate("CRATE.MX.snaps.length") == 0 and page.is_disabled("#snplay")
    _roll(page, "drums", 901)
    page.click("#sncap")
    page.wait_for_function("CRATE.MX.snaps.length===1&&CRATE.MX.snapSel===0")
    assert page.evaluate("CRATE.MX.key") != ""                                   # an auto key is frozen by the first snapshot
    page.wait_for_function("CRATE.MX.rated>=4", timeout=10000)                   # four slots, four weak yeses
    _roll(page, "drums", 902)
    page.click("#sncap")
    page.wait_for_function("CRATE.MX.snaps.length===2&&CRATE.MX.snapSel===1")
    label = page.inner_text('[data-sn="1"]')
    assert "B" in label and "drums" in label and "bass" not in label             # what changed since A
    assert "start" in page.inner_text('[data-sn="0"]')
    assert page.evaluate("CRATE.MX.trans.length") == 1 and page.is_enabled("#snplay")
    page.click('[data-sn="0"]')                                                  # A comes back
    page.wait_for_function("CRATE.MX.snapSel===0&&CRATE.MX.slots.drums.track===901&&CRATE.MX.slots.drums.buf", timeout=60000)
    bass = page.evaluate("CRATE.MX.slots.bass.track")
    _roll(page, "bass", 903 if bass != 903 else 901)
    page.click("#snrep")                                                         # ... and is replaced by what is playing now
    page.wait_for_function(f"CRATE.MX.snaps[0].slots.bass.track!=={bass}")
    assert page.evaluate("CRATE.MX.snaps.length") == 2
    page.reload()
    page.wait_for_function("typeof st!=='undefined'&&st.tab==='M'&&CRATE.MX.snaps.length===2", timeout=30000)
    assert page.evaluate("[CRATE.MX.snaps[0].slots.drums.track,CRATE.MX.snaps[1].slots.drums.track,CRATE.MX.trans.length]") == [901, 902, 1]
    page.click('[data-sn="1"]')
    page.wait_for_function("CRATE.MX.snapSel===1")
    page.click("#sndel")
    page.wait_for_function("CRATE.MX.snaps.length===1&&CRATE.MX.trans.length===0&&CRATE.MX.snapSel===null")
    assert page.is_disabled("#snplay")


# === Task 4: append to tests/test_ui.py ===


def test_blend_model(page):
    """The pure half of the stem blends block: which layers differ between two snapshots, each transition's settings (kept from
    the transition before), where a layer is for a master position, and the mix of a layer that stays."""
    r = page.evaluate("""() => { const B = BLEND, P = (stem, track, o) => Object.assign({stem, track, bar0: 0, n: 4, k: 1, off: 0, db: 0, eq: [0, 0, 0], dly: 0, dt: '1/8'}, o);
      const A = {order: ['drums', 'bass', 'vocals', 'other'], roles: {drums: 'drums', bass: 'bass', vocals: 'vocals', other: 'other'}, duck: {},
                 slots: {drums: P('drums', 1), bass: P('bass', 2, {db: -2}), vocals: P('vocals', 3, {mute: true})}};
      const Z = {order: ['drums', 'bass', 'vocals', 'other', 's1'], roles: {drums: 'drums', bass: 'bass', vocals: 'vocals', other: 'vocals', s1: 'other'}, duck: {},
                 slots: {drums: P('drums', 1, {bar0: 4}), bass: P('bass', 2, {db: -4}), other: P('vocals', 5), s1: P('other', 6)}};
      const rows = B.diffSnaps(A, Z), MX = {snaps: [A, Z, A], trans: [{bars: 4, layers: {drums: {style: 'xfade', win: 'second'}}}, {bars: 16, layers: {}}]};
      const T = B.transFor(MX, 0);
      return {rows: rows.map(x => [x.id, x.stem, x.kind]), back: B.diffSnaps(Z, A).map(x => [x.id, x.kind]), t0: T, t1: B.transFor(MX, 1),
        pos: [B.rowPos(rows[0], 0.75, T, {}), B.rowPos(rows[1], 0.75, T, {}), B.rowPos(rows[0], 0.75, T, {drums: 0.1})],
        mix: B.lerpMix(P('bass', 2, {db: -2, eq: [2, 0, 0], dly: 0.4, dt: '1/4'}), P('bass', 2, {db: -4, eq: [6, 0, 0], eqOn: false, dly: 0, dt: '1/16'}), 0.25),
        lp: [B.layerPos(0.25, 'all'), B.layerPos(0.25, 'first'), B.layerPos(0.25, 'second'), B.layerPos(0.75, 'second'), B.layerPos(0.49, 'cut'), B.layerPos(0.5, 'cut')],
        b: [B.blendAt('filter', 0, 22050), B.blendAt('filter', 0.5, 22050), B.blendAt('xfade', 0.5, 22050), B.blendAt('filter', 1, 22050), B.blendAt('filter', 0.025, 22050)]}; }""")
    # a moved loop is a changed layer; a volume change alone is not; a muted part counts as absent; a slot's stem is the side that sounds
    assert r["rows"] == [["drums", "drums", "change"], ["bass", "bass", "same"], ["vocals", "vocals", "empty"], ["other", "vocals", "enter"], ["s1", "other", "enter"]]
    assert r["back"] == [["drums", "change"], ["bass", "same"], ["vocals", "empty"], ["other", "exit"], ["s1", "exit"]]
    new = {"style": "filter", "win": "all"}
    assert r["t0"] == {"bars": 4, "layers": {"drums": {"style": "xfade", "win": "second"}, "other": new, "s1": new}}
    assert r["t1"] == {"bars": 16, "layers": {"drums": {"style": "xfade", "win": "second"}, "other": new, "s1": new}}   # drums: from the transition before
    assert r["pos"] == [0.5, 0.75, 0.1]
    m = r["mix"]
    assert m["db"] == -2.5 and m["eq"] == [1.5, 0, 0] and abs(m["dly"] - 0.3) < 1e-9 and m["dt"] == "1/4" and m["eqOn"] is True and m["dlyOn"] is True
    assert r["lp"] == [0.25, 0.5, 0, 0.5, 0, 1]
    b = r["b"]
    assert b[0] == {"ga": 1, "gb": 0, "hp": 0, "lp": 22050} and b[3] == {"ga": 0, "gb": 1, "hp": 0, "lp": 22050}
    assert b[1]["ga"] == 1 and b[1]["gb"] == 1 and abs(b[1]["hp"] - 632.4555) < 0.001 and b[1]["lp"] == b[1]["hp"]
    assert abs(b[2]["ga"] - 0.70711) < 1e-4 and abs(b[2]["gb"] - 0.70711) < 1e-4 and b[2]["hp"] == 0 and b[2]["lp"] == 22050
    assert b[4]["ga"] == 1 and abs(b[4]["gb"] - 0.5) < 1e-9


# === Task 5: append to tests/test_ui.py ===


def _strip(site, page, bpm=100, three=False):
    """A strip on the test songs: A (drums from song 901), B (drums from 902, "other" taken out) and, with three=True,
    C (bass from another song)."""
    _mixer(site, page, bpm)
    _roll(page, "drums", 901)
    page.click("#sncap")
    page.wait_for_function("CRATE.MX.snaps.length===1")
    _roll(page, "drums", 902)
    page.click('[data-mxdel="other"]')
    page.wait_for_function("!CRATE.MX.slots.other")
    page.click("#sncap")
    page.wait_for_function("CRATE.MX.snaps.length===2")
    if three:
        bass = page.evaluate("CRATE.MX.slots.bass.track")
        _roll(page, "bass", 903 if bass != 903 else 901)
        page.click("#sncap")
        page.wait_for_function("CRATE.MX.snaps.length===3")


def _voice(page, slot, side):
    """What a playback voice was last told: its gain, highpass and lowpass, and how long its loop is. None if there is none."""
    return page.evaluate(f"(()=>{{const v=CRATE.PB.voice('{slot}','{side}');return v?{{...v.set,dur:v.buf.duration}}:null}})()")


def test_playback_shows_both_sets_and_blends_by_hand(site, page):
    """▶ play strip: both snapshots' four slots side by side, the transition controls between them, and a master and a
    slider per layer that move the sound from the left snapshot to the right one."""
    _strip(site, page)
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing", timeout=90000)
    assert page.evaluate("CRATE.MX.on") is False and page.is_visible("#pb")
    assert page.locator('#pb [data-pbside="a"]').count() == 4 and page.locator('#pb [data-pbside="b"]').count() == 4   # all eight slots
    assert page.evaluate("CRATE.PB.rows.map(r=>[r.id,r.kind])") == [["drums", "change"], ["bass", "same"], ["vocals", "same"], ["other", "exit"]]
    a, b = _voice(page, "drums", "a"), _voice(page, "drums", "b")
    assert a["gain"] == 1 and b["gain"] == 0 and abs(b["dur"] - 9.6) < 0.01                 # 4 bars at 100 bpm, loaded but silent
    assert page.evaluate("CRATE.PB.voice('bass','a')===CRATE.PB.voice('bass','b')")          # a layer that stays is one voice
    assert "same in both" in page.inner_text('[data-pbrow="bass"]')
    # every slot shows its waveform with a play line, as the mixer's rows do
    page.wait_for_function("(()=>{const b=document.querySelector('[data-pbwave=\"b:drums\"]');return b&&b.querySelector('canvas').width>50&&getComputedStyle(b.querySelector('i')).display==='block'})()", timeout=10000)
    _set(page, "#pbm", 50)                                                                   # the master, halfway
    assert page.evaluate("CRATE.PB.m") == 0.5 and page.input_value('[data-pbpos="drums"]') == "50"
    a, b = _voice(page, "drums", "a"), _voice(page, "drums", "b")
    assert a["gain"] == 1 and b["gain"] == 1 and abs(a["hp"] - 632.46) < 0.1 and abs(b["lp"] - 632.46) < 0.1 and b["hp"] == 0
    assert abs(_voice(page, "other", "a")["hp"] - 632.46) < 0.1 and _voice(page, "other", "b") is None   # leaves alone
    page.select_option('[data-pbstyle="drums"]', "xfade")
    a, b = _voice(page, "drums", "a"), _voice(page, "drums", "b")
    assert abs(a["gain"] - 0.7071) < 0.001 and abs(b["gain"] - 0.7071) < 0.001 and a["hp"] == 0
    page.select_option('[data-pbwin="drums"]', "second")                                     # changes over the second half only
    assert page.evaluate("CRATE.PB.pos('drums')") == 0 and _voice(page, "drums", "b")["gain"] == 0
    _set(page, "#pbm", 75)
    assert page.evaluate("CRATE.PB.pos('drums')") == 0.5
    _set(page, '[data-pbpos="other"]', 100, ("input", "change"))                            # one layer by hand
    assert page.evaluate("[CRATE.PB.pos('other'),CRATE.PB.m]") == [1, 0.75]
    assert page.locator('[data-pbrow="other"] .tag.hot').count() == 1 and page.locator('[data-pbwin="other"]').count() == 0
    _set(page, "#pbm", 100)
    assert page.evaluate("CRATE.PB.atEnd(1)") is True and page.is_disabled("#pbnext")        # B is the last snapshot
    assert page.evaluate("JSON.parse(localStorage.getItem('dcStems')).trans[0].layers.drums") == {"style": "xfade", "win": "second"}
    page.click("#pbback")
    page.wait_for_selector("#mxall")
    assert page.evaluate("CRATE.PB.on") is False
    _set(page, "#mxbpm", 120, ("change",))                                                   # the strip plays at the mixer's tempo
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing", timeout=90000)
    assert abs(_voice(page, "drums", "a")["dur"] - 8.0) < 0.01


# === Task 6: append to tests/test_ui.py ===


def test_playback_arrows_walk_the_strip(site, page):
    """Fully on the right snapshot, ▶ moves the view on: B to the left without a gap in its sound, C on the right.
    ◀ goes back. A part whose song is no longer prepared shows as missing and the rest plays on."""
    _strip(site, page, three=True)
    page.evaluate("CRATE.MX.snaps[2].slots.vocals.track=999999")
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing&&CRATE.PB.nextReady", timeout=90000)
    assert page.is_disabled("#pbnext") and page.is_disabled("#pbprev")
    _set(page, "#pbm", 100)
    page.wait_for_function("!document.querySelector('#pbnext').disabled")
    key, t = page.evaluate("[CRATE.PB.voice('drums','b').key,CRATE.PB.voice('drums','b').t]")
    page.click("#pbnext")
    page.wait_for_function("CRATE.PB.i===1&&CRATE.PB.ready", timeout=60000)
    assert page.evaluate("[CRATE.PB.m,[...document.querySelectorAll('#pb .pbletter')].map(e=>e.textContent)]") == [0, ["B", "C"]]
    assert page.evaluate("[CRATE.PB.voice('drums','a').key,CRATE.PB.voice('drums','a').t]") == [key, t]     # B's drums never stopped
    assert "missing" in page.inner_text('[data-pbrow="vocals"] [data-pbside="b"]')
    assert page.evaluate("CRATE.PB.rows.find(r=>r.id==='vocals').kind") == "exit"
    assert page.is_disabled("#pbnext")                                                                    # C is the last one
    page.click("#pbprev")
    page.wait_for_function("CRATE.PB.i===0&&CRATE.PB.ready", timeout=60000)
    assert page.evaluate("CRATE.PB.m") == 1


def test_playback_waits_for_the_next_snapshot(site, page):
    """The arrow stays off until the next snapshot's parts are loaded, however long that takes."""
    _strip(site, page, three=True)
    page.evaluate("""(()=>{const api=CRATE.api,slow=CRATE.MX.snaps[2].slots.bass.track;
      CRATE.api=(p,b)=>p==='api/stems/render'&&b.stem==='bass'&&b.track===slow?new Promise(r=>setTimeout(r,4000)).then(()=>api(p,b)):api(p,b)})()""")
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing", timeout=90000)
    _set(page, "#pbm", 100)
    assert page.evaluate("CRATE.PB.nextReady") is False and page.is_disabled("#pbnext")
    page.wait_for_function("CRATE.PB.nextReady&&!document.querySelector('#pbnext').disabled", timeout=20000)


# === Task 7: append to tests/test_ui.py ===


def test_auto_walks_the_strip_and_hands_back_control(site, page):
    """auto: hold a snapshot, move the master across over the transition's bars, move the view on, and stop on the last
    snapshot. A hand on a slider switches it off where it stands."""
    _strip(site, page, bpm=200, three=True)                  # 200 bpm: a bar lasts 1.2 s
    page.click("#snplay")
    page.wait_for_function("CRATE.PB.on&&CRATE.PB.ready&&CRATE.PB.playing&&CRATE.PB.nextReady", timeout=90000)
    page.select_option("#pbbars", "2")
    page.evaluate("CRATE.PB.setHold(1)")                     # the menu offers 4, 8 and 16 bars: one keeps the test short
    page.click("#pbauto")
    assert page.evaluate("CRATE.PB.auto") is True
    page.wait_for_function("CRATE.PB.i===0&&CRATE.PB.m>0.2&&CRATE.PB.m<1", timeout=15000)   # moving, after the hold
    assert "bar" in page.inner_text("#pbstat")
    page.wait_for_function("CRATE.PB.i===1", timeout=15000)                                # on B: the view moved on by itself
    _set(page, "#pbm", 30)                                                                  # a hand on the master
    assert page.evaluate("[CRATE.PB.auto,CRATE.PB.m]") == [False, 0.3]
    page.click("#pbauto")                                                                   # on again from where it stands
    page.wait_for_function("CRATE.PB.i===1&&CRATE.PB.m===1&&CRATE.PB.auto===false", timeout=30000)   # the last snapshot: it stays
