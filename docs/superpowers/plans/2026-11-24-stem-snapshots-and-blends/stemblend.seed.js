// ---------- 📸 stem blends: the stem mixer's low-end duck, its snapshots, and the view that plays two of them side by
// side (docs/plans/blend.md). This block comes before the stem mixer's own: that one builds its chains with
// BLEND.mkChain, sets them with BLEND.applyChain, and hands over its own functions with BLEND.init(hooks) before the
// tab is first drawn.
(function () {
  const BL = {};
  BL.MAX_SNAPS = 8;
  BL.BARS = [2, 4, 8, 16];                                                     // a transition's length
  BL.WINS = { all: [0, 1], first: [0, 0.5], second: [0.5, 1], cut: [0.5, 0.5] };  // when in it a layer changes
  BL.STYLES = ['filter', 'xfade'];
  BL.DUCK = { fc: 120, keyLp: 100, smooth: 20, scale: 13, db: 3, max: 12 };
  BL.Q = -3.0103;      // Web Audio's lowpass / highpass Q is in dB: this is Butterworth (no resonance)
  BL.STAGES = 2;       // biquads per filter: 2 = 24 dB / octave
  BL.EDGE = 0.05;      // the share of a filter handoff, at each end, over which the part's gain opens or closes
  BL.clamp01 = x => Math.max(0, Math.min(1, x));

  // ---------------------------------------------------------------- the maths

  // where a layer is (0 = the left snapshot's part, 1 = the right one's) when the master is at m
  BL.layerPos = (m, win) => {
    const [a, b] = BL.WINS[win] || BL.WINS.all;
    return a === b ? (m >= a ? 1 : 0) : BL.clamp01((m - a) / (b - a));
  };

  // a layer at position p: the gains of its outgoing (a) and incoming (b) part, the outgoing part's highpass and
  // the incoming part's lowpass, in Hz. 0 and nyq park a filter: at those cutoffs a biquad passes everything.
  BL.blendAt = (style, p, nyq) => {
    if (p <= 0) return { ga: 1, gb: 0, hp: 0, lp: nyq };
    if (p >= 1) return { ga: 0, gb: 1, hp: 0, lp: nyq };
    if (style === 'xfade') return { ga: Math.cos(p * Math.PI / 2), gb: Math.sin(p * Math.PI / 2), hp: 0, lp: nyq };
    const fc = 20 * Math.pow(1000, p);
    return { ga: Math.min(1, (1 - p) / BL.EDGE), gb: Math.min(1, p / BL.EDGE), hp: fc, lp: fc };
  };

  // ---------------------------------------------------------------- the audio graph

  // a short ramp: unlike setTargetAtTime it ends, so a filter goes back to cheap processing afterwards
  BL.ramp = (param, v, t) => {
    param.cancelScheduledValues(t);
    param.setValueAtTime(param.value, t);
    param.linearRampToValueAtTime(v, t + 0.03);
  };

  // one side of a blend: highpass -> lowpass -> gain
  BL.mkXf = ctx => {
    const mk = (type, f0) => Array.from({ length: BL.STAGES }, () => {
      const f = ctx.createBiquadFilter(); f.type = type; f.frequency.value = f0; f.Q.value = BL.Q; return f;
    });
    const h = mk('highpass', 0), l = mk('lowpass', ctx.sampleRate / 2), g = ctx.createGain(), all = [...h, ...l, g];
    all.forEach((n, i) => { if (i) all[i - 1].connect(n); });
    return { in: all[0], out: g, h, l, g };
  };
  BL.setXf = (x, o, t) => {   // o: {gain, hp, lp}
    x.g.gain.setTargetAtTime(o.gain, t, 0.02);
    x.h.forEach(f => BL.ramp(f.frequency, o.hp, t));
    x.l.forEach(f => BL.ramp(f.frequency, o.lp, t));
  };

  // the duck: every drum slot feeds bus.in; bus.env is how loud their low end is right now, 0..1
  BL.duckBus = ctx => {
    const kin = ctx.createGain(), klp = ctx.createBiquadFilter(), rect = ctx.createWaveShaper(),
      ksm = ctx.createBiquadFilter(), ksc = ctx.createGain(), lim = ctx.createWaveShaper();
    klp.type = 'lowpass'; klp.frequency.value = BL.DUCK.keyLp; klp.Q.value = BL.Q;
    ksm.type = 'lowpass'; ksm.frequency.value = BL.DUCK.smooth; ksm.Q.value = -6.0206;   // critically damped: no overshoot
    rect.curve = new Float32Array([1, 0, 1]);   // |x|
    lim.curve = new Float32Array([0, 0, 1]);    // 0..1, and never above 1
    ksc.gain.value = BL.DUCK.scale;
    kin.connect(klp); klp.connect(rect); rect.connect(ksm); ksm.connect(ksc); ksc.connect(lim);
    return { in: kin, env: lim };
  };

  // the mixer's output and the duck bus, made once (MX.master, MX.bus)
  BL.out = (MX, ctx) => {
    if (!MX.master) {
      MX.master = ctx.createGain(); MX.master.gain.value = 0.9; MX.master.connect(ctx.destination);
      MX.bus = BL.duckBus(ctx);
    }
    return MX;
  };

  // a slot's chain: low shelf -> mid -> high shelf -> duck shelf -> volume -> out, a delay send, and a tap to the bus
  BL.mkChain = (ctx, out, bus) => {
    const lo = ctx.createBiquadFilter(), mid = ctx.createBiquadFilter(), hi = ctx.createBiquadFilter(),
      duck = ctx.createBiquadFilter(), dk = ctx.createGain(), vol = ctx.createGain(), key = ctx.createGain(),
      send = ctx.createGain(), dl = ctx.createDelay(2), fb = ctx.createGain(), lp = ctx.createBiquadFilter();
    lo.type = 'lowshelf'; lo.frequency.value = 200; mid.type = 'peaking'; mid.frequency.value = 1000; mid.Q.value = 0.8;
    hi.type = 'highshelf'; hi.frequency.value = 5000; lp.type = 'lowpass'; lp.frequency.value = 4500; fb.gain.value = 0.35;
    duck.type = 'lowshelf'; duck.frequency.value = BL.DUCK.fc; duck.gain.value = 0; dk.gain.value = 0; key.gain.value = 0;
    lo.connect(mid); mid.connect(hi); hi.connect(duck); duck.connect(vol); vol.connect(out);
    vol.connect(send); send.connect(dl); dl.connect(lp); lp.connect(fb); fb.connect(dl); lp.connect(out);
    vol.connect(key); key.connect(bus.in); bus.env.connect(dk);
    // drop(): take a chain that is no longer used out of the graph (the delay's feedback loop would keep it alive)
    const drop = () => { bus.env.disconnect(dk); [lo, mid, hi, duck, dk, vol, key, send, dl, fb, lp].forEach(n => n.disconnect()); };
    return { in: lo, lo, mid, hi, duck, dk, key, vol, send, dl, ducked: false, drop };
  };

  // s: {gain (linear), eq: [lo, mid, hi] dB, send, delay (s), key (feeds the bus), duck (dB taken off the lows, 0 = off)}
  BL.applyChain = (c, s, t) => {
    const T = 0.02;
    c.vol.gain.setTargetAtTime(s.gain, t, T);
    c.lo.gain.setTargetAtTime(s.eq[0], t, T); c.mid.gain.setTargetAtTime(s.eq[1], t, T); c.hi.gain.setTargetAtTime(s.eq[2], t, T);
    c.send.gain.setTargetAtTime(s.send, t, T); c.dl.delayTime.setTargetAtTime(Math.min(1.9, s.delay), t, T);
    c.key.gain.setTargetAtTime(s.key ? 1 : 0, t, T);
    c.dk.gain.setTargetAtTime(-s.duck, t, T);
    const want = s.duck > 0;
    if (want !== c.ducked) { if (want) c.dk.connect(c.duck.gain); else c.dk.disconnect(c.duck.gain); c.ducked = want; }
  };

  // a part's mix settings as applyChain takes them. stem: what its slot plays.
  // o: {on (audible: not muted, not soloed out), fx, bar (seconds), DT (note value -> share of a bar), duck: {on, db} | undefined}
  BL.duckDb = d => d && d.db != null ? Math.max(0, Math.min(BL.DUCK.max, +d.db)) : BL.DUCK.db;
  BL.mixOf = (p, stem, o) => ({
    gain: o.on ? Math.pow(10, (p.db || 0) / 20) : 0,
    eq: o.fx && p.eqOn !== false ? (p.eq || [0, 0, 0]) : [0, 0, 0],
    send: o.fx && p.dlyOn !== false ? (p.dly || 0) : 0,
    delay: o.bar * (o.DT[p.dt || '1/8'] || 1 / 8),
    key: stem === 'drums',
    duck: stem === 'bass' && !(o.duck && o.duck.on === false) ? BL.duckDb(o.duck) : 0,
  });

  // ---------------------------------------------------------------- saved state

  // trans[i] sits between snaps[i] and snaps[i + 1]: keep one per neighbouring pair, each well-formed
  BL.fixTrans = MX => {
    const n = Math.max(0, MX.snaps.length - 1);
    MX.trans = Array.from({ length: n }, (_, i) => {
      const t = MX.trans[i] || {};
      return { bars: BL.BARS.includes(t.bars) ? t.bars : 8, layers: t.layers && typeof t.layers === 'object' ? t.layers : {} };
    });
  };
  // saved state -> MX: the duck settings, the snapshots and their transitions (older saves have none of them)
  BL.adopt = (MX, sv) => {
    sv = sv || {};
    MX.duck = sv.duck && typeof sv.duck === 'object' ? sv.duck : {};
    MX.snaps = Array.isArray(sv.snaps) ? sv.snaps.slice(0, BL.MAX_SNAPS) : [];
    MX.trans = Array.isArray(sv.trans) ? sv.trans : [];
    BL.fixTrans(MX);
    MX.snapSel = null;
  };

  // ---------------------------------------------------------------- the mixer's side: the duck control

  let H = null;   // the mixer's own functions (studio.js): {MX, STEMS, ICON, PITCHED, DT, role, state, save, draw, sync, play, apply, ev, barLenM}
  BL.duckOf = id => H.MX.duck[id] || (H.MX.duck[id] = { on: true, db: BL.DUCK.db });
  BL.duckHTML = (id, stem) => {
    if (!H || stem !== 'bass') return '';
    const d = H.MX.duck[id] || {}, on = d.on !== false;
    return `<span class="mxeq${on ? '' : ' mxoff'}" title="duck: the drums' low end pushes this part's low end down a little, so kick and bass don't pile up · the slider is how many dB at most"><button class="tbtn mxtg${on ? ' on' : ''}" data-mxduckon="${id}" title="duck on / off (your setting is kept)">DUCK</button><label>lows<input type="range" min="0" max="${BL.DUCK.max}" step="0.5" value="${BL.duckDb(d)}" data-mxduck="${id}"></label></span>`;
  };

  // Task 3 replaces these two: the snapshot strip above the slots, and the playback view
  BL.stripHTML = () => '';
  BL.pbDraw = () => false;

  BL.init = hooks => {
    H = BL.H = hooks;
    if (!H.MX.duck || !H.MX.snaps) BL.adopt(H.MX, {});
    const L = $('list');
    L.addEventListener('click', e => {
      if (st.tab !== 'M') return;
      const t = e.target.closest('button'); if (!t) return;
      const ds = t.dataset;
      if (ds.mxduckon) { const d = BL.duckOf(ds.mxduckon); d.on = d.on === false; H.apply(ds.mxduckon); H.save(); H.draw(); }
    });
    L.addEventListener('input', e => {
      if (st.tab !== 'M') return;
      const ds = e.target.dataset || {};
      if (ds.mxduck) { BL.duckOf(ds.mxduck).db = +e.target.value; H.apply(ds.mxduck); }
    });
  };

  window.BLEND = BL;
})();
// ---------- end of stem blends
