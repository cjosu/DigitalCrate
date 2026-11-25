"""Cost of a stem mixer + sidechain duck + mastering chain, measured by rendering 60 s offline in headless Chromium."""
import json
from playwright.sync_api import sync_playwright

PAGE = "<!doctype html><title>bench</title>"
JS = r"""
async (variant) => {
  const SR = 48000, SECS = 60;
  const ctx = new OfflineAudioContext(2, SR * SECS, SR);
  const noise = (seed) => { const b = ctx.createBuffer(2, SR * 4, SR); for (let c = 0; c < 2; c++) { const d = b.getChannelData(c); let x = seed + c;
    for (let k = 0; k < d.length; k++) { x = (x * 1664525 + 1013904223) >>> 0; d[k] = ((x / 4294967296) * 2 - 1) * 0.35 * (0.3 + 0.7 * Math.abs(Math.sin(k / SR * Math.PI * 2))); } } return b; };
  const master = ctx.createGain(); master.gain.value = 0.9;
  const stems = [];
  for (let s = 0; s < 4; s++) {
    const src = ctx.createBufferSource(); src.buffer = noise(17 * (s + 1)); src.loop = true; src.start();
    if (variant === 'sources') { src.connect(master); continue; }
    const lo = ctx.createBiquadFilter(), mid = ctx.createBiquadFilter(), hi = ctx.createBiquadFilter(), vol = ctx.createGain(), send = ctx.createGain(),
      dl = ctx.createDelay(2), fb = ctx.createGain(), lp = ctx.createBiquadFilter();
    lo.type = 'lowshelf'; lo.frequency.value = 200; lo.gain.value = 2; mid.type = 'peaking'; mid.gain.value = -2; hi.type = 'highshelf'; hi.frequency.value = 5000; hi.gain.value = 1.5;
    lp.type = 'lowpass'; lp.frequency.value = 4500; fb.gain.value = 0.35; send.gain.value = 0.3; dl.delayTime.value = 0.3;
    src.connect(lo); lo.connect(mid); mid.connect(hi); hi.connect(vol); vol.connect(master); vol.connect(send); send.connect(dl); dl.connect(lp); lp.connect(fb); fb.connect(dl); lp.connect(master);
    stems.push({ vol, lo });
  }
  const duck = variant.includes('duck');
  if (duck) {  // drums' low end -> lowpass 100 -> rectify -> smooth 20 Hz -> x13 -> clamp 0..1 -> x(-amount) -> the bass's low shelf gain
    const key = ctx.createBiquadFilter(); key.type = 'lowpass'; key.frequency.value = 100;
    const abs = ctx.createWaveShaper(); abs.curve = Float32Array.from({ length: 1025 }, (_, k) => Math.abs(k / 512 - 1));
    const sm = ctx.createBiquadFilter(); sm.type = 'lowpass'; sm.frequency.value = 20; const sc = ctx.createGain(); sc.gain.value = 13;
    const clamp = ctx.createWaveShaper(); clamp.curve = Float32Array.from({ length: 1025 }, (_, k) => Math.max(0, k / 512 - 1)); const amt = ctx.createGain(); amt.gain.value = -3;
    const shelf = ctx.createBiquadFilter(); shelf.type = 'lowshelf'; shelf.frequency.value = 120;
    stems[0].vol.connect(key); key.connect(abs); abs.connect(sm); sm.connect(sc); sc.connect(clamp); clamp.connect(amt); amt.connect(shelf.gain);
    stems[1].vol.disconnect(master); stems[1].vol.connect(shelf); shelf.connect(master);
  }
  let out = master;
  if (variant.includes('master')) {
    const hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 30; const top = ctx.createBiquadFilter(); top.type = 'highshelf'; top.frequency.value = 12000; top.gain.value = -1.5;
    const glue = ctx.createDynamicsCompressor(); glue.threshold.value = -18; glue.ratio.value = 2; glue.knee.value = 12; glue.attack.value = 0.03; glue.release.value = 0.25;
    const mk = ctx.createGain(); mk.gain.value = 1.0;
    out.connect(hp); hp.connect(top); top.connect(glue); glue.connect(mk); out = mk;
    if (variant.includes('complim')) { const lim = ctx.createDynamicsCompressor(); lim.threshold.value = -1; lim.ratio.value = 20; lim.knee.value = 0; lim.attack.value = 0.001; lim.release.value = 0.05; out.connect(lim); out = lim; }
    if (variant.includes('clip')) { const ws = ctx.createWaveShaper(); ws.curve = Float32Array.from({ length: 4097 }, (_, k) => Math.tanh((k / 2048 - 1) * 1.5) / Math.tanh(1.5)); ws.oversample = '4x'; out.connect(ws); out = ws; }
    if (variant.includes('worklet')) {
      const code = `class Lim extends AudioWorkletProcessor{constructor(){super();this.L=new Float32Array(256);this.R=new Float32Array(256);this.w=0;this.g=1;this.look=72;this.rel=Math.exp(-1/(0.08*sampleRate));this.c=0.891}
        process(inputs,outputs){const i=inputs[0],o=outputs[0];if(!i.length)return true;const l=i[0],r=i[1]||i[0],ol=o[0],or=o[1]||o[0],L=this.L,R=this.R,look=this.look,rel=this.rel,c=this.c;let w=this.w,g=this.g;
          for(let k=0;k<l.length;k++){const a=l[k],b=r[k],pa=a<0?-a:a,pb=b<0?-b:b,pk=pa>pb?pa:pb,t=pk>c?c/pk:1;g=t<g?t:1-(1-g)*rel;const rd=(w-look)&255;ol[k]=L[rd]*g;or[k]=R[rd]*g;L[w]=a;R[w]=b;w=(w+1)&255}
          this.w=w;this.g=g;return true}}registerProcessor('lim',Lim)`;
      await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([code], { type: 'application/javascript' })));
      const lim = new AudioWorkletNode(ctx, 'lim', { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [2] }); out.connect(lim); out = lim;
    }
  }
  out.connect(ctx.destination);
  const t0 = performance.now(); const buf = await ctx.startRendering(); const ms = performance.now() - t0;
  let pk = 0; const d = buf.getChannelData(0); for (let k = 0; k < d.length; k += 7) pk = Math.max(pk, Math.abs(d[k]));
  return { ms, peak: pk };
}
"""
VARIANTS = ["sources", "mixer", "mixer+duck", "mixer+duck+master+complim", "mixer+duck+master+complim+clip", "mixer+duck+master+worklet"]

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.route("https://bench.test/", lambda r: r.fulfill(status=200, content_type="text/html", body=PAGE))
    pg.goto("https://bench.test/")
    out = {}
    RACE = "(v)=>Promise.race([(%s)(v),new Promise(r=>setTimeout(()=>r({ms:-1,peak:-1}),20000))])" % JS
    for v in VARIANTS:
        rs = [pg.evaluate(f"({RACE})({json.dumps(v)})") for _ in range(3)]
        runs = sorted(r["ms"] for r in rs)
        out[v] = (runs[1], rs[0]["peak"])
        print(v, runs, flush=True)
    b.close()
print(f"{'variant':38} {'median ms / 60 s':>17} {'% of real time':>15} {'peak':>6}")
for v, (ms, pk) in out.items():
    print(f"{v:38} {ms:17.1f} {ms / 600:14.3f}% {pk:6.2f}")
