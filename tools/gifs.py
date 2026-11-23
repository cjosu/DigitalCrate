"""Record the README's GIFs from the running app (digitalcrate serve on :8765), with ffmpeg for the conversion.

    uv run --no-project --with playwright==1.55.0 python tools/gifs.py [out_dir] [only ...]

Each clip is scripted with Playwright, recorded as video, trimmed to the action, cropped to the part of the screen
that matters and turned into a palette-optimized GIF. Private names (your own, from the config's reference entries, and DIGITALCRATE_SCRUB)
are replaced live on every frame, and a dot shows where the mouse is.

DIGITALCRATE_HIDE="Artist A,Artist B" leaves artists out of the recordings altogether: their samples are hidden the way
deleted ones are (lists, "goes well with", kits, sets, the Artists view), and their names are scrubbed as well. Each
clip reports whether a hidden or private name ever reached the page.
"""
import json
import re
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from digitalcrate import config as C  # noqa: E402

URL = "http://localhost:8765/"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].isidentifier() else Path(__file__).resolve().parent.parent / "docs" / "img"
ONLY = [a for a in sys.argv[1:] if a.isidentifier()]
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1440, 900
VERSION = "2"  # in each file name: bump it (and the README / guide links) so nobody sees a cached older GIF
HIDE = [n.strip() for n in os.environ.get("DIGITALCRATE_HIDE", "").split(",") if n.strip()]
# your own names (the config's personal reference entries) and DIGITALCRATE_SCRUB; other artists show as they are
PRIVATE = [n for n in [*C._cfg.get("reference_artists", []), *C._cfg.get("reference_exact", []),
                       *os.environ.get("DIGITALCRATE_SCRUB", "").split(","), *HIDE] if n.strip()]

INIT = """
(()=>{const names=__NAMES__;
 // live scrubbing: private names never reach a frame
 if(names.length){const re=new RegExp('\\\\b('+names.map(n=>n.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')).join('|')+')\\\\b','gi');
  // only what's on screen: never the page's data or code (scripts), which the page itself reads
  window.__scrubbed=0;const code=n=>{const p=n.parentNode;return p&&(p.nodeName==='SCRIPT'||p.nodeName==='STYLE')};
  const sub=n=>{if(code(n)||!re.test(n.nodeValue)){re.lastIndex=0;return}re.lastIndex=0;window.__scrubbed++;(window.__scrubLog=window.__scrubLog||[]).push([n.nodeValue.slice(0,70),n.parentNode&&n.parentNode.closest&&(n.parentNode.closest('[id]')||{}).id]);n.nodeValue=n.nodeValue.replace(re,'(private)')};
  const fix=root=>{if(root.nodeName==='SCRIPT'||root.nodeName==='STYLE')return;const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;while((n=w.nextNode()))sub(n)};
  new MutationObserver(ms=>ms.forEach(m=>{if(m.type==='characterData')sub(m.target);
   m.addedNodes.forEach(x=>x.nodeType===3?sub(x):x.nodeType===1&&fix(x))})).observe(document,{subtree:true,childList:true,characterData:true});
  document.addEventListener('DOMContentLoaded',()=>fix(document.body))}
 // a visible cursor (headless recordings have none)
 document.addEventListener('DOMContentLoaded',()=>{const d=document.createElement('div');d.id='fakecur';
  d.style.cssText='position:fixed;left:0;top:0;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;background:rgba(255,255,255,.85);border:2px solid #000;z-index:99999;pointer-events:none;transition:transform .08s';
  document.body.appendChild(d);document.addEventListener('mousemove',e=>{d.style.left=e.clientX+'px';d.style.top=e.clientY+'px'},true);
  document.addEventListener('mousedown',()=>d.style.transform='scale(.7)',true);document.addEventListener('mouseup',()=>d.style.transform='',true)});
})();
""".replace("__NAMES__", json.dumps(PRIVATE))


WRITES = re.compile(r"/api/(event|fav|trash/|sketch/(save|delete)|edit/save|pair/save|recat|bounce|quit|setup/)")


