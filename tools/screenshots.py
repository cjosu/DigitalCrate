"""Regenerate the README screenshots from the running app (python -m digitalcrate serve must be up on :8765).

    uvx --from playwright==1.55.0 playwright install chromium     # once
    uv run --with playwright==1.55.0 python tools/screenshots.py [out_dir]
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8765/"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "docs" / "img")
OUT.mkdir(parents=True, exist_ok=True)
VOX, PAD, MEL = "a59109", "4484c1", "0947ae"  # walkthrough samples: three different artists, compatible keys

# names that must never appear in the docs: your reference-only artists, plus anything in DIGITALCRATE_SCRUB (comma-separated)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from digitalcrate import config as C  # noqa: E402
import os  # noqa: E402
PRIVATE = [n for n in [*C._cfg.get("reference_artists", []), *C._cfg.get("reference_exact", []),
                       *os.environ.get("DIGITALCRATE_SCRUB", "").split(",")] if n.strip()]


def sel(page, sid):
    page.evaluate("""id=>{const i=S.findIndex(s=>s[F.id]===id);CRATE.setTab('S');select(i)}""", sid)
    page.wait_for_timeout(600)


def scrub(page):
    """Replace private names in every visible text node and input value before a screenshot."""
    page.evaluate("""names=>{const re=new RegExp(names.map(n=>n.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')).join('|'),'gi');
      const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
      while((n=w.nextNode()))if(re.test(n.nodeValue)){re.lastIndex=0;n.nodeValue=n.nodeValue.replace(re,'(private)')}
      document.querySelectorAll('input,option').forEach(e=>{if(e.value&&re.test(e.value))e.value=e.value.replace(re,'(private)')})}""",
                  PRIVATE) if PRIVATE else None


def shot(page, name, el=None, full=False):
    scrub(page)
    (page.locator(el) if el else page).screenshot(path=str(OUT / f"{name}.png"), **({} if el else {"full_page": full}))
    print("saved", name)


def clear_search(page):
    page.fill("#search", "")
    page.dispatch_event("#search", "input")
    page.wait_for_timeout(400)


def close_modal(page):
    page.evaluate("$('modal').hidden=true")


with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    page = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    page.add_init_script("try{localStorage.clear()}catch(e){}")
    page.goto(URL)
    page.wait_for_function("typeof S!=='undefined' && document.querySelectorAll('#list .row').length>10")
    page.wait_for_timeout(800)

    # 1. the browser, ordered by the taste model
    page.select_option("#sort", "you")
    page.wait_for_timeout(600)
    sel(page, VOX)
    shot(page, "01-browser")

    # 2. search by sound
    page.click("#sndbtn")
    page.fill("#search", "dusty piano chords, melancholy, -drums")
    page.press("#search", "Enter")
    page.wait_for_selector("#sbanner b", timeout=60000)
    page.wait_for_timeout(800)
    shot(page, "02-sound-search")
    page.click("#sclear")
    clear_search(page)

    # 3. feels like a reference track
    page.click("#refbtn")
    page.fill("#refIn", "Burial - Archangel")
    shot(page, "03a-reference-dialog", "#modalBody")
    page.click("#refGo")
    page.wait_for_selector("#sbanner b", timeout=180000)
    page.wait_for_timeout(800)
    shot(page, "03-reference-search")
    page.click("#sclear")
    clear_search(page)

    # 4. project mode
    page.select_option("#pjkey", label=page.evaluate(
        "[...$('pjkey').options].find(o=>/^4A|Fm/.test(o.text))?.text || $('pjkey').options[1].text"))
    page.fill("#pjbpm", "124")
    page.dispatch_event("#pjbpm", "change")
    if not page.is_checked("#pjon"):
        page.click("#pjon")
    for cat in ("Pads & Atmospheres", "Chords & Keys"):  # show material that gets conformed
        page.locator("#cats > *", has_text=cat).first.click()
    page.wait_for_timeout(800)
    sel(page, MEL)
    page.wait_for_timeout(1500)
    shot(page, "04-project-mode")
    for cat in ("Pads & Atmospheres", "Chords & Keys"):
        page.locator("#cats > *", has_text=cat).first.click()
    page.wait_for_timeout(500)

    # 5. sketchpad
    for sid in (VOX, PAD, MEL):
        page.evaluate("""id=>{const i=S.findIndex(s=>s[F.id]===id);CRATE.skAdd(i)}""", sid)
    page.wait_for_function("SK.lanes.length>=3 && SK.lanes.every(l=>l.state!=='loading')", timeout=120000)
    page.wait_for_timeout(3500)  # let the toast fade
    shot(page, "05-sketchpad", "#sk")

    # 6. pads + MIDI
    sel(page, VOX)
    page.click("#padsopen")
    page.wait_for_selector("#pads .pad", timeout=60000)
    page.wait_for_timeout(500)
    shot(page, "06-pads", "#detail")
    sel(page, MEL)
    page.click("#midiopen")
    page.wait_for_selector("#midibox canvas", timeout=120000)
    page.wait_for_timeout(1200)
    shot(page, "07-midi", "#detail")

    # 7. editor with vocal tuning
    sel(page, VOX)
    page.click("#edopen")
    page.wait_for_selector("#edtune", timeout=30000)
    page.select_option("#tnkey", index=1)  # the project key
    page.wait_for_function("!/measuring/.test($('tnrep').textContent) && $('tnrep').textContent.length>0", timeout=60000)
    page.wait_for_timeout(600)
    shot(page, "08-editor-tune", "#editor")
    page.evaluate("$('editor').hidden=true")

    # 8. crate, galaxy, scout, kits, for-you
    page.evaluate("CRATE.skStop();SK.lanes.length=0;SK.open=false;CRATE.drawSK()")
    for tab, name, wait in [("C", "09-crate", "#list .row"), ("G", "10-galaxy", "#galc"), ("Y", "11-scout", "#ytlist"),
                            ("K", "12-kits", "#list .kit"), ("R", "13-recent", "#list .row")]:
        page.evaluate(f"CRATE.setTab('{tab}')")
        page.wait_for_selector(wait, timeout=120000)
        page.wait_for_timeout(2500 if tab == "G" else 800)
        if tab == "Y":  # don't put private singers' names / titles in the docs
            page.evaluate("""async()=>{const r=(await (await fetch('/api/ytscout')).json()).results;
              const box=document.getElementById('ytlist');let h=box.innerHTML;
              r.forEach((x,k)=>{if(x.channel)h=h.split(x.channel).join('channel '+(k+1));
                                if(x.title)h=h.split(x.title.replace(/&/g,'&amp;')).join('video title '+(k+1))});box.innerHTML=h}""")
            page.wait_for_timeout(300)
        if tab == "G":
            page.wait_for_selector("#gtaste", timeout=180000)  # the map is recomputed after a rebuild
            page.click("#gtaste")
            page.evaluate("$('detail').scrollTop=0")
            page.wait_for_timeout(800)
        shot(page, name)

    # 9. export dialog
    page.evaluate("CRATE.setTab('F')")
    page.wait_for_timeout(500)
    page.click("#expbtn")
    page.wait_for_selector("#expRack")
    shot(page, "14-export", "#modalBody")
    close_modal(page)

    b.close()
