"""Writes Browser.html: a self-contained, offline sample browser at the library root."""
import json
from . import config as C

ABBR = {"Vocals": "VOX", "Vocal Atmospheres": "VATM", "Pads & Atmospheres": "PAD", "Chords & Keys": "KEYS",
        "Melodies & Leads": "MEL", "Textures & Field": "TEX", "Bass & Sub": "BASS", "Percussion": "PERC"}


def _ops_label(ops):
    if not ops:
        return ""
    from .edit import clean_params, _ops_tag
    o = json.loads(ops)
    if o.get("tag"):
        return o["tag"] + (f" · {o['name']}" if o.get("name") else "")
    return _ops_tag(clean_params(o)) + (f" · {o['name']}" if o.get("name") else "")


def write_browser(d, tags, parts, kits):
    S = []
    for i, r in enumerate(d["rows"]):
        keyed = r["key_from"] != "none"
        S.append([r["id"], r["path"], r["category"], r["subtype"], r["kind"],
                  r["camelot"] if keyed else "", (r["key"] + ("m" if r["scale"] == "minor" else "")) if keyed else "",
                  round(r["bpm"]) if r["bpm"] else 0, round(r["dur"], 1), r["artist"] or "", r["title"] or "",
                  round(r["quality"], 2), tags[i], json.loads(r["env"] or "[]"), r["note"] or "",
                  r["instrument"] or "", r["bars"] or 0, round(r["start"]),
                  round(float(d["ref_sim"][i]), 3), d["ref_match"][i], d["genre"][i], r["track_id"],
                  r["parent_id"] or "", r["root_id"] or "", _ops_label(r["ops"])])
    from .db import connect
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS variants (sample_id TEXT, idx INTEGER, technique TEXT,
                   chain TEXT, seed INTEGER, path TEXT, PRIMARY KEY(sample_id, idx))""")
    pos = {r["id"]: i for i, r in enumerate(d["rows"])}
    V = {}
    for r in con.execute("SELECT * FROM variants ORDER BY sample_id, idx"):
        if r["sample_id"] in pos and (C.LIB_ROOT / r["path"]).exists():
            V.setdefault(pos[r["sample_id"]], []).append([r["idx"], r["technique"], r["chain"], r["path"]])
    from .recat import SUBTYPES, overrides
    ov = set(overrides())
    import time as _t
    from datetime import datetime
    tracks = {}
    for r in d["rows"]:
        if r["track_id"] not in tracks:
            ts = r["processed_at"]
            ep = int(datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp()) if ts else 0
            added = not str(r["tpath"]).startswith(str(C.MUSIC_ROOT))
            kind = "YouTube" if "/YouTube/" in str(r["tpath"]) else ("added file" if added else "")
            tracks[r["track_id"]] = [ep, r["artist"] or "", r["title"] or "", kind]
    data = dict(tracks=tracks, samples=S, partners=parts, variants=V, subtypes=SUBTYPES, overridden=[i for i, r in enumerate(d["rows"]) if r["id"] in ov], kits=[dict(name=k["name"], m=k["members"]) for k in kits],
                abbr=ABBR)
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("</", "<\\/"))
    (C.LIB_ROOT / "Browser.html").write_text(html, encoding="utf-8")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DigitalCrate</title>
<style>
:root{--bg:#0e1013;--panel:#15181d;--line:#242932;--ink:#d9dde3;--mute:#7d8592;--acc:#e0a458;--acc2:#7fb0c9;
--VOX:#e0a458;--VATM:#d1857a;--PAD:#7fb0c9;--KEYS:#9fc29a;--MEL:#c4a7e0;--TEX:#8f8f86;--BASS:#6c7fd1;--PERC:#d96c6c}
*{box-sizing:border-box}[hidden]{display:none!important}html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);
font:13px/1.4 -apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif}
button{font:inherit;color:inherit;background:none;border:1px solid var(--line);border-radius:6px;padding:4px 9px;cursor:pointer}
button:hover{border-color:var(--mute)}button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
input,select{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:5px 8px}
.app{display:grid;grid-template-columns:260px 1fr 400px;height:100vh}
aside,.detail{overflow:auto;padding:16px;border-right:1px solid var(--line)}.detail{border-right:0;border-left:1px solid var(--line)}
main{overflow:auto;display:flex;flex-direction:column}
h1{font-size:15px;letter-spacing:.08em;text-transform:uppercase;margin:0 0 2px}h2{font-size:11px;letter-spacing:.1em;
text-transform:uppercase;color:var(--mute);margin:18px 0 8px;font-weight:600}
.sub{color:var(--mute);font-size:12px}.chips{display:flex;flex-wrap:wrap;gap:5px}.chips button{font-size:12px;padding:3px 8px}
.top{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;gap:8px;align-items:center;z-index:2;flex-wrap:wrap}
.top input[type=search]{flex:1;min-width:200px}
.row{display:grid;grid-template-columns:30px 120px 1fr auto;gap:12px;align-items:center;padding:7px 16px;border-bottom:1px solid #1a1d23;cursor:pointer}
.row:hover{background:#13161b}.row.sel{background:#1a1f27}
.play{width:28px;height:28px;border-radius:50%;padding:0;display:grid;place-items:center;font-size:10px}
.play.playing{background:var(--acc);color:#000;border-color:var(--acc)}
svg.wave{display:block}.name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.badge{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.06em;padding:1px 5px;border-radius:4px;color:#000;margin-right:6px}
.meta{color:var(--mute);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.right{display:flex;gap:10px;align-items:center;color:var(--mute);font-size:12px;font-variant-numeric:tabular-nums}
.key{color:var(--ink);font-weight:600;min-width:62px;text-align:right}.qbar{width:36px;height:4px;background:var(--line);border-radius:2px;overflow:hidden}
.qbar i{display:block;height:100%;background:var(--acc2)}
.id{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--mute);cursor:copy}.id:hover{color:var(--acc)}
.tag{font-size:11px;color:var(--mute);border:1px solid var(--line);border-radius:10px;padding:0 6px;margin-right:3px}
.more{margin:14px auto}.empty{padding:40px;color:var(--mute);text-align:center}
.prow{display:grid;grid-template-columns:28px 1fr auto;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid #1a1d23}
.score{font-variant-numeric:tabular-nums;font-size:12px;color:var(--acc)}
.big{font-size:16px;font-weight:600;margin:6px 0 2px}.kv{display:grid;grid-template-columns:90px 1fr;gap:3px 10px;font-size:12px;margin:10px 0}
.kv span:nth-child(odd){color:var(--mute)}.path{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--mute);word-break:break-all}
.wheel path{cursor:pointer;stroke:var(--bg);stroke-width:1.5}.wheel text{pointer-events:none;font-size:9px;fill:var(--ink)}
.tabs{display:flex;gap:6px}.kit{border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:10px 16px}
.kit h3{margin:0 0 6px;font-size:13px;display:flex;justify-content:space-between;align-items:center}
.star{border:0;padding:2px 4px;font-size:15px;color:#4a515c;line-height:1}.star.on{color:var(--acc)}.star:hover{color:var(--acc)}
.np{position:sticky;bottom:0;margin-top:auto;background:#12151a;border-top:1px solid var(--line);padding:8px 16px calc(8px + env(safe-area-inset-bottom,0px));display:flex;gap:10px;align-items:center;z-index:3}
.np .lbl{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pill{background:var(--acc);color:#000;border-color:var(--acc);font-size:12px}
.ed{border:1px solid var(--line);border-radius:8px;padding:10px;margin:10px 0;display:grid;gap:8px}
.edrow{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.edgrid{display:grid;grid-template-columns:auto 1fr auto;gap:6px 10px;align-items:center;font-size:12px}
.prov{border-left:2px solid var(--acc);padding:4px 10px;margin:8px 0;font-size:12px}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:10;display:grid;place-items:center}
.toast{position:fixed;left:50%;bottom:70px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:7px 14px;border-radius:8px;font-size:12px;z-index:20}
.xp{border:0;padding:2px 4px;font-size:13px;color:#4a515c}.xp:hover{color:var(--acc)}.xp.done{color:var(--acc)}
.hint{font-size:11px;color:var(--mute);margin-top:6px}
</style></head><body>
<div class="app">
<aside>
  <h1>DigitalCrate</h1><div class="sub" id="count"></div>
  <h2>Category</h2><div class="chips" id="cats"></div>
  <div id="subsBox" hidden><h2>Subtype</h2><div class="chips" id="subs"></div></div>
  <h2>Key <span class="sub" id="keylbl"></span></h2>
  <svg class="wheel" id="wheel" viewBox="-110 -110 220 220" width="220" height="220"></svg>
  <div class="chips" style="margin-top:6px"><button id="nbr" class="on" title="include Camelot neighbours">+ neighbours</button><button id="clrkey">clear</button></div>
  <h2>Tempo (loops)</h2>
  <div style="display:flex;gap:6px;align-items:center"><input id="bmin" type="number" placeholder="min" style="width:70px"> – <input id="bmax" type="number" placeholder="max" style="width:70px"> <label class="sub"><input type="checkbox" id="half"> ×½ ×2</label></div>
  <h2>Genre</h2><div class="chips" id="genres"></div>
  <h2>Exclude genres</h2><div id="excl" style="display:grid;grid-template-columns:1fr 1fr;gap:2px 8px;font-size:12px"></div>
  <h2>Kind</h2><div class="chips" id="kinds"></div>
  <h2>Mood</h2><div class="chips" id="moods"></div>
  <h2>Min quality <span class="sub" id="qv"></span></h2><input id="q" type="range" min="0" max="1" step="0.05" value="0.4" style="width:100%">
</aside>
<main>
  <div class="top"><div class="tabs"><button id="tabS" class="on">Samples</button><button id="tabK">Kits</button><button id="tabF">★ Favorites</button><button id="tabR">🆕 Recent</button></div>
    <input type="search" id="search" placeholder="search artist, title, mood, instrument, id…">
    <select id="sort"><option value="div">diverse (best of each artist)</option><option value="you">for you</option><option value="vibe">today's vibe</option><option value="disc">discover</option><option value="q">best quality</option><option value="key">key</option><option value="bpm">tempo</option><option value="dur">length</option><option value="ref">closest to reference</option><option value="var">has variations</option><option value="new">newest first</option><option value="rnd">shuffle</option></select>
    <button id="addsrc">＋ add source</button><button id="expbtn" title="copy what's listed into Ableton's User Library">⇩ export to Ableton</button><button id="refresh" class="pill" hidden>↻ recommendations updated</button><select id="grp" title="group by"><option value="">no grouping</option><option value="track">group by track</option><option value="type">group by type</option><option value="genre">group by genre</option></select><button id="stop">■ stop all</button></div>
  <div id="tbanner" class="prov" style="margin:8px 16px" hidden></div>
  <div id="list"></div>
  <div class="np" id="np" hidden></div>
  <div class="toast" id="toast" hidden></div>
  <div id="modal" class="modal" hidden>
   <div style="background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px;width:min(560px,92vw);display:grid;gap:10px" id="modalBody"></div></div>
</main>
<section class="detail" id="detail"><div class="empty">Select a sample to see what it goes with.<br><br>Click an <span class="id">ID</span> to copy it — paste into Ableton's browser search to find the file instantly.</div></section>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const S=D.samples, P=D.partners, AB=D.abbr;
const F={id:0,path:1,cat:2,sub:3,kind:4,cam:5,key:6,bpm:7,dur:8,artist:9,title:10,q:11,tags:12,env:13,note:14,inst:15,bars:16,start:17,ref:18,refm:19,genre:20,tid:21,parent:22,root:23,ops:24};
const st={tracks:null,subs:new Set(),rel:'go',genres:new Set(),open:new Set(),cats:new Set(),kinds:new Set(),moods:new Set(),key:null,nbr:true,tab:'S',sel:null,shown:200};
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const url=p=>p.split('/').map(encodeURIComponent).join('/');
const col=c=>`var(--${AB[c]})`;
function wave(env,w=120,h=26,c='#7d8592'){if(!env.length)return'';const bw=w/env.length;
 return `<svg class="wave" width="${w}" height="${h}">${env.map((v,i)=>{const hh=Math.max(1,v/99*h);return`<rect x="${(i*bw).toFixed(1)}" y="${((h-hh)/2).toFixed(1)}" width="${(bw*.7).toFixed(1)}" height="${hh.toFixed(1)}" fill="${c}"/>`}).join('')}</svg>`}
// ---------- favourites
const FAV=new Map(); let SERVED=location.protocol.startsWith('http');
function lsGet(){try{return JSON.parse(localStorage.getItem('atlasFavs')||'[]')}catch(e){return[]}}
function lsSet(){try{localStorage.setItem('atlasFavs',JSON.stringify([...FAV.values()]))}catch(e){}}
async function loadFavs(){let list=[];if(SERVED){try{list=await (await fetch('api/favs')).json()}catch(e){SERVED=false}}
 if(!SERVED)list=lsGet();list.forEach(f=>FAV.set(f.path,f));render()}
async function toggleFav(path,id,label){const on=!FAV.has(path);
 if(on)FAV.set(path,{path,sample_id:id,label,added_at:new Date().toISOString()});else FAV.delete(path);
 if(SERVED){try{const r=await fetch('api/fav',{method:'POST',body:JSON.stringify({path,id,label,on})});if(!r.ok)throw 0}catch(e){SERVED=false}}
 if(!SERVED)lsSet();document.querySelectorAll(`[data-fav="${CSS.escape(path)}"]`).forEach(b=>b.classList.toggle('on',on));if(st.tab==='F')render()}
const star=(path,id,label)=>`<button class="star${FAV.has(path)?' on':''}" data-fav="${esc(path)}" data-fid="${esc(id||'')}" data-flabel="${esc(label||'')}" title="favourite">★</button>`;
document.addEventListener('click',e=>{const b=e.target.closest('[data-fav]');if(!b)return;e.stopPropagation();toggleFav(b.dataset.fav,b.dataset.fid,b.dataset.flabel)},true);
// ---------- taste
let TASTE={score:{},discover:{},vibe:{},disliked:new Set(),n:0};
async function loadTaste(){if(!SERVED)return;try{const a=await (await fetch('api/taste')).json();const b=await (await fetch('api/taste?recent=1')).json();
 const first=!TASTE.loaded;
 TASTE={loaded:true,score:a.score||{},discover:a.discover||{},vibe:b.score||{},disliked:new Set([...(a.disliked||[]),...TASTE.disliked]),n:a.n_labels||0};
 if(first)render();else{$('refresh').hidden=false;const c=$('count');if(c&&!c.textContent.includes('taste'))render.countOnly&&render.countOnly()}}catch(e){}}
let refitT=null;function scheduleRefit(){clearTimeout(refitT);refitT=setTimeout(loadTaste,4000)}
function sendEvent(path,type,value,id){if(!SERVED)return;fetch('api/event',{method:'POST',body:JSON.stringify({path,type,value,id})}).catch(()=>{});scheduleRefit()}
const listenStart=new Map();
function beginListen(key,path){listenStart.set(key,{t:performance.now(),path})}
function endListen(key,audio){const s=listenStart.get(key);if(!s)return;listenStart.delete(key);
 const secs=(performance.now()-s.t)/1000,dur=(audio&&isFinite(audio.duration))?audio.duration:8,frac=Math.min(1,secs/dur);sendEvent(s.path,'listen',+frac.toFixed(2))}
function toggleDislike(path,id){const on=!TASTE.disliked.has(path);on?TASTE.disliked.add(path):TASTE.disliked.delete(path);sendEvent(path,'dislike',on?1:0,id);
 document.querySelectorAll(`[data-nope="${CSS.escape(path)}"]`).forEach(b=>{b.classList.toggle('on',on);const r=b.closest('.row');if(r&&on)r.style.opacity=.35;else if(r)r.style.opacity=''});
 if(on&&NP&&NP.path===path)stopAll();drawNP()}
const nope=(path,id)=>`<button class="star${TASTE.disliked.has(path)?' on':''}" data-nope="${esc(path)}" data-nid="${esc(id||'')}" title="not for me" style="font-size:12px">✕</button>`;
document.addEventListener('click',e=>{const b=e.target.closest('[data-nope]');if(!b)return;e.stopPropagation();toggleDislike(b.dataset.nope,b.dataset.nid)},true);
// ---------- now playing
let NP=null;
function setNP(path,id,label,i){NP={path,id,label,i};drawNP()}
function drawNP(){const el=$('np');if(!NP||!(players.size||(ED&&ED.P))){el.hidden=true;return}el.hidden=false;
 el.innerHTML=`<button class="play playing" id="npstop">■</button><div class="lbl"><span class="sub">now playing</span> · ${esc(NP.label)}</div>
 ${star(NP.path,NP.id,NP.label)}${nope(NP.path,NP.id)}${xp(NP.path)}${NP.i!=null?`<button id="npshow">show</button>`:''}<span class="sub">F ★ · X ✕</span>`;
 $('npstop').onclick=()=>{stopAll()};if($('npshow'))$('npshow').onclick=()=>select(NP.i,'go')}
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'||!NP||!players.size)return;
 if(e.key==='f'||e.key==='F'){toggleFav(NP.path,NP.id,NP.label);setTimeout(drawNP,50)}else if(e.key==='x'||e.key==='X'){toggleDislike(NP.path,NP.id)}});
const lbl=i=>`${S[i][F.artist]} — ${S[i][F.title]} · ${S[i][F.sub]}${S[i][F.cam]?' · '+S[i][F.cam]:''}`;
// ---------- provenance
function provHTML(i){const s=S[i];let h='';
 if(s[F.parent]){const p=BYID.get(s[F.parent]),r=BYID.get(s[F.root]);
  h+=`<div class="prov">✎ edit · <b>${esc(s[F.ops])}</b><br>derived from ${p!=null?`<a href="#" data-go2="${p}">${esc(S[p][F.sub])} · ${esc(S[p][F.artist])} — ${esc(S[p][F.title])} (${S[p][F.id]})</a>`:s[F.parent]}
  ${r!=null&&s[F.root]!==s[F.parent]?`<br>original: <a href="#" data-go2="${r}">${esc(S[r][F.sub])} (${S[r][F.id]})</a>`:''}</div>`}
 const kids=S.map((t,j)=>t[F.parent]===s[F.id]?j:-1).filter(j=>j>=0);
 if(kids.length)h+=`<div class="prov">your edits of this sample (${kids.length}):${kids.map(j=>`<div class="prow"><button class="play" data-play="${j}">▶</button><div class="name">${esc(S[j][F.ops])} · ${S[j][F.dur]}s ${S[j][F.cam]||''}</div><div style="display:flex;gap:6px">${star(S[j][F.path],S[j][F.id],lbl(j))}<button data-go="${j}">→</button></div></div>`).join('')}</div>`;
 return h}
// ---------- editor
let ED=null;const AC=new (window.AudioContext||window.webkitAudioContext)();
function edStop(){const P=ED&&ED.P;if(!P)return;clearTimeout(P.timer);const now=AC.currentTime;
 P.voices.forEach(v=>{try{v.g.gain.cancelScheduledValues(now);v.g.gain.setValueAtTime(v.g.gain.value,now);v.g.gain.linearRampToValueAtTime(0,now+0.02);v.src.stop(now+0.03)}catch(e){}});
 ED.P=null;setTimeout(()=>{typeof drawNP==='function'&&drawNP();typeof edButtons==='function'&&edButtons();edPaint()},0)}
async function openEditor(i){const box=$('editor');if(!box)return;if(!box.hidden){box.hidden=true;edStop();return}box.hidden=false;
 if(!SERVED){box.innerHTML='<div class="sub">Editing needs the local server: run <code>python -m digitalcrate serve</code> and open http://localhost:8765</div>';return}
 box.innerHTML=`<canvas id="edc" style="width:100%;height:120px;background:#101317;border-radius:6px;cursor:crosshair"></canvas>
 <div class="sub" id="edsel">drag to select · double-click selects one syllable/note · loading…</div>
 <div class="edrow"><button id="edplay">▶ selection</button><label class="sub"><input type="checkbox" id="edloop" checked> loop</label>
 <label class="sub"><input type="checkbox" id="edsnap" checked> snap to syllables</label><button id="edall">select all</button><button id="edzoom">🔍 zoom to selection</button><span class="sub">wheel = zoom</span></div>
 <div class="edgrid"><span>Stretch</span><input type="range" id="edst" min="0.5" max="4" step="0.05" value="1"><span id="edstv">1×</span>
 <span>Pitch</span><input type="range" id="edpi" min="-12" max="12" step="1" value="0"><span id="edpiv">0 st</span>
 <span>Loop crossfade</span><input type="range" id="edxf" min="0" max="1000" step="10" value="20"><span id="edxfv">20 ms</span></div>
 <div class="edgrid" style="margin-top:-2px"><span>Fade in</span><input type="range" id="edfi" min="0" max="2000" step="5" value="10"><span id="edfiv">10 ms</span>
 <span id="edfol">Fade out</span><input type="range" id="edfo" min="0" max="2000" step="5" value="40"><span id="edfov">40 ms</span></div>
 <div class="edrow sub"><label title="Rubber Band's formant mode: keeps a voice's character on big shifts, but scored lowest in your blind shootout"><input type="checkbox" id="edfm"> keep formants</label><label><input type="checkbox" id="edrev"> reverse</label>
 <span title="Fade in: start of playback. Fade out: end of a one-shot, or when you stop. Loop crossfade: between loop passes.">ⓘ which fade applies when</span></div>
 <div class="edrow"><button id="edprev">▶ preview edit</button><input id="edname" placeholder="name (optional)" style="flex:1;min-width:120px"><button id="edsave" class="pill">save as new</button></div>
 <div class="sub" id="edmsg">original is never modified · the new sample remembers where it came from</div>`;
 ED={i,sel:null,onsets:[],buf:null,P:null,peaks:null,base:null,view:null};
 const path=S[i][F.path];
 const [ab,on]=await Promise.all([fetch(url(path)).then(r=>r.arrayBuffer()),fetch('api/onsets?path='+encodeURIComponent(path)).then(r=>r.json()).catch(()=>({onsets:[]}))]);
 ED.buf=await AC.decodeAudioData(ab);ED.onsets=on.onsets||[];ED.sel=[0,ED.buf.duration];edDraw();
 const c=$('edc'),tx=e=>edT(e.offsetX,c.clientWidth);
 c.addEventListener('wheel',e=>{e.preventDefault();const [v0,v1]=edView(),t=tx(e),f=e.deltaY>0?1.25:0.8,d=ED.buf.duration;
  let n0=t-(t-v0)*f,n1=t+(v1-t)*f;if(n1-n0>=d){n0=0;n1=d}if(n1-n0<0.02)return;edZoom([Math.max(0,n0),Math.min(d,n1)])},{passive:false});
 const snap=t=>{if(!$('edsnap').checked||!ED.onsets.length)return t;const n=ED.onsets.reduce((a,b)=>Math.abs(b-t)<Math.abs(a-t)?b:a);return Math.abs(n-t)<0.2?n:t};
 let down=null,drag=null;c.onmousedown=e=>{drag=edHandleAt(e);if(drag)return;down=snap(tx(e));ED.sel=[down,down];edDraw()};
 c.onmousemove=e=>{if(drag){const t=tx(e),[a,b]=ED.sel;edSetEnv(drag,Math.max(0,(drag==='in'||drag==='xin'?t-a:b-t))*1000);return}
  c.style.cursor=edHandleAt(e)?'ew-resize':'crosshair';if(down==null)return;const t=tx(e);ED.sel=[Math.min(down,t),Math.max(down,t)];edDraw()};
 window.addEventListener('mouseup',()=>{if(drag){drag=null;['edxf','edfi','edfo'].forEach(id=>$(id).dispatchEvent(new Event('change')));return}
  if(down==null)return;down=null;ED.sel=[snap(ED.sel[0]),snap(ED.sel[1])];if(ED.sel[1]-ED.sel[0]<0.03)ED.sel=[0,ED.buf.duration];edDraw();edChanged()},{once:false});
 c.ondblclick=e=>{const t=tx(e),b=[0,...ED.onsets,ED.buf.duration];let k=b.findIndex(x=>x>t);if(k<1)k=1;ED.sel=[b[k-1],b[k]];edDraw();
 if(ED.P&&ED.P.loop)edChanged();else edPlaySel()};
 $('edplay').onclick=edToggleSel;$('edzoom').onclick=()=>{const d=ED.buf.duration;ED.view&&(ED.view[1]-ED.view[0])<d-1e-3?edZoom(null):edZoom('sel')};$('edall').onclick=()=>{ED.sel=[0,ED.buf.duration];edDraw();edChanged()};
 ['edst','edpi','edfm','edrev','edfi','edfo','edxf'].forEach(id=>$(id).addEventListener('change',edChanged));
 $('edloop').addEventListener('change',()=>{if(ED.P){ED.P.loop=$('edloop').checked;if(!ED.P.loop){const last=ED.P.segs[ED.P.segs.length-1];ED.P.end=last?last.t0+last.len:AC.currentTime}}});
 $('edxf').oninput=()=>{$('edxfv').textContent=$('edxf').value+' ms';if(ED&&ED.P&&ED.P.mode==='sel'&&ED.P.cur)ED.P.cur.xf=+$('edxf').value/1000};
 $('edfi').addEventListener('input',()=>$('edfiv').textContent=$('edfi').value+' ms');$('edfo').addEventListener('input',()=>$('edfov').textContent=$('edfo').value+' ms');
 window.addEventListener('resize',()=>{if(ED&&ED.buf)edDraw()});
 ['edxf','edfi','edfo'].forEach(id=>$(id).addEventListener('input',()=>{edDraw();const P=ED.P;if(P&&P.mode==='sel'&&P.cur){P.cur.fin=+$('edfi').value/1000;P.cur.fout=+$('edfo').value/1000}}));
 const foMode=()=>{const L=$('edloop').checked;$('edfol').textContent=L?'Fade out (on stop)':'Fade out';
  [$('edfol'),$('edfo'),$('edfov')].forEach(x=>x.style.opacity=L?.55:1);$('edfo').title=L?'While looping, passes use the loop crossfade; this fade applies when you stop or turn loop off.':''};
 foMode();$('edloop').addEventListener('change',()=>{foMode();edDraw()});
 $('edst').oninput=()=>$('edstv').textContent=(+$('edst').value).toFixed(2)+'×';
 $('edpi').oninput=()=>$('edpiv').textContent=(+$('edpi').value>0?'+':'')+$('edpi').value+' st';
 $('edprev').onclick=edPreview;$('edsave').onclick=edSave}
function edButtons(){if(!$('edprev'))return;const m=ED&&ED.P&&ED.P.mode;
 $('edprev').textContent=m==='prev'?'■ stop preview':'▶ preview edit';$('edprev').classList.toggle('playing',m==='prev');
 $('edplay').textContent=m==='sel'?'■ stop':'▶ selection';$('edplay').classList.toggle('playing',m==='sel')}
function edParams(){return{start:+ED.sel[0].toFixed(3),end:+ED.sel[1].toFixed(3),stretch:+$('edst').value,semis:+$('edpi').value,
 formant:$('edfm').checked,reverse:$('edrev').checked,fade_in:+$('edfi').value,fade_out:+$('edfo').value,normalize:true,loop_xfade:$('edloop').checked?+$('edxf').value:0}}
function edDraw(){const c=$('edc');if(!c||!ED||!ED.buf)return;const dpr=window.devicePixelRatio||1,W=Math.round(c.clientWidth*dpr),H=Math.round(120*dpr);
 if(c.width!==W||c.height!==H){c.width=W;c.height=H;ED.peaks=null}
 const base=ED.base||(ED.base=document.createElement('canvas'));base.width=W;base.height=H;const g=base.getContext('2d');
 const d0=ED.buf.getChannelData(0),d1=ED.buf.numberOfChannels>1?ED.buf.getChannelData(1):d0,sr=ED.buf.sampleRate,[v0,v1]=edView();
 if(!ED.peaks){ED.peaks=[];const s0=v0*sr,step=(v1-v0)*sr/W;for(let x=0;x<W;x++){let mn=0,mx=0;const k0=Math.floor(s0+x*step),k1=Math.max(k0+1,Math.floor(s0+(x+1)*step));
  for(let k=k0;k<Math.min(d0.length,k1);k++){const v=(d0[k]+d1[k])/2;if(v<mn)mn=v;if(v>mx)mx=v}ED.peaks.push([mn,mx])}}
 const [a,b]=ED.sel,X=t=>edX(t,W),e=edEnv(),top=6*dpr,bot=H-14*dpr,mid=(top+bot)/2,amp=(bot-top)/2;
 const gain=t=>{if(t<a||t>b)return 1;const gi=e.fin>0?Math.min(1,(t-a)/e.fin):1,tail=e.loop?e.xf:e.fout,go=tail>0?Math.min(1,(b-t)/tail):1;return Math.min(gi,go)};
 g.clearRect(0,0,W,H);g.fillStyle='rgba(224,164,88,.10)';g.fillRect(X(a),0,X(b)-X(a),H);
 ED.peaks.forEach(([mn,mx],x)=>{const t=edT(x/dpr,W/dpr),inS=t>=a&&t<=b,k=inS?gain(t):1;g.fillStyle=inS?'#8cc0da':'#3f4e58';
  g.fillRect(x,mid-mx*amp*k,1,Math.max(1,(mx-mn)*amp*k))});
 g.fillStyle='rgba(255,255,255,.28)';ED.onsets.forEach(t=>g.fillRect(X(t),H-7*dpr,1*dpr,7*dpr));
 g.fillStyle='#e0a458';[a,b].forEach(t=>g.fillRect(X(t)-1*dpr,0,2*dpr,H));
 const line=(x0,y0,x1,y1,col,dash)=>{g.save();g.strokeStyle=col;g.lineWidth=1.5*dpr;g.setLineDash(dash?[4*dpr,3*dpr]:[]);g.beginPath();g.moveTo(x0,y0);g.lineTo(x1,y1);g.stroke();g.restore()};
 if(e.fin>0)line(X(a),bot,X(a+e.fin),top,'#ffffff');
 if(e.loop){if(e.fout>0)line(X(b-e.fout),top,X(b),bot,'rgba(255,255,255,.45)',true);
  if(e.xf>0){line(X(b-e.xf),top,X(b),bot,'#e0a458');line(X(a),bot,X(a+e.xf),top,'#e0a458',true)}}
 else if(e.fout>0)line(X(b-e.fout),top,X(b),bot,'#ffffff');
 edKnobs().forEach(k=>{g.beginPath();g.arc(X(k.t),top,(k.small?4:6)*dpr,0,Math.PI*2);g.fillStyle=k.col;g.fill();g.lineWidth=2*dpr;g.strokeStyle='#101317';g.stroke()});
 $('edsel').textContent=`selection ${a.toFixed(2)}–${b.toFixed(2)} s (${(b-a).toFixed(2)} s) · fade in ${Math.round(e.fin*1000)} ms · `+
  (e.loop?`loop crossfade ${Math.round(e.xf*1000)} ms`:`fade out ${Math.round(e.fout*1000)} ms`)+(e.loop?` · fade out on stop ${Math.round(e.fout*1000)} ms`:'')+` · drag knobs to adjust`;
 edPaint()}
function edView(){const d=ED.buf.duration,v=ED.view||[0,d];return [Math.max(0,v[0]),Math.min(d,v[1])]}
function edX(t,W){const [v0,v1]=edView();return (t-v0)/(v1-v0)*W}
function edT(px,W){const [v0,v1]=edView();return Math.max(0,Math.min(ED.buf.duration,v0+px/W*(v1-v0)))}
function edZoom(to){const d=ED.buf.duration;if(to==='sel'){const [a,b]=ED.sel,m=Math.max(0.05,(b-a)*0.12);ED.view=[a-m,b+m]}else ED.view=to;
 ED.peaks=null;edDraw();if($('edzoom'))$('edzoom').textContent=ED.view&&(ED.view[1]-ED.view[0])<d-1e-3?'🔍 zoom out':'🔍 zoom to selection'}
function edEnv(){const [a,b]=ED.sel,len=b-a,loop=$('edloop').checked,cap=v=>Math.max(0,Math.min(v,len/2-0.002));
 return{loop,fin:cap(+$('edfi').value/1000),fout:cap(+$('edfo').value/1000),xf:cap(+$('edxf').value/1000)}}
function edKnobs(){const e=edEnv(),[a,b]=ED.sel;const k=[{id:'in',t:a+e.fin,col:'#ffffff'}];
 if(e.loop){k.push({id:'xout',t:b-e.xf,col:'#e0a458'},{id:'xin',t:a+e.xf,col:'#e0a458',small:true})}else k.push({id:'out',t:b-e.fout,col:'#ffffff'});return k}
function edHandleAt(ev){const c=$('edc');if(ev.offsetY>24)return null;let best=null,bd=10;
 edKnobs().forEach(k=>{const d=Math.abs(ev.offsetX-edX(k.t,c.clientWidth));if(d<bd){bd=d;best=k.id}});return best}
function edSetEnv(which,ms){const el={in:$('edfi'),out:$('edfo'),xin:$('edxf'),xout:$('edxf')}[which],st=+el.step||1;
 el.value=Math.round(ms/st)*st;el.dispatchEvent(new Event('input'))}
function edPaint(pos){const c=$('edc');if(!c||!ED||!ED.base)return;const g=c.getContext('2d');g.clearRect(0,0,c.width,c.height);g.drawImage(ED.base,0,0);
 if(pos==null)return;const dpr=window.devicePixelRatio||1,x=edX(pos,c.width);if(x<0||x>c.width)return;g.fillStyle='#fff';g.fillRect(x-dpr,0,2*dpr,c.height);g.fillStyle='rgba(255,255,255,.12)';g.fillRect(x-6*dpr,0,5*dpr,c.height)}
// one sample-accurate loop player for both the selection and the rendered preview
const eqIn=n=>Float32Array.from({length:n},(_,k)=>Math.sin(k/(n-1)*Math.PI/2)),eqOut=n=>Float32Array.from({length:n},(_,k)=>Math.cos(k/(n-1)*Math.PI/2));
function lpGrain(P,when,pass,first,last){const len=pass.b-pass.a,ov=P.loop&&!last?Math.min(pass.xf,len/3):0,
 fin=first?Math.max(0.004,pass.fin):Math.min(pass.xf,len/3),fout=last?Math.max(0.004,pass.fout):ov;
 const g=AC.createGain(),src=AC.createBufferSource();src.buffer=pass.buf;src.connect(g);g.connect(AC.destination);
 const fi=Math.min(fin,len/2-0.002),fo=Math.min(fout,len/2-0.002);
 if(fi>0.001)g.gain.setValueCurveAtTime(eqIn(64),when,fi);else g.gain.setValueAtTime(1,when);
 if(fo>0.001)g.gain.setValueCurveAtTime(eqOut(64),when+len-fo,fo);
 src.start(when,pass.a,len);const v={src,g};P.voices.push(v);src.onended=()=>{P.voices=P.voices.filter(x=>x!==v)};
 P.segs.push({t0:when,len,map:pass.map});if(P.segs.length>8)P.segs.shift();return len-ov}
function lpSchedule(){const P=ED&&ED.P;if(!P)return;
 if(P.pending&&(!P.loop||P.next<=AC.currentTime+0.35)){P.cur=P.pending;P.pending=null;if(P.onSwitch)P.onSwitch()}
 if(!P.loop){if(!P.segs.length){const len=lpGrain(P,P.next,P.cur,true,true);P.end=P.next+len}
  if(AC.currentTime>P.end+0.05){ED.P=null;edButtons();drawNP();edPaint();return}P.timer=setTimeout(lpSchedule,60);return}
 while(P.next<AC.currentTime+0.35){if(P.pending){P.cur=P.pending;P.pending=null;if(P.onSwitch)P.onSwitch()}
  P.next+=Math.max(0.03,lpGrain(P,P.next,P.cur,!P.segs.length,false))}
 P.timer=setTimeout(lpSchedule,60)}
function lpStart(mode,pass,label){stopAll();AC.resume();
 ED.P={mode,loop:$('edloop').checked,next:AC.currentTime+0.03,cur:pass,pending:null,segs:[],voices:[],timer:null};
 lpSchedule();setNP(S[ED.i][F.path],S[ED.i][F.id],label,ED.i);edButtons();requestAnimationFrame(edTick)}
function selPass(){const [a,b]=ED.sel;return{buf:ED.buf,a,b,map:t=>a+t,fin:+$('edfi').value/1000,fout:+$('edfo').value/1000,xf:+$('edxf').value/1000}}
function prevPass(buf,p){return{buf,a:0,b:buf.duration,fin:0.004,fout:0.004,xf:0,
 map:t=>{const src=Math.min(t/p.stretch,p.end-p.start);return p.reverse?p.end-src:p.start+src}}}
function edPos(){const P=ED&&ED.P;if(!P)return null;const now=AC.currentTime,seg=[...P.segs].reverse().find(x=>x.t0<=now);
 if(!seg)return null;const t=now-seg.t0;return t<=seg.len?seg.map(t):null}
function edTick(){if(!ED||!ED.P){edPaint();return}const p=edPos();edPaint(p);requestAnimationFrame(edTick)}
function edToggleSel(){if(ED&&ED.P&&ED.P.mode==='sel'){edStop();return}edPlaySel()}
function edPlaySel(){const [a,b]=ED.sel;lpStart('sel',selPass(),`selection ${a.toFixed(2)}–${b.toFixed(2)} s of `+lbl(ED.i))}
function pvPlaying(){return !!(ED&&ED.P&&ED.P.mode==='prev')}
async function edRender(params){const r=await (await fetch('api/edit/preview',{method:'POST',body:JSON.stringify({path:S[ED.i][F.path],params})})).json();
 if(r.error)throw new Error(r.error);const ab=await (await fetch(url(r.url)+'?t='+Date.now())).arrayBuffer();return AC.decodeAudioData(ab)}
async function edPreview(){if(pvPlaying()){edStop();$('edmsg').textContent='stopped';return}
 $('edmsg').textContent='rendering…';const params=edParams();
 try{const buf=await edRender(params);lpStart('prev',prevPass(buf,params),'preview: edit of '+lbl(ED.i));
  $('edmsg').textContent='previewing — change anything and it updates after this pass'}
 catch(e){$('edmsg').textContent='error: '+e.message}}
let pvTimer=null,pvSeq=0;
function edChanged(){if(!ED||!ED.P)return;
 if(ED.P.mode==='sel'){ED.P.pending=selPass();return}
 clearTimeout(pvTimer);pvTimer=setTimeout(edQueuePreview,250)}
async function edQueuePreview(){const seq=++pvSeq,params=edParams();$('edmsg').textContent='rendering the change…';
 try{const buf=await edRender(params);if(seq!==pvSeq||!pvPlaying())return;
  ED.P.pending=prevPass(buf,params);ED.P.onSwitch=()=>{$('edmsg').textContent='now playing the updated preview'};
  $('edmsg').textContent=ED.P.loop?'updated preview queued — plays after this pass':'updated — press preview again to hear it'}
 catch(e){$('edmsg').textContent='error: '+e.message}}
function edQueueSel(){if(ED&&ED.P&&ED.P.mode==='sel')ED.P.pending=selPass()}
async function edSave(){$('edmsg').textContent='saving (analysing for related-sample matches)…';
 const i=ED.i,p=S[i];const r=await (await fetch('api/edit/save',{method:'POST',body:JSON.stringify({path:p[F.path],params:edParams(),name:$('edname').value,label:lbl(i)})})).json();
 if(r.error){$('edmsg').textContent='error: '+r.error;return}const n=r.row,row=p.slice();
 Object.assign(row,{[F.id]:n.id,[F.path]:n.path,[F.sub]:n.subtype,[F.kind]:n.kind,[F.cam]:n.cam,[F.key]:n.key,[F.bpm]:n.bpm,[F.dur]:n.dur,
  [F.env]:n.env,[F.note]:n.note,[F.bars]:n.bars,[F.start]:n.start,[F.parent]:n.parent,[F.root]:n.root,[F.ops]:n.ops});
 const j=S.push(row)-1;P.push(P[i]);BYID.set(n.id,j);byPath.set(n.path,j);(BYTRACK.get(row[F.tid])||[]).push(j);
 FAV.set(n.path,{path:n.path,sample_id:n.id,label:'edit of '+lbl(i),added_at:new Date().toISOString()});
 edStop();select(j,'go')}
// ---------- source focus (show only some tracks' samples)
function showTracks(ids,{group='type'}={}){st.tracks=new Set(ids.map(String));st.tab='S';Object.values(tabs).forEach(t=>$(t).classList.toggle('on',t==='tabS'));
 st.excl=new Set();if(group)$('grp').value=group;st.shown=500;history.replaceState(null,'','#tracks='+ids.join(','));render()}
function clearTracks(){st.tracks=null;history.replaceState(null,'',location.pathname);
 st.excl=new Set((()=>{try{const v=localStorage.getItem('atlasExcl');return v?JSON.parse(v):['Electronic']}catch(e){return['Electronic']}})());$('grp').value='';render()}
function drawBanner(){const b=$('tbanner');if(!st.tracks||st.tab!=='S'){b.hidden=true;return}const ids=[...st.tracks],n=S.filter(s=>st.tracks.has(String(s[F.tid]))).length;
 const names=ids.map(t=>D.tracks[t]?`${D.tracks[t][1]} – ${D.tracks[t][2]}`:t);
 b.hidden=false;b.innerHTML=`Showing <b>${n}</b> samples from ${esc(names.slice(0,3).join(' · '))}${names.length>3?` +${names.length-3} more`:''} &nbsp;<button id="tclear">✕ clear</button>`;$('tclear').onclick=clearTracks}
// ---------- per-clip export
const XPKEY='atlasExportName';
function xpName(){try{return localStorage.getItem(XPKEY)||'Clips'}catch(e){return 'Clips'}}
function setXpName(v){try{localStorage.setItem(XPKEY,v||'Clips')}catch(e){}}
function toast(msg){const t=$('toast');t.textContent=msg;t.hidden=false;clearTimeout(toast.t);toast.t=setTimeout(()=>t.hidden=true,2200)}
const xp=path=>`<button class="xp" data-xp="${esc(path)}" title="export this clip to Ableton (${esc(xpName())})">⇩</button>`;
async function exportOne(path,btn){if(!SERVED){toast('export needs the local server');return}
 const r=await (await fetch('api/export',{method:'POST',body:JSON.stringify({scope:'paths',paths:[path],name:xpName(),reveal:false})})).json();
 if(r.error||!r.count){toast('export failed'+(r.error?': '+r.error:''));return}
 document.querySelectorAll(`[data-xp="${CSS.escape(path)}"]`).forEach(b=>{b.classList.add('done');b.textContent='✓'});toast(`exported to ${xpName()} ✓`)}
document.addEventListener('click',e=>{const b=e.target.closest('[data-xp]');if(!b)return;e.stopPropagation();exportOne(b.dataset.xp,b)},true);
// ---------- add source / export
function modal(html){$('modalBody').innerHTML=html;$('modal').hidden=false}
$('modal').addEventListener('click',e=>{if(e.target.id==='modal'||e.target.dataset.close!=null)$('modal').hidden=true});
let jobTimer=null;
async function pollJobs(){const js=await (await fetch('api/jobs')).json();const el=$('jobs');if(!el){clearInterval(jobTimer);return}
 el.innerHTML=js.slice(-3).reverse().map(j=>`<div class="prov"><b>${esc(j.target)}</b> — ${j.running?'running…':j.ok?'<span style="color:var(--acc)">done</span>':'stopped'}
  <div class="meta" style="white-space:pre-wrap">${j.tail.map(esc).join('\n')}</div>${!j.running&&j.ok&&j.tracks?`<button class="pill" onclick="location.hash='tracks=${j.tracks}';location.reload()">show the new samples →</button>`:''}</div>`).join('')}
$('addsrc').onclick=()=>{if(!SERVED){alert('needs the local server');return}
 modal(`<h2 style="margin:0">Add a source</h2><div class="sub">A YouTube (or other) URL, an audio file path, or a folder path. It is downloaded / catalogued, mined for vocals, pads and textures (and optionally percussion), then the library is rebuilt.</div>
 <input id="srcIn" placeholder="https://www.youtube.com/watch?v=…   or   /path/to/song.mp3   or   /path/to/folder" style="width:100%">
 <label class="sub"><input type="checkbox" id="srcDrums"> also mine percussion (slower)</label>
 <div class="edrow"><button id="srcGo" class="pill">start</button><button data-close>close</button></div><div id="jobs"></div>`);
 $('srcGo').onclick=async()=>{const t=$('srcIn').value.trim();if(!t)return;await fetch('api/ingest',{method:'POST',body:JSON.stringify({target:t,drums:$('srcDrums').checked})});$('srcIn').value='';pollJobs()};
 pollJobs();clearInterval(jobTimer);jobTimer=setInterval(pollJobs,2500)};
$('expbtn').onclick=()=>{if(!SERVED){alert('needs the local server');return}
 const scope=st.tab==='F'?'favorites':'list',ids=st.tab==='F'?[...FAV.keys()]:filtered().slice(0,500).map(i=>S[i][F.path]);
 modal(`<h2 style="margin:0">Export to Ableton</h2><div class="sub">${ids.length} ${scope==='favorites'?'favourites':'samples from the current list'}${scope!=='favorites'&&filtered().length>500?' (first 500)':''} → <code>User Library/Samples/DigitalCrate/&lt;name&gt;/&lt;category&gt;/&lt;subtype&gt;/</code>, with an _info.csv of keys, tempos and sources. Live's browser shows it under User Library.</div>
 <input id="expName" placeholder="export name (e.g. Night session)" style="width:100%"><div class="edrow"><button id="expGo" class="pill">export</button><button data-close>close</button></div><div id="expMsg" class="sub"></div>`);
 $('expGo').onclick=async()=>{$('expMsg').textContent='copying…';const r=await (await fetch('api/export',{method:'POST',body:JSON.stringify(scope==='favorites'?{scope,name:$('expName').value}:{scope:'paths',paths:ids,name:$('expName').value})})).json();
  $('expMsg').textContent=r.error?'error: '+r.error:`exported ${r.count} files to ${r.dest} (opened in Finder)`}};
// ---------- audio
const players=new Map();
function stopAll(){if(typeof edStop==='function')edStop();setTimeout(()=>{if(typeof edButtons==='function')edButtons()},0);players.forEach((a,k)=>{a.pause();endListen(k,a)});players.clear();document.querySelectorAll('.play.playing').forEach(b=>b.classList.remove('playing'))}
function toggle(i,btn,{loop=true,exclusive=true}={}){
 if(players.has(i)){const a=players.get(i);a.pause();endListen(i,a);players.delete(i);mark();return}
 if(exclusive)stopAll();
 const a=new Audio(url(S[i][F.path]));a.loop=loop&&S[i][F.kind]!=='oneshot';a.onended=()=>{endListen(i,a);players.delete(i);mark()};
 a.play();players.set(i,a);beginListen(i,S[i][F.path]);setNP(S[i][F.path],S[i][F.id],lbl(i),i);mark()}
function playTogether(ids){stopAll();const as=ids.map(i=>{const a=new Audio(url(S[i][F.path]));a.loop=S[i][F.kind]!=='oneshot';a.volume=.8;players.set(i,a);return a});
 setNP(S[ids[ids.length-1]][F.path],S[ids[ids.length-1]][F.id],'together: '+ids.map(i=>S[i][F.artist]).join(' + '),ids[ids.length-1]);
 Promise.all(as.map(a=>new Promise(r=>{a.oncanplaythrough=r;a.load()}))).then(()=>{as.forEach(a=>a.play());mark()})}
function mark(){drawNP();document.querySelectorAll('[data-play]').forEach(b=>b.classList.toggle('playing',players.has(+b.dataset.play)))}
// ---------- filters
const CATS=[...new Set(S.map(s=>s[F.cat]))], KINDS=['loop','phrase','free','oneshot'];
const MOODS=[...new Set(S.flatMap(s=>s[F.tags]))].sort();
function chips(el,items,set,label=x=>x){el.innerHTML=items.map(x=>`<button data-v="${esc(x)}">${esc(label(x))}</button>`).join('');
 el.onclick=e=>{const v=e.target.dataset.v;if(v==null)return;set.has(v)?set.delete(v):set.add(v);e.target.classList.toggle('on');st.shown=200;render()}}
chips($('cats'),CATS,st.cats,c=>`${c} (${S.filter(s=>s[F.cat]===c).length})`);
chips($('kinds'),KINDS,st.kinds);
function drawSubs(){const box=$('subsBox');if(!st.cats.size){box.hidden=true;st.subs.clear();return}box.hidden=false;
 const cnt={};S.forEach(s=>{if(st.cats.has(s[F.cat]))cnt[s[F.sub]]=(cnt[s[F.sub]]||0)+1});
 [...st.subs].forEach(x=>{if(!cnt[x])st.subs.delete(x)});
 $('subs').innerHTML=Object.keys(cnt).sort((a,b)=>cnt[b]-cnt[a]).map(x=>`<button data-v="${esc(x)}" class="${st.subs.has(x)?'on':''}">${esc(x)} (${cnt[x]})</button>`).join('')}
$('subs').onclick=e=>{const v=e.target.dataset.v;if(v==null)return;st.subs.has(v)?st.subs.delete(v):st.subs.add(v);e.target.classList.toggle('on');st.shown=200;render()};
$('cats').addEventListener('click',()=>setTimeout(()=>{drawSubs();render()},0));
const GENRES=[...new Set(S.map(s=>s[F.genre]))].sort((a,b)=>S.filter(s=>s[F.genre]===b).length-S.filter(s=>s[F.genre]===a).length);
chips($('genres'),GENRES,st.genres,g=>`${g} (${S.filter(s=>s[F.genre]===g).length})`);
st.excl=new Set((()=>{try{const v=localStorage.getItem('atlasExcl');return v?JSON.parse(v):['Electronic']}catch(e){return['Electronic']}})());
$('excl').innerHTML=GENRES.map(g=>`<label class="sub" style="white-space:nowrap"><input type="checkbox" data-ex="${esc(g)}" ${st.excl.has(g)?'checked':''}> ${esc(g)}</label>`).join('');
$('excl').onchange=e=>{const g=e.target.dataset.ex;if(!g)return;e.target.checked?st.excl.add(g):st.excl.delete(g);
 try{localStorage.setItem('atlasExcl',JSON.stringify([...st.excl]))}catch(err){}st.shown=200;render();if(st.sel!=null)select(st.sel,'back')};chips($('moods'),MOODS,st.moods);
function camNbrs(c){const n=+c.slice(0,-1),l=c.slice(-1),o=l==='A'?'B':'A',w=k=>((k+11)%12)+1;return new Set([c,`${w(n-1)}${l}`,`${w(n+1)}${l}`,`${n}${o}`])}
// Camelot wheel
(function(){const names={B:['B','F#','Db','Ab','Eb','Bb','F','C','G','D','A','E'],A:['Abm','Ebm','Bbm','Fm','Cm','Gm','Dm','Am','Em','Bm','F#m','Dbm']};
 let h='';for(const [ring,r0,r1] of [['B',70,105],['A',38,70]])for(let k=0;k<12;k++){const a0=(k-0.5)/12*2*Math.PI-Math.PI/2,a1=(k+0.5)/12*2*Math.PI-Math.PI/2;
 const p=(r,a)=>`${(r*Math.cos(a)).toFixed(1)},${(r*Math.sin(a)).toFixed(1)}`;const code=`${k+1}${ring}`;
 h+=`<path data-c="${code}" d="M${p(r0,a0)}A${r0},${r0} 0 0 1 ${p(r0,a1)}L${p(r1,a1)}A${r1},${r1} 0 0 0 ${p(r1,a0)}Z"/>`;
 const am=k/12*2*Math.PI-Math.PI/2,rm=(r0+r1)/2;h+=`<text x="${(rm*Math.cos(am)).toFixed(1)}" y="${(rm*Math.sin(am)+3).toFixed(1)}" text-anchor="middle">${code}</text>`;
 h+=`<title>${names[ring][k]}</title>`}
 $('wheel').innerHTML=h;$('wheel').onclick=e=>{const c=e.target.dataset.c;if(!c)return;st.key=st.key===c?null:c;st.shown=200;render()}})();
function paintWheel(){const cnt={};S.forEach(s=>{if(s[F.cam])cnt[s[F.cam]]=(cnt[s[F.cam]]||0)+1});const mx=Math.max(1,...Object.values(cnt));
 const nb=st.key?(st.nbr?camNbrs(st.key):new Set([st.key])):null;
 document.querySelectorAll('#wheel path').forEach(p=>{const c=p.dataset.c,v=(cnt[c]||0)/mx;
 p.style.fill=nb&&nb.has(c)?(c===st.key?'#e0a458':'#8a6a3e'):`rgba(127,176,201,${0.08+v*0.6})`});
 $('keylbl').textContent=st.key?st.key:''}
$('nbr').onclick=e=>{st.nbr=!st.nbr;e.target.classList.toggle('on');render()};$('clrkey').onclick=()=>{st.key=null;render()};
['bmin','bmax','half','q','search','sort','grp'].forEach(id=>$(id).addEventListener('input',()=>{st.shown=200;render()}));
$('stop').onclick=stopAll;
$('refresh').onclick=()=>{$('refresh').hidden=true;render()};

const tabs={S:'tabS',K:'tabK',F:'tabF',R:'tabR'};
Object.entries(tabs).forEach(([k,id])=>$(id).onclick=()=>{st.tab=k;Object.values(tabs).forEach(t=>$(t).classList.toggle('on',t===id));render()});
function filtered(){const q=$('search').value.toLowerCase().trim(),mq=+$('q').value,bmin=+$('bmin').value||0,bmax=+$('bmax').value||0,half=$('half').checked;
 const nb=st.key?(st.nbr?camNbrs(st.key):new Set([st.key])):null;$('qv').textContent=mq.toFixed(2);
 const okB=b=>{if(!bmin&&!bmax)return true;if(!b)return false;const t=[b];if(half)t.push(b*2,b/2);return t.some(x=>(!bmin||x>=bmin)&&(!bmax||x<=bmax))};
 let out=[];S.forEach((s,i)=>{if(s[F.q]<mq)return;if(st.tracks&&!st.tracks.has(String(s[F.tid])))return;if(st.cats.size&&!st.cats.has(s[F.cat]))return;if(st.subs.size&&!st.subs.has(s[F.sub]))return;if(st.kinds.size&&!st.kinds.has(s[F.kind]))return;if(st.genres.size&&!st.genres.has(s[F.genre]))return;if(st.excl.has(s[F.genre]))return;
 if(nb&&!(s[F.cam]&&nb.has(s[F.cam])))return;if(!okB(s[F.kind]==='loop'?s[F.bpm]:0)&&(bmin||bmax))return;
 if(st.moods.size&&![...st.moods].every(m=>s[F.tags].includes(m)))return;
 if(q&&!(`${s[F.artist]} ${s[F.title]} ${s[F.tags].join(' ')} ${s[F.inst]} ${s[F.id]} ${s[F.cat]} ${s[F.sub]} ${s[F.genre]}`.toLowerCase().includes(q)))return;out.push(i)});
 out=out.filter(i=>!TASTE.disliked.has(S[i][F.path]));
 const k=$('sort').value;
 const tsort=m=>(a,b)=>((m[S[b][F.path]]??-9)-(m[S[a][F.path]]??-9));
 if(k==='div'){const by=new Map();out.sort((a,b)=>S[b][F.q]-S[a][F.q]||((TASTE.score[S[b][F.path]]??0)-(TASTE.score[S[a][F.path]]??0)));
  out.forEach(i=>{const a=S[i][F.artist];if(!by.has(a))by.set(a,[]);by.get(a).push(i)});
  const lists=[...by.values()].sort((x,y)=>(TASTE.score[S[y[0]][F.path]]??S[y[0]][F.q])-(TASTE.score[S[x[0]][F.path]]??S[x[0]][F.q]));
  const rr=[];for(let r=0;rr.length<out.length;r++)lists.forEach(l=>{if(l[r]!=null)rr.push(l[r])});return rr}
 if(k==='you')return out.sort(tsort(TASTE.score));if(k==='vibe')return out.sort(tsort(TASTE.vibe));if(k==='disc')return out.sort(tsort(TASTE.discover));
 const cmp={q:(a,b)=>S[b][F.q]-S[a][F.q],key:(a,b)=>(S[a][F.cam]||'zz').localeCompare(S[b][F.cam]||'zz',undefined,{numeric:true}),
 bpm:(a,b)=>S[a][F.bpm]-S[b][F.bpm],dur:(a,b)=>S[b][F.dur]-S[a][F.dur],ref:(a,b)=>S[b][F.ref]-S[a][F.ref],new:(a,b)=>((D.tracks[S[b][F.tid]]||[0])[0]-(D.tracks[S[a][F.tid]]||[0])[0])||S[b][F.q]-S[a][F.q],var:(a,b)=>((D.variants[b]||[]).length-(D.variants[a]||[]).length)||S[b][F.q]-S[a][F.q],rnd:()=>Math.random()-.5}[k];return out.sort(cmp)}
function rowHTML(i){const s=S[i],c=col(s[F.cat]);const bpm=s[F.bpm]?`${s[F.bpm]} bpm`:'free';
 const kind=s[F.kind]==='loop'?`${s[F.bars]}-bar loop`:s[F.kind];
 return `<div class="row${st.sel===i?' sel':''}" data-i="${i}"><button class="play" data-play="${i}">▶</button>${wave(s[F.env],120,26,'#5b6370')}
 <div style="min-width:0"><div class="name"><span class="badge" style="background:${c}">${AB[s[F.cat]]}</span>${esc(s[F.sub])} · ${esc(kind)}${D.variants[i]?` · <span style="color:var(--acc)">${D.variants[i].length} variations</span>`:''}${s[F.parent]?` · <span style="color:var(--acc)">✎ edit</span>`:''}${s[F.note]?` · ${s[F.note]}`:''} · ${s[F.dur]}s
 ${s[F.tags].map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div>
 <div class="meta">${esc(s[F.artist])} — ${esc(s[F.title])} @ ${Math.floor(s[F.start]/60)}:${String(s[F.start]%60).padStart(2,'0')}</div></div>
 <div class="right">${star(s[F.path],s[F.id],`${s[F.artist]} — ${s[F.title]} · ${s[F.sub]}`)}${nope(s[F.path],s[F.id])}${xp(s[F.path])}<span class="id" data-id="${s[F.id]}" title="copy ID">${s[F.id]}</span><span>${bpm}</span><span class="key">${s[F.cam]?`${s[F.cam]} ${s[F.key]}`:'—'}</span><span class="qbar" title="quality ${s[F.q]}"><i style="width:${s[F.q]*100}%"></i></span></div></div>`}
const OVR=new Set((D.overridden||[]).map(i=>S[i][F.id]));
const BYID=new Map(S.map((s,i)=>[s[F.id],i]));
const BYTRACK=new Map();S.forEach((s,i)=>{if(!BYTRACK.has(s[F.tid]))BYTRACK.set(s[F.tid],[]);BYTRACK.get(s[F.tid]).push(i)});
BYTRACK.forEach(l=>l.sort((a,b)=>S[a][F.start]-S[b][F.start]||S[b][F.dur]-S[a][F.dur]));
const byPath=new Map(S.map((s,i)=>[s[F.path],i]));
function render(){paintWheel();const L=$('list');$('refresh').hidden=true;drawBanner();
 if(st.tab==='R'){const cnt={};S.forEach(s=>cnt[s[F.tid]]=(cnt[s[F.tid]]||0)+1);
  const tr=Object.entries(D.tracks).filter(([t])=>cnt[t]).sort((a,b)=>b[1][0]-a[1][0]).slice(0,60);
  $('count').textContent='recently processed sources';
  L.innerHTML=tr.map(([t,[ep,ar,ti,kind]])=>`<div class="row" style="grid-template-columns:1fr auto;cursor:default"><div style="min-width:0"><div class="name">${kind?`<span class="badge" style="background:var(--acc)">${esc(kind)}</span>`:''}${esc(ar)} — ${esc(ti)}</div>
   <div class="meta">${ep?new Date(ep*1000).toLocaleString():''} · ${cnt[t]} samples</div></div><button data-showt="${t}">show samples →</button></div>`).join('');return}
 if(st.tab==='F'){const favs=[...FAV.values()].sort((a,b)=>(b.added_at||'').localeCompare(a.added_at||''));
  $('count').textContent=`${favs.length} favourites`+(SERVED?' · also in SampleLibrary/Favorites':' · run "python -m digitalcrate serve" to sync them to Ableton');
  L.innerHTML=favs.length?favs.map(f=>{const i=byPath.get(f.path);if(i!=null)return rowHTML(i);
   return `<div class="row" style="cursor:default"><button class="play" data-vp2="${esc(f.path)}">▶</button><span class="sub">variation</span>
   <div style="min-width:0"><div class="name">${esc(f.label||f.path)}</div><div class="meta">${esc(f.path)}</div></div><div class="right">${star(f.path,f.sample_id,f.label)}</div></div>`}).join('')
   :'<div class="empty">No favourites yet — click ★ on any sample or variation.</div>';mark();return}
 if(st.tab==='K'){$('count').textContent=`${D.kits.length} kits`;
  L.innerHTML=D.kits.length?D.kits.map((k,ki)=>`<div class="kit"><h3><span>${esc(k.name)}</span><button data-kit="${ki}">▶ play together</button> <button data-kitexp="${esc(k.name)}">⇩ export</button></h3>${k.m.map(rowHTML).join('')}</div>`).join(''):'<div class="empty">No kits yet.</div>';return}
 const ids=filtered();$('count').textContent=`${ids.length.toLocaleString()} of ${S.length.toLocaleString()} samples`+(st.excl.size?` · excluding ${[...st.excl].join(', ')}`:'')+(SERVED?` · taste model: ${TASTE.n} ratings`:'');
 const gm=$('grp').value;
 if(gm&&ids.length){const keyOf={track:i=>S[i][F.artist]+' — '+S[i][F.title],type:i=>S[i][F.cat]+' / '+S[i][F.sub],genre:i=>S[i][F.genre]}[gm];
  const per=gm==='track'?3:6,g=new Map();ids.forEach(i=>{const k=keyOf(i);if(!g.has(k))g.set(k,[]);g.get(k).push(i)});
  let groups=[...g.entries()];if(gm!=='track')groups.sort((a,b)=>b[1].length-a[1].length);
  const shownGroups=gm==='track'?groups.slice(0,Math.ceil(st.shown/3)):groups;
  L.innerHTML=shownGroups.map(([k,l])=>{const open=st.open.has(gm+k),lim=open?Math.min(l.length,60):per;
   return `<div class="kit"><h3><span>${esc(k)}</span><span class="sub">${l.length} samples ${l.length>per?`<button data-grp="${esc(gm+k)}">${open?'collapse':'show more'}</button>`:''}</span></h3>${l.slice(0,lim).map(rowHTML).join('')}</div>`}).join('')
   +(gm==='track'&&g.size>shownGroups.length?`<button class="more" id="more">show more tracks</button>`:'');mark();return}
 L.innerHTML=ids.length?ids.slice(0,st.shown).map(rowHTML).join('')+(ids.length>st.shown?`<button class="more" id="more">show more (${ids.length-st.shown})</button>`:''):'<div class="empty">Nothing matches these filters.</div>';mark()}
$('list').addEventListener('click',async e=>{const stb=e.target.closest('[data-showt]');if(stb){showTracks([stb.dataset.showt]);return}const ke=e.target.closest('[data-kitexp]');if(ke){const r=await (await fetch('api/export',{method:'POST',body:JSON.stringify({scope:'kit',kit:ke.dataset.kitexp,name:ke.dataset.kitexp})})).json();ke.textContent=r.error?'error':`exported ${r.count} ✓`;return}
 const gb=e.target.closest('[data-grp]');if(gb){const k=gb.dataset.grp;st.open.has(k)?st.open.delete(k):st.open.add(k);render();return}
 const vp=e.target.closest('[data-vp2]');if(vp){stopAll();const a=new Audio(url(vp.dataset.vp2));a.play();players.set('f',a);const f=FAV.get(vp.dataset.vp2);setNP(vp.dataset.vp2,f&&f.sample_id,(f&&f.label)||vp.dataset.vp2,null);return}
 const t=e.target.closest('[data-play],[data-id],[data-kit],#more,.row');if(!t)return;
 if(t.id==='more'){st.shown+=300;render();return}
 if(t.dataset.kit!=null){playTogether(D.kits[+t.dataset.kit].m);return}
 if(t.dataset.id){navigator.clipboard&&navigator.clipboard.writeText(t.dataset.id);t.textContent='copied';setTimeout(()=>t.textContent=t.dataset.id,800);return}
 if(t.dataset.play!=null){toggle(+t.dataset.play,t);return}
 select(+t.dataset.i,'list')});
let HIST=[];
function select(i,from){edStop&&edStop();if(from==='go'&&st.sel!=null&&st.sel!==i)HIST.push({i:st.sel,scroll:$('detail').scrollTop});else if(from==='list')HIST=[];
 st.sel=i;vcur=0;document.querySelectorAll('.row').forEach(r=>r.classList.toggle('sel',+r.dataset.i===i));const s=S[i];
 const back=HIST.length?`<div style="margin-bottom:10px"><button id="back">← back to ${esc(S[HIST[HIST.length-1].i][F.artist])} — ${esc(S[HIST[HIST.length-1].i][F.title])}</button> <span class="sub">${HIST.length>1?HIST.length+' steps · ':''}Backspace</span></div>`:'';
 $('detail').innerHTML=back+`<span class="badge" style="background:${col(s[F.cat])}">${AB[s[F.cat]]}</span><span class="sub">${esc(s[F.cat])} / ${esc(s[F.sub])}</span>
 <div class="big">${esc(s[F.artist])} — ${esc(s[F.title])}</div>${wave(s[F.env],368,48,col(s[F.cat]))}
 <div style="margin:10px 0;display:flex;gap:6px;align-items:center">${star(s[F.path],s[F.id],`${s[F.artist]} — ${s[F.title]} · ${s[F.sub]}`)}<button data-play="${i}" class="play" style="width:auto;border-radius:6px;padding:4px 12px">▶ play</button><button id="edopen">✎ edit</button><button data-xp="${esc(s[F.path])}" title="export this clip to Ableton">⇩ export</button>
 <span class="sub">to <input id="xpname" value="${esc(xpName())}" style="width:110px;padding:2px 6px" title="export folder name under User Library/Samples/DigitalCrate"></span></div>
 <div class="ed" id="editor" hidden></div>
 ${provHTML(i)}
 <div class="kv"><span>Key</span><span>${s[F.cam]?`${s[F.cam]} · ${s[F.key]}`:'atonal'}${s[F.note]?` · root note ${s[F.note]}`:''}</span>
 <span>Tempo</span><span>${s[F.bpm]?s[F.bpm]+' bpm':'free'}${s[F.kind]==='loop'?` · ${s[F.bars]} bars`:''}</span><span>Length</span><span>${s[F.dur]} s · ${s[F.kind]}</span>
 <span>Sounds like</span><span>${esc(s[F.inst].replace('_',' '))}${s[F.tags].length?' · '+s[F.tags].map(esc).join(', '):''}</span><span>Category</span><span><select id="rcat">${Object.keys(D.subtypes).map(c=>`<option ${c===s[F.cat]?'selected':''}>${esc(c)}</option>`).join('')}</select>
 <select id="rsub">${D.subtypes[s[F.cat]].map(c=>`<option ${c===s[F.sub]?'selected':''}>${esc(c)}</option>`).join('')}</select>
 <button id="rsave" class="pill" hidden>save</button>${OVR.has(s[F.id])?' <span class="sub">(your correction)</span>':''}</span>
 <span>Source</span><span><a href="#" data-showt2="${s[F.tid]}">show all ${(BYTRACK.get(s[F.tid])||[]).length} samples from this track →</a></span>
 <span>Genre</span><span>${esc(s[F.genre])}</span><span>Quality</span><span>${s[F.q]}</span>
 ${s[F.refm]?`<span>Echoes</span><span>${esc(s[F.refm])} <span class="sub">(${Math.round(s[F.ref]*100)}% similar)</span></span>`:''}
 <span>ID</span><span class="id" data-id="${s[F.id]}">${s[F.id]}</span></div><div class="path">${esc(s[F.path])}</div>
 ${(D.variants[i]||[]).length?`<h2>Variations (${D.variants[i].length}) <span class="sub">← → to scroll · 0 = original</span></h2>
 <div id="vars">${[[0,'original','',s[F.path]],...D.variants[i]].map(([k,t,c,p])=>`<div class="prow vrow" data-v="${k}">
 <button class="play" data-vp="${esc(p)}" data-vk="${k}">▶</button><div style="min-width:0"><div class="name">${String(k).padStart(2,'0')} · ${esc(t.replace('_',' '))}</div>
 <div class="meta">${esc(c)}</div></div>${star(p,s[F.id],`${s[F.artist]} — ${s[F.title]} · ${String(k).padStart(2,'0')} ${t}`)}${nope(p,s[F.id])}${xp(p)}</div>`).join('')}</div>`:''}
 <h2 style="display:flex;gap:6px;align-items:center"><button data-rel="go" class="${st.rel==='go'?'on':''}">Goes well with</button><button data-rel="song" class="${st.rel==='song'?'on':''}">Same song (${(BYTRACK.get(s[F.tid])||[]).length-1})</button></h2>
 <div class="hint">${st.rel==='go'?'▶ auditions alone · ⧉ plays it together with the selected sample':'every sample cut from this track, in song order · ⧉ plays it with the selected one'}</div>
 ${st.rel==='song'?(BYTRACK.get(s[F.tid])||[]).filter(j=>j!==i).map(j=>{const t=S[j];return`<div class="prow"><button class="play" data-play="${j}">▶</button>
 <div style="min-width:0"><div class="name"><span class="badge" style="background:${col(t[F.cat])}">${AB[t[F.cat]]}</span>${Math.floor(t[F.start]/60)}:${String(t[F.start]%60).padStart(2,'0')} · ${esc(t[F.sub])} · ${t[F.dur]}s${t[F.note]?' · '+t[F.note]:''}</div>
 <div class="meta">${t[F.cam]||'—'} ${esc(t[F.key])}${t[F.tags].length?' · '+t[F.tags].map(esc).join(', '):''}</div></div>
 <div style="display:flex;gap:6px;align-items:center">${star(t[F.path],t[F.id],lbl(j))}${nope(t[F.path],t[F.id])}${xp(t[F.path])}<button data-pair="${j}" title="play together">⧉</button><button data-go="${j}" title="open">→</button></div></div>`}).join('')
 :P[i].filter(([j])=>!st.excl.has(S[j][F.genre])).map(([j,sc,h,v])=>{const t=S[j];return`<div class="prow"><button class="play" data-play="${j}">▶</button>
 <div style="min-width:0"><div class="name"><span class="badge" style="background:${col(t[F.cat])}">${AB[t[F.cat]]}</span>${t[F.cam]||'—'} ${esc(t[F.key])} · ${t[F.bpm]?t[F.bpm]:'free'} · ${t[F.dur]}s</div>
 <div class="meta">${esc(t[F.artist])} — ${esc(t[F.title])}</div></div>
 <div style="display:flex;gap:6px;align-items:center"><span class="score" title="harmony ${h} · vibe ${v}">${Math.round(sc*100)}</span>${star(t[F.path],t[F.id],lbl(j))}${nope(t[F.path],t[F.id])}${xp(t[F.path])}<button data-pair="${j}" title="play together">⧉</button><button data-go="${j}" title="open">→</button></div></div>`}).join('')}`;mark()}
let vcur=0;
function playVar(k){const rows=[...document.querySelectorAll('#vars .vrow')];if(!rows.length)return;k=Math.max(0,Math.min(rows.length-1,k));vcur=k;
 const b=rows[k].querySelector('[data-vp]');stopAll();const a=new Audio(url(b.dataset.vp));a.loop=true;a.play();players.set('v'+k,a);beginListen('v'+k,b.dataset.vp);
 if(st.sel!=null)setNP(b.dataset.vp,S[st.sel][F.id],`${S[st.sel][F.artist]} — ${S[st.sel][F.title]} · variation ${String(k).padStart(2,'0')} ${rows[k].querySelector('.name').textContent.split('·').slice(1).join('·')}`,st.sel);
 rows.forEach((r,j)=>{r.style.background=j===k?'#1f2630':'';r.querySelector('.play').classList.toggle('playing',j===k)});rows[k].scrollIntoView({block:'nearest'})}
document.addEventListener('keydown',e=>{if(e.target.tagName!=='INPUT'&&e.key==='Backspace'&&HIST.length){e.preventDefault();goBack()}});
document.addEventListener('keydown',e=>{if(e.key!==' '||['INPUT','SELECT','TEXTAREA','BUTTON'].includes(e.target.tagName))return;
 if(players.size||(ED&&ED.P)){e.preventDefault();e.stopImmediatePropagation();stopAll();if(ED)edPaint()}},true);
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;if(!document.querySelector('#vars'))return;
 if(e.key==='ArrowRight'){e.preventDefault();playVar(vcur+1)}else if(e.key==='ArrowLeft'){e.preventDefault();playVar(vcur-1)}
 else if(e.key==='0'){playVar(0)}else if(e.key===' '){e.preventDefault();stopAll();document.querySelectorAll('.vrow .play').forEach(b=>b.classList.remove('playing'))}});
function goBack(){if(!HIST.length)return;const h=HIST.pop();select(h.i,'back');$('detail').scrollTop=h.scroll}
$('detail').addEventListener('change',e=>{if(e.target.id==='xpname'){setXpName(e.target.value.trim());toast(`clips will export to ${xpName()}`);return}
 if(e.target.id==='rcat'){const c=e.target.value;
  $('rsub').innerHTML=D.subtypes[c].map(x=>`<option ${x===S[st.sel][F.sub]?'selected':''}>${esc(x)}</option>`).join('');$('rsave').hidden=false}
 else if(e.target.id==='rsub')$('rsave').hidden=false});
async function recat(i){const cat=$('rcat').value,sub=$('rsub').value;if(!SERVED){alert('needs the local server');return}
 $('rsave').textContent='saving…';const r=await (await fetch('api/recat',{method:'POST',body:JSON.stringify({id:S[i][F.id],category:cat,subtype:sub})})).json();
 if(r.error){$('rsave').textContent='error';return}const old=S[i][F.path];
 S[i][F.cat]=r.category;S[i][F.sub]=r.subtype;S[i][F.path]=r.path;byPath.delete(old);byPath.set(r.path,i);OVR.add(S[i][F.id]);
 if(FAV.has(old)){const f=FAV.get(old);FAV.delete(old);f.path=r.path;FAV.set(r.path,f)}
 const row=document.querySelector(`.row[data-i="${i}"]`);if(row)row.outerHTML=rowHTML(i);const sc=$('detail').scrollTop;select(i,'back');$('detail').scrollTop=sc}
$('detail').addEventListener('click',e=>{if(e.target.id==='back'){goBack();return}
 const s2=e.target.closest('[data-showt2]');if(s2){e.preventDefault();showTracks([s2.dataset.showt2]);return}
 if(e.target.id==='rsave'){recat(st.sel);return}
 if(e.target.id==='edopen'){openEditor(st.sel);return}
 const g2=e.target.closest('[data-go2]');if(g2){e.preventDefault();select(+g2.dataset.go2,'go');return}
 const rb=e.target.closest('[data-rel]');if(rb){st.rel=rb.dataset.rel;const sc=$('detail').scrollTop;select(st.sel,'back');$('detail').scrollTop=sc;return}
 const vb=e.target.closest('[data-vk]');if(vb){const k=+vb.dataset.vk;
 if(players.has('v'+k)){stopAll();vb.classList.remove('playing')}else playVar(k);return}
 const t=e.target.closest('[data-play],[data-pair],[data-go],[data-id]');if(!t)return;
 if(t.dataset.play!=null)toggle(+t.dataset.play,t);else if(t.dataset.pair!=null)playTogether([st.sel,+t.dataset.pair]);
 else if(t.dataset.go!=null){select(+t.dataset.go,'go');$('detail').scrollTop=0}else if(t.dataset.id){navigator.clipboard&&navigator.clipboard.writeText(t.dataset.id)}});
render();loadFavs();loadTaste();
// deep link: #edit=<id>[&sel=a,b][&fi=ms][&fo=ms][&xf=ms][&loop=0|1][&zoom=1]
(async()=>{const h=new URLSearchParams(location.hash.slice(1));if(h.get('tracks')){showTracks(h.get('tracks').split(','));return}const id=h.get('edit')||h.get('s');if(!id||!BYID.has(id))return;
 const i=BYID.get(id);select(i,'list');if(!h.get('edit'))return;await openEditor(i);
 if(h.get('loop'))$('edloop').checked=h.get('loop')==='1';[['fi','edfi'],['fo','edfo'],['xf','edxf']].forEach(([k,el])=>{if(h.get(k)){$(el).value=h.get(k);$(el).dispatchEvent(new Event('input'))}});
 if(h.get('sel')){ED.sel=h.get('sel').split(',').map(Number)}if(h.get('zoom'))edZoom('sel');edDraw()})();
</script>
<link rel="stylesheet" href="studio/studio.css"><script src="studio/studio.js"></script></body></html>"""