class Clip:
    def __init__(self, b, name):
        self.name, self.dir = name, tempfile.mkdtemp()
        self.ctx = b.new_context(viewport={"width": W, "height": H}, record_video_dir=self.dir,
                                 record_video_size={"width": W, "height": H})
        self.ctx.add_init_script(INIT)
        # recording must not change your library: listens, stars, ✕, deletes, saved sketches and edits are dropped
        self.ctx.route(WRITES, lambda r: r.fulfill(status=200, content_type="application/json", body="{}")
                       if r.request.method == "POST" else r.continue_())
        self.t0 = time.time()
        self.page = self.ctx.new_page()
        self.start = None

    def go(self):
        self.page.goto(URL)
        self.page.wait_for_function("typeof S!=='undefined' && document.querySelectorAll('#list .row').length>10")
        if HIDE:  # hidden like deleted samples, so they never come up
            n = self.page.evaluate("""h=>{const H=new Set(h.map(x=>x.toLowerCase()));let n=0;
                S.forEach((s,i)=>{if(H.has(String(s[F.artist]).toLowerCase())){GONE.add(i);n++}});
                for(let k=ARTISTS.length-1;k>=0;k--)if(H.has(ARTISTS[k].name.toLowerCase()))ARTISTS.splice(k,1);
                render();return n}""", HIDE)
            self.page.wait_for_timeout(300)
            print(f"  {self.name}: hid {n} samples")
        self.page.evaluate("window.__scrubLog=[]")  # count only what can reach the recording from here on
        self.page.mouse.move(W / 2, H / 2)
        self.page.wait_for_timeout(600)

    def action(self):
        """Mark the moment the GIF starts (everything before is loading)."""
        self.start = time.time() - self.t0

    def click(self, sel, steps=14, dx=0, dy=0, mods=None):
        bb = self.page.locator(sel).first.bounding_box()
        x, y = bb["x"] + bb["width"] / 2 + dx, bb["y"] + bb["height"] / 2 + dy
        self.page.mouse.move(x, y, steps=steps)
        self.page.wait_for_timeout(120)
        if mods:
            for m in mods:
                self.page.keyboard.down(m)
        self.page.mouse.down(); self.page.mouse.up()
        if mods:
            for m in mods:
                self.page.keyboard.up(m)
        return x, y

    def drag(self, x0, y0, x1, y1, steps=18, alt=False):
        self.page.mouse.move(x0, y0, steps=10)
        if alt:
            self.page.keyboard.down("Alt")
        self.page.mouse.down(); self.page.mouse.move(x1, y1, steps=steps); self.page.mouse.up()
        if alt:
            self.page.keyboard.up("Alt")

    def save(self, crop=None, width=900, fps=12):
        """crop: (x, y, w, h) in page pixels, or a selector whose box (padded) is used."""
        end = time.time() - self.t0
        leaks = self.page.evaluate("window.__scrubLog||[]")
        print(f"  {self.name}: {'no private names reached the page' if not leaks else f'{len(leaks)} private names scrubbed (where: ' + ', '.join(sorted({str(x[1]) for x in leaks})) + ')'}")
        if os.environ.get("GIFS_DEBUG"):
            for x in leaks:
                print("    ", x)
        if isinstance(crop, str):
            bb = self.page.locator(crop).first.bounding_box()
            p = 10
            crop = (max(0, bb["x"] - p), max(0, bb["y"] - p), min(W, bb["width"] + 2 * p), min(H, bb["height"] + 2 * p))
        video = self.page.video.path()
        self.ctx.close()
        x, y, w, h = [int(v) // 2 * 2 for v in (crop or (0, 0, W, H))]
        out = OUT / f"{self.name}-{VERSION}.gif"
        vf = (f"fps={fps},crop={w}:{h}:{x}:{y},scale={min(width, w)}:-1:flags=lanczos,split[a][b];"
              "[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{(self.start or 0):.2f}", "-t", f"{end - (self.start or 0):.2f}",
                        "-i", video, "-vf", vf, str(out)], check=True)
        import shutil
        if shutil.which("gifsicle"):  # about half the size, text still crisp (brew install gifsicle)
            subprocess.run(["gifsicle", "-O3", "--lossy=40", "-b", str(out)], check=True)
        print(f"saved {out.name}: {out.stat().st_size / 1e6:.1f} MB, {end - (self.start or 0):.1f} s")


def browse(b):
    c = Clip(b, "browse"); c.go(); pg = c.page
    pg.wait_for_function("TASTE.loaded", timeout=60000)
    c.action()
    c.click('#cats [data-v="Vocals"]'); pg.wait_for_timeout(900)
    for _ in range(3):  # ↓ moves through the list, previewing each
        pg.keyboard.press("ArrowDown"); pg.wait_for_timeout(1100)
    c.click('#cats [data-v="Pads & Atmospheres"]'); pg.wait_for_timeout(900)
    c.click("#list .row:nth-of-type(2)", dx=-200); pg.wait_for_timeout(1200)
    c.click("#whybtn"); pg.wait_for_selector("#whybox b", timeout=30000); pg.wait_for_timeout(2600)
    pg.locator("#detail [data-gcat]").nth(3).scroll_into_view_if_needed(); pg.wait_for_timeout(300)
    c.click("#detail [data-gcat]:nth-of-type(3)"); pg.wait_for_timeout(1400)
    c.click("#tabA"); pg.wait_for_timeout(700)
    c.click("#aq"); pg.keyboard.type("brubeck", delay=90); pg.wait_for_timeout(900)
    c.click(".art .tw"); pg.wait_for_timeout(1200)
    c.click(".alb > a"); pg.wait_for_timeout(1800)
    c.save(crop=(262, 0, W - 262, H), width=840, fps=9)  # without the filter sidebar, so the text stays readable


def sketch(b):
    c = Clip(b, "sketch"); c.go(); pg = c.page
    pg.wait_for_function("P_READY&&TASTE.loaded", timeout=60000)
    pg.click("#tabK"); pg.wait_for_function("D.kits[0]&&D.kits[0].yours", timeout=30000); pg.wait_for_timeout(800)
    k = pg.evaluate("D.kits.findIndex(k=>kitMembers(k).length>=5)")
    pg.locator(f"[data-kitsk='{k}']").click()
    pg.wait_for_function("SK.lanes.length&&SK.lanes.every(l=>l.state==='ok')", timeout=60000); pg.wait_for_timeout(1500)
    c.action(); pg.wait_for_timeout(2500)
    box = pg.locator("[data-skw='2']").bounding_box(); y = box["y"] + box["height"] / 2
    c.drag(box["x"] + box["width"] * 0.12, y, box["x"] + box["width"] * 0.7, y); pg.wait_for_timeout(1500)
    fb = pg.locator("[data-skv='0']").bounding_box()
    c.drag(fb["x"] + fb["width"] * 0.8, fb["y"] + fb["height"] / 2, fb["x"] + fb["width"] * 0.55, fb["y"] + fb["height"] / 2); pg.wait_for_timeout(900)
    if pg.locator("[data-skfit]").count():
        c.click("[data-skfit]"); pg.wait_for_timeout(5000)
    pg.wait_for_timeout(2500)
    c.save(crop="#sk")


def chords(b):
    c = Clip(b, "chords"); c.go(); pg = c.page
    pg.evaluate("select(BYID.get('1fe9dc'),'list')"); pg.wait_for_timeout(800)
    pg.click("#chordsopen"); pg.wait_for_selector(".chopt", timeout=60000); pg.wait_for_timeout(600)
    pg.locator("#chordbox").scroll_into_view_if_needed(); pg.wait_for_timeout(500)
    c.action()
    c.click("[data-chplay='0']"); pg.wait_for_timeout(9000)
    c.click("[data-chplay='1']"); pg.wait_for_timeout(5000)
    c.click('[data-chone="2:2"]'); pg.wait_for_timeout(1800)
    c.save(crop="#chordbox")


def pads(b):
    c = Clip(b, "pads"); c.go(); pg = c.page
    pg.evaluate("select(BYID.get('a59109'),'list')"); pg.wait_for_timeout(800)
    pg.click("#padsopen"); pg.wait_for_selector("#pads .pad", timeout=60000); pg.wait_for_timeout(500)
    pg.locator("#pads").scroll_into_view_if_needed(); pg.wait_for_timeout(400)
    c.action()
    for key in "1234qwer":
        pg.keyboard.press(key); pg.wait_for_timeout(330)
    c.click("#pdrec"); pg.wait_for_timeout(700)
    beat = 60 / 90
    for key in "1.q1.wq.1.q1.r..":  # a little rhythm; dots are rests (8th notes)
        if key != ".":
            pg.keyboard.press(key)
        pg.wait_for_timeout(int(beat / 2 * 1000))
    c.click("#pdrec"); pg.wait_for_timeout(300)
    c.click("#pdplay"); pg.wait_for_timeout(4500)
    c.save(crop="#pads")


def drums(b):
    c = Clip(b, "drums"); c.go(); pg = c.page
    pg.click("#tabA"); pg.fill("#aq", "brubeck quartet"); pg.wait_for_timeout(800)
    c.action()
    c.click(".art [data-rack]"); pg.wait_for_timeout(1500)
    for key in "1234qwerasdf":
        pg.keyboard.press(key); pg.wait_for_timeout(260)
    c.click('[data-rpage="1"]'); pg.wait_for_timeout(700)
    for key in "1qaz2wsx":
        pg.keyboard.press(key); pg.wait_for_timeout(240)
    pg.wait_for_timeout(600)
    c.save(crop="#modalBody")


def drumlane(b):
    """A kit built around one kick: the hits that complete it, a starter pattern, velocity and a flam, playing."""
    c = Clip(b, "drumlane"); c.go(); pg = c.page
    pg.wait_for_function("TASTE.loaded", timeout=60000)
    i = pg.evaluate("""S.map((s,i)=>i).filter(i=>S[i][F.cat]==='Percussion'&&S[i][F.sub]==='Kick'&&S[i][F.kind]==='oneshot'&&!GONE.has(i)&&S[i][F.dur]<1.5)
        .sort((a,b)=>(TASTE.score[S[b][F.path]]||0)-(TASTE.score[S[a][F.path]]||0))[0]""")
    pg.evaluate(f"select({i},'list')"); pg.wait_for_timeout(700)
    c.action()
    c.click("#kitaround"); pg.wait_for_selector(".dfrow [data-dfadd]", timeout=60000); pg.wait_for_timeout(1500)
    for kind in ("Snare", "Hats", "Rim"):
        row = pg.locator(".dfrow").filter(has_text=kind)
        if row.count():
            b0 = row.first.locator("[data-dfadd]").first.bounding_box()
            pg.mouse.move(b0["x"] + 8, b0["y"] + 8, steps=12); pg.wait_for_timeout(150); pg.mouse.down(); pg.mouse.up()
            pg.wait_for_function("SK.lanes[0].pads.every(p=>p.buf)", timeout=30000); pg.wait_for_timeout(900)
    if pg.locator("[data-dfind].on").count():
        c.click("[data-dfind].on"); pg.wait_for_timeout(500)  # fold the finder away to show the pattern
    c.click("#skplay"); pg.wait_for_timeout(2500)
    for j in (2, 6, 10, 14):  # scroll a few kick steps softer / louder, live
        sb = pg.locator(f"[data-dstep='0:0:{j}']").bounding_box()
        pg.mouse.move(sb["x"] + 6, sb["y"] + 6, steps=8)
        if not pg.evaluate(f"SK.lanes[0].pads[0].steps[{j}]"):
            pg.mouse.down(); pg.mouse.up()
        for _ in range(4):
            pg.mouse.wheel(0, 120); pg.wait_for_timeout(110)
    c.click("[data-dstep='0:1:15']", mods=["Alt"]); pg.wait_for_timeout(600)  # a flam into the next bar
    hb = pg.locator("[data-dhuman='0']").bounding_box()
    c.drag(hb["x"] + 2, hb["y"] + hb["height"] / 2, hb["x"] + hb["width"] * 0.5, hb["y"] + hb["height"] / 2); pg.wait_for_timeout(4000)
    c.click("#skplay"); pg.wait_for_timeout(300)
    c.save(crop="#sk")


with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    for f in (browse, sketch, chords, pads, drums, drumlane):
        if not ONLY or f.__name__ in ONLY:
            f(b)
    b.close()
