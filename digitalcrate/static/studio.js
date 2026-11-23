// DigitalCrate — studio features layered on Browser.html (loaded after the main script; shares its globals).
// Project mode · sound & reference search · daily crate · galaxy · sketchpad · chop pads · MIDI · vocal tuning
// · Ableton racks · YouTube scout · Ableton Link.
(function(){
if(typeof S==='undefined'||typeof F==='undefined')return;
const KEYS24=(()=>{const B=['B','F#','Db','Ab','Eb','Bb','F','C','G','D','A','E'],A=['Abm','Ebm','Bbm','Fm','Cm','Gm','Dm','Am','Em','Bm','F#m','Dbm'];
 const o=[];for(let k=0;k<12;k++){o.push([`${k+1}A`,A[k]]);o.push([`${k+1}B`,B[k]])}return o})();
const keyFromCam=c=>(KEYS24.find(([k])=>k===c)||[])[1]||'';
const camOfKey=n=>(KEYS24.find(([,k])=>k===n)||[])[0]||'';
const catColor=c=>getComputedStyle(document.documentElement).getPropertyValue('--'+AB[c]).trim()||'#888';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path,body){const r=await fetch(path,body?{method:'POST',body:JSON.stringify(body)}:undefined);const j=await r.json();if(j&&j.error)throw new Error(j.error);return j}

// ================= project mode =================
const PROJ=Object.assign({on:false,key:'',bpm:0,link:false,linkTransport:false},(()=>{try{return JSON.parse(localStorage.getItem('atlasProj')||'{}')}catch(e){return{}}})());
window.PROJ=PROJ;
const conformURL=(path,key,bpm)=>`api/conform?path=${encodeURIComponent(path)}&key=${encodeURIComponent(key||'')}&bpm=${bpm||''}`;
const purl=path=>PROJ.on&&SERVED&&(PROJ.key||PROJ.bpm)?conformURL(path,PROJ.key,PROJ.bpm):url(path);
const projTag=()=>PROJ.on&&(PROJ.key||PROJ.bpm)?` → ${[PROJ.key,PROJ.bpm?PROJ.bpm+' bpm':''].filter(Boolean).join(' · ')}`:'';
function setProj(patch){const before=PROJ.key+'|'+PROJ.bpm;Object.assign(PROJ,patch);try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(e){}
 drawProj();if(PROJ.key+'|'+PROJ.bpm!==before){skReload();if(st.sel!=null&&$('pjinfo'))projInfo(st.sel)}}
const top=document.querySelector('.top');
top.insertAdjacentHTML('afterend',`<div class="projbar" id="projbar"><b>Project</b>
 key <select id="pjkey"><option value="">—</option>${KEYS24.map(([c,n])=>`<option value="${n}">${c} · ${n}</option>`).join('')}</select>
 tempo <input id="pjbpm" type="number" step="0.1" min="40" max="220" placeholder="bpm" style="width:72px">
 <label title="every preview, variation and 'play together' is pitched/stretched into the project key & tempo"><input type="checkbox" id="pjon"> play everything in the project key/tempo</label>
 <button id="pjlink" class="tbtn" title="follow Ableton Live's tempo via Link (turn on Link in Live's top bar)">🔗 Live</button>${hq('project')}
 <label class="sub" title="start/stop the sketchpad with Live's transport (Live: Link → Start Stop Sync)"><input type="checkbox" id="pjlt"> start/stop with Live</label>
 <span class="lk" id="pjlk"></span><span style="flex:1"></span><button id="skbtn" class="tbtn">🎛 sketchpad (0)</button></div>
 <div id="sbanner" class="prov sbanner" hidden></div>`);
function drawProj(){$('pjkey').value=PROJ.key||'';$('pjbpm').value=PROJ.bpm||'';$('pjon').checked=!!PROJ.on;$('pjlink').classList.toggle('on',!!PROJ.link);$('pjlt').checked=!!PROJ.linkTransport;
 $('skbtn').textContent=`🎛 sketchpad (${SK.lanes.length})`;$('skbtn').classList.toggle('on',SK.open)}
$('pjkey').onchange=e=>setProj({key:e.target.value});
$('pjbpm').onchange=e=>setProj({bpm:Math.max(0,+e.target.value||0)});
$('pjon').onchange=e=>{setProj({on:e.target.checked});if(e.target.checked&&!PROJ.key&&!PROJ.bpm)toast('set a key and/or tempo for the project');stopAll()};
$('pjlink').onclick=()=>{setProj({link:!PROJ.link});if(PROJ.link)linkPoll();else $('pjlk').textContent=''};
$('pjlt').onchange=e=>setProj({linkTransport:e.target.checked});
// playback that respects the project (overrides the main script's players)
toggle=function(i,btn,{loop=true,exclusive=true}={}){
 if(players.has(i)){const a=players.get(i);a.pause();endListen(i,a);players.delete(i);mark();return}
 if(exclusive)stopAll();
 const a=new Audio(purl(S[i][F.path]));a.loop=loop&&S[i][F.kind]!=='oneshot';a.onended=()=>{endListen(i,a);players.delete(i);mark()};
 a.play().catch(()=>{});players.set(i,a);beginListen(i,S[i][F.path]);setNP(S[i][F.path],S[i][F.id],lbl(i)+projTag(),i);mark()};
playTogether=function(ids){stopAll();const as=ids.map(i=>{const a=new Audio(purl(S[i][F.path]));a.loop=S[i][F.kind]!=='oneshot';a.volume=.8;players.set(i,a);return a});
 setNP(S[ids[ids.length-1]][F.path],S[ids[ids.length-1]][F.id],'together: '+ids.map(i=>S[i][F.artist]).join(' + ')+projTag(),ids[ids.length-1]);
 Promise.all(as.map(a=>new Promise(r=>{a.oncanplaythrough=r;a.load()}))).then(()=>{as.forEach(a=>a.play());mark()})};
playVar=function(k){const rows=[...document.querySelectorAll('#vars .vrow')];if(!rows.length)return;k=Math.max(0,Math.min(rows.length-1,k));vcur=k;
 const b=rows[k].querySelector('[data-vp]');stopAll();const a=new Audio(purl(b.dataset.vp));a.loop=true;a.play();players.set('v'+k,a);beginListen('v'+k,b.dataset.vp);
 if(st.sel!=null)setNP(b.dataset.vp,S[st.sel][F.id],`${S[st.sel][F.artist]} — ${S[st.sel][F.title]} · variation ${String(k).padStart(2,'0')}${projTag()}`,st.sel);
 rows.forEach((r,j)=>{r.style.background=j===k?'#1f2630':'';r.querySelector('.play').classList.toggle('playing',j===k)});rows[k].scrollIntoView({block:'nearest'})};
async function projInfo(i){const el=$('pjinfo');if(!el)return;if(!PROJ.key&&!PROJ.bpm){el.textContent='';return}
 try{const r=await api(`api/conform/info?path=${encodeURIComponent(S[i][F.path])}&key=${encodeURIComponent(PROJ.key)}&bpm=${PROJ.bpm||''}`);
  const parts=[];if(r.semis)parts.push(`${r.semis>0?'+':''}${r.semis} st`);if(Math.abs(r.time-1)>1e-3)parts.push(`stretch ×${(+r.time).toFixed(3)}`);
  el.textContent=`in your project (${[PROJ.key,PROJ.bpm&&PROJ.bpm+' bpm'].filter(Boolean).join(' · ')}): ${parts.length?parts.join(', '):'fits as is'}${r.key?' → '+r.key:''}`}catch(e){el.textContent=''}}

// ================= Link =================
const LINK={ok:false,peers:0,tempo:0,ref:null,wasPlaying:false};
let linkT=null;
async function linkPoll(){clearTimeout(linkT);if(!PROJ.link||!SERVED)return;
 try{const t0=performance.now(),r=await api('api/link'),t1=performance.now();
  if(!r.ok){$('pjlk').textContent='Link: '+r.error}else{
   Object.assign(LINK,{ok:true,peers:r.peers,tempo:r.tempo,ref:{perf:(t0+t1)/2,beat:r.beat}});
   $('pjlk').className='lk'+(r.peers?' on':'');$('pjlk').textContent=r.peers?`Live: ${r.tempo.toFixed(1)} bpm · ${r.playing?'playing':'stopped'}`:'Link on — enable Link in Live';
   if(r.peers&&Math.abs(r.tempo-(PROJ.bpm||0))>0.05)setProj({bpm:+r.tempo.toFixed(2)});
   if(PROJ.linkTransport&&r.peers){if(r.playing&&!LINK.wasPlaying&&SK.lanes.length&&!SK.playing)skPlay();if(!r.playing&&LINK.wasPlaying&&SK.playing)skStop()}
   LINK.wasPlaying=!!r.playing}}catch(e){$('pjlk').textContent='Link unavailable'}
 linkT=setTimeout(linkPoll,300)}
function linkNextBar(){// AudioContext time of Live's next bar line
 if(!(PROJ.link&&LINK.ok&&LINK.peers&&LINK.ref))return AC.currentTime+0.06;
 const beatNow=LINK.ref.beat+(performance.now()-LINK.ref.perf)/1000*LINK.tempo/60,next=Math.ceil(beatNow/4+1e-4)*4;
 let t=AC.currentTime+(next-beatNow)*60/LINK.tempo-(AC.outputLatency||AC.baseLatency||0);if(t<AC.currentTime+0.03)t+=240/LINK.tempo;return t}

// ================= sound search & reference search =================
let SOUND=null;
document.getElementById('search').insertAdjacentHTML('afterend',`<button id="sndbtn" class="tbtn" title="search by what it sounds like (CLAP): e.g. “lonely female voice, distant” · add -word to push away">≈ by sound</button><button id="refbtn" class="tbtn" title="find samples that feel like a reference track (never sampled)">🎧 feels like…</button>${hq('sound')}`);
let soundMode=false;
$('sndbtn').onclick=()=>{soundMode=!soundMode;$('sndbtn').classList.toggle('on',soundMode);$('search').placeholder=soundMode?'describe a sound, press Enter — e.g. “lonely female voice, distant, rainy night”':'search artist, title, mood, instrument, id…';
 if(!soundMode&&SOUND&&!SOUND.ref){SOUND=null;render()}if(soundMode&&$('search').value.trim())soundSearch($('search').value.trim());$('search').focus()};
$('search').addEventListener('keydown',e=>{if(e.key==='Enter'&&soundMode&&$('search').value.trim()){e.preventDefault();soundSearch($('search').value.trim())}});
async function soundSearch(q){if(!SERVED){toast('sound search needs the local server');return}toast(`listening for “${q}”…`);
 try{const r=await api('api/search?q='+encodeURIComponent(q));SOUND={label:`sounds like “${q}”`,score:new Map(r.results.map((x,k)=>[x.path,r.results.length-k])),at:null};
  setTab('S');st.shown=200;render()}catch(e){toast('search failed: '+e.message)}}
$('refbtn').onclick=()=>{if(!SERVED){toast('needs the local server');return}
 modal(`<h2 style="margin:0">Find samples that feel like a track</h2><div class="sub">A YouTube/SoundCloud URL, an audio file path, or “artist – title” from your library (e.g. <i>Burial – Archangel</i>). The reference is only listened to — never sampled, never added. Results come from your own library, minus cuts of the reference itself.</div>
 <input id="refIn" style="width:100%" placeholder="Burial – Archangel   ·   https://…   ·   /path/to/track.mp3"><div class="edrow"><button id="refGo" class="pill">find</button><button data-close>close</button></div><div id="refMsg" class="sub"></div>`);
 $('refIn').focus();$('refIn').onkeydown=e=>{if(e.key==='Enter')$('refGo').click()};
 $('refGo').onclick=async()=>{const t=$('refIn').value.trim();if(!t)return;$('refMsg').textContent='listening to the reference… (10–60 s; a URL has to download first)';$('refGo').disabled=true;
  try{const r=await api('api/refsearch',{target:t});SOUND={ref:true,label:`feels like ${r.reference}`,score:new Map(r.results.map((x,k)=>[x.path,r.results.length-k])),at:new Map(r.results.map(x=>[x.path,x.at]))};
   $('modal').hidden=true;setTab('S');st.shown=200;render()}catch(e){$('refMsg').textContent='error: '+e.message}finally{$('refGo')&&($('refGo').disabled=false)}}};
const _filtered=filtered;
filtered=function(){const blank=soundMode||(SOUND&&SOUND.ref);if(!blank&&(!SOUND||st.tab!=='S'&&st.tab!=='G'))return _filtered();const el=$('search'),v=el.value;if(blank)el.value='';let out;try{out=_filtered()}finally{el.value=v}
 if(!SOUND||st.tab!=='S'&&st.tab!=='G')return out;return out.filter(i=>SOUND.score.has(S[i][F.path])).sort((a,b)=>SOUND.score.get(S[b][F.path])-SOUND.score.get(S[a][F.path]))};
function drawSBanner(){const b=$('sbanner');if(!SOUND||!(st.tab==='S'||st.tab==='G')){b.hidden=true;return}b.hidden=false;
 b.innerHTML=`≈ <b>${esc(SOUND.label)}</b> — closest first; your other filters still apply &nbsp;<button id="sclear">✕ clear</button>`;$('sclear').onclick=()=>{SOUND=null;if(soundMode)$('sndbtn').click();render()}}

// ================= tabs: crate · galaxy · scout =================
$('tabS').insertAdjacentHTML('afterend',`<button id="tabC" title="today's crate: 20 picks for you + wildcards">🎲 Crate</button>`);
document.querySelector('.tabs').insertAdjacentHTML('beforeend',`<button id="tabG" title="every sample on a map by sound">🌌 Galaxy</button><button id="tabY" title="scout YouTube for raw singing">🔭 Scout</button>`);
const MYTABS={C:'tabC',G:'tabG',Y:'tabY'};
function setTab(k){st.tab=k;document.querySelectorAll('.tabs button').forEach(b=>b.classList.remove('on'));const id=tabs[k]||MYTABS[k];if($(id))$(id).classList.add('on');render()}
Object.entries(MYTABS).forEach(([k,id])=>$(id).onclick=()=>setTab(k));
Object.values(tabs).forEach(id=>$(id).addEventListener('click',()=>Object.values(MYTABS).forEach(m=>$(m).classList.remove('on'))));
const _render=render;
render=function(){drawSBanner();if('CGY'.includes(st.tab)&&typeof drawCats==='function')drawCats();if(st.tab==='C'){paintWheel();drawBanner();return renderCrate()}if(st.tab==='G'){paintWheel();drawBanner();return renderGalaxy()}
 if(st.tab==='Y'){paintWheel();drawBanner();return renderScout()}
 if(st.tab==='F'&&FAVVIEW==='sets'&&SERVED){paintWheel();drawBanner();return renderSets()}
 if(st.tab==='F'&&FAVVIEW==='cols'&&SERVED){paintWheel();drawBanner();return renderCollections()}
 _render();if(st.tab==='K')renderKitExtras();if(st.tab==='F'&&SERVED)$('list').insertAdjacentHTML('afterbegin',favViewBar());if(st.tab==='S'&&SOUND&&SOUND.at)annotateAt()};
function annotateAt(){document.querySelectorAll('#list .row[data-i]').forEach(r=>{const p=S[+r.dataset.i][F.path],a=SOUND.at.get(p);const m=r.querySelector('.meta');
 if(a&&m&&!m.dataset.at){m.dataset.at=1;m.insertAdjacentHTML('beforeend',` · <span style="color:var(--acc)">like the reference @ ${a}</span>`)}})}
// rows get a ＋ (add to sketchpad)
const _rowHTML=rowHTML;
rowHTML=function(i){return _rowHTML(i).replace('<span class="id"',`<button class="xp" data-sk="${i}" title="add to the sketchpad">＋</button><span class="id"`)};

// ---------- daily crate
function rng(seed){let a=0;for(const c of seed)a=(a*31+c.charCodeAt(0))|0;return()=>{a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function lsj(k,d){try{return JSON.parse(localStorage.getItem(k)||'null')??d}catch(e){return d}}
// which sample types the crate draws from: [] = all (the default); remembered per browser
const crateMix=()=>lsj('atlasCrateMix',[]);
function buildCrate(force){const day=new Date().toLocaleDateString('en-CA');const saved=lsj('atlasCrate',null),mix=crateMix();
 if(!force&&saved&&saved.day===day&&saved.paths&&saved.paths.length&&String(saved.mix||[])===String(mix))return saved;
 const n=(saved&&saved.day===day?saved.n||0:0)+(force?1:0),R=rng(day+':'+n),seen=new Set(lsj('atlasCrateSeen',[]));
 const rated=new Set([...FAV.keys(),...TASTE.disliked]);
 const pool=S.map((s,i)=>i).filter(i=>{const s=S[i];return !rated.has(s[F.path])&&!seen.has(s[F.path])&&!st.excl.has(s[F.genre])&&s[F.q]>=0.45&&!s[F.path].startsWith('_Reference')&&!s[F.parent]&&(!mix.length||mix.includes(s[F.cat]))});
 const sc=i=>TASTE.score[S[i][F.path]]??(S[i][F.q]-1),ds=i=>TASTE.discover[S[i][F.path]]??R();
 const pick=(list,k,out,byT,byA)=>{for(const i of list){if(out.length>=k)break;const t=S[i][F.tid],a=S[i][F.artist];if(byT.has(t)||(byA.get(a)||0)>=2)continue;byT.add(t);byA.set(a,(byA.get(a)||0)+1);out.push(i)}return out};
 const byT=new Set(),byA=new Map();
 const you=pick(pool.slice().sort((a,b)=>sc(b)-sc(a)+(R()-.5)*0.15),14,[],byT,byA);
 const disc=pool.slice().sort((a,b)=>ds(b)-ds(a)).slice(30,900);for(let k=disc.length-1;k>0;k--){const j=Math.floor(R()*(k+1));[disc[k],disc[j]]=[disc[j],disc[k]]}
 const wild=pick(disc,6,[],byT,byA);
 const c={day,n,mix,paths:you.map(i=>S[i][F.path]),wild:wild.map(i=>S[i][F.path])};try{localStorage.setItem('atlasCrate',JSON.stringify(c));
  localStorage.setItem('atlasCrateSeen',JSON.stringify([...seen,...c.paths,...c.wild].slice(-3000)))}catch(e){}return c}
function renderCrate(){const c=buildCrate(false),all=[...c.paths,...c.wild],ids=p=>p.map(x=>byPath.get(x)).filter(x=>x!=null);
 const done=all.filter(p=>FAV.has(p)||TASTE.disliked.has(p)).length;
 $('count').textContent=`today's crate · ${done}/${all.length} rated`+(TASTE.n?` · taste model: ${TASTE.n} ratings`:'');
 const mix=crateMix(),cats=Object.keys(D.subtypes).filter(c=>S.some(s=>s[F.cat]===c));
 $('list').innerHTML=`<div class="crateprog"><i style="width:${all.length?done/all.length*100:0}%"></i></div>
 <div class="chips" style="margin:0 16px 12px;display:flex;gap:6px;flex-wrap:wrap;align-items:center"><span class="sub">In this crate:</span>
 <button data-crmix="" class="${mix.length?'':'on'}" title="every type (the default)">All</button>${cats.map(c=>`<button data-crmix="${esc(c)}" class="${mix.includes(c)?'on':''}" title="${esc(c)}"><span class="badge" style="background:${col(c)}">${AB[c]}</span>${esc(c.replace('Atmospheres','Atmos'))}</button>`).join('')}
 <span class="sub">pick one or more</span></div>
 <div class="kit"><h3><span>For you — what the taste model rates highest that you haven't heard${hq('crate')}</span><button id="crnew" title="a fresh crate">↻ new crate</button></h3>${ids(c.paths).map(rowHTML).join('')||(mix.length?'<div class="empty">No unheard samples of these types left. Add another type.</div>':'<div class="empty">rate a few samples first</div>')}</div>
 <div class="kit"><h3><span>Wildcards — outside your usual, picked to teach the model fastest</span></h3>${ids(c.wild).map(rowHTML).join('')}</div>
 <div class="hint" style="margin:0 16px 16px">★ and ✕ train the taste model; a new crate appears each day. Already-crated samples don't come back.</div>`;
 $('crnew').onclick=()=>{buildCrate(true);renderCrate()};
 $('list').querySelectorAll('[data-crmix]').forEach(b=>b.onclick=()=>{const v=b.dataset.crmix;let m=crateMix();
  m=v===''?[]:m.includes(v)?m.filter(x=>x!==v):[...m,v];try{localStorage.setItem('atlasCrateMix',JSON.stringify(m))}catch(e){}buildCrate(true);renderCrate()});mark()}

// ---------- 🧩 sets: favourites that fit together (sets.py), on the Favorites tab
let FAVVIEW=lsj('atlasFavView','list'),SETS=null;
const favViewBar=()=>`<div class="chips" style="margin:0 16px 10px;display:flex;gap:6px;align-items:center"><span class="sub">View:</span><button data-favview="list" class="${FAVVIEW==='list'?'on':''}">★ list</button><button data-favview="sets" class="${FAVVIEW==='sets'?'on':''}" title="your favourites grouped into sets that fit together, and what would complete each">🧩 sets that fit together</button><button data-favview="cols" class="${FAVVIEW==='cols'?'on':''}" title="collections: samples saved for a project you have in mind">📁 collections</button></div>`;
document.addEventListener('click',e=>{const b=e.target.closest('[data-favview]');if(!b)return;FAVVIEW=b.dataset.favview;try{localStorage.setItem('atlasFavView',JSON.stringify(FAVVIEW))}catch(err){}render()});
async function renderSets(){const L=$('list');$('count').textContent='your favourites, grouped into sets that fit together';
 const key=[...FAV.keys()].sort().join('|');
 if(!SETS||SETS.key!==key){L.innerHTML=favViewBar()+'<div class="sub" style="margin:12px 16px">grouping your favourites…</div>';
  try{SETS=await api('api/sets');SETS.key=key}catch(e){L.innerHTML=favViewBar()+`<div class="empty">couldn't group them: ${esc(e.message)}</div>`;return}}
 if(st.tab!=='F'||FAVVIEW!=='sets')return;
 const ids=ps=>ps.map(p=>byPath.get(p)).filter(i=>i!=null&&!GONE.has(i));
 L.innerHTML=favViewBar()+`<div class="hint" style="margin:0 16px 12px">Every pair in a set fits: key (and the notes actually played), tempo for loops, role and sound, scored like "goes well with". ${SETS.loose?`${SETS.loose} favourites don't fit a set strongly yet; starring more fills them in.`:''}</div>`
  +(SETS.sets.length?SETS.sets.map((s,k)=>{const m=ids(s.members),c=s.complete.filter(x=>byPath.has(x.path)&&!GONE.has(byPath.get(x.path)));
   return `<div class="kit"><h3><span>Set ${k+1} · ${esc(s.name)} <span class="sub">${m.length} samples · every pair fits ≥ ${Math.round(s.weakest*100)}%</span></span><button data-setplay="${k}">▶ play together</button> <button data-setsk="${k}" title="open the set in the sketchpad">🎛 sketch</button> <button data-setexp="${k}">⇩ export</button></h3>
   ${m.map(rowHTML).join('')}
   ${c.length?`<div class="sub" style="margin:10px 0 4px">Would complete it, from the rest of your library (fits every sample above):</div>${c.map(x=>{const i=byPath.get(x.path);return rowHTML(i).replace('<div class="meta">',`<div class="meta">${x.new_role?'<span style="color:var(--acc)">adds a new role</span> · ':''}fit ${Math.round(x.fit*100)}% · `)}).join('')}`:''}</div>`}).join('')
   :'<div class="empty">No sets yet: star a few more samples that sound good together.</div>');mark()}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-setplay],[data-setsk],[data-setexp]');if(!b||!SETS)return;e.stopPropagation();
 const k=+(b.dataset.setplay??b.dataset.setsk??b.dataset.setexp),s=SETS.sets[k],m=s.members.map(p=>byPath.get(p)).filter(i=>i!=null&&!GONE.has(i));
 if(b.dataset.setplay!=null){playTogether(m);return}
 if(b.dataset.setsk!=null){if(SK.lanes.length)setTimeout(()=>toast('the sketch was replaced · ⌘Z brings it back'),400);skStop();SK.lanes=[];SK.drums=null;SK.name=`Set ${k+1} · ${s.name}`;for(const i of m)await skAdd(i);skPlay();return}
 b.textContent='exporting…';try{const r=await api('api/export',{scope:'paths',paths:m.map(i=>S[i][F.path]),name:`Set ${k+1} ${s.name}`.replace(/[^\w #·-]/g,'')});b.textContent=`exported ${r.count} ✓`}catch(err){b.textContent='error'}},true);

// ---------- 📁 collections: samples saved with a project in mind (collections_.py)
let COLS=[],COLLAST=lsj('atlasColLast','');
const colsOf=p=>COLS.filter(c=>c.set.has(p)).map(c=>c.name);
async function colLoad(){if(!SERVED)return;try{COLS=(await api('api/collections')).map(c=>({...c,set:new Set(c.paths)}))}catch(e){COLS=[]}
 document.querySelectorAll('[data-col]').forEach(b=>b.classList.toggle('on',colsOf(b.dataset.colp).length>0))}
const colBtn=(i,big)=>SERVED?`<button class="${big?'':'xp '}${colsOf(S[i][F.path]).length?'on':''}" data-col="${i}" data-colp="${esc(S[i][F.path])}" title="add to a collection (a project you have in mind)">📁${big?' collection':''}</button>`:'';
async function colToggle(name,i,on){const p=S[i][F.path];
 await api(`api/collections/${on?'add':'remove'}`,{name,path:p,id:S[i][F.id]});COLLAST=name;try{localStorage.setItem('atlasColLast',JSON.stringify(name))}catch(e){}
 await colLoad();
 if(!window.ACT_QUIET)actPush(`${on?'added':'removed'} ${nameOf(p)} ${on?'to':'from'} “${name}”`,()=>colToggle(name,i,!on),!on);else return;
 if(on)toast(`added to “${name}”`)}
function colPop(b){const i=+b.dataset.col,p=S[i][F.path];let pop=$('colpop');if(!pop){pop=document.createElement('div');pop.id='colpop';pop.className='colpop';document.body.appendChild(pop)}
 const names=COLS.map(c=>c.name).sort((a,c)=>(c===COLLAST)-(a===COLLAST)),mine=new Set(colsOf(p));
 pop.innerHTML=`<div class="sub" style="margin-bottom:6px">Collections for this sample</div>${names.map(n=>`<label class="colrow"><input type="checkbox" data-colname="${esc(n)}" ${mine.has(n)?'checked':''}> ${esc(n)} <span class="sub">${COLS.find(c=>c.name===n).n}</span></label>`).join('')||'<div class="sub">none yet</div>'}
 <div style="display:flex;gap:6px;margin-top:8px"><input id="colnew" placeholder="new collection, e.g. Night drive EP" style="flex:1;min-width:0"><button id="colmk">＋</button></div>`;
 const r=b.getBoundingClientRect();pop.style.left=Math.max(8,Math.min(innerWidth-280,r.left-120))+'px';pop.style.top=(r.bottom+6+scrollY)+'px';pop.hidden=false;pop.dataset.i=i;
 pop.onchange=async e=>{const n=e.target.dataset.colname;if(n!=null)await colToggle(n,i,e.target.checked)};
 const mk=async()=>{const n=$('colnew').value.trim();if(!n)return;await colToggle(n,i,true);colPop(b)};$('colmk').onclick=mk;$('colnew').onkeydown=e=>{if(e.key==='Enter')mk()};setTimeout(()=>$('colnew').focus(),0)}
document.addEventListener('click',e=>{const b=e.target.closest('[data-col]');const pop=$('colpop');
 if(b){e.stopPropagation();e.preventDefault();if(pop&&!pop.hidden&&+pop.dataset.i===+b.dataset.col){pop.hidden=true;return}colPop(b);return}
 if(pop&&!pop.hidden&&!e.target.closest('#colpop'))pop.hidden=true},true);
// rows and the sample panel get 📁
const _rowHTMLc=rowHTML;rowHTML=function(i){return _rowHTMLc(i).replace('<span class="id"',colBtn(i)+'<span class="id"')};
const _selectC=select;select=function(i,from){_selectC(i,from);
 if(SERVED&&S[i][F.cat]==='Percussion'&&S[i][F.kind]==='loop'){const xb=document.querySelector('#detail [data-xp]');if(xb&&!$('sliceit'))xb.insertAdjacentHTML('afterend',`<button id="sliceit" title="slice this loop at its hits into pads of the sketchpad's drum lane, each on its step, so you can re-sequence it">🥁 slice into pads</button>`)}
 if(SERVED){const xb=document.querySelector('#detail [data-xp]');if(xb&&!$('reveal'))xb.insertAdjacentHTML('afterend',`<button id="reveal" title="show the file in Finder, selected: drag it from there into Live (or anywhere)">↗ Finder</button>`)}
 if(SERVED&&S[i][F.cat]==='Percussion'&&S[i][F.kind]!=='loop'){const xb=document.querySelector('#detail [data-xp]');if(xb&&!$('kitaround'))xb.insertAdjacentHTML('afterend',`<button id="kitaround" title="start (or add to) the sketchpad's drum lane with this hit, then find the rest of a kit that sounds like it">🥁 build a kit around this</button>`)}const xb=document.querySelector('#detail [data-xp]');if(xb&&SERVED&&!$('detail').querySelector('[data-col]'))xb.insertAdjacentHTML('afterend',colBtn(i,true))};
// the Favorites tab's 📁 view
let COLSEL=lsj('atlasColSel','');
async function renderCollections(){const L=$('list');await colLoad();if(st.tab!=='F'||FAVVIEW!=='cols')return;
 if(!COLS.some(c=>c.name===COLSEL))COLSEL=(COLS[0]||{}).name||'';const c=COLS.find(x=>x.name===COLSEL);
 $('count').textContent=`${COLS.length} collection${COLS.length===1?'':'s'}`+(SERVED?' · also in SampleLibrary/Collections':'');
 const ids=c?c.paths.map(p=>byPath.get(p)).filter(i=>i!=null&&!GONE.has(i)):[];
 L.innerHTML=favViewBar()+(COLS.length?`<div class="chips" style="margin:0 16px 12px;display:flex;gap:6px;flex-wrap:wrap">${COLS.map(x=>`<button data-colsel="${esc(x.name)}" class="${x.name===COLSEL?'on':''}">📁 ${esc(x.name)} <span class="sub">${x.n}</span></button>`).join('')}</div>`:'')
  +(c?`<div class="kit"><h3><span>📁 ${esc(c.name)} <span class="sub">${ids.length} samples</span></span><button data-colplay>▶ play together</button> <button data-colsk title="open it in the sketchpad (drum hits go to the drum lane)">🎛 sketch</button> <button data-colexp>⇩ export</button> <button data-colsets title="its samples grouped into sets that fit together">🧩 sets</button> <button data-colren>rename</button> <button data-coldel title="removes the collection, not the samples">delete</button></h3>
   <div id="colsets"></div>${ids.map(rowHTML).join('')||'<div class="empty">Empty: add samples with 📁</div>'}</div>`
  :`<div class="empty">No collections yet. Click 📁 on any sample (or press C while one plays) to save it to a collection for a project you have in mind.</div>`);mark()}
document.addEventListener('click',async e=>{const t=e.target.closest('[data-colsel],[data-colplay],[data-colsk],[data-colexp],[data-colsets],[data-colren],[data-coldel]');if(!t)return;e.stopPropagation();
 if(t.dataset.colsel!=null){COLSEL=t.dataset.colsel;try{localStorage.setItem('atlasColSel',JSON.stringify(COLSEL))}catch(err){}renderCollections();return}
 const c=COLS.find(x=>x.name===COLSEL);if(!c)return;const ids=c.paths.map(p=>byPath.get(p)).filter(i=>i!=null&&!GONE.has(i));
 if(t.dataset.colplay!=null){playTogether(ids);return}
 if(t.dataset.colsk!=null){if(SK.lanes.length)setTimeout(()=>toast('the sketch was replaced · ⌘Z brings it back'),400);skStop();SK.lanes=[];SK.name=c.name;for(const i of ids)await skAdd(i);skPlay();return}
 if(t.dataset.colexp!=null){t.textContent='exporting…';try{const r=await api('api/export',{scope:'paths',paths:ids.map(i=>S[i][F.path]),name:c.name});t.textContent=`exported ${r.count} ✓`}catch(err){t.textContent='error'}return}
 if(t.dataset.colsets!=null){const box=$('colsets');box.innerHTML='<div class="sub">grouping…</div>';const r=await api('api/sets?collection='+encodeURIComponent(c.name));
  box.innerHTML=r.sets.length?r.sets.map((s,k)=>`<div class="sub" style="margin:6px 0 2px">🧩 set ${k+1} · ${esc(s.name)} · every pair fits ≥ ${Math.round(s.weakest*100)}% · ${s.members.length} samples</div>`).join('')+'<div class="sub" style="margin-bottom:8px">(the full sets view with play and sketch buttons is in 🧩 sets for favourites)</div>':`<div class="sub">${r.note||'no sets that fit tightly yet: add a few more samples'}</div>`;return}
 if(t.dataset.colren!=null){const n=window.prompt?prompt('New name',c.name):null;if(!n||n===c.name)return;try{await api('api/collections/rename',{name:c.name,new:n});COLSEL=n;renderCollections()}catch(err){toast(err.message)}return}
 if(t.dataset.coldel!=null){if(t.dataset.armed!=='1'){t.dataset.armed='1';t.textContent='delete? (samples stay)';setTimeout(()=>{t.dataset.armed='';t.textContent='delete'},3000);return}
  await api('api/collections/delete',{name:c.name});COLSEL='';renderCollections()}},true);
colLoad();

// ---------- new samples appear while you work (live.py): no `digitalcrate build`, no reload
let LIVE_SINCE=BORN.reduce((a,b)=>Math.max(a,b||0),0);
async function liveCheck(force){if(!SERVED||(document.hidden&&!force))return 0;let r;try{r=await api('api/live/new?since='+LIVE_SINCE)}catch(e){return 0}
 const add=r.samples.map((row,k)=>({row,parts:r.partners[k]||[],b:r.born[k]})).filter(x=>!BYID.has(x.row[F.id]));if(!add.length)return 0;
 add.forEach(x=>{const e=x.row[F.env];if(typeof e==='string'){const b=atob(e),v=new Array(b.length);for(let k=0;k<b.length;k++)v[k]=b.charCodeAt(k);x.row[F.env]=v}});  // waveforms come packed, like in the page file
 Object.assign(D.tracks,r.tracks);
 add.forEach(x=>{const j=S.push(x.row)-1;x.j=j;BYID.set(x.row[F.id],j);byPath.set(x.row[F.path],j);if(!BYTRACK.has(x.row[F.tid]))BYTRACK.set(x.row[F.tid],[]);BYTRACK.get(x.row[F.tid]).push(j);BORN[j]=x.b});
 add.forEach(x=>{P[x.j]=x.parts.map(([id,sc,h,v])=>[BYID.get(id),sc,h,v]).filter(q=>q[0]!=null)});  // second pass: partners may be other new ones
 LIVE_SINCE=Math.max(LIVE_SINCE,...add.map(x=>x.b));
 toast(`${add.length} new sample${add.length>1?'s':''} from your mining run · in the list now`);
 if(typeof loadTaste==='function')loadTaste();
 if(['S','C','R','F'].includes(st.tab)){const m=document.querySelector('main'),y=m?m.scrollTop:0;render();if(m)m.scrollTop=y}
 return add.length}
window.liveCheck=liveCheck;setInterval(liveCheck,60000);setTimeout(liveCheck,8000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)liveCheck()});

// ---------- drag samples out (into Live, Finder, anywhere that takes files) and ↗ show in Finder
let LIBROOT=null;if(SERVED)api('api/libroot').then(r=>LIBROOT=r.root).catch(()=>{});
document.addEventListener('dragstart',e=>{const row=e.target.closest&&e.target.closest('.row[data-i]');if(!row||!SERVED)return;const s=S[+row.dataset.i],p=s[F.path],name=p.split('/').pop();
 const dt=e.dataTransfer;dt.effectAllowed='copy';
 dt.setData('DownloadURL',`audio/wav:${name}:${location.origin}/${p.split('/').map(encodeURIComponent).join('/')}`);  // a file promise: Finder, the desktop, most apps
 if(LIBROOT){const abs=LIBROOT+'/'+p;dt.setData('text/uri-list','file://'+abs.split('/').map(encodeURIComponent).join('/'));dt.setData('text/plain',abs)}  // the real file, for apps that take a path
 toast('drop it in Live, Finder or anywhere that takes audio files · if Live won’t take it, ↗ Finder in the sample panel')});
// rows are draggable (but not their buttons, sliders or text you select)
new MutationObserver(()=>document.querySelectorAll('#list .row[data-i]:not([draggable])').forEach(r=>r.setAttribute('draggable','true'))).observe(document.body,{subtree:true,childList:true});
document.addEventListener('click',async e=>{const b=e.target.closest('#reveal');if(!b)return;e.stopPropagation();const i=st.sel;if(i==null)return;
 try{await api('api/reveal',{path:S[i][F.path]});toast('shown in Finder: drag it from there into Live')}catch(err){toast("couldn't show it: "+err.message)}},true);

// ---------- recent actions, with undo (★, ✕, moving a sample to another category, collections, deletes)
// ⌘Z undoes the sketch when the sketchpad is open, otherwise the last action here
const ACTS=[];window.ACT_QUIET=false;
function actPush(label,undo,toastIt){ACTS.push({label,undo,t:Date.now(),done:false});if(ACTS.length>50)ACTS.shift();
 const b=$('actbtn');if(b){b.hidden=false;b.textContent='🕘 '+ACTS.filter(a=>!a.done).length}
 if(toastIt){const t=$('toast');t.innerHTML=`${esc(label)} <button id="actundo">undo</button>`;t.hidden=false;clearTimeout(toast.t);toast.t=setTimeout(()=>t.hidden=true,6000);
  const a=ACTS[ACTS.length-1];$('actundo').onclick=()=>actUndo(a)}}
window.actPush=actPush;
async function actUndo(a){if(!a||a.done)return;a.done=true;window.ACT_QUIET=true;try{await a.undo()}finally{window.ACT_QUIET=false}
 const b=$('actbtn');if(b)b.textContent='🕘 '+ACTS.filter(x=>!x.done).length;toast('undone: '+a.label);const p=$('actpop');if(p&&!p.hidden)actPop()}
const nameOf=p=>{const i=byPath.get(p);return i==null?p.split('/').pop():`${S[i][F.artist]} — ${S[i][F.sub]}`};
function actPop(){let p=$('actpop');if(!p){p=document.createElement('div');p.id='actpop';p.className='colpop';document.body.appendChild(p)}
 const r=$('actbtn').getBoundingClientRect();p.style.left=(r.left)+'px';p.style.top=(r.bottom+6+scrollY)+'px';p.style.width='330px';p.hidden=false;
 const list=ACTS.slice().reverse();
 p.innerHTML=`<div class="sub" style="margin-bottom:6px">Recent actions (newest first)</div>${list.map((a,k)=>`<div class="colrow" style="justify-content:space-between"><span style="${a.done?'opacity:.45;text-decoration:line-through':''}">${esc(a.label)} <span class="sub">${Math.max(1,Math.round((Date.now()-a.t)/60000))} min</span></span>${a.done?'':`<button data-actu="${ACTS.length-1-k}">undo</button>`}</div>`).join('')||'<div class="sub">nothing yet</div>'}`;
 p.onclick=e=>{const b=e.target.closest('[data-actu]');if(b){e.stopPropagation();actUndo(ACTS[+b.dataset.actu])}}}
document.addEventListener('click',e=>{if(e.target.closest('#actbtn')){e.stopPropagation();const p=$('actpop');if(p&&!p.hidden){p.hidden=true;return}actPop();return}
 const p=$('actpop');if(p&&!p.hidden&&!e.target.closest('#actpop'))p.hidden=true},true);
// ★ and ✕ (the page's own functions, wrapped so every way of starring is recorded)
const _toggleFavA=toggleFav;toggleFav=async function(path,id,label){const was=FAV.has(path);const r=await _toggleFavA(path,id,label);
 if(!window.ACT_QUIET)actPush(`${was?'unstarred':'starred'} ${nameOf(path)}`,()=>toggleFav(path,id,label));return r};
const _toggleDisA=toggleDislike;toggleDislike=function(path,id){const was=TASTE.disliked.has(path);const r=_toggleDisA(path,id);
 if(!window.ACT_QUIET)actPush(`${was?'un-✕':'✕'} ${nameOf(path)}`,()=>toggleDislike(path,id),!was);return r};

// ---------- the keyboard: ↑/↓ (J/K) move through the list with a preview, Enter edit, F ★, X ✕, C 📁, A sketch, / search, ? help
let KPREVIEW=lsj('atlasKPreview',true);
const typing=e=>['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)||e.target.isContentEditable;
const padsOpen=()=>$('pads')&&!$('pads').hidden;  // the pads use the letter keys
const keyTarget=()=>st.sel!=null?st.sel:(NP&&!NP.edit&&NP.i!=null&&players.size?NP.i:null);
function kMove(d){const rows=[...document.querySelectorAll('#list .row[data-i]')];if(!rows.length)return;
 let k=rows.findIndex(r=>+r.dataset.i===st.sel);k=k<0?(d>0?0:rows.length-1):Math.max(0,Math.min(rows.length-1,k+d));
 const i=+rows[k].dataset.i;select(i,'list');rows[k].scrollIntoView({block:'nearest'});if(KPREVIEW)toggle(i,null,{loop:false})}
function kHelp(){let p=$('khelp');if(p){p.hidden=!p.hidden;return}p=document.createElement('div');p.id='khelp';p.className='colpop';p.style.cssText+=';left:50%;top:80px;transform:translateX(-50%);width:420px;position:fixed';
 const rows=[['↓ ↑ or J K','next / previous sample (with a preview)'],['P','preview while moving: '+(KPREVIEW?'on':'off')],['Enter','edit the selected sample'],['Space','stop'],['F','★ favourite'],['X','✕ not for me'],['C','📁 add to your last collection'],['A','＋ add to the sketchpad'],['/','search'],['Esc','unselect · close'],['Backspace','back to the previous sample'],['← →','variations (when shown)'],['⌘Z  ⌘⇧Z','undo / redo (the sketch when the sketchpad is open)'],['⌘S','save the sketch'],['?','this list']];
 p.innerHTML=`<div style="display:flex;justify-content:space-between;margin-bottom:6px"><b>Keyboard</b><button id="khclose">✕</button></div><div style="display:grid;grid-template-columns:110px 1fr;gap:4px 10px">${rows.map(([k,v])=>`<code>${k}</code><span>${v}</span>`).join('')}</div>`;
 document.body.appendChild(p);$('khclose').onclick=()=>p.hidden=true}
document.addEventListener('keydown',e=>{if(e.metaKey||e.ctrlKey||e.altKey||typing(e))return;
 if(padsOpen()&&/^[a-z0-9]$/i.test(e.key))return;
 const k=e.key;
 if(k==='ArrowDown'||k==='j'){e.preventDefault();kMove(1);return}
 if(k==='ArrowUp'||k==='k'){e.preventDefault();kMove(-1);return}
 if(k==='?'){e.preventDefault();kHelp();return}
 if(k==='/'){e.preventDefault();$('search').focus();return}
 if(k==='p'||k==='P'){KPREVIEW=!KPREVIEW;try{localStorage.setItem('atlasKPreview',JSON.stringify(KPREVIEW))}catch(err){}toast('preview while moving: '+(KPREVIEW?'on':'off'));return}
 const i=keyTarget();if(i==null)return;const s=S[i];
 if(k==='Enter'&&st.sel!=null){e.preventDefault();const b=$('edopen');if(b)b.click();return}
 if(k==='f'||k==='F'){toggleFav(s[F.path],s[F.id],`${s[F.artist]} — ${s[F.title]} · ${s[F.sub]}`);setTimeout(()=>{drawNP();mark()},60);return}
 if(k==='x'||k==='X'){toggleDislike(s[F.path],s[F.id]);return}
 if(k==='a'||k==='A'){skAdd(i);return}
 if(k==='c'||k==='C'){if(!SERVED)return;if(!COLLAST||!COLS.some(c=>c.name===COLLAST)){toast('use 📁 once to pick a collection; then C adds to it');return}
  colToggle(COLLAST,i,!colsOf(s[F.path]).includes(COLLAST))}});

// ---------- slice a drum loop into pads: one pad per hit, on the step where it falls in the original (so it plays the
// loop back, now re-sequenceable and at the sketch's tempo without stretching)
async function sliceLoop(i){const s=S[i];let r;try{r=await api('api/slices?path='+encodeURIComponent(s[F.path])+'&n=16')}catch(e){toast("couldn't slice it: "+e.message);return}
 const bpm=s[F.bpm]||PROJ.bpm||120,st=60/bpm/4,bars=Math.max(1,Math.min(2,s[F.bars]||Math.round(s[F.dur]/(st*16))||1));
 if(!PROJ.bpm){PROJ.bpm=bpm;try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(e){}drawProj()}
 const old=drumLane();if(old&&old.pads.length){SK.lanes.splice(SK.lanes.indexOf(old),1);setTimeout(()=>toast('the drum lane was replaced · ⌘Z brings it back'),500)}
 const l=drumLane(true);if(!l){toast('the sketchpad holds 8 lanes');return}l.bars=bars;
 r.slices.forEach(([t0,t1],k)=>{const idx=Math.round(t0/st);if(idx>=16*bars||l.pads.length>=16)return;const steps=new Array(DSTEPS).fill(0);steps[idx]=1;
  l.pads.push({i,path:s[F.path],label:`slice ${k+1}`,start:t0,end:t1,auto:false,db:0,mute:false,steps})});
 SK.open=true;drawSK();drawProj();await drumLoad(l);drawSK();toast(`${l.pads.length} slices, each on its step · move, retune or drop them`)}
document.addEventListener('click',e=>{if(!e.target.closest('#sliceit'))return;e.stopPropagation();if(st.sel!=null)sliceLoop(st.sel)},true);

// ---------- galaxy
let GAL=null,GV={x:0,y:0,z:1},GH=null,GTASTE=false,GHOVER=true;
async function renderGalaxy(){const L=$('list');$('count').textContent='sample galaxy';
 L.innerHTML=`<div class="galaxy" id="gal"><canvas id="galc"></canvas><div class="gl" id="gll">loading the map (first time ≈30 s)…</div><div class="gtip" id="gtip" hidden></div></div>`;
 if(!GAL){try{const g=await api('api/galaxy');GAL=g.xy}catch(e){$('gll').textContent='map unavailable: '+e.message;return}}
 if(st.tab!=='G')return;galSetup();galDraw()}
function galPts(){const keep=new Set(filtered()),out=[];S.forEach((s,i)=>{let p=GAL[s[F.path]];if(!p&&s[F.root]&&BYID.has(s[F.root]))p=GAL[S[BYID.get(s[F.root])][F.path]];if(p)out.push([i,p[0],p[1],keep.has(i)])});return out}
let GP=[];
function galXY(c,x,y){const W=c.clientWidth,H=c.clientHeight,m=24,s=Math.min(W,H)-2*m;return[(x-.5-GV.x)*GV.z*s+W/2,(y-.5-GV.y)*GV.z*s+H/2]}
function galSetup(){const c=$('galc'),tip=$('gtip');GP=galPts();
 $('gll').innerHTML=`${hq('galaxy')} ${GP.filter(p=>p[3]).length.toLocaleString()} samples by sound — nearby = similar · wheel zoom · drag pan · click opens<br>
 <label style="pointer-events:auto"><input type="checkbox" id="ghov" ${GHOVER?'checked':''}> hover to play</label> <label style="pointer-events:auto"><input type="checkbox" id="gtaste" ${GTASTE?'checked':''}> show taste</label>
 <span style="pointer-events:auto">${CATS.map(cn=>`<span class="badge" style="background:${col(cn)}">${AB[cn]}</span>`).join('')}</span> <span>★ = favourite (ringed)</span>`;
 $('gll').style.pointerEvents='auto';$('ghov').onchange=e=>GHOVER=e.target.checked;$('gtaste').onchange=e=>{GTASTE=e.target.checked;galDraw()};
 let drag=null,hoverT=null,last=null;
 const near=e=>{const r=c.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;let best=null,bd=81;
  for(const p of GP){if(!p[3])continue;const[x,y]=galXY(c,p[1],p[2]);const d=(x-mx)**2+(y-my)**2;if(d<bd){bd=d;best=p}}return best};
 c.onwheel=e=>{e.preventDefault();const r=c.getBoundingClientRect(),W=c.clientWidth,H=c.clientHeight,s=Math.min(W,H)-48,f=e.deltaY>0?0.85:1.18;
  const mx=(e.clientX-r.left-W/2)/(GV.z*s)+GV.x,my=(e.clientY-r.top-H/2)/(GV.z*s)+GV.y;GV.z=Math.max(0.8,Math.min(60,GV.z*f));
  GV.x=mx-(e.clientX-r.left-W/2)/(GV.z*s);GV.y=my-(e.clientY-r.top-H/2)/(GV.z*s);galDraw()};
 c.onmousedown=e=>{drag={x:e.clientX,y:e.clientY,gx:GV.x,gy:GV.y,moved:false}};
 c.onmouseup=()=>{setTimeout(()=>{drag=null},0)};
 c.onmousemove=e=>{if(drag&&e.buttons){const s=Math.min(c.clientWidth,c.clientHeight)-48,dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>3)drag.moved=true;
   GV.x=drag.gx-dx/(GV.z*s);GV.y=drag.gy-dy/(GV.z*s);galDraw();return}
  const p=near(e);GH=p;galDraw();if(!p){tip.hidden=true;clearTimeout(hoverT);last=null;return}const i=p[0],[x,y]=galXY(c,p[1],p[2]);
  tip.hidden=false;tip.style.left=Math.min(x+12,c.clientWidth-260)+'px';tip.style.top=(y+10)+'px';
  tip.innerHTML=`<span class="badge" style="background:${col(S[i][F.cat])}">${AB[S[i][F.cat]]}</span>${esc(S[i][F.sub])} · ${S[i][F.cam]||'—'} · ${esc(S[i][F.artist])} — ${esc(S[i][F.title])}`;
  if(GHOVER&&last!==i){clearTimeout(hoverT);last=i;hoverT=setTimeout(()=>{if(GH&&GH[0]===i&&!players.has(i))toggle(i)},160)}};
 c.onmouseleave=()=>{tip.hidden=true;GH=null;galDraw()};
 c.onclick=e=>{if(drag&&drag.moved)return;const p=near(e);if(p)select(p[0],'list')};
 }
window.addEventListener('resize',()=>{if(st.tab==='G')galDraw()});
function galDraw(){const c=$('galc');if(!c)return;const dpr=devicePixelRatio||1,W=c.clientWidth,H=c.clientHeight;c.width=W*dpr;c.height=H*dpr;const g=c.getContext('2d');g.scale(dpr,dpr);
 g.fillStyle='#0b0d10';g.fillRect(0,0,W,H);const cc={};CATS.forEach(k=>cc[k]=catColor(k));
 const ts=Object.values(TASTE.score||{}),tmin=Math.min(...ts,0),tmax=Math.max(...ts,1);
 for(const p of GP){if(p[3])continue;const[x,y]=galXY(c,p[1],p[2]);if(x<-5||y<-5||x>W+5||y>H+5)continue;g.fillStyle='rgba(255,255,255,.05)';g.fillRect(x-1,y-1,2,2)}
 const r0=Math.min(5,1.6+GV.z*0.25);
 for(const p of GP){if(!p[3])continue;const i=p[0],path=S[i][F.path];const[x,y]=galXY(c,p[1],p[2]);if(x<-5||y<-5||x>W+5||y>H+5)continue;
  const dis=TASTE.disliked.has(path);g.globalAlpha=dis?0.15:0.85;
  if(GTASTE){const v=TASTE.score[path];const t=v==null?0:(v-tmin)/(tmax-tmin+1e-9);g.fillStyle=`hsl(${30+t*0},${40+t*60}%,${18+t*55}%)`}else g.fillStyle=cc[S[i][F.cat]];
  g.beginPath();g.arc(x,y,r0,0,7);g.fill();
  if(FAV.has(path)){g.globalAlpha=1;g.strokeStyle='#fff';g.lineWidth=1.5;g.beginPath();g.arc(x,y,r0+2.5,0,7);g.stroke()}
  if(players.has(i)||st.sel===i){g.globalAlpha=1;g.strokeStyle='#e0a458';g.lineWidth=2;g.beginPath();g.arc(x,y,r0+5,0,7);g.stroke()}}
 g.globalAlpha=1;if(GH){const[x,y]=galXY(c,GH[1],GH[2]);g.strokeStyle='#fff';g.lineWidth=1;g.beginPath();g.arc(x,y,r0+4,0,7);g.stroke()}}
setInterval(()=>{if(st.tab==='G'&&players.size)galDraw()},500);

// ---------- YouTube scout
let ytT=null,ytRes=[],ytQ='',ytAll=false,ytSty='',ytMode=(()=>{try{return localStorage.getItem('ytMode')||'voice'}catch(e){return 'voice'}})();
const YTM={voice:{label:'🎤 voice',intro:'Search YouTube for raw, private-feeling singing. A minute of each result is listened to and scored for clean, unaccompanied voice (and how close it is to your favourite vocals).',
  ph:'e.g. acapella cover · singing in my car · choir rehearsal',bars:['voice','band/talk']},
 pads:{label:'🌫 pads & textures',intro:'Search YouTube for ambient material: pads, drones, soundtracks, slow strings. A minute of each result (from the middle of long mixes) is scored for sustained, atmospheric sound with no drums, talking or singing, and for closeness to your favourite pads and textures.',
  ph:'e.g. ps1 ambient soundtrack · organ drone · 70s synth soundtrack',bars:['ambient','drums/talk/voice']},
 guided:{label:'🧭 your styles',intro:'Search YouTube guided by your styles: the Discogs styles (heard in the audio, out of 400) of the songs you\'ve liked samples from, ranked by how much more they turn up there than in your collection overall. Each result is listened to and scored for how much it sounds like those styles and like the songs you liked, minus talking and crowd noise. The searches below are built from your styles; pick one, or type your own and choose a style to listen for.',
  ph:'e.g. rare neo soul · modal jazz 1960s',bars:['your styles','talk/noise']}};
async function renderScout(){$('count').textContent='YouTube scout';const L=$('list');
 if(!SERVED){L.innerHTML='<div class="empty">The scout needs the local server.</div>';return}
 let d={presets:{},results:[]};try{d=await api('api/ytscout')}catch(e){}if(st.tab!=='Y')return;ytRes=d.results;const M=YTM[ytMode],pre=(d.presets&&d.presets[ytMode])||[];
 L.innerHTML=`<div style="padding:12px 16px;display:grid;gap:8px"><div class="chips">${Object.entries(YTM).map(([k,m])=>`<button data-ytmode="${k}" class="${k===ytMode?'on':''}">${m.label}</button>`).join('')}</div>
 <div class="sub">${hq('scout')} ${M.intro} Nothing enters the library until you press <b>add source</b>. Repeating a search digs further down YouTube's results instead of returning the same videos.</div>
 <div class="edrow"><input id="ytq" placeholder="${M.ph}" style="flex:1;min-width:200px" value="${esc(ytQ)}"><select id="ytn"><option>10</option><option selected>15</option><option>25</option></select><button id="ytgo" class="pill">scout</button></div>
 ${ytMode==='guided'?ytGuided(d):`<div class="chips">${pre.map(p=>`<button data-ytp="${esc(p)}">${esc(p)}</button>`).join('')}</div>`}<div id="ytjobs"></div>
 <div class="edrow sub"><label><input type="checkbox" id="ytall" ${ytAll||!ytQ?'checked':''}> all searches</label><label><input type="checkbox" id="ytsk"> show dismissed</label><span id="ytcount"></span></div></div><div id="ytlist"></div>`;
 $('ytgo').onclick=()=>ytStart($('ytq').value.trim());$('ytq').onkeydown=e=>{if(e.key==='Enter')$('ytgo').click()};$('ytsk').onchange=ytDraw;if($('ytsty'))$('ytsty').onchange=e=>{ytSty=e.target.value};$('ytall').onchange=e=>{ytAll=e.target.checked;ytDraw()};
 ytDraw();ytPoll();if(ytMode==='guided')ytRelated()}
async function ytRelated(){const el=$('ytrel');if(!el)return;let r=ytRelated.cache;if(!r){try{r=await api('api/related-artists')}catch(e){r={artists:[]}}ytRelated.cache=r}
 const el2=$('ytrel');if(!el2)return;const A=(r.artists||[]).slice(0,18);
 el2.innerHTML=A.length?`artists you don't have, that listeners pair with yours (ListenBrainz) — scout one: <div class="chips" style="margin-top:4px">${A.map(a=>`<button data-ytp="${esc(a.name)}" data-yts="" title="listeners of ${esc(a.because.join(', '))} play them too${a.comment?' · '+esc(a.comment):''}">${esc(a.name)} <span style="opacity:.6">← ${esc(a.because[0])}</span></button>`).join('')}</div>`:'';}
function ytGuided(d){const P=(d.profile&&d.profile.styles)||[],G=d.guided||[];
 if(!P.length)return `<div class="sub">${d.profile&&d.profile.ready===false?'Your songs\' styles haven\'t been analysed yet: run <b>Tag styles</b> on the ⚙ Processing page (about an hour for the whole collection).':'Like (★) some samples first: your styles come from the songs behind the samples you like.'}</div>`;
 return `<div class="edrow sub"><span>listen for</span><select id="ytsty"><option value="">all your styles</option>${P.map(p=>`<option value="${esc(p.full)}" ${p.full===ytSty?'selected':''}>${esc(p.name)} (${Math.round(p.share*100)}%${p.era?' · '+p.era:''})</option>`).join('')}</select></div>
 <div class="chips">${G.map(g=>`<button data-ytp="${esc(g.query)}" data-yts="${esc(g.style)}" title="listens for ${esc(g.style.split('---')[1])}">${esc(g.query)}</button>`).join('')}</div>
 <div class="sub" id="ytrel">artists related to yours (ListenBrainz): looking up… (about 20 s the first time)</div>
 <div class="sub" style="line-height:1.9">your styles <span style="opacity:.7">(how much more often than in your whole collection; ✕ if one isn't really yours)</span>: ${P.slice(0,12).map(p=>`<span style="white-space:nowrap;margin-right:10px"><b>${esc(p.name)}</b> ${p.lift}× more<button data-hidesty="${esc(p.full)}" title="not one of my styles: leave it out of the searches" style="border:0;background:none;color:var(--mute);cursor:pointer;padding:0 0 0 5px">✕</button></span>`).join('')}</div>`}
document.addEventListener('click',async e=>{const h=e.target.closest('[data-hidesty]');if(!h)return;h.disabled=true;
 try{await api('api/styles/hide',{style:h.dataset.hidesty,hide:true});toast(h.dataset.hidesty.split('---')[1]+' left out of your styles');renderScout()}catch(err){toast('error: '+err.message)}});
function ytDraw(){const el=$('ytlist');if(!el)return;const sk=$('ytsk')&&$('ytsk').checked,all=!ytQ||($('ytall')&&$('ytall').checked);
 const inQ=r=>('|'+(r.queries||r.query||'')+'|').includes('|'+ytQ+'|');
 const rows=ytRes.filter(r=>(sk||r.status!=='skipped')&&(all||inQ(r)));
 if($('ytcount'))$('ytcount').textContent=all?`${rows.length} videos from every search`:`${rows.length} video${rows.length===1?'':'s'} for “${ytQ}”`;
 const mx=Math.max(...rows.map(r=>r.score),1e-6);
 el.innerHTML=rows.length?rows.map(r=>{const bl=(YTM[r.mode||'voice']||YTM.voice).bars;return`<div class="yt" style="${r.status==='skipped'?'opacity:.4':''}"><button class="play" data-ytsnip="${esc(r.snippet||'')}" data-ytt="${esc(r.title||'')}">▶</button>
  <div style="min-width:0"><div class="name">${r.status==='ingested'?'<span class="badge" style="background:var(--acc)">added</span>':''}<a href="${esc(r.url)}" target="_blank" rel="noopener" style="color:inherit">${esc(r.title||r.id)}</a></div>
  <div class="meta">${r.style?`🧭 ${esc(r.style.split('---')[1])} · `:r.mode==='guided'?'🧭 your styles · ':''}${esc(r.channel||'')} · ${r.views!=null?Number(r.views).toLocaleString()+' views':''} · ${r.duration?Math.floor(r.duration/60)+':'+String(Math.round(r.duration%60)).padStart(2,'0'):''} · best moment @ ${Math.floor(r.best_at/60)}:${String(Math.round(r.best_at%60)).padStart(2,'0')} · “${esc((r.queries||r.query||'').split('|').join('”, “'))}”</div>
  <div class="bars"><span>${bl[0]}</span><i style="width:${Math.max(2,r.vocal*120)}px"></i><span>${bl[1]}</span><i style="width:${Math.max(2,r.neg*120)}px;background:#d96c6c"></i><span>your taste</span><i style="width:${Math.max(2,(r.taste||0)*120)}px;background:var(--acc)"></i></div></div>
  <div style="display:flex;gap:6px;align-items:center"><span class="score">${Math.round(r.score/mx*100)}</span>${r.status==='ingested'?'':`<button data-ytadd="${esc(r.url)}" data-ytid="${esc(r.id)}" class="pill">add source →</button>`}<button data-ytskip="${esc(r.id)}" title="dismiss">✕</button></div></div>`}).join('')
  :`<div class="empty">${ytQ&&!all?`Nothing scored for “${esc(ytQ)}” yet${ytPoll.wasRunning?' — still listening…':'. Try scouting again (it digs deeper each time) or tick “all searches”.'}`:'No candidates yet — pick a preset or type a search.'}</div>`}
async function ytStart(q){if(!q)return;ytQ=q;ytAll=false;if($('ytall'))$('ytall').checked=false;ytDraw();
 try{await api('api/ytscout',{query:q,n:+$('ytn').value,mode:ytMode,style:ytMode==='guided'?($('ytsty')?$('ytsty').value:ytSty):''});toast('scouting “'+q+'”…');ytPoll()}catch(e){toast('error: '+e.message)}}
async function ytPoll(){clearTimeout(ytT);if(st.tab!=='Y')return;let js=[];try{js=await api('api/jobs?kind=ytscout')}catch(e){}
 const el=$('ytjobs');if(!el)return;const run=js.filter(j=>j.running);
 el.innerHTML=js.slice(-1).map(j=>{const sm=j.tail.map(t=>t.startsWith('SUMMARY ')?JSON.parse(t.slice(8)):null).filter(Boolean).pop();
  const txt=sm?`${sm.found} found · ${sm.listened} listened to · ${sm.already} already scouted${sm.too_short?` · ${sm.too_short} too short`:''}${sm.failed?` · ${sm.failed} failed to download`:''}`:j.tail.slice(-2).map(esc).join('\n');
  return `<div class="prov"><b>${esc(j.target)}</b> — ${j.running?'listening…':'done'}<div class="meta" style="white-space:pre-wrap">${txt}</div></div>`}).join('');
 if(run.length||ytPoll.wasRunning){try{const d=await api('api/ytscout');ytRes=d.results;ytDraw()}catch(e){}}
 ytPoll.wasRunning=run.length>0;if(run.length)ytT=setTimeout(ytPoll,2500)}
document.addEventListener('click',async e=>{const ym=e.target.closest('[data-ytmode]');if(ym){ytMode=ym.dataset.ytmode;try{localStorage.setItem('ytMode',ytMode)}catch(err){}renderScout();return}
 const p=e.target.closest('[data-ytp]');if(p){$('ytq').value=p.dataset.ytp;if(p.dataset.yts!=null&&$('ytsty')){ytSty=p.dataset.yts;$('ytsty').value=ytSty}ytStart(p.dataset.ytp);return}
 const sn=e.target.closest('[data-ytsnip]');if(sn){if(!sn.dataset.ytsnip)return;if(players.has('yt')&&sn.classList.contains('playing')){stopAll();return}stopAll();
  const a=new Audio(url(sn.dataset.ytsnip));a.play();players.set('yt',a);a.onended=()=>{players.delete('yt');sn.classList.remove('playing');drawNP()};document.querySelectorAll('[data-ytsnip]').forEach(b=>b.classList.remove('playing'));sn.classList.add('playing');
  setNP(sn.dataset.ytsnip,null,'scout preview · '+sn.dataset.ytt,null);return}
 const ad=e.target.closest('[data-ytadd]');if(ad){ad.disabled=true;ad.textContent='adding…';try{await api('api/ingest',{target:ad.dataset.ytadd,drums:false});await api('api/ytscout/mark',{id:ad.dataset.ytid,status:'ingested'});
  ytRes.forEach(r=>{if(r.id===ad.dataset.ytid)r.status='ingested'});ytDraw();toast('added — downloading & mining in the background (progress under ＋ add source)')}catch(err){toast('error: '+err.message)}return}
 const skp=e.target.closest('[data-ytskip]');if(skp){await api('api/ytscout/mark',{id:skp.dataset.ytskip,status:'skipped'}).catch(()=>{});ytRes.forEach(r=>{if(r.id===skp.dataset.ytskip)r.status='skipped'});ytDraw()}});

// ================= sketchpad =================
const SK={lanes:[],playing:false,open:false,voices:[],timer:null,master:null,nextBar:0,start:0,arr:'',sec:4};window.SK=SK;
// ---------- arrangement: sections like "AABA", each SK.sec bars; every lane plays in the sections ticked on it (all by
// default). Empty = the sketch loops as one section. Playback, bounce, stems and the Live set all go through skBar.
const secAt=bar=>SK.arr?SK.arr[Math.floor(bar/SK.sec)%SK.arr.length]:'';
const laneOn=(l,bar)=>!SK.arr||!l.secs||l.secs.includes(secAt(bar));
const secLetters=()=>[...new Set(SK.arr.split(''))].sort();
const songBars=()=>SK.arr?SK.arr.length*SK.sec:0;
function secChips(l,k){if(!SK.arr)return'';return`<span class="secs" title="the sections this lane plays in">${secLetters().map(c=>`<button class="tbtn sec${!l.secs||l.secs.includes(c)?' on':''}" data-sksec="${k}:${c}">${c}</button>`).join('')}</span>`}
const np=$('np'),dock=document.createElement('div');dock.className='dock';np.parentNode.insertBefore(dock,np);
dock.insertAdjacentHTML('beforeend','<div class="sk" id="sk" hidden></div>');dock.appendChild(np);
$('skbtn').onclick=()=>{SK.open=!SK.open;drawSK();drawProj()};
const barLen=()=>240/(PROJ.bpm||120);
// a non-loop lane repeats every N bars: the shortest of 1/2/4/8/16 that fits the whole clip (so it never piles up on itself)
// repeat on the clip's own length in whole bars, so it comes back as it ends (powers of two left every lane
// silent together for bars at a time); a slightly longer clip's tail crossfades into the next pass
const skEvery=dur=>Math.max(1,Math.min(16,Math.round(dur/barLen())));
async function skAdd(i){if(!SERVED){toast('the sketchpad needs the local server');return}
 if(S[i][F.cat]==='Percussion'&&S[i][F.kind]!=='loop')return drumAdd(i);  // drum hits become pads in the drum lane
 if(SK.lanes.length>=8){toast('the sketchpad holds 8 lanes');return}
 if(SK.lanes.some(l=>l.path===S[i][F.path])){toast('already in the sketch');return}
 const patch={};if(!PROJ.key&&S[i][F.cam])patch.key=keyFromCam(S[i][F.cam]);if(!PROJ.bpm)patch.bpm=S[i][F.bpm]||120;if(Object.keys(patch).length){Object.assign(PROJ,patch);try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(e){}drawProj()}
 const loop=S[i][F.kind]==='loop';
 const lane={i,path:S[i][F.path],db:0,mute:false,solo:false,every:loop?0:skEvery(S[i][F.dur]),offset:0,buf:null,state:'loading'};
 SK.lanes.push(lane);SK.open=true;drawSK();drawProj();await skLoad(lane);drawSK();toast(`added to the sketch (${SK.lanes.length})`)}
async function skLoad(lane){if(lane.type==='drums'){await drumLoad(lane);return}lane.state='loading';lane.att=null;try{const ab=await (await fetch(conformURL(lane.path,lane.nat?'':PROJ.key,PROJ.bpm)+(lane.src?`&src=${lane.src}`:''))).arrayBuffer();lane.buf=await AC.decodeAudioData(ab);lane.norm=skNorm(lane.buf);
  if(S[lane.i]&&S[lane.i][F.kind]!=='loop'&&!lane.pulse)lane.pulse=await api('api/pulse?path='+encodeURIComponent(lane.path)).catch(()=>null);lane.state='ok'}catch(e){lane.state='error'}
 if(lane.db==null)lane.db=lane.vol!=null?Math.max(-24,Math.min(6,Math.round(20*Math.log10(Math.max(lane.vol,0.01)/0.8)*2)/2)):0}
// relative volume: every lane is levelled to the same loudness when it loads, so 0 dB on every fader = equally loud;
// the fader then moves it relative to the others
function skNorm(b){let s=0,n=0;const g=Math.pow(10,-50/20);for(let c=0;c<b.numberOfChannels;c++){const d=b.getChannelData(c);for(let k=0;k<d.length;k+=8){const v=d[k];if(Math.abs(v)>g){s+=v*v;n++}}}
 const rms=n?Math.sqrt(s/n):0.05;return Math.min(6,0.07/Math.max(rms,1e-4))}
const laneGain=l=>(l.norm||1)*Math.pow(10,(l.db||0)/20);
const dbTxt=db=>`${db>0?'+':''}${(+db).toFixed(1)} dB`;
// where the sound really starts inside a (trimmed) clip: phrases often open with a breath or silence, so the
// attack, not the file's first sample, is what gets placed on the beat
function skAttack(l){const [r0,R]=skRegion(l),key=`${r0}|${R}`;if(l.att&&l.att.key===key)return l.att.v;
 // the first attack tick in the selection (the same ticks drawn on the waveform), else the first loud sample
 const first=skStrong(l,r0,r0+R)[0];if(first!=null){const v=Math.max(0,first-r0-0.01);l.att={key,v};return v}const sr=l.buf.sampleRate,a=Math.floor(r0*sr),b=Math.min(l.buf.length,a+Math.floor(Math.min(R,4)*sr));
 let pk=0;const chs=[...Array(l.buf.numberOfChannels).keys()].map(c=>l.buf.getChannelData(c));for(const d of chs)for(let k=a;k<b;k+=2)pk=Math.max(pk,Math.abs(d[k]));
 let at=a;outer:for(let k=a;k<b;k+=2)for(const d of chs)if(Math.abs(d[k])>0.2*pk){at=k;break outer}
 const v=Math.min(1,Math.max(0,(at-a)/sr-0.01));l.att={key,v};return v}
let reloadSeq=0;
async function skReload(){if(!SK.lanes.length)return;const seq=++reloadSeq,was=SK.playing;if(was)skStop();SK.lanes.forEach(l=>l.state='loading');drawSK();
 await Promise.all(SK.lanes.map(skLoad));if(seq!==reloadSeq)return;drawSK();if(was)skPlay()}
function skGains(){const solo=SK.lanes.some(l=>l.solo);SK.lanes.forEach(l=>{if(l.g)l.g.gain.setTargetAtTime(l.mute||(solo&&!l.solo)?0:laneGain(l),AC.currentTime,0.02)})}
// a lane can be trimmed to part of its clip: trim = [from, to] as fractions of the (conformed) clip
const skRegion=l=>{const d=l.buf.duration,[a,b]=l.trim||[0,1];return [a*d,Math.max(0.01,(b-a)*d)]};
function skVoice(ctx,dest,l,t,dur,arr,xf=0){const s=ctx.createBufferSource();s.buffer=l.buf;const g=ctx.createGain();s.connect(g);g.connect(dest);
 let off=skRegion(l)[0];const lead=l.every===0||!skPulse(l)?0:skAttack(l);t+=l.nudge||0;
 if(lead>0){if(t-lead>=ctx.currentTime+0.005)t-=lead;else{off+=lead;dur=Math.max(0.01,dur-lead)}}
 const fi=Math.min(Math.max(0.004,(l.fin||0)/1000),dur/2),fo=Math.min(Math.max(0.004,xf,(l.fout||0)/1000),dur/2);
 g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(1,t+fi);g.gain.setValueAtTime(1,Math.max(t+fi,t+dur-fo));g.gain.linearRampToValueAtTime(0,t+dur);s.start(t,off,dur);
 if(ctx===AC){(l.on||(l.on=[])).push({t0:t,off,dur});if(l.on.length>8)l.on.shift()}  /* remembered for the playhead */if(arr){arr.push(s);s.onended=()=>{const k=arr.indexOf(s);if(k>=0)arr.splice(k,1)}}}
function skBar(ctx,dest,l,bar,t,L,arr){if(!laneOn(l,bar))return;if(l.type==='drums'){drumBar(ctx,dest,l,bar,t,L,arr);return}if(!l.buf)return;const R=skRegion(l)[1];if(l.every===0){const n=Math.max(1,Math.round(R/L));if(bar%n)return;skVoice(ctx,dest,l,t,Math.min(R,n*L),arr)}
 else{if(bar%l.every)return;const cut=R>l.every*L;skVoice(ctx,dest,l,t+l.offset*L/4,cut?l.every*L+0.15:R,arr,cut?0.15:0)}}  // a longer clip fades out under the next pass
// ---------- the drum lane: drum one-shots as pads in a step sequencer (16 steps a bar, 1 or 2 bars, velocity, swing)
// It's one lane, so mute / solo / its fader and every export (bounce, stems, Live set) treat it like any other.
const DSTEPS=32;  // steps stored per pad (2 bars); a 1-bar pattern uses the first 16
// the same kinds as drumkit.py (single hits; layered ones go by their first drum)
function drumKind(i){const t=(S[i][F.sub]||'').toLowerCase();
 return /^kick/.test(t)?'kick':/^snare/.test(t)?'snare':/rim|clap/.test(t)?'clap':/hat/.test(t)?'hat':/ride|crash|cymbal/.test(t)?'cymbal':/shaker|tamb/.test(t)?'shaker':/tom/.test(t)?'tom':'perc'}
function drumStarter(kind){const s=new Array(DSTEPS).fill(0),on=(ks,v=1)=>ks.forEach(k=>{s[k]=v;s[k+16]=v});
 if(kind==='kick'){on([0,10]);on([8],0.75)}else if(kind==='snare')on([4,12]);else if(kind==='clap')on([4,12],0.8);else if(kind==='cymbal')s[0]=0.8;else if(kind==='hat'){for(let k=0;k<DSTEPS;k+=2)s[k]=k%4?0.5:0.8}
 else if(kind==='shaker'){for(let k=0;k<DSTEPS;k++)s[k]=k%2?0.3:0.5}else if(kind==='tom')on([14],0.7);else on([6],0.6);return s}
function drumLane(make){let l=SK.lanes.find(x=>x.type==='drums');if(l||!make)return l;if(SK.lanes.length>=8)return null;
 l={type:'drums',pads:[],bars:1,swing:0,db:-4,mute:false,solo:false,state:'ok',buf:null};SK.lanes.push(l);return l}
const PADBUF=new Map();  // path -> decoding promise: the slices of one loop share it
async function drumPadLoad(p){if(p.buf)return;try{if(!PADBUF.has(p.path))PADBUF.set(p.path,fetch(url(p.path)).then(r=>r.arrayBuffer()).then(b=>AC.decodeAudioData(b)));
 p.buf=await PADBUF.get(p.path);p.norm=skNorm(p.buf);
 if(p.start==null){p.start=padAttack(p.buf);p.auto=p.start>0.003}}catch(e){p.err=true}}  // pads start on the hit, not on silence before it
async function drumLoad(l){l.state='loading';await Promise.all(l.pads.map(drumPadLoad));
 l.buf=l.pads.map(p=>p.buf).filter(Boolean).sort((a,b)=>b.duration-a.duration)[0]||AC.createBuffer(1,1,44100);l.state='ok'}  // buf: so "is it loaded" checks pass
async function drumAdd(i,{quiet=false,starter=true}={}){const l=drumLane(true);if(!l){toast('the sketchpad holds 8 lanes');return}
 if(l.pads.some(p=>p.path===S[i][F.path])){if(!quiet)toast('already in the drum lane');return}if(l.pads.length>=16){toast('the drum lane holds 16 pads');return}
 if(!PROJ.bpm){PROJ.bpm=S[i][F.bpm]||120;try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(e){}drawProj()}
 const kind=drumKind(i),first=!l.pads.some(p=>drumKind(p.i)===kind);  // a starter pattern for the first pad of each kind
 const pad={i,path:S[i][F.path],db:0,mute:false,steps:starter&&first?drumStarter(kind):new Array(DSTEPS).fill(0)};
 l.pads.push(pad);SK.open=true;drawSK();drawProj();await drumLoad(l);drawSK();if(!quiet)toast(`pad ${l.pads.length} in the drum lane (${kind})`)}
// offline (bounce, stems): a whole bar at once. Live playback uses drumTick, step by step, so edits are heard at once.
function drumBar(ctx,dest,l,bar,t,L,arr){const base=(bar%l.bars)*16,st=L/16,solo=l.pads.some(p=>p.solo);
 if(ctx===AC){(l.sched||(l.sched=[])).push({t,bar});if(l.sched.length>8)l.sched.shift()}
 for(let s=0;s<16;s++)l.pads.forEach(p=>{if(!p.buf||p.mute||(solo&&!p.solo))return;drumStep(ctx,dest,l,p,base+s,t+s*st+(s%2?l.swing*st:0),arr)})}
// one step of one pad: velocity, humanize (timing ±12 ms, velocity ±15% at 100%), a flam (a soft grace hit 20 ms
// before), and choke groups (a hit cuts off whatever else in its group is still ringing: closed hat chokes open hat)
function drumStep(ctx,dest,l,p,idx,t,arr){let v=p.steps[idx];if(!v)return null;const h=l.human||0;
 if(h){t+=(Math.random()*2-1)*0.012*h;v=Math.max(0.05,Math.min(1,v*(1+(Math.random()*2-1)*0.15*h)))}
 if(p.flams&&p.flams[idx])drumHit(ctx,dest,p,t-0.02,v*0.45,arr);
 const src=drumHit(ctx,dest,p,t,v,arr);
 if(src&&p.choke){const m=(l._choke||(l._choke=new WeakMap())),g=m.get(ctx)||{};m.set(ctx,g);const prev=g[p.choke];
  if(prev&&prev!==src&&prev._t<=t){try{prev._g.gain.cancelScheduledValues(t);prev._g.gain.setTargetAtTime(0,Math.max(t,ctx.currentTime),0.004);prev.stop(t+0.06)}catch(e){}}
  g[p.choke]=src}
 return src}
function drumTick(l){const L=barLen(),st=L/16,solo=l.pads.some(p=>p.solo);if(l.nextAbs==null)l.nextAbs=Math.max(0,Math.ceil((AC.currentTime-SK.start)/st));
 l.live=l.live||new Map();
 const look=document.hidden?1.5:0.12;  // background tabs tick about once a second: look further ahead there
 while(SK.start+l.nextAbs*st<AC.currentTime+look){const abs=l.nextAbs++,bar=Math.floor(abs/16),s=abs%16,base=(bar%l.bars)*16;
  if(s===0){(l.sched||(l.sched=[])).push({t:SK.start+bar*L,bar});if(l.sched.length>8)l.sched.shift()}
  const t=SK.start+abs*st+(s%2?l.swing*st:0);
  if(!laneOn(l,bar))continue;
  l.pads.forEach((p,r)=>{if(!p.steps[base+s]||!p.buf||p.mute||(solo&&!p.solo))return;const src=drumStep(AC,l.g,l,p,base+s,t,SK.voices);if(src)l.live.set(r+':'+(base+s),{src,t})})}
 if(l.live.size>256)[...l.live.keys()].slice(0,128).forEach(k=>l.live.delete(k))}
function drumHit(ctx,dest,p,t,v,arr){if(!p.buf)return null;
  const tt=Math.max(t,ctx.currentTime),src=ctx.createBufferSource(),g=ctx.createGain();src.buffer=p.buf;
  const rate=padRate(p),a=p.start||0,len=Math.max(0.005,((p.end||p.buf.duration)-a)/rate),amp=v*(p.norm||1)*Math.pow(10,(p.db||0)/20);
  src.playbackRate.value=rate;src.connect(g);g.connect(dest);g.gain.setValueAtTime(amp,tt);
  if(p.decay){g.gain.setTargetAtTime(0,tt+0.005,p.decay/4.6);src.start(tt,a,Math.min(len,p.decay*1.5))}  // -40 dB at `decay`
  else{g.gain.setValueAtTime(amp,tt+Math.max(0,len-0.004));g.gain.linearRampToValueAtTime(0,tt+len);src.start(tt,a,len)}
  src._g=g;src._t=tt;  // for choke groups
  if(arr){arr.push(src);src.onended=()=>{const k=arr.indexOf(src);if(k>=0)arr.splice(k,1)}}return src}
function drumLaneHTML(l,k){const n=16*l.bars;
 return `<div class="lane dlane${l.mute?' muted':''}" data-ln="${k}">
 <label class="onoff" title="turn the drum lane on or off"><input type="checkbox" data-skon="${k}" ${l.mute?'':'checked'}><span></span></label>
 <div class="lname"><div class="name">${secChips(l,k)}<span class="badge" style="background:${col('Percussion')}">${AB.Percussion}</span>Drums · ${l.pads.length} pad${l.pads.length===1?'':'s'}</div><div class="meta" title="click: on → soft → off · scroll over a step: its velocity · ⌥-click: a flam">click · scroll = velocity · ⌥ = flam</div></div>
 <div class="ctl"><select data-dbars="${k}" title="pattern length"><option value="1">1 bar</option><option value="2" ${l.bars===2?'selected':''}>2 bars</option></select>
  <label title="delays every other 16th: 0 = straight">swing <input type="range" min="0" max="0.6" step="0.05" value="${l.swing}" data-dswing="${k}" style="width:70px"></label>
  <label title="loosens timing (up to ±12 ms) and velocity (up to ±15%), so it isn't machine-tight">humanize <input type="range" min="0" max="1" step="0.05" value="${l.human||0}" data-dhuman="${k}" style="width:60px"></label>
  <button class="tbtn" data-dmidi="${k}" title="a Drum Rack of these pads (trimmed and edited as here, choke groups included) and a MIDI clip of the pattern, for Live">⇩ MIDI + rack</button>
  <button class="tbtn" data-dstart="${k}" title="a starter pattern from the pad types (kick, snare, hats…)">✨ starter</button><button class="tbtn" data-dclear="${k}">clear</button>
  <button class="tbtn${l.find?' on':''}" data-dfind="${k}" title="hits for the kinds this kit is missing, that sound like they were recorded with the pads you have">🔎 complete the kit</button></div>
 <div class="fader" title="drum lane volume · double-click for 0 dB"><input type="range" min="-24" max="6" step="0.5" value="${l.db||0}" data-skv="${k}"><output>${dbTxt(l.db||0)}</output></div>
 <button class="tbtn${l.solo?' on':''}" data-sks="${k}" title="solo">S</button><button class="tbtn" data-skx="${k}" title="remove the drum lane">✕</button>
 <div class="dgrid" data-dgrid="${k}" style="--n:${n}">${l.pads.map((p,r)=>{const s=S[p.i]||[];return `<div class="drow${p.mute?' muted':''}">
  <button class="tbtn" data-dpad="${k}:${r}" title="hear it">▶</button><button class="dlab dedit${p.open?' on':''}" data-dedit="${k}:${r}" title="${esc(s[F.artist]||'')} — ${esc(s[F.title]||'')} · click to ${p.open?'close':'open'} this pad's editor (start, end, tune, decay)"><span class="dtri">${p.open?'▾':'▸'}</span>${esc(p.label||s[F.sub]||'hit')}${p.tune||p.decay||p.end||(p.start>0.003&&!p.auto)?' ✎':''}</button>
  <div class="dsteps">${p.steps.slice(0,n).map((v,j)=>`<button class="dstep${v?' on':''}${j%4===0?' beat':''}${p.flams&&p.flams[j]?' flam':''}" data-dstep="${k}:${r}:${j}" ${v?`style="--v:${Math.round(v*100)}%"`:''} title="${v?`velocity ${Math.round(v*100)}%${p.flams&&p.flams[j]?' · flam':''}`:'off'}"></button>`).join('')}</div>
  <select class="dchoke" data-dchoke="${k}:${r}" title="choke group: a hit cuts off the others in its group that are still ringing (closed hat chokes open hat)"><option value="0">—</option>${[1,2,3].map(g=>`<option value="${g}" ${p.choke===g?'selected':''}>choke ${g}</option>`).join('')}</select>
  <span class="dvol" title="this pad's volume against the other pads (every pad starts equally loud at 0 dB) · double-click for 0 dB"><input type="range" min="-24" max="6" step="0.5" value="${p.db||0}" data-dpv="${k}:${r}"><output>${dbTxt(p.db||0)}</output></span>
  <button class="tbtn${p.mute?' on':''}" data-dmute="${k}:${r}" title="mute this pad">M</button><button class="tbtn" data-dpx="${k}:${r}" title="remove this pad">✕</button></div>${p.open?padEditHTML(l,k,p,r):''}`}).join('')||'<div class="sub">add drum one-shots with ＋, or send a song\'s drum rack here</div>'}${drumFindHTML(l,k)}</div></div>`}
function drumFindHTML(l,k){const f=l.find;if(!f)return'';if(f.loading&&!f.missing)return '<div class="sub dfind">listening for hits that match this kit…</div>';if(f.error)return `<div class="sub dfind">${esc(f.error)}</div>`;
 const rows=f.missing.filter(m=>f.all||!m.have);
 const pick=(m,p)=>{const i=byPath.get(p.path);if(i==null)return'';const s=S[i];const steer=f.steer[m.kind]===p.path;
  return `<span class="dfpick${steer?' steer':''}"><button class="tbtn" data-dfplay="${esc(p.path)}" title="hear it">▶</button><span class="sub" title="${esc(s[F.artist])} — ${esc(s[F.title])} · ${esc(p.sub)}">${esc(s[F.artist]).slice(0,18)}${p.same_song?' · same song':''}</span>
   <button class="tbtn" data-dfsteer="${k}|${m.kind}|${esc(p.path)}" title="more like this: re-rank ${esc(m.label.toLowerCase())} toward this one's sound (click again to undo)">≈</button><button class="tbtn" data-dfno="${k}|${m.kind}|${esc(p.path)}" title="not this one: the next slides in">✕</button><button class="tbtn" data-dfadd="${i}" title="add it as a pad (with a starter part)">＋</button></span>`};
 return `<div class="dfind"><div class="sub" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span>${rows.length?'Picked to sound like the same recording (room, tape, brightness):':'Every kind is covered.'}</span>
  <label><input type="checkbox" data-dfall="${k}" ${f.all?'checked':''}> also kinds you have (alternatives)</label>${f.loading?'<span>…</span>':''}</div>
  ${rows.map(m=>{const vis=m.picks.filter(p=>!f.hidden.has(p.path)),o=Math.min(f.off[m.kind]||0,Math.max(0,vis.length-3)),page=vis.slice(o,o+3);
  return `<div class="dfrow"><span class="dlab">${esc(m.label)}${m.have?' <span class="sub">(have)</span>':''}${m.steered?' <span class="sub">· steered</span>':''}</span><div class="dfpicks">${page.map(p=>pick(m,p)).join('')||'<span class="sub">no more</span>'}
   <span class="dfnav">${o>0?`<button class="tbtn" data-dfmore="${k}|${m.kind}|-3" title="back">‹</button>`:''}<span class="sub">${vis.length?`${o+1}–${Math.min(o+3,vis.length)} of ${vis.length}`:''}</span>${o+3<vis.length?`<button class="tbtn" data-dfmore="${k}|${m.kind}|3" title="three more">↻ more</button>`:''}</span></div></div>`}).join('')}</div>`}
async function drumFind(l,keep){const prev=l.find||{};l.find={...prev,loading:true,missing:keep?prev.missing:null,off:keep?prev.off||{}:{},hidden:prev.hidden||new Set(),steer:prev.steer||{},all:!!prev.all};drawSK();
 try{const r=await api('api/drumkit',{paths:l.pads.map(p=>p.path),steer:l.find.steer,everything:true});
  if(r.error)l.find={error:r.error};else{const off={...l.find.off};r.missing.forEach(m=>{if(m.steered)off[m.kind]=0});Object.assign(l.find,{missing:r.missing,loading:false,off})}}catch(e){l.find={error:"couldn't search: "+e.message}}drawSK()}
// the playing step lights up
function drumHeads(){const now=AC.currentTime;SK.lanes.forEach((l,k)=>{if(l.type!=='drums')return;const g=document.querySelector(`[data-dgrid="${k}"]`);if(!g)return;
 const L=barLen(),v=(l.sched||[]).filter(x=>now>=x.t&&now<x.t+L).pop(),cur=SK.playing&&v?(v.bar%l.bars)*16+Math.floor((now-v.t)/(L/16)):-1;
 if(g._cur===cur)return;g._cur=cur;g.querySelectorAll('.dstep.now').forEach(b=>b.classList.remove('now'));if(cur>=0)g.querySelectorAll(`[data-dstep$=":${cur}"]`).forEach(b=>b.classList.add('now'))})}
$('sk').addEventListener('click',async e=>{const t=e.target.closest('[data-dstep],[data-dpad],[data-dpx],[data-dmute],[data-dstart],[data-dclear],[data-dfind],[data-dfplay],[data-dfadd],[data-dfmore],[data-dfno],[data-dfsteer]');if(!t)return;e.stopPropagation();
 if(t.dataset.dfmore!=null){const [k,kind,d]=t.dataset.dfmore.split('|'),f=SK.lanes[+k].find;f.off[kind]=Math.max(0,(f.off[kind]||0)+(+d));drawSK();return}
 if(t.dataset.dfno!=null){const [k,,p]=t.dataset.dfno.split('|');SK.lanes[+k].find.hidden.add(p);drawSK();return}
 if(t.dataset.dfsteer!=null){const [k,kind,p]=t.dataset.dfsteer.split('|'),l=SK.lanes[+k];if(l.find.steer[kind]===p)delete l.find.steer[kind];else l.find.steer[kind]=p;drumFind(l,true);return}
 if(t.dataset.dfind!=null){const l=SK.lanes[+t.dataset.dfind];if(l.find&&!l.find.loading){l.find=null;drawSK();return}drumFind(l);return}
 if(t.dataset.dfplay!=null){stopAll();const a=new Audio(url(t.dataset.dfplay));a.play();players.set('df',a);a.onended=()=>players.delete('df');return}
 if(t.dataset.dfadd!=null){const l=drumLane();await drumAdd(+t.dataset.dfadd);if(l&&l.find)drumFind(l,true);return}
 if(t.dataset.dstep){const [k,r,j]=t.dataset.dstep.split(':').map(Number),p=SK.lanes[k].pads[r],v=p.steps[j];
  if(e.altKey){p.flams=p.flams||new Array(DSTEPS).fill(0);p.flams[j]=p.flams[j]?0:1;if(!v)p.steps[j]=1;drawSK();return}
  p.steps[j]=!v?1:v>0.7?0.55:0;
  t.classList.toggle('on',!!p.steps[j]);t.style.setProperty('--v',Math.round(p.steps[j]*100)+'%');
  const q=SK.lanes[k].live&&SK.lanes[k].live.get(r+':'+j);if(q&&!p.steps[j]&&q.t>AC.currentTime){try{q.src.stop()}catch(err){}}return}
 if(t.dataset.dpad){const [k,r]=t.dataset.dpad.split(':').map(Number),p=SK.lanes[k].pads[r];if(!p.buf)return;AC.resume();
  const one={...SK.lanes[k],pads:[{...p,steps:[1],mute:false,solo:false}],bars:1,swing:0};drumBar(AC,AC.destination,one,0,AC.currentTime+0.01,barLen(),null);return}
 if(t.dataset.dmute){const [k,r]=t.dataset.dmute.split(':').map(Number),p=SK.lanes[k].pads[r];p.mute=!p.mute;drawSK();return}
 if(t.dataset.dpx){const [k,r]=t.dataset.dpx.split(':').map(Number),l=SK.lanes[k];l.pads.splice(r,1);if(!l.pads.length)SK.lanes.splice(k,1);if(!SK.lanes.length)skStop();drawSK();drawProj();return}
 const l=SK.lanes[+(t.dataset.dstart??t.dataset.dclear)];
 if(t.dataset.dclear!=null){l.pads.forEach(p=>p.steps.fill(0));drawSK();return}
 const seen=new Set();l.pads.forEach(p=>{const kd=drumKind(p.i);p.steps=seen.has(kd)?new Array(DSTEPS).fill(0):drumStarter(kd);seen.add(kd)});drawSK()},true);
$('sk').addEventListener('change',e=>{const t=e.target;if(t.dataset.dbars!=null){const l=SK.lanes[+t.dataset.dbars];l.bars=+t.value;
  if(l.bars===2)l.pads.forEach(p=>{if(!p.steps.slice(16).some(Boolean))for(let j=0;j<16;j++)p.steps[16+j]=p.steps[j]});drawSK()}},true);  // 1 → 2 bars: the second bar starts as a copy
document.addEventListener('click',async e=>{if(!e.target.closest('#racksk'))return;e.stopPropagation();
 const per={},order=['kick','snare','hat','shaker','tom','perc'],ids=[];  // a playable kit: up to 2 of each kind, 12 pads at most
 RACK.ids.forEach(i=>{const k=drumKind(i);(per[k]||(per[k]=[])).push(i)});order.forEach(k=>(per[k]||[]).slice(0,2).forEach(i=>ids.length<12&&ids.push(i)));const l=drumLane(true);if(!l){toast('the sketchpad holds 8 lanes');return}
 for(const i of ids)await drumAdd(i,{quiet:true});toast(`${ids.length} pads in the drum lane · press ▶ in the sketchpad`)},true);
$('sk').addEventListener('change',e=>{const t=e.target;if(t.dataset.dfall!=null){const l=SK.lanes[+t.dataset.dfall];l.find.all=t.checked;drawSK()}},true);
$('sk').addEventListener('change',e=>{const t=e.target;
 if(t.id==='skarr'){SK.arr=t.value.toUpperCase().replace(/[^A-H]/g,'').slice(0,16);
  SK.lanes.forEach(l=>{if(l.secs){l.secs=l.secs.split('').filter(c=>SK.arr.includes(c)).join('');if(!l.secs)l.secs=null}});drawSK()}
 else if(t.id==='sksec'){SK.sec=+t.value;drawSK()}},true);
$('sk').addEventListener('keydown',e=>{if(e.target.id==='skarr'&&e.key==='Enter')e.target.blur()},true);
$('sk').addEventListener('click',e=>{const b=e.target.closest('[data-sksec]');if(!b)return;e.stopPropagation();const [k,c]=b.dataset.sksec.split(':'),l=SK.lanes[+k];
 const cur=l.secs==null?secLetters().join(''):l.secs,next=cur.includes(c)?cur.replace(c,''):cur+c;
 l.secs=next.length===secLetters().length?null:[...next].sort().join('');drawSK()},true);
$('sk').addEventListener('wheel',e=>{const t=e.target.closest&&e.target.closest('[data-dstep]');if(!t)return;e.preventDefault();
 const [k,r,j]=t.dataset.dstep.split(':').map(Number),p=SK.lanes[k].pads[r];let v=p.steps[j]||0;v=Math.round(Math.max(0,Math.min(1,v+(e.deltaY<0?0.1:-0.1)))*10)/10;
 p.steps[j]=v;t.classList.toggle('on',!!v);t.style.setProperty('--v',Math.round(v*100)+'%');t.title=v?`velocity ${Math.round(v*100)}%`:'off'},{passive:false});
$('sk').addEventListener('change',e=>{const t=e.target;if(t.dataset.dchoke!=null){const [k,r]=t.dataset.dchoke.split(':').map(Number);SK.lanes[k].pads[r].choke=+t.value||0}},true);
$('sk').addEventListener('input',e=>{const t=e.target;if(t.dataset.dhuman!=null)SK.lanes[+t.dataset.dhuman].human=+t.value},true);
$('sk').addEventListener('click',async e=>{const b=e.target.closest('[data-dmidi]');if(!b)return;e.stopPropagation();const l=SK.lanes[+b.dataset.dmidi];
 const name=(($('skname').value||'').trim()||SK.name||'Drums '+new Date().toISOString().slice(0,10))+' drums';b.textContent='exporting…';
 try{const r=await api('api/drums/export',{name,bpm:PROJ.bpm||120,bars:l.bars,swing:l.swing,
   pads:l.pads.map(p=>({path:p.path,label:p.label||(S[p.i]||[])[F.sub]||'',steps:p.steps.slice(0,16*l.bars),flams:(p.flams||[]).slice(0,16*l.bars),choke:p.choke||0,mute:!!p.mute,start:p.start||0,end:p.end||null,tune:p.tune||0,decay:p.decay||0}))});
  b.textContent='⇩ MIDI + rack';toast(`rack + MIDI clip → ${r.dest.split('/').slice(-2).join('/')} · drop the rack on a track, then the clip`)}catch(err){b.textContent='⇩ MIDI + rack';toast('export failed: '+err.message)}},true);
$('sk').addEventListener('input',e=>{const t=e.target;if(t.dataset.dswing!=null)SK.lanes[+t.dataset.dswing].swing=+t.value},true);
// ---------- editing pads inside the drum lane: start on the hit, end, tune, decay (all live, no rendering)
// where the hit really starts: the first sample above a quarter of the peak, backed up to where it rises from quiet
function padAttack(buf){const sr=buf.sampleRate,d=buf.getChannelData(0),n=Math.min(d.length,sr*3);let pk=0;for(let k=0;k<n;k++)pk=Math.max(pk,Math.abs(d[k]));
 let a=0;while(a<n&&Math.abs(d[a])<0.25*pk)a++;let b=a;const floor=0.03*pk,lim=Math.max(0,a-Math.floor(0.02*sr));while(b>lim&&Math.abs(d[b])>floor)b--;
 return Math.max(0,b/sr-0.001)}
const padRate=p=>Math.pow(2,(p.tune||0)/12);
function padWaves(){SK.lanes.forEach((l,k)=>{if(l.type!=='drums')return;l.pads.forEach((p,r)=>{if(!p.open||!p.buf)return;const c=document.querySelector(`[data-dpc="${k}:${r}"]`);if(c)padWave(c,p)})})}
function padWave(c,p){const dpr=devicePixelRatio||1,W=c.clientWidth*dpr,H=56*dpr;c.width=W;c.height=H;const g=c.getContext('2d'),buf=p.buf,d=buf.getChannelData(0),sr=buf.sampleRate;
 const view=Math.min(buf.duration,Math.max(0.5,(p.end||buf.duration)+0.1)),per=Math.max(1,Math.floor(view*sr/W)),X=t=>t/view*W,s0=p.start||0,e0=p.end||buf.duration;
 for(let x=0;x<W;x++){let m=0;for(let j=x*per;j<Math.min(d.length,(x+1)*per);j+=2)m=Math.max(m,Math.abs(d[j]));const t=x/W*view;g.fillStyle=t>=s0&&t<=e0?'#e0a458':'#3a4048';g.fillRect(x,H/2-m*H/2,1,Math.max(1,m*H))}
 g.fillStyle='#fff';g.fillRect(X(s0)-dpr,0,2*dpr,H);g.fillStyle='#7fb0c9';g.fillRect(X(e0)-dpr,0,2*dpr,H);c._view=view}
function padEditHTML(l,k,p,r){const ms=Math.round((p.start||0)*1000),dec=p.decay||0;
 return `<div class="dped"><canvas data-dpc="${k}:${r}" title="drag the white line to where the hit starts, the blue one to where it ends"></canvas>
 <div class="ctl"><span class="sub">start ${ms} ms${p.auto?' (moved to the hit)':''}</span><button class="tbtn" data-dpstart="${k}:${r}:hit" title="put the start on the hit again">to the hit</button><button class="tbtn" data-dpstart="${k}:${r}:0" title="play from the file's beginning">from 0</button>
  <button class="tbtn" data-dpend="${k}:${r}" title="let it ring to the end of the file">full length</button>
  <label>tune <input type="range" min="-12" max="12" step="1" value="${p.tune||0}" data-dptune="${k}:${r}"><output>${p.tune>0?'+':''}${p.tune||0} st</output></label>
  <label title="shortens the tail with a natural fade">decay <input type="range" min="0" max="100" step="1" value="${decayVal(dec)}" data-dpdec="${k}:${r}"><output>${dec?dec.toFixed(2)+' s':'natural'}</output></label>
  <button class="tbtn" data-dpad="${k}:${r}">▶</button><button class="tbtn" data-dpfull="${k}:${r}" title="open it in the full editor (punch, drive, low cut…); save as new and the pad switches to your edit">↗ full editor</button></div></div>`}
// drag the start / end lines
document.addEventListener('mousedown',e=>{const c=e.target.closest&&e.target.closest('[data-dpc]');if(!c)return;e.preventDefault();
 const [k,r]=c.dataset.dpc.split(':').map(Number),p=SK.lanes[k].pads[r],t0=()=>((e.offsetX)/c.clientWidth)*c._view;
 const at=ev=>Math.max(0,Math.min(p.buf.duration,(ev.clientX-c.getBoundingClientRect().left)/c.clientWidth*c._view));
 const which=Math.abs(t0()-(p.start||0))<=Math.abs(t0()-(p.end||p.buf.duration))?'start':'end';
 const move=ev=>{const t=at(ev);if(which==='start'){p.start=Math.min(t,(p.end||p.buf.duration)-0.01);p.auto=false}else p.end=Math.max(t,(p.start||0)+0.01);padWave(c,p)};
 move(e);const up=()=>{removeEventListener('mousemove',move);removeEventListener('mouseup',up);drawSK()};addEventListener('mousemove',move);addEventListener('mouseup',up)});
$('sk').addEventListener('click',async e=>{const t=e.target.closest('[data-dedit],[data-dpstart],[data-dpend],[data-dpfull]');if(!t)return;e.stopPropagation();
 const [k,r,how]=(t.dataset.dedit||t.dataset.dpstart||t.dataset.dpend||t.dataset.dpfull).split(':'),p=SK.lanes[+k].pads[+r];
 if(t.dataset.dedit!=null){p.open=!p.open;drawSK();return}
 if(t.dataset.dpstart!=null){if(how==='hit'){p.start=padAttack(p.buf);p.auto=true}else{p.start=0;p.auto=false}drawSK();return}
 if(t.dataset.dpend!=null){p.end=null;drawSK();return}
 // the full editor: when you save as new, this pad switches to your edit
 select(p.i,'list');await openEditor(p.i);if(ED){ED.fromPad={lane:SK.lanes[+k],pad:p}};toast('edit it, then save as new: the pad switches to your edit')},true);
$('sk').addEventListener('input',e=>{const t=e.target;if(t.dataset.dpv==null)return;const [k,r]=t.dataset.dpv.split(':').map(Number),p=SK.lanes[k].pads[r];
 p.db=+t.value;t.parentNode.querySelector('output').textContent=dbTxt(p.db)},true);  // heard within a step (drumTick reads it as it schedules)
$('sk').addEventListener('dblclick',e=>{const t=e.target;if(!t.dataset||t.dataset.dpv==null)return;e.stopPropagation();const [k,r]=t.dataset.dpv.split(':').map(Number);SK.lanes[k].pads[r].db=0;drawSK()},true);
$('sk').addEventListener('input',e=>{const t=e.target;if(t.dataset.dptune==null&&t.dataset.dpdec==null)return;const [k,r]=(t.dataset.dptune||t.dataset.dpdec).split(':').map(Number),p=SK.lanes[k].pads[r],o=t.parentNode.querySelector('output');
 if(t.dataset.dptune!=null){p.tune=+t.value;o.textContent=(p.tune>0?'+':'')+p.tune+' st'}else{p.decay=+decayS(+t.value).toFixed(3);o.textContent=p.decay?p.decay.toFixed(2)+' s':'natural'}},true);
const _drawSKpad=drawSK;drawSK=function(){_drawSKpad();padWaves()};
const _edSavePad=edSave;edSave=async function(...a){const fp=ED&&ED.fromPad,n0=S.length;const r=await _edSavePad.apply(this,a);
 if(fp&&S.length>n0){const j=S.length-1,p=fp.pad;Object.assign(p,{i:j,path:S[j][F.path],buf:null,start:null,end:null,tune:0,decay:0});await drumLoad(fp.lane);drawSK();toast('the pad now plays your edit')}return r};
// ---------- tempo in the sketchpad: drums-only sketches change tempo live; sample lanes need re-stretching (a reload)
function skTempo(b){b=Math.max(40,Math.min(220,Math.round(b*10)/10));if(!b||b===PROJ.bpm)return;
 if(!SK.playing||SK.lanes.some(l=>l.type!=='drums')){if(SK.playing&&SK.lanes.some(l=>l.type!=='drums'))toast(`re-stretching the lanes to ${b} bpm…`);setProj({bpm:b});drawSK();return}
 const now=AC.currentTime,pos=(now-SK.start)/barLen();PROJ.bpm=b;try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(e){}drawProj();
 SK.start=now-pos*barLen();SK.lanes.forEach(l=>{l.nextAbs=null;l.sched=[]});  // same place in the bar, new speed
 const inp=$('skbpm');if(inp&&document.activeElement!==inp)inp.value=Math.round(b)}
let TAPS=[];
$('sk').addEventListener('click',e=>{const t=e.target.closest('[data-skbpm],#sktap');if(!t)return;e.stopPropagation();
 if(t.id==='sktap'){const now=performance.now();TAPS=TAPS.filter(x=>now-x<2500);TAPS.push(now);
  if(TAPS.length>=3){const iv=TAPS.slice(1).map((x,k)=>x-TAPS[k]);skTempo(60000/(iv.reduce((a,c)=>a+c,0)/iv.length));const inp=$('skbpm');if(inp)inp.value=Math.round(PROJ.bpm)}
  t.textContent=TAPS.length<3?`tap ${TAPS.length}/3…`:'tap';clearTimeout(t._r);t._r=setTimeout(()=>{t.textContent='tap'},2600);return}
 skTempo((PROJ.bpm||120)+(+t.dataset.skbpm)*(e.shiftKey?5:1))},true);
$('sk').addEventListener('change',e=>{if(e.target.id==='skbpm')skTempo(+e.target.value)},true);
$('sk').addEventListener('keydown',e=>{if(e.target.id==='skbpm'&&e.key==='Enter')e.target.blur()},true);
// ---------- sketch state: one definition, used by save, bounce provenance, undo/redo, "unsaved" and the draft
function skLanesState(){return SK.lanes.map(l=>l.type==='drums'?{type:'drums',secs:l.secs||null,bars:l.bars,swing:l.swing,db:l.db||0,mute:!!l.mute,solo:!!l.solo,
  human:l.human||0,pads:l.pads.map(p=>({path:p.path,label:p.label||null,db:p.db||0,mute:!!p.mute,steps:p.steps.slice(),flams:(p.flams||[]).slice(),choke:p.choke||0,start:p.start,end:p.end||null,tune:p.tune||0,decay:p.decay||0,auto:!!p.auto}))}
 :({path:l.path,secs:l.secs||null,db:l.db||0,vol:+(0.8*Math.pow(10,(l.db||0)/20)).toFixed(3),mute:!!l.mute,solo:!!l.solo,every:l.every,offset:l.offset,trim:l.trim||null,fin:l.fin||0,fout:l.fout||0,nudge:l.nudge||0,src:l.src||null,nat:!!l.nat}))}
const skSnap=()=>JSON.stringify({key:PROJ.key||null,bpm:PROJ.bpm||null,name:SK.name||'',arr:SK.arr||'',sec:SK.sec||4,lanes:skLanesState()});
const EMPTY_SNAP=()=>JSON.stringify({key:PROJ.key||null,bpm:PROJ.bpm||null,name:'',arr:'',sec:4,lanes:[]});
SK.saved=null;
const skDirty=()=>SK.lanes.length>0&&skSnap()!==SK.saved;
// put a remembered state back, reusing audio already loaded (only what changed is fetched again)
async function skRestore(st){const was=SK.playing;if(was)skStop();
 const keyChanged=(st.key||null)!==(PROJ.key||null)||(st.bpm||null)!==(PROJ.bpm||null);
 if(keyChanged){Object.assign(PROJ,{key:st.key,bpm:st.bpm});try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(e){}drawProj()}
 const old=new Map();SK.lanes.forEach(l=>{if(l.type==='drums')l.pads.forEach(p=>{if(p.buf)old.set('d|'+p.path,p)});else if(l.buf)old.set(`${l.path}|${l.nat?1:0}|${l.src||''}`,l)});
 SK.name=st.name||'';SK.arr=st.arr||'';SK.sec=st.sec||4;
 SK.lanes=st.lanes.map(l=>{if(l.type==='drums'){return {...l,state:'loading',buf:null,pads:l.pads.map(p=>{const o=old.get('d|'+p.path);return {...p,steps:p.steps.slice(),i:byPath.get(p.path),buf:o?o.buf:null,norm:o?o.norm:null}}).filter(p=>p.i!=null)}}
  const o=keyChanged?null:old.get(`${l.path}|${l.nat?1:0}|${l.src||''}`);return {...l,i:byPath.get(l.path),buf:o?o.buf:null,norm:o?o.norm:null,pulse:o?o.pulse:null,ons:o?o.ons:null,state:o?'ok':'loading'}})
  .filter(l=>l.type==='drums'?l.pads.length:l.i!=null);
 drawSK();drawProj();await Promise.all(SK.lanes.filter(l=>l.type==='drums'||l.state!=='ok').map(skLoad));drawSK();if(was&&SK.lanes.length)skPlay()}
// undo / redo: a change is recorded once the sketch has been still for a moment, so a fader drag is one step
const UNDO={past:[],future:[],cur:null,seen:null,still:0,hold:false};
// the draft: a refresh or crash keeps your sketch (written whenever the sketch settles, undo and redo included)
const skDraft=()=>{try{localStorage.setItem('atlasSketchDraft',JSON.stringify({snap:UNDO.cur,saved:SK.saved}))}catch(e){}};
function undoTick(){if(UNDO.hold)return;const s=skSnap();
 if(UNDO.cur===null){UNDO.cur=s;UNDO.seen=s;return}
 if(s!==UNDO.seen){UNDO.seen=s;UNDO.still=0}else if(s!==UNDO.cur&&++UNDO.still>=1){UNDO.past.push(UNDO.cur);if(UNDO.past.length>100)UNDO.past.shift();UNDO.future=[];UNDO.cur=s;skDraft()}
 skMarkSave()}
async function skUndo(dir){const from=dir<0?UNDO.past:UNDO.future,to=dir<0?UNDO.future:UNDO.past;undoTick();
 if(UNDO.seen!==UNDO.cur){to.push(UNDO.cur);UNDO.cur=UNDO.seen}  // an unrecorded change in flight counts as a step
 if(!from.length){toast(dir<0?'nothing to undo':'nothing to redo');return}
 to.push(UNDO.cur);const s=from.pop();UNDO.cur=UNDO.seen=s;UNDO.hold=true;try{await skRestore(JSON.parse(s))}finally{UNDO.cur=UNDO.seen=skSnap();UNDO.hold=false}
 skDraft();SK.open=true;drawSK();toast(dir<0?`undone · ${UNDO.past.length} more to undo`:`redone`)}
function skMarkSave(){const b=$('sksave');if(!b)return;const d=skDirty();b.classList.toggle('dirty',d);b.textContent=d?'save •':'save';b.title=d?'unsaved changes: save to keep this version (⌘S)':'saved (⌘S)';
 const u=$('skundo'),r=$('skredo');if(u)u.disabled=!UNDO.past.length&&UNDO.seen===UNDO.cur;if(r)r.disabled=!UNDO.future.length}
setInterval(undoTick,300);
$('sk').addEventListener('click',e=>{const t=e.target.closest('#skundo,#skredo');if(!t)return;e.stopPropagation();skUndo(t.id==='skundo'?-1:1)},true);
document.addEventListener('keydown',e=>{if(!(e.metaKey||e.ctrlKey))return;const k=e.key.toLowerCase();
 if(k==='s'&&SK.lanes.length){e.preventDefault();if(e.target.id==='skname')SK.name=e.target.value;SK.open=true;drawSK();$('sksave')&&$('sksave').click();return}  // ⌘S saves, even from the name field
 if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;  // ⌘Z in a text field undoes the typing
 if(k==='z'&&SK.open&&(SK.lanes.length||UNDO.past.length||UNDO.future.length)){e.preventDefault();skUndo(e.shiftKey?1:-1);return}
 if(k==='z'&&!e.shiftKey){const a=[...ACTS].reverse().find(x=>!x.done);if(a){e.preventDefault();actUndo(a)};return}
 if(k==='y'&&UNDO.future.length){e.preventDefault();skUndo(1);return}
 });
// your sketch from last time (a refresh, a crash): it comes back, not playing, marked unsaved if it was
setTimeout(async()=>{let d=null;try{d=JSON.parse(localStorage.getItem('atlasSketchDraft')||'null')}catch(e){}
 if(!d||!d.snap||SK.lanes.length)return;const st=JSON.parse(d.snap);if(!st.lanes||!st.lanes.length)return;
 UNDO.hold=true;try{await skRestore(st);SK.saved=d.saved||null}finally{UNDO.cur=UNDO.seen=skSnap();UNDO.hold=false}
 drawSK();toast(`your sketch from last time is back (${SK.lanes.length} lane${SK.lanes.length>1?'s':''}) · 🎛 sketchpad`)},1500);
function skPlay(){if(SK.playing||!SK.lanes.length)return;AC.resume();
 stopAll();padsStopLoop();  // a sketch takes over from whatever was playing (clips over a running sketch still work)
SK.master=AC.createGain();SK.master.gain.value=0.9;SK.master.connect(AC.destination);
 SK.lanes.forEach(l=>{l.g=AC.createGain();l.g.connect(SK.master);if(l.type==='drums'){l.nextAbs=null;l.live=new Map();l.sched=[]}});skGains();SK.start=linkNextBar();SK.nextBar=0;SK.playing=true;SK.voices=[];skTick();requestAnimationFrame(skAnim);drawSK()}
function skTick(){if(!SK.playing)return;const L=barLen(),ahead=1.2+Math.max(0,...SK.lanes.map(l=>l.buf&&l.every&&l.type!=='drums'?Math.min(8,skAttack(l)):0));
 SK.lanes.forEach(l=>{if(!l.g&&SK.master){l.g=AC.createGain();l.g.connect(SK.master);skGains()}});  // a lane added while playing joins in
 while(SK.start+SK.nextBar*L<AC.currentTime+ahead){const t=SK.start+SK.nextBar*L;SK.lanes.forEach(l=>{if(l.g&&l.type!=='drums')skBar(AC,l.g,l,SK.nextBar,t,L,SK.voices)});SK.nextBar++}
 SK.lanes.forEach(l=>{if(l.g&&l.type==='drums')drumTick(l)});  // drums: step by step, 120 ms ahead, so edits are heard at once
 SK.timer=setTimeout(skTick,25)}
function skStop(){SK.playing=false;clearTimeout(SK.timer);const now=AC.currentTime;if(SK.master){SK.master.gain.setTargetAtTime(0,now,0.015);const m=SK.master;setTimeout(()=>{try{m.disconnect()}catch(e){}},150)}
 SK.voices.forEach(s=>{try{s.stop(now+0.08)}catch(e){}});SK.voices=[];SK.lanes.forEach(l=>l.on=[]);drawSK()}
function skAnim(){skHeads();drumHeads();if(!SK.playing)return;const el=$('skpos');if(el){const L=barLen(),t=AC.currentTime-SK.start;const b=Math.floor(t/L);el.textContent=t<0?'waiting for the bar…':`${SK.arr?`section ${secAt(b)} · `:''}bar ${(SK.arr?b%songBars():b)+1} · beat ${Math.floor(t%L/(L/4))+1}`}requestAnimationFrame(skAnim)}
function skWave(c,buf,trim){if(!c||!buf)return;const dpr=devicePixelRatio||1,W=c.clientWidth*dpr,H=30*dpr;c.width=W;c.height=H;const g=c.getContext('2d'),d=buf.getChannelData(0),st2=Math.max(1,Math.floor(d.length/W));
 const [ta,tb]=trim||[0,1],xa=ta*W,xb=tb*W;
 for(let x=0;x<W;x++){let m=0;for(let k=x*st2;k<Math.min(d.length,(x+1)*st2);k+=4)m=Math.max(m,Math.abs(d[k]));g.fillStyle=x>=xa&&x<=xb?'#8cc0da':'#3a4048';g.fillRect(x,H/2-m*H/2,1,Math.max(1,m*H))}
 const ln=SK.lanes[+c.dataset.skw];
 // the project's beats as this lane plays them: the attack (or a loop's start) sits on a beat, shifted by any nudge
 if(ln){const L=barLen(),bt=L/4,[r0]=skRegion(ln),pad=ln.every!==0&&!skPulse(ln),o=r0+(ln.every===0||pad?0:skAttack(ln))-(ln.nudge||0),X=p=>p/buf.duration*W;
  for(let k=Math.ceil(-o/bt);o+k*bt<=buf.duration;k++){const x=X(o+k*bt);if(x<0)continue;const bar=((k%4)+4)%4===0;g.fillStyle=bar?'rgba(224,164,88,.7)':'rgba(224,164,88,.22)';g.fillRect(x,0,(bar?1.5:1)*dpr,H)}
  const strong=new Set(skStrong(ln,0,buf.duration));g.fillStyle='rgba(255,255,255,.6)';skOnsets(ln).forEach(p=>{const h=strong.has(p)?9:4;g.fillRect(X(p)-0.5*dpr,H-h*dpr,(strong.has(p)?1.5:1)*dpr,h*dpr)});
  if(!pad){const xo=X(o<0?o+Math.ceil(-o/bt)*bt:o);g.fillStyle='#e0a458';g.beginPath();g.moveTo(xo-4*dpr,0);g.lineTo(xo+4*dpr,0);g.lineTo(xo,6*dpr);g.fill()}}  // ▼ = the point on the beat
 if(trim){g.fillStyle='rgba(224,164,88,.12)';g.fillRect(xa,0,xb-xa,H);g.fillStyle='#e0a458';[xa,xb].forEach(x=>{g.fillRect(x-dpr,0,2*dpr,H);g.fillRect(x-3*dpr,H/2-6*dpr,6*dpr,12*dpr)})}
 const l=SK.lanes[+c.dataset.skw];if(l&&(l.fin||l.fout)){const px=ms=>ms/1000/buf.duration*W;g.strokeStyle='#ffffff';g.lineWidth=1.2*dpr;g.beginPath();
  if(l.fin){g.moveTo(xa,H-2*dpr);g.lineTo(Math.min(xb,xa+px(l.fin)),2*dpr)}if(l.fout){g.moveTo(Math.max(xa,xb-px(l.fout)),2*dpr);g.lineTo(xb,H-2*dpr)}g.stroke()}
 const copy=document.createElement('canvas');copy.width=W;copy.height=H;copy.getContext('2d').drawImage(c,0,0);c._base=copy}
// playhead: a white line on each lane's waveform at the point that's sounding, like the editor's
// attacks inside a clip (spectral-flux-ish on a coarse energy envelope), cached per buffer
function skOnsets(l){if(l.ons&&l.ons.buf===l.buf)return l.ons.v;const b=l.buf,sr=b.sampleRate,hop=256,n=Math.floor(b.length/hop),e=new Float32Array(n);
 const chs=[...Array(b.numberOfChannels).keys()].map(c=>b.getChannelData(c));
 for(let i=0;i<n;i++){let s=0;for(const d of chs)for(let k=i*hop;k<(i+1)*hop;k++)s+=d[k]*d[k];e[i]=10*Math.log10(1e-12+s/(hop*chs.length))}
 // rise in level (dB) over ~20 ms against the level just before; ignore anything far below the clip's peak,
 // where small noise wobbles look like big jumps on a log scale
 let pk=-200;for(let i=0;i<n;i++)pk=Math.max(pk,e[i]);const floor=pk-30,w=Math.max(1,Math.round(0.02*sr/hop)),gap=Math.round(0.09*sr/hop);
 const f=new Float32Array(n);for(let i=w;i<n;i++){let pre=-200;for(let k=i-w;k<i;k++)pre=Math.max(pre,e[k]);f[i]=e[i]>floor?Math.max(0,e[i]-pre):0}
 const v=[],lv=[];let last=-1e9;const lvAt=i=>{let m=-200;for(let k=i;k<Math.min(n,i+Math.round(0.08*sr/hop));k++)m=Math.max(m,e[k]);return m};
 for(let i=w;i<n-1;i++)if(f[i]>=4&&f[i]>=f[i-1]&&f[i]>=f[i+1]){if(i-last>gap){v.push(i*hop/sr);lv.push(lvAt(i));last=i}
  else if(f[i]>f[Math.round(v[v.length-1]*sr/hop)]){v[v.length-1]=i*hop/sr;lv[lv.length-1]=lvAt(i);last=i}}
 // a long clip cut from inside a song starts with a short fade-in, which reads as an "attack" at 0: drop it
 if(b.duration>4&&v.length&&v[0]<0.06){v.shift();lv.shift()}
 l.ons={buf:b,v,lv};return v}
// the attacks that matter: within 10 dB of the loudest attack in the range
function skStrong(l,a,b){skOnsets(l);const {v,lv}=l.ons;let mx=-200;v.forEach((p,k)=>{if(p>=a&&p<=b)mx=Math.max(mx,lv[k])});return v.filter((p,k)=>p>=a&&p<=b&&lv[k]>=mx-10)}
// re-align: try putting each attack near the start of the selection on the beat (and small shifts around it),
// keep the placement where the most of the clip's attacks fall on the project's 8th-note grid
function skAlign(l){if(l.every!==0&&!skPulse(l)){l.nudge=0;return 'no steady pulse in this selection: it plays from its start, like a pad'}
 const [r0,R]=skRegion(l),e8=barLen()/8,o0=r0+(l.every===0?0:skAttack(l));
 const ons=skOnsets(l).filter(p=>p>=r0&&p<=r0+R);if(ons.length<4){l.nudge=0;return 'too few attacks to find a pulse: first attack put on the beat'}
 const hit=c=>ons.reduce((s,p)=>{const ph=(((p-c)/e8)%1+1)%1,d=Math.min(ph,1-ph)*e8;return s+Math.exp(-((d/0.025)**2))},0);
 const cands=ons.filter(p=>p<=r0+Math.min(R,barLen()*2));let best=o0,bs=hit(o0);
 for(const c of cands)for(let dl=-0.04;dl<=0.0401;dl+=0.01){const s=hit(c+dl);if(s>bs+1e-9){bs=s;best=c+dl}}
 // what random placement would score, to tell a real pulse from noise
 let rnd=0;for(let k=0;k<16;k++)rnd+=hit(o0+k*e8/16);rnd/=16;
 const on=ons.filter(p=>{const ph=(((p-best)/e8)%1+1)%1;return Math.min(ph,1-ph)*e8<0.035}).length;
 if(bs<rnd*1.5){l.nudge=0;return `no clear pulse in this selection (${on} of ${ons.length} attacks near the grid, about what chance gives): first attack put on the beat`}
 // any whole number of 8ths fits the grid equally well: apply only the smallest shift, so the clip stays where it was
 let dlt=best-o0;dlt-=Math.round(dlt/e8)*e8;
 l.nudge=-dlt;return `aligned: ${on} of ${ons.length} attacks on the grid${Math.abs(l.nudge)>0.001?` (moved ${Math.round(l.nudge*1000)} ms)`:''}`}
// does this lane have a steady pulse? Measured on the server with Essentia's beat tracker (confidence >= 2.5 and
// steady beats). No pulse = a pad or texture: it plays from the start of its selection, nothing to line up.
function skPulse(l){return l.pulse&&l.pulse.ok?l.pulse:null}
function skHeads(){const now=AC.currentTime,dpr=devicePixelRatio||1;SK.lanes.forEach((l,k)=>{const c=document.querySelector(`[data-skw="${k}"]`);if(!c||!c._base||!l.buf)return;
 const g=c.getContext('2d');g.clearRect(0,0,c.width,c.height);g.drawImage(c._base,0,0);
 const v=(l.on||[]).filter(v=>now>=v.t0&&now<v.t0+v.dur).pop();if(!v||!SK.playing)return;
 const x=(v.off+(now-v.t0))/l.buf.duration*c.width;g.fillStyle='#fff';g.fillRect(x-dpr,0,2*dpr,c.height);g.fillStyle='rgba(255,255,255,.15)';g.fillRect(x-6*dpr,0,5*dpr,c.height)})}
function drawSK(){const el=$('sk');if(typeof drawNP==='function')drawNP();
 if(!SK.open){el.classList.toggle('skmini',SK.playing);el.hidden=!SK.playing;  // hidden but playing: a small bar to stop it or bring it back
  if(SK.playing)el.innerHTML=`<div class="skminibar">🎛 <b>sketch playing</b><span class="sub">samples you play are heard over it</span><span id="skpos" class="sub"></span><span style="flex:1"></span><button id="skplay" class="pill">■ stop</button><button id="skshow">▴ show</button></div>`;
  return}
 el.classList.remove('skmini');el.hidden=false;
 el.innerHTML=`<h3><button id="skhide" title="hide the sketchpad (it keeps playing; the 🎛 sketchpad button brings it back)">▾ hide</button> 🎛 Sketchpad${hq('sketch')} <span class="skbpm" title="the sketch's tempo (the project tempo): − / + (shift: ±5), type it, or tap the beat"><button class="tbtn" data-skbpm="-1">−</button><input id="skbpm" type="number" min="40" max="220" step="1" value="${Math.round(PROJ.bpm||120)}"><button class="tbtn" data-skbpm="1">+</button> bpm <button class="tbtn" id="sktap">tap</button></span> <span class="sub">${esc(PROJ.key||'no key')} — every lane conformed to the project${PROJ.link&&LINK.peers?' · starts on Live\'s next bar':''}</span>
 <button id="skplay" class="${SK.playing?'pill':''}">${SK.playing?'■ stop':'▶ play'}</button><span id="skpos" class="sub"></span><span style="flex:1"></span>
 <span class="skarr" title="arrangement: sections in order (e.g. AABA), each the length chosen; tick the letters on each lane for the sections it plays in. Empty = loop everything"><input id="skarr" placeholder="arrange: AABA" maxlength="16" value="${esc(SK.arr||'')}" style="width:96px"> × <select id="sksec">${[1,2,4,8].map(n=>`<option value="${n}" ${SK.sec===n?'selected':''}>${n} bar${n>1?'s':''}</option>`).join('')}</select></span>
 <button class="tbtn" id="skundo" title="undo (⌘Z)">↶</button><button class="tbtn" id="skredo" title="redo (⌘⇧Z)">↷</button>
 <input id="skname" placeholder="sketch name" style="width:130px" value="${esc(SK.name||'')}"><button id="sksave" class="${skDirty()?'dirty':''}" title="${skDirty()?'unsaved changes: save to keep this version (⌘S)':'saved (⌘S)'}">${skDirty()?'save •':'save'}</button><select id="skbars" title="bounce / stems / Live set length">${songBars()?`<option value="${songBars()}" selected>song · ${songBars()} bars</option>`:''}<option value="4">4 bars</option><option value="8" ${songBars()?'':'selected'}>8 bars</option><option value="16">16 bars</option></select><button id="skbounce" title="render the mix as a new sample (favourited, with provenance)">⤓ bounce</button>
 <button id="skstems" title="each lane as its own WAV, all the same length from bar 1, in the sketch's key and tempo: drop them into Live and they line up">⇩ stems</button><button id="skals" title="a Live set: one audio track per lane, a clip wherever it plays, at the sketch's tempo (muted lanes come in as muted tracks). Opens in Live.">⇩ Live set</button><button id="skexp" title="export conformed copies + a Drum Rack to Ableton">⇩ Ableton</button><button id="skclear">clear</button></h3>
 ${SK.lanes.map((l,k)=>{if(l.type==='drums')return drumLaneHTML(l,k);const s=S[l.i]||[];const loop=s[F.kind]==='loop';const pu=l.state==='ok'&&!loop?skPulse(l):null;
  const tags=[l.trim?`✂ ${Math.round((l.trim[1]-l.trim[0])*100)}%`:'',l.nat?'orig key':'',loop?'loop':`every ${l.every} · +${l.offset}`,
   loop||l.state!=='ok'?'':l.src?`tempo-matched to ${PROJ.bpm}`:pu?`pulse ≈ ${pu.bpm} bpm`:'no pulse'].filter(Boolean).join(' · ');
  const fit=!loop&&l.state==='ok'&&pu&&!l.src;
  return`<div class="lane${l.mute?' muted':''}" data-ln="${k}">
  <label class="onoff" title="turn this lane on or off"><input type="checkbox" data-skon="${k}" ${l.mute?'':'checked'}><span></span></label>
  <div class="lname" title="${esc(s[F.artist]||'')} — ${esc(s[F.title]||'')} · ${esc(s[F.sub]||'')} ${s[F.cam]||''}"><div class="name">${secChips(l,k)}<span class="badge" style="background:${col(s[F.cat])}">${AB[s[F.cat]]}</span>${esc(s[F.artist]||'')}</div><div class="meta">${esc(s[F.title]||'')} · ${tags}</div></div>
  <div class="lwave"><div class="lbtns">${fit?`<button class="tbtn realign fitb" data-skfit="${k}" title="the clip has a steady pulse of about ${pu.bpm} bpm: stretch it onto ${PROJ.bpm} bpm so every attack stays on the grid">⟷ match tempo</button>`:''}${l.src?`<button class="tbtn realign fitb" data-skunfit="${k}" title="back to the clip's own tempo">⟷ undo match</button>`:''}${l.trim||l.nudge?`<button class="tbtn realign" data-skalign="${k}" title="put the first strong attack of the selection on the beat (clears any nudge)">↺ re-align</button>`:''}</div>${l.state==='ok'?`<canvas data-skw="${k}"></canvas>`:`<span class="sub">${l.state==='loading'?'conforming…':'failed to load'}</span>`}</div>
  <div class="fader" title="volume relative to the other lanes (all start equally loud at 0 dB) · double-click for 0 dB"><input type="range" min="-24" max="6" step="0.5" value="${l.db||0}" data-skv="${k}"><output>${dbTxt(l.db||0)}</output></div>
  <button class="tbtn${l.solo?' on':''}" data-sks="${k}" title="solo">S</button><button class="tbtn${l.more?' on':''}" data-skmore="${k}" title="timing, key, fades, open, remove">⋯</button>
  ${l.more?`<div class="lmore">${loop?'<span class="sub">loop: locked to the bar</span>':`<label class="sub">repeat <select data-ske="${k}">${Array.from({length:16},(_,j)=>j+1).map(n=>`<option value="${n}" ${l.every===n?'selected':''}>every ${n} bar${n>1?'s':''}</option>`).join('')}</select></label>
   <label class="sub">start <select data-sko="${k}">${Array.from({length:32},(_,b)=>b/2).map(b=>`<option value="${b}" ${l.offset===b?'selected':''}>+${b} beat${b===1?'':'s'}</option>`).join('')}</select></label>`}
   ${s[F.cat]!=='Percussion'&&s[F.cam]?`<button class="tbtn${l.nat?' on':''}" data-sknat="${k}" title="keep this lane's own key instead of moving it to the project key">orig key (${s[F.cam]})</button>`:''}
   <span class="sub" title="slide this lane in time (or ⌥-drag its waveform)">nudge <button class="tbtn" data-sknudge="${k}" data-d="-1">◀</button><output>${Math.round((l.nudge||0)*1000)} ms</output><button class="tbtn" data-sknudge="${k}" data-d="1">▶</button></span>
   <label class="sub" title="fade in at every repeat">fade in <input type="range" min="0" max="2000" step="10" value="${l.fin||0}" data-skfi="${k}" style="width:80px"> <output>${l.fin||0} ms</output></label>
   <label class="sub" title="fade out at the end of every repeat">fade out <input type="range" min="0" max="2000" step="10" value="${l.fout||0}" data-skfo="${k}" style="width:80px"> <output>${l.fout||0} ms</output></label>
   ${l.trim?'<span class="sub">trimmed: double-click the waveform for the whole clip</span>':'<span class="sub">drag on the waveform to use part of the clip</span>'}
   <span style="flex:1"></span><button data-go="${l.i}" title="open in the sample panel">open →</button><button data-skx="${k}" title="remove from the sketch">remove ✕</button></div>`:''}</div>`}).join('')||'<div class="sub">Empty — press ＋ on any sample (list, detail panel, “goes well with”) to add it.</div>'}
 <div class="hint">Amber lines = the project's bars and beats as each lane plays; white ticks = the clip's own attacks. Drag a waveform to use part of it · ⌥-drag to slide it in time (⌥⇧ for fine) · ↺ re-align puts the first attack back on the beat.</div>`;
 SK.lanes.forEach((l,k)=>skWave(el.querySelector(`[data-skw="${k}"]`),l.buf,l.trim))}
// trim a lane: drag on its waveform to pick a part, grab an edge to move just that edge, double-click for the whole clip
(function(){let drag=null;const sk=$('sk'),frac=(c,e)=>Math.max(0,Math.min(1,(e.clientX-c.getBoundingClientRect().left)/c.clientWidth));
 sk.addEventListener('mousedown',e=>{const c=e.target.closest('[data-skw]');if(!c)return;e.preventDefault();const l=SK.lanes[+c.dataset.skw];if(!l||!l.buf)return;
  if(e.altKey){drag={c,l,nudgeFrom:e.clientX,n0:l.nudge||0};return}  // ⌥-drag slides the lane in time (+shift: 10x finer)
  const f=frac(c,e),[a,b]=l.trim||[0,1],px=7/c.clientWidth;
  const nearA=Math.abs(f-a)<=px,nearB=Math.abs(f-b)<=px;
  if(nearA||nearB)drag={c,l,anchor:nearA&&(!nearB||Math.abs(f-a)<Math.abs(f-b))?b:a};  // move one edge, keep the other
  else{drag={c,l,anchor:f};l.trim=[f,f]}});
 window.addEventListener('mousemove',e=>{if(drag&&drag.nudgeFrom!=null){drag.l.nudge=Math.max(-2,Math.min(2,drag.n0+(e.clientX-drag.nudgeFrom)/drag.c.clientWidth*drag.l.buf.duration*(e.shiftKey?0.1:1)));
   skWave(drag.c,drag.l.buf,drag.l.trim);return}
  if(drag){const f=frac(drag.c,e);drag.l.trim=[Math.min(drag.anchor,f),Math.max(drag.anchor,f)];skWave(drag.c,drag.l.buf,drag.l.trim);return}
  const c=e.target.closest&&e.target.closest('[data-skw]');if(c){const l=SK.lanes[+c.dataset.skw];const f=frac(c,e),[a,b]=(l&&l.trim)||[0,1],px=7/c.clientWidth;c.style.cursor=l&&l.trim&&(Math.abs(f-a)<=px||Math.abs(f-b)<=px)?'ew-resize':'crosshair'}});
 window.addEventListener('mouseup',()=>{if(!drag)return;if(drag.nudgeFrom!=null){drag=null;drawSK();return}const l=drag.l;if(l.trim&&l.trim[1]-l.trim[0]<0.01)l.trim=null;if(l.trim&&l.trim[0]<0.002&&l.trim[1]>0.998)l.trim=null;drag=null;drawSK()});
 sk.addEventListener('dblclick',e=>{const c=e.target.closest('[data-skw]');if(!c)return;SK.lanes[+c.dataset.skw].trim=null;drawSK()})})();
$('sk').addEventListener('click',async e=>{const t=e.target;
 if(t.id==='skplay'){SK.playing?skStop():skPlay();return}if(t.id==='skhide'){SK.open=false;drawSK();drawProj();return}
 if(t.id==='skshow'){SK.open=true;drawSK();drawProj();return}
 if(t.id==='skclear'){skStop();SK.lanes=[];SK.name='';drawSK();drawProj();toast('cleared · ⌘Z brings it back');return}
 if(t.dataset.skm!=null){const l=SK.lanes[+t.dataset.skm];l.mute=!l.mute;skGains();drawSK();return}
 if(t.dataset.sks!=null){const l=SK.lanes[+t.dataset.sks];l.solo=!l.solo;skGains();drawSK();return}
 if(t.dataset.skfit!=null){const l=SK.lanes[+t.dataset.skfit],pu=skPulse(l);if(!pu)return;l.src=pu.bpm;l.nudge=0;toast('stretching…');drawSK();await skLoad(l);const r=skAlign(l);drawSK();toast(`tempo-matched (${pu.bpm} → ${PROJ.bpm} bpm) · ${r}`);return}
 if(t.dataset.skunfit!=null){const l=SK.lanes[+t.dataset.skunfit];l.src=null;l.nudge=0;drawSK();await skLoad(l);drawSK();return}
 if(t.dataset.skalign!=null){const l=SK.lanes[+t.dataset.skalign];if(!l.buf)return;const r=skAlign(l);drawSK();toast(r);return}
 if(t.dataset.sknudge!=null){const l=SK.lanes[+t.dataset.sknudge],step=e.shiftKey?barLen()/16:0.01;l.nudge=Math.max(-2,Math.min(2,(l.nudge||0)+(+t.dataset.d)*step));drawSK();return}
 if(t.dataset.skmore!=null){const l=SK.lanes[+t.dataset.skmore];l.more=!l.more;drawSK();return}
 if(t.dataset.sknat!=null){const l=SK.lanes[+t.dataset.sknat];l.nat=!l.nat;drawSK();await skLoad(l);drawSK();return}
 if(t.dataset.skx!=null){SK.lanes.splice(+t.dataset.skx,1);if(!SK.lanes.length)skStop();drawSK();drawProj();return}
 if(t.dataset.go!=null){select(+t.dataset.go,'list');return}
 if(t.id==='sksave'){const name=($('skname').value||'').trim()||`Sketch ${new Date().toLocaleString()}`;SK.name=name;
  await api('api/sketch/save',{name,state:{key:PROJ.key,bpm:PROJ.bpm,arr:SK.arr||'',sec:SK.sec||4,lanes:skLanesState()}}).then(()=>{SK.saved=skSnap();skDraft();skMarkSave();toast(`“${name}” saved · find it in the Kits tab`)}).catch(err=>toast('error: '+err.message));return}
 if(t.id==='skexp'){const name=($('skname').value||'').trim()||'Sketch '+new Date().toISOString().slice(0,10);toast('exporting conformed copies + Drum Rack…');
  api('api/export',{scope:'paths',paths:SK.lanes.flatMap(l=>l.type==='drums'?l.pads.map(p=>p.path):[l.path]),name,
   pad_edits:Object.fromEntries(SK.lanes.filter(l=>l.type==='drums').flatMap(l=>l.pads.map(p=>[p.path,{start:p.start||0,end:p.end||null,tune:p.tune||0,decay:p.decay||0}]))),key:PROJ.key,bpm:PROJ.bpm,rack:true,reveal:true}).then(r=>toast(`exported ${r.count} files + rack → ${name}`)).catch(err=>toast('error: '+err.message));return}
 if(t.id==='skbounce'){skBounce(+$('skbars').value);return}
 if(t.id==='skstems'){skStems(+$('skbars').value);return}if(t.id==='skals'){skStems(+$('skbars').value,true);return}});
// aligned stems: render every audible lane alone over the same N bars, so each file starts on bar 1 and they all line up
async function skStems(bars,als){if(!SK.lanes.length||SK.lanes.some(l=>!l.buf)){toast('wait for every lane to load');return}
 const L=barLen(),sr=44100,solo=SK.lanes.some(l=>l.solo),name=($('skname').value||'').trim()||SK.name||'Sketch '+new Date().toISOString().slice(0,10);
 const off=l=>l.mute||(solo&&!l.solo);
 // stems: only what you hear; a Live set: every lane, the silent ones as muted tracks you can bring back
 const lanes=als?SK.lanes:SK.lanes.filter(l=>!off(l));if(!lanes.length){toast('every lane is muted');return}toast(`rendering ${lanes.length} ${als?'tracks':'stems'}…`);
 const stems=[];for(const l of lanes){const ctx=new OfflineAudioContext(2,Math.ceil(bars*L*sr),sr),g=ctx.createGain();g.gain.value=laneGain(l);g.connect(ctx.destination);
  for(let b=0;b<bars;b++)skBar(ctx,g,l,b,b*L,L,null);const s=l.type==='drums'?null:S[l.i];
  stems.push({label:s?`${AB[s[F.cat]]} ${s[F.artist]} - ${s[F.title]}`:`DRUMS ${l.pads.length} pads`,wav:wavB64(await ctx.startRendering()),mute:off(l),category:s?s[F.cat]:'Percussion',drums:!s||s[F.cat]==='Percussion'})}
 try{const r=await api('api/stems',{name,key:PROJ.key,bpm:PROJ.bpm,stems,als:!!als,bars});
  toast(als?`Live set “${r.als.split('/').pop()}” written · opening it in Live`:`${r.files.length} stems → ${r.dest.split('/').slice(-2).join('/')} · set Live to ${PROJ.bpm} bpm, ⌘-drag them in to get one track each`)}catch(e){toast((als?'Live set':'stems')+' failed: '+e.message)}}
$('sk').addEventListener('input',e=>{const t=e.target;
 if(t.dataset.skfi!=null||t.dataset.skfo!=null){const l=SK.lanes[+(t.dataset.skfi??t.dataset.skfo)];l[t.dataset.skfi!=null?'fin':'fout']=+t.value;
  const o=t.parentNode.querySelector('output');if(o)o.textContent=t.value+' ms';const k=SK.lanes.indexOf(l);skWave(document.querySelector(`[data-skw="${k}"]`),l.buf,l.trim);return}if(t.dataset.skv!=null){const l=SK.lanes[+t.dataset.skv];l.db=+t.value;skGains();const o=t.parentNode.querySelector('output');if(o)o.textContent=dbTxt(l.db)}});
$('sk').addEventListener('dblclick',e=>{const t=e.target;if(t.dataset&&t.dataset.skv!=null){const l=SK.lanes[+t.dataset.skv];l.db=0;skGains();drawSK()}});
$('sk').addEventListener('change',e=>{const t=e.target;if(t.dataset.skon!=null){const l=SK.lanes[+t.dataset.skon];l.mute=!t.checked;skGains();drawSK();return}if(t.dataset.ske!=null){SK.lanes[+t.dataset.ske].every=+t.value;drawSK();return}if(t.dataset.sko!=null){SK.lanes[+t.dataset.sko].offset=+t.value;drawSK();return}if(t.id==='skname')SK.name=t.value});
$('sk').addEventListener('input',e=>{if(e.target.id==='skname')SK.name=e.target.value},true);
async function skBounce(bars){if(!SK.lanes.length||SK.lanes.some(l=>!l.buf)){toast('wait for every lane to load');return}
 const L=barLen(),sr=44100,len=bars*L,tail=SK.lanes.some(l=>l.every)?Math.min(4,Math.max(...SK.lanes.map(l=>l.buf.duration))):0;
 const ctx=new OfflineAudioContext(2,Math.ceil((len)*sr),sr),solo=SK.lanes.some(l=>l.solo);
 SK.lanes.forEach(l=>{if(l.mute||(solo&&!l.solo))return;const g=ctx.createGain();g.gain.value=laneGain(l);g.connect(ctx.destination);for(let b=0;b<bars;b++)skBar(ctx,g,l,b,b*L,L,null)});
 toast('bouncing…');const buf=await ctx.startRendering();const first=SK.lanes.find(l=>l.path)||{path:(SK.lanes[0].pads[0]||{}).path};
 try{const r=await api('api/bounce',{parent:first.path,wav:wavB64(buf),kind:'loop',bpm:PROJ.bpm,bars,key:PROJ.key,prefix:'Sketch',name:($('skname').value||'').trim(),
   tag:`sketch ${SK.lanes.length} layers`,ops:{key:PROJ.key,bpm:PROJ.bpm,lanes:skLanesState()}});
  const j=addRow(first.i,r.row);toast('bounced → new sample (★ favourited)');select(j,'go')}catch(e){toast('bounce failed: '+e.message)}}
function addRow(i,n){const row=S[i].slice();Object.assign(row,{[F.id]:n.id,[F.path]:n.path,[F.cat]:n.category,[F.sub]:n.subtype,[F.kind]:n.kind,[F.cam]:n.cam,[F.key]:n.key,[F.bpm]:n.bpm,[F.dur]:n.dur,
 [F.env]:n.env,[F.note]:n.note,[F.bars]:n.bars,[F.start]:n.start,[F.parent]:n.parent,[F.root]:n.root,[F.ops]:n.ops});
 const j=S.push(row)-1;P.push(n.partners?n.partners.map(([id,sc,h,v])=>[BYID.get(id),sc,h,v]).filter(x=>x[0]!=null):P[i]);BYID.set(n.id,j);byPath.set(n.path,j);(BYTRACK.get(row[F.tid])||[]).push(j);
 FAV.set(n.path,{path:n.path,sample_id:n.id,label:n.ops,added_at:new Date().toISOString()});return j}
function wavB64(buf){const n=buf.length,ch=2,sr=buf.sampleRate,b=new ArrayBuffer(44+n*ch*2),v=new DataView(b),w=(o,s)=>{for(let k=0;k<s.length;k++)v.setUint8(o+k,s.charCodeAt(k))};
 w(0,'RIFF');v.setUint32(4,36+n*ch*2,true);w(8,'WAVE');w(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,ch,true);v.setUint32(24,sr,true);v.setUint32(28,sr*ch*2,true);v.setUint16(32,ch*2,true);v.setUint16(34,16,true);w(36,'data');v.setUint32(40,n*ch*2,true);
 const Lc=buf.getChannelData(0),Rc=buf.numberOfChannels>1?buf.getChannelData(1):Lc;let o=44;for(let k=0;k<n;k++){v.setInt16(o,Math.max(-1,Math.min(1,Lc[k]))*32767,true);v.setInt16(o+2,Math.max(-1,Math.min(1,Rc[k]))*32767,true);o+=4}
 const u=new Uint8Array(b);let s='';for(let k=0;k<u.length;k+=0x8000)s+=String.fromCharCode.apply(null,u.subarray(k,k+0x8000));return btoa(s)}
// sketches + kit racks in the Kits tab
async function renderKitExtras(){const L=$('list');
 L.querySelectorAll('[data-kitexp]').forEach(b=>{const k=D.kits.findIndex(x=>x.name===b.dataset.kitexp);b.insertAdjacentHTML('afterend',` <button data-kitrack="${k}" title="export + Ableton Drum Rack">⇩ rack</button> <button data-kitsk="${k}" title="load into the sketchpad">🎛 sketch</button>`)});
 if(!SERVED)return;let sk=[];try{sk=await api('api/sketches')}catch(e){}if(st.tab!=='K'||!sk.length)return;
 L.insertAdjacentHTML('afterbegin',`<div class="kit"><h3><span>Your sketches${hq('kits')}</span></h3>${sk.map(x=>{const s=JSON.parse(x.state);return`<div class="prow"><button class="play" data-skopen="${esc(x.name)}">▶</button><div style="min-width:0"><div class="name"><a href="#" data-skload="${esc(x.name)}" title="open in the sketchpad without playing">${esc(x.name)}</a></div><div class="meta">${esc(s.key||'')} · ${s.bpm||'—'} bpm · ${s.lanes.length} lanes · ${esc(x.updated_at?new Date(x.updated_at.replace(' ','T')+'Z').toLocaleString():'')}</div></div><button data-skdel="${esc(x.name)}">✕</button></div>`}).join('')}</div>`);
 L.querySelectorAll('[data-skopen]').forEach(b=>b.onclick=()=>{const x=sk.find(z=>z.name===b.dataset.skopen);skOpen(x.name,JSON.parse(x.state))});
 L.querySelectorAll('[data-skload]').forEach(b=>b.onclick=e=>{e.preventDefault();const x=sk.find(z=>z.name===b.dataset.skload);skOpen(x.name,JSON.parse(x.state),false)});
 L.querySelectorAll('[data-skdel]').forEach(b=>b.onclick=async()=>{await api('api/sketch/delete',{name:b.dataset.skdel});render()})}
async function skOpen(name,s,play=true){skStop();Object.assign(PROJ,{key:s.key,bpm:s.bpm});try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(e){}drawProj();
 UNDO.hold=true;SK.name=name;SK.arr=s.arr||'';SK.sec=s.sec||4;SK.lanes=s.lanes.map(l=>l.type==='drums'?{...l,state:'loading',buf:null,pads:l.pads.map(p=>({...p,i:byPath.get(p.path),buf:null})).filter(p=>p.i!=null)}:({...l,i:byPath.get(l.path),buf:null,state:'loading'})).filter(l=>l.type==='drums'?l.pads.length:l.i!=null);
 SK.saved=skSnap();UNDO.hold=false;
 const miss=s.lanes.length-SK.lanes.length;if(miss)toast(`${miss} lane${miss>1?'s are':' is'} newer than this page: run "digitalcrate build" and reload to hear the whole sketch`);SK.open=true;drawSK();drawProj();await Promise.all(SK.lanes.map(skLoad));drawSK();if(play)skPlay()}
document.addEventListener('click',async e=>{const kr=e.target.closest('[data-kitrack]');if(kr){e.stopPropagation();const k=D.kits[+kr.dataset.kitrack];kr.textContent='building…';
  try{const r=await api('api/export',{scope:'paths',paths:kitMembers(k).map(i=>S[i][F.path]),name:k.name,rack:true,reveal:true});kr.textContent=`rack ✓ (${r.count})`}catch(err){kr.textContent='error'}return}
 const ks=e.target.closest('[data-kitsk]');if(ks){e.stopPropagation();const k=D.kits[+ks.dataset.kitsk];if(SK.lanes.length)setTimeout(()=>toast('the sketch was replaced · ⌘Z brings it back'),400);skStop();SK.lanes=[];SK.name=k.name;
  // a kit was built around one key and tempo (they're in its name): use those, not whatever the project was last set to
  const m=k.name.match(/_(\d{1,2}[AB])-[^_]*_(\d+)bpm/);if(m){PROJ.key=keyFromCam(m[1].replace(/^0/,''));if(!(PROJ.link&&LINK.peers))PROJ.bpm=+m[2];
   try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(err){}drawProj();toast(`sketch set to ${PROJ.key} · ${PROJ.bpm} bpm, from the kit`)}
  for(const i of kitMembers(k))await skAdd(i);skPlay();return}
 const a=e.target.closest('[data-sk]');if(a){e.stopPropagation();e.preventDefault();skAdd(+a.dataset.sk)}},true);

// ================= detail panel: ＋ sketch · pads · MIDI · project info =================
const _select=select;
select=function(i,from){if(CH.play&&CH.i!==i)chStop();_select(i,from);augment(i)};
function augment(i){const eo=$('edopen');if(!eo)return;eo.parentNode.style.flexWrap='wrap';
 eo.insertAdjacentHTML('afterend',` <button data-sk="${i}" title="add to the sketchpad">＋ sketch</button><button id="padsopen" title="play its syllables / notes from the keyboard, record a pattern">🎹 pads</button>${S[i][F.cat]!=='Percussion'&&S[i][F.cam]?'<button id="midiopen" title="notes & chords → MIDI">♪ MIDI</button>':''}${S[i][F.cat]!=='Percussion'&&!String(S[i][F.path]).startsWith('_Reference')?'<button id="chordsopen" title="chord progressions that suit this sample, played on a synth pad">🎼 chords</button>':''}`);
 eo.parentNode.insertAdjacentHTML('afterend','<div class="sub" id="pjinfo" style="margin:-4px 0 8px"></div>');
 $('editor').insertAdjacentHTML('afterend','<div class="ed" id="pads" hidden></div><div class="ed" id="midibox" hidden></div><div class="ed" id="chordbox" hidden></div>');
 document.querySelectorAll('#detail [data-pair]').forEach(b=>b.insertAdjacentHTML('beforebegin',`<button data-sk="${b.dataset.pair}" title="add to the sketchpad">＋</button><button data-savepair="${b.dataset.pair}" title="save this pair as a sketch (Kits tab), ready to open or export as aligned stems">💾</button>`));
 if(PROJ.key||PROJ.bpm)projInfo(i);if(PADS.i!==i)padsClose()}
$('detail').addEventListener('click',async e=>{const sp=e.target.closest('[data-savepair]');if(sp){e.stopPropagation();const j=+sp.dataset.savepair;
  try{const r=await api('api/pair/save',{src:S[st.sel][F.path],partner:S[j][F.path]});sp.textContent='✓';toast(`saved “${r.name}” · open it from the Kits tab`)}catch(err){toast('error: '+err.message)}return}
 if(e.target.id==='padsopen'){openPads(st.sel);return}if(e.target.id==='midiopen'){openMidi(st.sel);return}if(e.target.id==='chordsopen'){openChords(st.sel);return}});

// ---------- MIDI
// ================= chords: progressions that suit a sample, heard on a synth pad =================
// pad voices: each note = a few detuned oscillators through a lowpass, slow attack, long release, into a shared reverb
const PADV={warm:{osc:[['sawtooth',-7],['sawtooth',7]],cut:900,q:0.7,att:0.6,rel:1.6,gain:0.16},
 glass:{osc:[['triangle',0],['sine',1200]],cut:4200,q:0.4,att:0.35,rel:2.2,gain:0.2},
 strings:{osc:[['sawtooth',-12],['sawtooth',0],['sawtooth',12]],cut:2300,q:0.6,att:0.9,rel:1.8,gain:0.11,vib:5},
 rhodes:{osc:[['sine',0],['triangle',1200]],cut:3000,q:0.5,att:0.01,rel:1.2,gain:0.24,decay:1.6}};
function padReverb(ctx){const n=Math.floor(ctx.sampleRate*3),b=ctx.createBuffer(2,n,ctx.sampleRate);
 for(let c=0;c<2;c++){const d=b.getChannelData(c);for(let k=0;k<n;k++)d[k]=(Math.random()*2-1)*Math.pow(1-k/n,3)}const cv=ctx.createConvolver();cv.buffer=b;return cv}
function padChord(ctx,dest,notes,t,dur,kind){const v=PADV[kind]||PADV.warm;
 notes.forEach((n,ni)=>{const f=440*Math.pow(2,(n-69)/12),g=ctx.createGain(),lp=ctx.createBiquadFilter();lp.type='lowpass';lp.frequency.value=v.cut*(ni===0?0.6:1);lp.Q.value=v.q;
  const lvl=v.gain*(ni===0?0.8:1)/Math.sqrt(notes.length);g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(lvl,t+v.att);
  if(v.decay)g.gain.setTargetAtTime(lvl*0.35,t+v.att,v.decay/3);g.gain.setValueAtTime(v.decay?lvl*0.35:lvl,t+dur);g.gain.linearRampToValueAtTime(0,t+dur+v.rel);
  lp.connect(g);g.connect(dest);
  v.osc.forEach(([type,cents])=>{const o=ctx.createOscillator();o.type=type;o.frequency.value=f;o.detune.value=cents;
   if(v.vib){const l=ctx.createOscillator(),lg=ctx.createGain();l.frequency.value=v.vib;lg.gain.value=4;l.connect(lg);lg.connect(o.detune);l.start(t);l.stop(t+dur+v.rel)}
   o.connect(lp);o.start(t);o.stop(t+dur+v.rel+0.05)})})}
const chLen=(r,o)=>r.follows?r.total:o.chords.length*r.step;           // one pass of the progression
const chAt=(r,c,k)=>r.follows?[c.t,c.d]:[k*r.step,r.step];             // a chord's start and length in that pass
function padProgression(ctx,dest,opt,step,t0,kind,reps=1,r=CH.res){const L=chLen(r,opt);for(let n=0;n<reps;n++)opt.chords.forEach((c,k)=>{const [a,d]=chAt(r,c,k);padChord(ctx,dest,c.notes,t0+n*L+a,d,kind)})}
// ---- basslines under the chords: patterns built from each chord's root, 3rd and 5th on the beat grid
const BASSES={off:'no bass',held:'held roots',root5:'root & fifth',pulse:'8th-note pulse',sync:'syncopated (R&B)',walk:'walking (jazz)'};
function bassAuto(r,s){if(r.follows&&!r.loop)return 'held';  // changes off any steady beat: hold the roots
 if(/jazz/i.test(s[F.genre]||''))return 'walk';return {soulful:'sync',dark:'pulse',ethereal:'held'}[r.style]||'root5'}
function chTones(c){const root=c.notes[0]%12,nm=c.name.replace(/^[A-G][b#♭♯]?/,'');
 const dim=/dim|°|ø|m7b5/.test(nm),aug=/aug|\+/.test(nm),minor=dim||/^m(?!aj)/.test(nm);
 return {root,third:root+(minor?3:4),fifth:root+(dim?6:aug?8:7)}}
// near the last note, in the bass register (E1–G2 for roots)
const bassNear=(pc,prev)=>{let best=null;for(let n=28;n<=50;n++)if(((n-pc)%12+12)%12===0&&(best===null||Math.abs(n-prev)<Math.abs(best-prev)))best=n;return best};
function bassLine(r,o,style){if(!style||style==='off')return [];const beat=60/r.tempo,out=[];let prev=36;
 const cs=o.chords.map((c,k)=>{const [a,d]=chAt(r,c,k);return {c,a,d,t:chTones(c)}});
 cs.forEach((x,k)=>{const nx=cs[(k+1)%cs.length],R=bassNear(x.t.root,prev);prev=R;const F5=R+((x.t.fifth-x.t.root+12)%12),T3=R+((x.t.third-x.t.root+12)%12);
  const beats=[];for(let b=Math.ceil(x.a/beat-1e-6);b*beat<x.a+x.d-1e-6;b++)beats.push(b*beat);if(beats.length&&beats[0]-x.a<beat*0.25)beats[0]=x.a;else beats.unshift(x.a);  // the chord change always gets its root, even off the grid
  const end=x.a+x.d,add=(n,t,d,v=1)=>{if(t<end-1e-4)out.push({n,t,d:Math.min(d,end-t),v})};
  const bar=b=>Math.round(b/beat)%4;
  if(style==='held')add(R,x.a,x.d,0.9);
  else if(style==='root5')beats.forEach(t=>{const p=bar(t);if(p===0||t===x.a)add(R,t,beat*1.9);else if(p===2)add(F5,t,beat*1.9,0.85)});
  else if(style==='pulse')beats.forEach(t=>{add(R,t,beat*0.45,bar(t)===0?1:0.8);add(bar(t)===3?R+12:R,t+beat/2,beat*0.4,0.7)});
  else if(style==='sync')beats.forEach(t=>{const p=bar(t);if(p===0||t===x.a)add(R,t,beat*1.3);if(p===1)add(R,t+beat/2,beat*0.4,0.75);if(p===2)add(R+12,t+beat/2,beat*0.35,0.7);if(p===3)add(F5,t+beat/2,beat*0.45,0.8)});
  else if(style==='walk'){const nR=bassNear(nx.t.root,R),tones=[R,T3,F5,R+12,F5,T3];
   beats.forEach((t,j)=>{let n;if(j===0)n=R;else if(j===beats.length-1)n=nR+(nR>=R?-1:1);else n=tones[j%tones.length];add(n,t,beat*0.9,j===0?1:0.85)})}});
 return out}
function bassNote(ctx,dest,n,t,d,v=1){const f=440*Math.pow(2,(n-69)/12),g=ctx.createGain(),lp=ctx.createBiquadFilter();lp.type='lowpass';lp.Q.value=2;
 lp.frequency.setValueAtTime(900,t);lp.frequency.exponentialRampToValueAtTime(260,t+0.25);
 const lvl=0.32*v;g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(lvl,t+0.006);g.gain.setTargetAtTime(lvl*0.7,t+0.006,0.12);
 g.gain.setValueAtTime(lvl*0.7,t+Math.max(0.01,d-0.04));g.gain.linearRampToValueAtTime(0,t+d+0.06);lp.connect(g);g.connect(dest);
 [['sawtooth',0,0.5],['sine',0,1],['sine',-1200,0.6]].forEach(([type,cents,amp])=>{const o=ctx.createOscillator(),og=ctx.createGain();og.gain.value=amp;o.type=type;o.frequency.value=f;o.detune.value=cents;o.connect(og);og.connect(lp);o.start(t);o.stop(t+d+0.1)})}
function bassProgression(ctx,dest,r,o,t0,style){bassLine(r,o,style).forEach(b=>bassNote(ctx,dest,b.n,t0+b.t,b.d,b.v))}
const CH={i:null,res:null,bpc:1,pad:null,lvl:0.8,play:null,bass:null,blvl:0.8};window.CH=CH;window.bassLine=(r,o,st)=>bassLine(r,o,st);window.chAt=chAt;window.BASSES=BASSES;
async function openChords(i,keep){const box=$('chordbox');if(!keep){if(!box.hidden&&CH.i===i){chStop();box.hidden=true;return}}box.hidden=false;CH.i=i;
 box.innerHTML='<div class="sub">listening to the notes and working out chords…</div>';
 const s=S[i],bpm=s[F.kind]==='loop'?'':(PROJ.bpm||90);
 try{const r=await api(`api/chords?path=${encodeURIComponent(s[F.path])}&bpc=${CH.bpc}${bpm?'&bpm='+bpm:''}`);if(st.sel!==i)return;CH.res=r;CH.pad=CH.pad||r.timbre;if(!CH.bassPicked)CH.bass=bassAuto(r,s);drawChords()}
 catch(e){box.innerHTML='<div class="sub">chords failed: '+esc(e.message)+'</div>'}}
function drawChords(){const r=CH.res,box=$('chordbox');if(!r)return;
 box.innerHTML=`<div class="edrow"><b>🎼 ${esc(r.key)}</b>${hq('chords')}<span class="sub">${esc(r.style)} flavour (${r.moods.map(esc).join(', ')}) · ${r.follows?`follows the sample's own changes: ${r.own.map(esc).join(' → ')}`:`${r.steps} chords × ${r.bars_per_chord} bar at ${r.tempo} bpm${r.loop?'':' (project tempo)'}`}</span></div>
 <div class="edrow sub"><label ${r.follows?'hidden':''}>chord every <select id="chbpc"><option value="1" ${CH.bpc===1?'selected':''}>1 bar</option><option value="2" ${CH.bpc===2?'selected':''}>2 bars</option></select></label>
  <label>pad <select id="chpad">${r.pads.map(p=>`<option ${p===CH.pad?'selected':''}>${p}</option>`).join('')}</select></label>
  <label>pad level <input type="range" id="chlvl" min="0" max="1.5" step="0.05" value="${CH.lvl}" style="width:80px"></label><label>bass <select id="chbass">${Object.entries(BASSES).map(([k,v])=>`<option value="${k}" ${k===CH.bass?'selected':''}>${v}${k===bassAuto(r,S[CH.i])?' ✓':''}</option>`).join('')}</select></label><label ${CH.bass==='off'?'hidden':''} id="chblw">bass level <input type="range" id="chblvl" min="0" max="1.5" step="0.05" value="${CH.blvl}" style="width:70px"></label><button id="chstop">■ stop</button></div>
 ${r.options.map((o,k)=>`<div class="chopt"><button class="play" data-chplay="${k}" title="the sample with this progression">▶</button>${o.label?`<span class="chlab">${esc(o.label)}</span>`:''}
  <div class="chs">${o.chords.map((c,ci)=>`<span class="chd" data-chone="${k}:${ci}" title="fit ${c.fit} · click to hear this chord"><b>${esc(c.name)}</b><i>${esc(c.roman)}</i></span>`).join('')}</div>
  <span class="sub" title="how well the chords' notes match what the sample plays">${Math.round(o.fit*100)}%</span>
  <div class="chbtn"><button data-chmidi="${k}" title="the chords as a MIDI clip, in your Ableton User Library/Chords">⇩ MIDI</button><button data-chsk="${k}" title="render the pad as a new sample and put it in the sketchpad with this sample">＋ sketch</button></div></div>`).join('')||'<div class="sub">no confident suggestions for this one</div>'}
 <div class="kbd" id="chkeys"></div>
 <div class="hint">Click a chord to hear it alone. ${r.follows?"This sample has chords of its own, so suggestions change where it does: “follows” enriches its chords in another register, “reharmonized” swaps in chords that still contain what it plays;":"Chords follow the sample's key and what it plays in each bar;"} the flavour comes from its mood. Voiced ${r.register[0]<55?'below':'above'} the sample's own register so they don't mask it.</div>`;
 chKeys([]);
 $('chbpc').onchange=e=>{CH.bpc=+e.target.value;chStop();openChords(CH.i,true)};$('chpad').onchange=e=>{CH.pad=e.target.value;if(CH.play)chPlay(CH.play.k)};
 $('chlvl').oninput=e=>{CH.lvl=+e.target.value;if(CH.play)CH.play.pg.gain.value=CH.lvl};$('chbass').onchange=e=>{CH.bass=e.target.value;CH.bassPicked=true;$('chblw').hidden=CH.bass==='off';if(CH.play)chPlay(CH.play.k)};$('chblvl').oninput=e=>{CH.blvl=+e.target.value;if(CH.play&&CH.play.bg)CH.play.bg.gain.value=CH.blvl};$('chstop').onclick=chStop}
// a piano keyboard over the register the chords use; lit keys = the chord sounding now (bass in a darker colour)
function chKeys(notes,label){const el=$('chkeys');if(!el||!CH.res)return;const lo=Math.min(36,...notes.map(n=>n-(n%12))),hi=Math.max(84,...notes.map(n=>n+1));
 const blk=n=>[1,3,6,8,10].includes(n%12),wh=[];for(let n=lo;n<=hi;n++)if(!blk(n))wh.push(n);const W=100/wh.length,on=new Set(notes),bass=notes.length?Math.min(...notes):null;
 let h=wh.map((n,k)=>`<i class="w${on.has(n)?(n===bass?' bs':' on'):''}" style="left:${k*W}%;width:${W}%">${n%12===0?`<em>C${n/12-1}</em>`:''}</i>`).join('');
 for(let n=lo;n<=hi;n++)if(blk(n)){const k=wh.filter(x=>x<n).length;h+=`<i class="b${on.has(n)?(n===bass?' bs':' on'):''}" style="left:${k*W-W*0.32}%;width:${W*0.64}%"></i>`}
 el.innerHTML=`<div class="kl">${label?esc(label):'&nbsp;'}</div><div class="kk">${h}</div>`}
function chMark(k,ci){document.querySelectorAll('[data-chone]').forEach(x=>x.classList.toggle('now',x.dataset.chone===`${k}:${ci}`));const c=CH.res&&CH.res.options[k]&&CH.res.options[k].chords[ci];
 const b=c&&CH.bass&&CH.bass!=='off'?bassLine(CH.res,CH.res.options[k],CH.bass).find(x=>Math.abs(x.t-chAt(CH.res,c,ci)[0])<1e-3):null;
 chKeys(c?(b?[b.n,...c.notes]:c.notes):[],c?`${c.name} · ${c.roman}${b?' · bass '+NOTE_NAMES[b.n%12]+(Math.floor(b.n/12)-1):''}`:'')}
const NOTE_NAMES=['C','C♯','D','E♭','E','F','F♯','G','A♭','A','B♭','B'];
function chStop(){if(!CH.play)return;const p=CH.play;CH.play=null;clearTimeout(p.timer);cancelAnimationFrame(p.raf);chMark(-1,-1);const now=AC.currentTime;p.master.gain.setTargetAtTime(0,now,0.05);setTimeout(()=>{try{p.master.disconnect()}catch(e){}},400);
 try{p.src.stop(now+0.2)}catch(e){}document.querySelectorAll('[data-chplay]').forEach(b=>b.classList.remove('playing'))}
// anything else starting to play (a sample, play-together, a variation, the sketch, the stop button) stops the chords too
const _stopAllChords=stopAll;stopAll=function(){_stopAllChords.apply(this,arguments);chStop()};
async function chPlay(k){chStop();stopAll();skStop();AC.resume();const r=CH.res,o=r.options[k],s=S[CH.i];
 const buf=await AC.decodeAudioData(await (await fetch(url(s[F.path]))).arrayBuffer());
 const L=chLen(r,o),master=AC.createGain();master.connect(AC.destination);const pg=AC.createGain();pg.gain.value=CH.lvl;const rv=padReverb(AC),wet=AC.createGain();wet.gain.value=0.35;
 pg.connect(master);pg.connect(rv);rv.connect(wet);wet.connect(master);
 const src=AC.createBufferSource();src.buffer=buf;src.loop=true;src.loopEnd=Math.min(buf.duration,L);const sg=AC.createGain();sg.gain.value=Math.min(4,skNorm(buf))*0.8;src.connect(sg);sg.connect(master);
 const bg=AC.createGain();bg.gain.value=CH.blvl;bg.connect(master);
 const t0=AC.currentTime+0.1;src.start(t0);CH.play={k,master,pg,bg,src,timer:null};
 const sched=n=>{if(!CH.play||CH.play.k!==k)return;padProgression(AC,pg,o,r.step,t0+n*L,CH.pad);bassProgression(AC,bg,r,o,t0+n*L,CH.bass);CH.play.timer=setTimeout(()=>sched(n+1),Math.max(50,(t0+(n+1)*L-AC.currentTime-1)*1000))};sched(0);
 let last=-1;const follow=()=>{if(!CH.play||CH.play.k!==k)return;const t=AC.currentTime-t0,tl=t<0?0:t%L;
  let ci=0;o.chords.forEach((c,j)=>{if(chAt(r,c,j)[0]<=tl+1e-6)ci=j});if(ci!==last){last=ci;chMark(k,ci)}CH.play.raf=requestAnimationFrame(follow)};follow();
 document.querySelectorAll('[data-chplay]').forEach(b=>b.classList.toggle('playing',+b.dataset.chplay===k))}
document.addEventListener('click',async e=>{const one=e.target.closest('[data-chone]');if(one){const [k,ci]=one.dataset.chone.split(':').map(Number),r=CH.res,c=r.options[k].chords[ci];
  chStop();stopAll();AC.resume();const pg=AC.createGain();pg.gain.value=CH.lvl;const rv=padReverb(AC),wet=AC.createGain();wet.gain.value=0.35;pg.connect(AC.destination);pg.connect(rv);rv.connect(wet);wet.connect(AC.destination);
  padChord(AC,pg,c.notes,AC.currentTime+0.02,Math.min(2.5,chAt(r,c,ci)[1]),CH.pad);chMark(k,ci);return}
 const p=e.target.closest('[data-chplay]');if(p){if(CH.play&&CH.play.k===+p.dataset.chplay)chStop();else chPlay(+p.dataset.chplay);return}
 const m=e.target.closest('[data-chmidi]');if(m){const r=CH.res,o=r.options[+m.dataset.chmidi],s=S[CH.i];
  try{await api('api/chords/midi',{name:`${s[F.artist]} - ${s[F.title]} - ${o.chords.map(c=>c.name).join(' ')}`,chords:o.chords.map(c=>c.notes),times:o.chords.map((c,j)=>chAt(r,c,j)),step:r.step,tempo:r.tempo,bass:bassLine(r,o,CH.bass).map(b=>[b.n,b.t,b.d,Math.round(70+40*b.v-30)])});m.textContent='✓ MIDI';toast(CH.bass&&CH.bass!=='off'?'MIDI clip saved (chords + bass tracks) to your Ableton User Library › Chords':'MIDI clip saved to your Ableton User Library › Chords')}catch(err){toast('error: '+err.message)}return}
 const sk=e.target.closest('[data-chsk]');if(sk){const r=CH.res,o=r.options[+sk.dataset.chsk],i=CH.i,s=S[i];sk.textContent='rendering…';
  // render offline, folding the release/reverb tail past the loop end back onto its start so the loop is seamless
  const L=chLen(r,o),render=async(build,verb)=>{const sr=44100,ctx=new OfflineAudioContext(2,Math.ceil((L+3)*sr),sr),g=ctx.createGain();g.connect(ctx.destination);
   if(verb){const rv=padReverb(ctx),wet=ctx.createGain();wet.gain.value=0.35;g.connect(rv);rv.connect(wet);wet.connect(ctx.destination)}build(ctx,g);
   const full=await ctx.startRendering(),n=Math.round(L*sr),out=new AudioBuffer({numberOfChannels:2,length:n,sampleRate:sr});
   for(let c=0;c<2;c++){const a=full.getChannelData(c),b=out.getChannelData(c);b.set(a.subarray(0,n));for(let k=n;k<a.length;k++)b[(k-n)%n]+=a[k]}return out};
  // stored as new loops (key + tempo + provenance): the pad in Chords & Keys, the bass in Bass & Sub; then all lanes go in the sketch
  const meta={parent:s[F.path],kind:r.follows?'free':'loop',bpm:r.follows?null:r.tempo,bars:r.follows?null:o.chords.length*r.bars_per_chord,key:r.key},names=o.chords.map(c=>c.name);
  try{const pad=await render((ctx,g)=>padProgression(ctx,g,o,r.step,0,CH.pad),true);
   const res=await api('api/bounce',{...meta,wav:wavB64(pad),prefix:'Chords',category:'Chords & Keys',name:names.join(' '),tag:`chords ${CH.pad}`,ops:{chords:names,pad:CH.pad,from:s[F.id]}});
   const j=addRow(i,res.row);if(!SK.lanes.some(l=>l.path===s[F.path]))await skAdd(i);await skAdd(j);
   if(CH.bass&&CH.bass!=='off'){const bs=await render((ctx,g)=>bassProgression(ctx,g,r,o,0,CH.bass),false);
    const rb=await api('api/bounce',{...meta,wav:wavB64(bs),prefix:'Bass',category:'Bass & Sub',name:'bass '+names.join(' '),tag:`bass ${CH.bass}`,ops:{chords:names,bass:CH.bass,from:s[F.id]}});
    await skAdd(addRow(i,rb.row))}
   sk.textContent='✓ in sketch';toast(CH.bass&&CH.bass!=='off'?'chord pad and bassline saved (★) and added to the sketchpad with the sample':'chord pad saved (★) and added to the sketchpad with the sample')}
  catch(err){sk.textContent='＋ sketch';toast('error: '+err.message)}}});
async function openMidi(i){const box=$('midibox');if(!box.hidden){box.hidden=true;return}box.hidden=false;box.innerHTML='<div class="sub">transcribing notes & chords (basic-pitch)…</div>';
 try{const s=S[i],r=await api(`api/midi?path=${encodeURIComponent(s[F.path])}${s[F.kind]==='loop'&&s[F.bpm]?'&bpm='+s[F.bpm]:''}`);if(st.sel!==i)return;
  const name=s[F.path].split('/').pop().replace(/\.wav$/,'')+'.mid';
  box.innerHTML=`<div class="edrow"><b>♪ ${r.notes.length} notes</b><span class="sub">${r.chords.length?r.chords.length+' chords (below)':'no clear chords'}</span><a href="${url(r.midi)}" download="${esc(name)}"><button>⇩ .mid</button></a><span class="sub">drag the downloaded file into a MIDI track</span></div>
  <canvas class="roll" id="roll"></canvas><div>${r.chords.map(c=>`<span class="chord" title="${c[0].toFixed(1)}–${c[1].toFixed(1)} s">${esc(c[2])}</span>`).join('')}</div>`;
  drawRoll($('roll'),r)}catch(e){box.innerHTML='<div class="sub">MIDI failed: '+esc(e.message)+'</div>'}}
function drawRoll(c,r){const dpr=devicePixelRatio||1,W=c.clientWidth*dpr,H=150*dpr;c.width=W;c.height=H;const g=c.getContext('2d');g.fillStyle='#101317';g.fillRect(0,0,W,H);
 if(!r.notes.length)return;const lo=Math.min(...r.notes.map(n=>n[2]))-2,hi=Math.max(...r.notes.map(n=>n[2]))+2,rh=H/(hi-lo+1),X=t=>t/r.dur*W;
 for(let p=lo;p<=hi;p++){if([1,3,6,8,10].includes(p%12)){g.fillStyle='rgba(255,255,255,.03)';g.fillRect(0,H-(p-lo+1)*rh,W,rh)}if(p%12===0){g.fillStyle='rgba(255,255,255,.25)';g.font=`${9*dpr}px sans-serif`;g.fillText('C'+(p/12-1),2,H-(p-lo)*rh-2)}}
 r.notes.forEach(([s,e,p,v])=>{g.fillStyle=`rgba(224,164,88,${0.35+v/127*0.65})`;g.fillRect(X(s),H-(p-lo+1)*rh+1,Math.max(2,X(e)-X(s)),Math.max(2,rh-2))})}

// ---------- vocal tuning in the editor
const _openEditor=openEditor;
openEditor=async function(i){await _openEditor(i);const box=$('editor');if(!box||box.hidden||!$('edprev')||$('edtune'))return;
 const row=$('edprev').closest('.edrow'),d=document.createElement('div');d.className='edgrid';d.id='edtune';const own=S[i][F.key];
 d.innerHTML=`<span>Tune to${hq('tune')}</span><select id="tnkey"><option value="">off</option>${PROJ.key?`<option value="${esc(PROJ.key)}">project · ${esc(PROJ.key)}</option>`:''}${own?`<option value="${esc(own)}">its own key · ${esc(own)}</option>`:''}${KEYS24.map(([c,n])=>`<option value="${n}">${c} ${n}</option>`).join('')}</select><span id="tnrep" class="sub"></span>
 <span>Strength</span><input type="range" id="tnstr" min="0" max="1" step="0.05" value="0.8"><span id="tnstrv">80%</span>
 <span>Glide</span><input type="range" id="tnspd" min="0" max="300" step="5" value="60"><span id="tnspdv">60 ms</span>
 <span>Detune</span><input type="range" id="tndet" min="-50" max="50" step="1" value="0"><span id="tndetv">0 ¢</span>
 <span>Drift</span><input type="range" id="tndri" min="0" max="40" step="1" value="0"><span id="tndriv">0 ¢</span>`;
 row.parentNode.insertBefore(d,row);
 const lab={tnstr:v=>Math.round(v*100)+'%',tnspd:v=>v+' ms'+(v<15?' (hard: audible on every engine)':v>150?' (natural)':''),tndet:v=>(v>0?'+':'')+v+' ¢',tndri:v=>v+' ¢'};
 Object.entries(lab).forEach(([id,f])=>{$(id).addEventListener('input',()=>$(id+'v').textContent=f(+$(id).value));$(id).addEventListener('change',()=>edChanged())});
 $('tnkey').addEventListener('change',async()=>{edChanged();const k=$('tnkey').value;$('tnrep').textContent='';if(!k)return;$('tnrep').textContent='measuring…';
  try{const r=await api(`api/tune/report?path=${encodeURIComponent(S[i][F.path])}&key=${encodeURIComponent(k)}`);
   $('tnrep').textContent=r.voiced?`${Math.round(r.in_key*100)}% of its notes are in ${k} · sits ${r.cents>0?'+':''}${r.cents}¢ · wobble ±${r.spread}¢`:'no clear pitch found'}catch(e){$('tnrep').textContent=''}})};
const _edParams=edParams;
edParams=function(){const p=_edParams();if($('tnkey')){p.tune_key=$('tnkey').value||null;p.tune_strength=+$('tnstr').value;p.tune_speed=+$('tnspd').value;p.tune_detune=+$('tndet').value;p.tune_drift=+$('tndri').value}return p};

// ---------- your plugins (AU/VST3 via Pedalboard) in the editor
let FXLIST=null;
const _openEditorFx=openEditor;
openEditor=async function(i){await _openEditorFx(i);const box=$('editor');if(!box||box.hidden||!$('edprev')||$('edfx')||!SERVED)return;
 if(!FXLIST){try{FXLIST=await api('api/plugins')}catch(e){FXLIST=[]}}if(!FXLIST.length||$('edfx'))return;
 const row=$('edprev').closest('.edrow'),d=document.createElement('div');d.className='edgrid';d.id='edfx';
 d.innerHTML=`<span>Plugin</span><select id="fxp"><option value="">none</option>${FXLIST.map(x=>`<option value="${esc(x.path)}">${esc(x.name)} (${x.format})</option>`).join('')}</select><span id="fxmsg" class="sub">your own effects</span>
 <span class="fxt" hidden>Tail</span><input class="fxt" hidden type="range" id="fxtail" min="0" max="12" step="0.5" value="4"><span class="fxt" hidden id="fxtailv">4 s to ring out</span><div id="fxctl" style="grid-column:1/-1;display:grid;grid-template-columns:auto 1fr auto;gap:4px 8px;align-items:center"></div>`;
 row.parentNode.insertBefore(d,row);
 $('fxtail').addEventListener('input',()=>$('fxtailv').textContent=$('fxtail').value+' s to ring out');$('fxtail').addEventListener('change',()=>edChanged());
 $('fxp').addEventListener('change',async()=>{const path=$('fxp').value,c=$('fxctl');c.innerHTML='';document.querySelectorAll('.fxt').forEach(e=>e.hidden=!path);if(!path){edChanged();return}
  $('fxmsg').textContent='loading…';let ps=[];try{ps=await api('api/plugins/params?path='+encodeURIComponent(path))}catch(e){$('fxmsg').textContent='couldn\'t load: '+e.message;return}
  if(ps.error){$('fxmsg').textContent=ps.error;return}$('fxmsg').textContent=ps.length+' controls';
  c.innerHTML=ps.slice(0,16).map(p=>p.kind==='choice'?`<span>${esc(p.name)}</span><select data-fx="${esc(p.key)}">${p.choices.map(o=>`<option ${o===p.value?'selected':''}>${esc(o)}</option>`).join('')}</select><span></span>`
   :p.kind==='bool'?`<span>${esc(p.name)}</span><input type="checkbox" data-fx="${esc(p.key)}" ${p.value?'checked':''}><span></span>`
   :`<span>${esc(p.name)}</span><input type="range" data-fx="${esc(p.key)}" min="${p.min}" max="${p.max}" step="${p.step}" value="${p.value}"><span data-fxv="${esc(p.key)}">${+(+p.value).toFixed(2)} ${esc(p.label||'')}</span>`).join('');
  c.querySelectorAll('[data-fx]').forEach(el=>{el.addEventListener('change',()=>el.dataset.touched=1);el.addEventListener('input',()=>{el.dataset.touched=1;const v=c.querySelector(`[data-fxv="${el.dataset.fx}"]`);if(v)v.textContent=(+(+el.value).toFixed(2))+' '+(v.textContent.split(' ').slice(1).join(' '))});el.addEventListener('change',()=>edChanged())});
  edChanged()})};
const _edParamsFx=edParams;
edParams=function(){const p=_edParamsFx();if($('fxp')&&$('fxp').value){const pr={};$('fxctl').querySelectorAll('[data-fx][data-touched]').forEach(el=>{pr[el.dataset.fx]=el.type==='checkbox'?el.checked:el.tagName==='SELECT'?el.value:+el.value});
 p.plugins=[{path:$('fxp').value,params:pr}];p.tail=+$('fxtail').value}return p};

// ---------- ✨ edit suggestions, judged by your taste model (suggest.py)
let SG=null;
const _openEditorSg=openEditor;
openEditor=async function(i){await _openEditorSg(i);const box=$('editor');if(!box||box.hidden||!$('edprev')||$('edsg')||!SERVED)return;
 const row=$('edprev').closest('.edrow'),d=document.createElement('div');d.id='edsg';d.style.margin='6px 0';
 d.innerHTML=`<div class="edrow"><button id="sgbtn" title="try a dozen edits that suit this kind of sound and let your taste model pick">✨ suggest edits</button>${hq('suggest')}<span class="sub" id="sgmsg"></span></div><div id="sglist"></div>`;
 row.parentNode.insertBefore(d,row);$('sgbtn').onclick=()=>sgRun(i)};
const SGREASONS=['too much','too subtle','sounds processed','wrong mood'];
const sgRate=(body)=>api('api/suggest/rate',body).catch(()=>{});
const sgFb=(x,action)=>SG&&api('api/suggest/feedback',{path:S[SG.i][F.path],id:S[SG.i][F.id],move:x.id,family:x.family,arm:x.arm,material:x.material,action}).catch(()=>{});
async function sgRun(i){const s=S[i];$('sgbtn').disabled=true;$('sglist').innerHTML='';$('sgmsg').textContent='trying a dozen edits on the selection… (a few seconds)';
 let r;try{r=await api('api/suggest',{path:s[F.path],project_key:PROJ.key||'',start:ED&&ED.sel?ED.sel[0]:0,end:ED&&ED.sel?ED.sel[1]:null})}
 catch(e){$('sgbtn').disabled=false;$('sgmsg').textContent="couldn't: "+e.message;return}
 $('sgbtn').disabled=false;if(r.error){$('sgmsg').textContent=r.error;return}
 SG={i,r,run:Date.now()};const up=r.suggestions.filter(x=>x.arm==='critic'&&x.delta>0).length;
 $('sgmsg').textContent=`tried ${r.tried} · `+(up?`${up} it thinks you'd like more than the original`:'it rates the original highest, so these are the ones it minds least');
 $('sglist').innerHTML=r.suggestions.map((x,k)=>`<div class="prow" data-sgk="${k}"><button class="play" data-sgplay="${k}">▶</button><div style="min-width:0">
  <div class="name">${x.arm==='wildcard'?'<span class="badge" style="background:#5b6370" title="picked at random from the rest, to check the model">wildcard</span> ':''}${esc(x.label)}</div>
  <div class="meta">${x.delta>=0?'+':''}${x.delta.toFixed(2)} taste · ${Math.round(x.close*100)}% like the original</div></div>
  <div style="display:flex;gap:6px"><button data-sgup="${k}" title="I like this edit">👍</button><button data-sgdown="${k}" title="I don't like this edit">👎</button><button data-sguse="${k}" title="set the editor to this edit, then adjust anything">use</button></div>
  <div class="sgwhy" data-sgwhy="${k}" hidden style="grid-column:1/-1">${SGREASONS.map(w=>`<button data-sgreason="${k}" data-r="${w}">${w}</button>`).join(' ')}<span class="sub"> why? (optional)</span></div></div>`).join('');
 const L=r.learning||{};$('sgmsg').textContent+=L.ratings?` · learning from ${L.ratings} rating${L.ratings>1?'s':''}`+(L.model_on?(L.model_auc!=null?` (its edit model predicts your 👍/👎 ${Math.round(L.model_auc*100)}% of the time)`:' (edit model on)'):''):' · rate them 👍/👎 to teach it'}
async function sgApply(x){const p=x.params,set=(id,v)=>{const el=$(id);if(!el)return;if(el.type==='checkbox')el.checked=!!v;else el.value=v;el.dispatchEvent(new Event('input'))};
 set('edst',p.stretch||1);set('edpi',p.semis||0);set('edfm',false);set('edtape',!!p.tape||(!!$('eddrum')&&!p.semis));
 if($('eddrum')){set('edpunch',Math.round((p.punch||0)*100));set('eddecay',decayVal(p.decay||0));set('eddrive',Math.round((p.drive||0)*100));set('edlow',p.lowcut||0)}set('edrev',!!p.reverse);set('edtone',toneVal(p.tone||20000));
 if($('tnkey')){const k=p.tune_key||'';if(k&&![...$('tnkey').options].some(o=>o.value===k))$('tnkey').insertAdjacentHTML('beforeend',`<option value="${esc(k)}">${esc(k)}</option>`);
  $('tnkey').value=k;set('tnstr',p.tune_strength??0.8);set('tnspd',p.tune_speed??60);set('tndet',0);set('tndri',0)}
 if($('fxp')){const pl=(p.plugins||[])[0];if(($('fxp').value||'')!==(pl?pl.path:'')){$('fxp').value=pl?pl.path:'';$('fxp').dispatchEvent(new Event('change'))}
  if(pl){for(let t=0;t<50&&!$('fxctl').querySelector('[data-fx]');t++)await new Promise(r=>setTimeout(r,100));
   Object.entries(pl.params||{}).forEach(([k,v])=>{const el=$('fxctl').querySelector(`[data-fx="${CSS.escape(k)}"]`);if(!el)return;if(el.type==='checkbox')el.checked=!!v;else el.value=v;el.dataset.touched=1;el.dispatchEvent(new Event('input'))});
   if(p.tail!=null){$('fxtail').value=p.tail;$('fxtail').dispatchEvent(new Event('input'))}}}
 ED.sugg=x;edChanged();$('edmsg').textContent=`set to “${x.label}” · adjust anything, then ▶ preview edit or save as new`}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-sgplay],[data-sguse],[data-sgno],[data-sgup],[data-sgdown],[data-sgreason]');if(!b||!SG)return;e.stopPropagation();
 const k=+(b.dataset.sgplay??b.dataset.sguse??b.dataset.sgno??b.dataset.sgup??b.dataset.sgdown??b.dataset.sgreason),x=SG.r.suggestions[k];
 const base={path:S[SG.i][F.path],move:x.id,family:x.family,material:x.material,arm:x.arm,params:x.params,source:'suggestion'};
 if(b.dataset.sgup!=null||b.dataset.sgdown!=null){const up=b.dataset.sgup!=null,row=b.closest('[data-sgk]');
  row.querySelector('[data-sgup]').classList.toggle('on',up);row.querySelector('[data-sgdown]').classList.toggle('on',!up);
  row.querySelector('[data-sgwhy]').hidden=up;sgRate({...base,rating:up?1:-1});return}
 if(b.dataset.sgreason!=null){b.parentNode.querySelectorAll('[data-sgreason]').forEach(z=>z.classList.toggle('on',z===b));sgRate({...base,rating:-1,reason:b.dataset.r});return}
 if(b.dataset.sgplay!=null){const key=`sg${SG.run}_${k}`,was=players.has(key);stopAll();if(was)return;  // ids per set of suggestions: slots repeat across samples
  const a=new Audio(x.url);a.loop=true;a.play();players.set(key,a);b.classList.add('playing');
  NP={path:S[SG.i][F.path],id:S[SG.i][F.id],label:`✨ edit: ${x.label} — ${lbl(SG.i)}`,i:SG.i,edit:true};drawNP();sgFb(x,'play');return}
 if(b.dataset.sguse!=null){stopAll();await sgApply(x);sgFb(x,'apply');document.querySelectorAll('[data-sgk]').forEach(r=>r.style.background=+r.dataset.sgk===k?'#1f2630':'');return}
 sgFb(x,'dismiss');b.closest('[data-sgk]').remove()},true);
// rate your own edit (whatever the editor is set to): the same ratings teach the suggestions
const _openEditorRate=openEditor;
openEditor=async function(i){await _openEditorRate(i);const box=$('editor');if(!box||box.hidden||!$('edprev')||$('edrate')||!SERVED)return;
 const d=document.createElement('div');d.id='edrate';d.className='edrow sub';
 d.innerHTML=`<span>rate this edit:</span><button id="edup" title="I like this edit">👍</button><button id="eddown" title="I don't like this edit">👎</button><span id="edwhy" hidden>${SGREASONS.map(w=>`<button data-edr="${w}">${w}</button>`).join(' ')}</span><span id="edrmsg"></span>`;
 $('edprev').closest('.edrow').after(d);
 const send=async(rating,reason)=>{$('edrmsg').textContent='listening…';const p=edParams();
  try{await api('api/suggest/rate',{path:S[i][F.path],rating,reason:reason||null,params:p,move:ED.sugg&&!edMoved(p,ED.sugg.params)?ED.sugg.id:null,
   family:ED.sugg&&!edMoved(p,ED.sugg.params)?ED.sugg.family:null,arm:ED.sugg&&!edMoved(p,ED.sugg.params)?ED.sugg.arm:null,source:'editor'});
   $('edrmsg').textContent=reason?' noted: '+reason:' noted: it learns from this'}catch(err){$('edrmsg').textContent=' couldn\'t save the rating'}};
 $('edup').onclick=()=>{$('edup').classList.add('on');$('eddown').classList.remove('on');$('edwhy').hidden=true;send(1)};
 $('eddown').onclick=()=>{$('eddown').classList.add('on');$('edup').classList.remove('on');$('edwhy').hidden=false;send(-1)};
 $('edwhy').onclick=e=>{const r=e.target.dataset.edr;if(!r)return;$('edwhy').querySelectorAll('button').forEach(z=>z.classList.toggle('on',z===e.target));send(-1,r)}};
// has the edit been changed since a suggestion set it? (then it's your edit, not the suggestion)
const edNz=(k,v)=>{if(v==null||v===false||v==='')v={stretch:1,semis:0,tone:20000}[k]??'';return v===true?'on':typeof v==='number'?Math.round(v*100)/100:String(v)};
const edMoved=(p,q)=>['stretch','semis','tape','reverse','tune_key'].some(k=>edNz(k,p[k])!==edNz(k,q[k]))||Math.abs(Math.log((p.tone||20000)/(q.tone||20000)))>0.05;
const _edSaveSg=edSave;
edSave=async function(...a){const x=ED&&ED.sugg;const r=await _edSaveSg.apply(this,a);if(x)sgFb(x,'save');return r};

// ---------- chop pads
const PADKEYS='1234qwerasdfzxcv'.split('');
const PADS={i:null,buf:null,sl:[],voice:null,events:[],rec:false,loop:null,start:0,len:0,timer:null,clickG:null};
function padsClose(){padsStopLoop();PADS.i=null;const b=$('pads');if(b)b.hidden=true}
function mergeSlices(b,n,minLen){let s=[];for(let k=0;k<b.length-1;k++)if(b[k+1]>b[k])s.push([b[k],b[k+1]]);
 while(s.length>1&&(s.length>n||s.some(x=>x[1]-x[0]<minLen))){let k=0;s.forEach((x,j)=>{if(x[1]-x[0]<s[k][1]-s[k][0])k=j});
  const j=k===s.length-1?k-1:k===0?1:((s[k-1][1]-s[k-1][0])<(s[k+1][1]-s[k+1][0])?k-1:k+1);const a=Math.min(j,k),c=Math.max(j,k);s.splice(a,2,[s[a][0],s[c][1]])}return s}
const padBpm=()=>PROJ.bpm||(PADS.i!=null&&S[PADS.i][F.bpm])||120;
async function openPads(i){const box=$('pads');if(!box.hidden&&PADS.i===i){padsClose();return}box.hidden=false;PADS.i=i;padsStopLoop();PADS.events=[];
 box.innerHTML='<div class="sub">slicing at syllables / notes…</div>';
 try{const path=S[i][F.path],conf=PROJ.on&&(PROJ.key||PROJ.bpm);const res=await fetch(conf?conformURL(path,PROJ.key,PROJ.bpm):url(path));
  const info=JSON.parse(res.headers.get('X-Conform')||'{}'),tr=+(info.length||info.time||1);PADS.buf=await AC.decodeAudioData(await res.arrayBuffer());
  const on=await api('api/onsets?path='+encodeURIComponent(path));if(st.sel!==i)return;
  PADS.sl=mergeSlices([0,...on.onsets.map(t=>t*tr),PADS.buf.duration],16,0.08)}catch(e){box.innerHTML='<div class="sub">pads failed: '+esc(e.message)+'</div>';return}
 const env=([a,b])=>{const d=PADS.buf.getChannelData(0),sr=PADS.buf.sampleRate,i0=Math.floor(a*sr),i1=Math.floor(b*sr),n=24,st2=Math.max(1,Math.floor((i1-i0)/n)),v=[];
  for(let k=0;k<n;k++){let m=0;for(let j=i0+k*st2;j<Math.min(i1,i0+(k+1)*st2);j+=4)m=Math.max(m,Math.abs(d[j]));v.push(m)}const mx=Math.max(...v,1e-6);return v.map(x=>Math.round(x/mx*99))};
 box.innerHTML=`<div class="edrow"><b>🎹 pads</b>${hq('pads')}<span class="sub">keys 1–4 · Q–R · A–F · Z–V (or click) · ${PADS.sl.length} slices${PROJ.on&&(PROJ.key||PROJ.bpm)?' · in the project key/tempo':''}</span></div>
 <div class="sub" style="margin:-2px 0 4px">your sample cut into syllables or notes: tap keys to replay them in a new rhythm, record a pattern, or save the slices as a Drum Rack</div>
 <div class="grid16">${PADS.sl.map((sl,k)=>`<div class="pad" data-pad="${k}"><b>${PADKEYS[k].toUpperCase()}</b>${wave(env(sl),110,16,'#7d8592')}<span>${sl[0].toFixed(2)}s · ${(sl[1]-sl[0]).toFixed(2)}</span></div>`).join('')}</div>
 <div class="edrow sub"><label><input type="checkbox" id="pdmono" checked> one voice at a time (choke)</label>
 quantise <select id="pdq"><option value="0">off</option><option value="2">1/8</option><option value="4" selected>1/16</option><option value="8">1/32</option></select>
 <select id="pdbars"><option value="1">1 bar</option><option value="2" selected>2 bars</option><option value="4">4 bars</option></select> at ${padBpm()} bpm</div>
 <div class="edrow"><button id="pdrec">● record</button><button id="pdplay">▶ pattern</button><button id="pdclr">clear</button><span class="sub" id="pdmsg">record loops the bar(s) with a click; play pads to overdub</span></div>
 <div class="edrow"><input id="pdname" placeholder="name (optional)" style="flex:1;min-width:110px"><button id="pdsave" class="pill">save pattern as new sample</button><button id="pdrack" title="every slice as its own pad in an Ableton Drum Rack">⇩ chops → Drum Rack</button></div>`;
 box.querySelectorAll('[data-pad]').forEach(p=>p.onmousedown=e=>{e.preventDefault();padHit(+p.dataset.pad)});
 $('pdrec').onclick=()=>{if(PADS.rec){PADS.rec=false;$('pdrec').textContent='● record';$('pdmsg').textContent=`${PADS.events.length} hits — looping`;return}padsStartLoop(true)};
 $('pdplay').onclick=()=>{if(PADS.loop){padsStopLoop();return}if(!PADS.events.length){toast('record a pattern first');return}padsStartLoop(false)};
 $('pdclr').onclick=()=>{PADS.events=[];$('pdmsg').textContent='cleared'};
 $('pdsave').onclick=padsSave;
 $('pdrack').onclick=async()=>{$('pdrack').textContent='building…';try{const r=await api('api/export',{scope:'paths',paths:[S[i][F.path]],name:xpName(),chop:true,reveal:true});$('pdrack').textContent='rack ✓';toast(`Drum Rack of chops → ${xpName()}`)}catch(e){$('pdrack').textContent='error'}}}
function padVoice(ctx,dest,k,t){const[a,b]=PADS.sl[k],s=ctx.createBufferSource();s.buffer=PADS.buf;const g=ctx.createGain();s.connect(g);g.connect(dest);const d=b-a,f=Math.min(0.004,d/4);
 g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(1,t+f);g.gain.setValueAtTime(1,t+d-f);g.gain.linearRampToValueAtTime(0,t+d);s.start(t,a,d);return{s,g}}
function padHit(k){if(PADS.i==null||!PADS.sl[k])return;AC.resume();const now=AC.currentTime;let t=now;
 if(PADS.loop){const pos=(now-PADS.start)%PADS.len,q=+$('pdq').value,step=q?60/padBpm()/q:0;let qp=step?Math.round(pos/step)*step:pos;qp=qp%PADS.len;
  if(PADS.rec)PADS.events.push([qp,k]);}
 if($('pdmono')&&$('pdmono').checked&&PADS.voice){try{PADS.voice.g.gain.cancelScheduledValues(t);PADS.voice.g.gain.setTargetAtTime(0,t,0.006);PADS.voice.s.stop(t+0.05)}catch(e){}}
 PADS.voice=padVoice(AC,AC.destination,k,t);const el=document.querySelector(`[data-pad="${k}"]`);if(el){el.classList.add('hit');setTimeout(()=>el.classList.remove('hit'),120)}}
function padsStartLoop(rec){padsStopLoop();AC.resume();PADS.len=+$('pdbars').value*240/padBpm();PADS.start=AC.currentTime+0.1;PADS.rec=rec;PADS.loop={next:0,voices:[]};
 if(rec){$('pdrec').textContent='■ stop recording';$('pdmsg').textContent='recording — play the pads'}$('pdplay').textContent='■ stop';padsTick()}
function padsTick(){const Lp=PADS.loop;if(!Lp)return;const beat=60/padBpm();
 while(PADS.start+Lp.next*PADS.len<AC.currentTime+0.4){const t0=PADS.start+Lp.next*PADS.len;
  PADS.events.forEach(([p,k])=>{const t=t0+p;if(t>AC.currentTime+0.005)Lp.voices.push(padVoice(AC,AC.destination,k,t))});
  if(PADS.rec)for(let b=0;b<PADS.len/beat-1e-6;b++){const o=AC.createOscillator(),g=AC.createGain();o.frequency.value=b%4?1000:1600;o.connect(g);g.connect(AC.destination);const t=t0+b*beat;g.gain.setValueAtTime(0.12,t);g.gain.exponentialRampToValueAtTime(0.0001,t+0.04);o.start(t);o.stop(t+0.05)}
  Lp.next++}PADS.timer=setTimeout(padsTick,80)}
function padsStopLoop(){clearTimeout(PADS.timer);if(PADS.loop){PADS.loop.voices.forEach(v=>{try{v.s.stop()}catch(e){}})}PADS.loop=null;PADS.rec=false;if($('pdrec')){$('pdrec').textContent='● record';$('pdplay').textContent='▶ pattern'}}
async function padsSave(){if(!PADS.events.length){toast('record a pattern first');return}const bars=+$('pdbars').value,len=bars*240/padBpm(),sr=44100;
 const ctx=new OfflineAudioContext(2,Math.ceil(len*sr),sr),mono=$('pdmono').checked,ev=PADS.events.slice().sort((a,b)=>a[0]-b[0]);
 ev.forEach(([p,k],j)=>{const v=padVoice(ctx,ctx.destination,k,p);if(mono&&ev[j+1]){const t=ev[j+1][0];if(t<p+PADS.sl[k][1]-PADS.sl[k][0]){v.g.gain.cancelScheduledValues(t);v.g.gain.setValueAtTime(1,Math.max(p,t-0.006));v.g.gain.linearRampToValueAtTime(0,t);}}});
 $('pdmsg').textContent='rendering…';const buf=await ctx.startRendering();const i=PADS.i;
 try{const conf=PROJ.on&&PROJ.key;const r=await api('api/bounce',{parent:S[i][F.path],wav:wavB64(buf),kind:'loop',bpm:padBpm(),bars,key:conf?PROJ.key:'',prefix:'Pads',name:$('pdname').value.trim(),
  tag:`pads ${ev.length} hits`,ops:{pattern:ev,slices:PADS.sl,bpm:padBpm(),conformed:!!conf}});padsStopLoop();const j=addRow(i,r.row);toast('pattern saved as a new sample (★)');select(j,'go')}
 catch(e){$('pdmsg').textContent='save failed: '+e.message}}
window.addEventListener('keydown',e=>{if(PADS.i==null||$('pads').hidden||e.metaKey||e.ctrlKey||e.altKey)return;if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;
 const k=PADKEYS.indexOf(e.key.toLowerCase());if(k<0||k>=PADS.sl.length)return;e.preventDefault();e.stopImmediatePropagation();if(!e.repeat)padHit(k)},true);

// ================= export dialog: racks, conform, MIDI =================
$('expbtn').onclick=()=>{if(!SERVED){toast('needs the local server');return}
 const scope=st.tab==='F'?'favorites':'list',ids=st.tab==='F'?[...FAV.keys()]:filtered().slice(0,500).map(i=>S[i][F.path]);
 modal(`<h2 style="margin:0">Export to Ableton</h2><div class="sub">${ids.length} ${scope==='favorites'?'favourites':'samples from the current list'}${scope!=='favorites'&&filtered().length>500?' (first 500)':''} → <code>User Library/Samples/DigitalCrate/&lt;name&gt;/&lt;category&gt;/&lt;subtype&gt;/</code> with an _info.csv.</div>
 <input id="expName" placeholder="export name (e.g. Night session)" style="width:100%">
 <label class="sub"><input type="checkbox" id="expRack"> also build an Ableton <b>Drum Rack</b> (.adg) with every sample on a pad (first 128)</label>
 <label class="sub"><input type="checkbox" id="expConf" ${PROJ.key||PROJ.bpm?'':'disabled'}> conform copies to the project (${esc(PROJ.key||'no key')} · ${PROJ.bpm||'no tempo'})</label>
 <label class="sub"><input type="checkbox" id="expMidi"> add a .mid of the notes next to each tonal sample (slower)</label>
 <div class="edrow"><button id="expGo" class="pill">export</button><button data-close>close</button></div><div id="expMsg" class="sub"></div>`);
 $('expGo').onclick=async()=>{$('expMsg').textContent='copying…';const conf=$('expConf').checked;
  const body=Object.assign(scope==='favorites'?{scope}:{scope:'paths',paths:ids},{name:$('expName').value,rack:$('expRack').checked,midi:$('expMidi').checked,key:conf?PROJ.key:'',bpm:conf?PROJ.bpm:''});
  try{const r=await api('api/export',body);$('expMsg').textContent=`exported ${r.count} files${r.extra&&r.extra.length?` + ${r.extra.length} extras (racks / MIDI)`:''} to ${r.dest} (opened in Finder)`}catch(e){$('expMsg').textContent='error: '+e.message}}};

// ================= stop everything =================
$('stop').onclick=()=>{stopAll();skStop();padsStopLoop()};

window.CRATE={setTab,skAdd,skStop,drawSK,openPads,openMidi,PROJ,skBar,barLen,drumAdd,sliceLoop,skSnap};  // hooks for tools/screenshots.py and the console
drawProj();if(PROJ.link)linkPoll();render();
})();

// ================= MIDI controller (Web MIDI: Chrome, Edge, Firefox — Safari doesn't support it) =================
// Any controller works: open 🎹, press "learn" next to an action, then the pad, key or button you want for it.
// Pads/keys also play the chop pads when those are open (the first learned "pad 1" note and the 15 above it).
const MIDI_NOTES=['C','C♯','D','E♭','E','F','F♯','G','A♭','A','B♭','B'];
const MIDI_ACTIONS=[['play','play / stop the selected sample'],['next','next sample (and play it)'],['prev','previous sample (and play it)'],
 ['star','★ favourite'],['nope','✕ not for me (and go to the next)'],['pad1','chop pad 1 (pads 2–16 follow on the next notes)']];
const MIDI={map:(()=>{try{return JSON.parse(localStorage.getItem('midiMap')||'null')}catch(e){return null}})()||{play:'n:36',next:'n:37',prev:'n:38',star:'n:39',nope:'n:40',pad1:'n:44'},
 learn:null,inputs:[],status:'',last:''};
function midiSave(){try{localStorage.setItem('midiMap',JSON.stringify(MIDI.map))}catch(e){}}
function midiRows(){return [...document.querySelectorAll('#list .row')]}
function midiStep(d){const rows=midiRows();if(!rows.length)return;let k=rows.findIndex(r=>r.classList.contains('sel'));k=k<0?0:Math.max(0,Math.min(rows.length-1,k+d));
 const i=+rows[k].dataset.i;select(i,'list');rows[k].scrollIntoView({block:'nearest'});stopAll();const b=rows[k].querySelector('[data-play]');if(b)b.click()}
function midiDo(a,k){const i=st.sel;
 if(a==='next')return midiStep(1);if(a==='prev')return midiStep(-1);
 if(a==='play'){if(players.size){stopAll();return}if(i==null){midiStep(0);return}const b=document.querySelector(`#list .row[data-i="${i}"] [data-play]`)||document.querySelector(`[data-play="${i}"]`);if(b)b.click();return}
 if(i==null)return;const s=S[i];
 if(a==='star'){const on=!FAV.has(s[F.path]);toggleFav(s[F.path],s[F.id],lbl(i));toast(on?'★ favourite':'☆ removed');return}
 if(a==='nope'){toggleDislike(s[F.path],s[F.id]);midiStep(1);return}
 if(a==='pad'&&typeof padHit==='function'&&PADS.i!=null&&!$('pads').hidden)padHit(k)}
function midiMsg(e){const [st0,d1,d2]=e.data,type=st0&0xf0;let id=null;
 if(type===0x90&&d2>0)id='n:'+d1;else if(type===0xB0&&d2>=64)id='cc:'+d1;if(!id)return;MIDI.last=id;
 if(MIDI.learn){MIDI.map[MIDI.learn]=id;Object.keys(MIDI.map).forEach(k=>{if(k!==MIDI.learn&&MIDI.map[k]===id)delete MIDI.map[k]});MIDI.learn=null;midiSave();midiPanel();return}
 const a=Object.keys(MIDI.map).find(k=>MIDI.map[k]===id&&k!=='pad1');if(a){midiDo(a);return}
 const p=MIDI.map.pad1;if(p&&p[0]==='n'&&id[0]==='n'){const k=+id.slice(2)-+p.slice(2);if(k>=0&&k<16)midiDo('pad',k)}}
async function midiInit(){if(!navigator.requestMIDIAccess){MIDI.status='this browser has no Web MIDI (use Chrome, Edge or Firefox)';return}
 try{const acc=await navigator.requestMIDIAccess();const hook=()=>{MIDI.inputs=[...acc.inputs.values()];MIDI.inputs.forEach(inp=>inp.onmidimessage=midiMsg);
  MIDI.status=MIDI.inputs.length?MIDI.inputs.map(x=>x.name).join(', '):'no controller connected';midiBtn();if(!$('modal').hidden&&$('midipanel'))midiPanel()};
  acc.onstatechange=hook;hook()}catch(e){MIDI.status='MIDI not allowed: '+e.message}midiBtn()}
function midiBtn(){let b=$('midibtn');if(!b){b=document.createElement('button');b.id='midibtn';b.onclick=()=>{midiPanel();if(!MIDI.inputs.length&&!MIDI.status)midiInit()};$('expbtn').after(b)}
 b.textContent=MIDI.inputs.length?'🎹 '+MIDI.inputs.length:'🎹';b.title='MIDI controller: '+(MIDI.status||'click to connect')}
function midiPanel(){const nm=id=>!id?'—':id[0]==='n'?`note ${id.slice(2)} (${MIDI_NOTES[+id.slice(2)%12]}${Math.floor(+id.slice(2)/12)-1})`:`CC ${id.slice(3)}`;
 modal(`<div id="midipanel"><h2 style="margin:0">🎹 MIDI controller</h2><div class="sub">${esc(MIDI.status||'connecting…')}</div>
 <div class="sub" style="margin:6px 0">Press <b>learn</b>, then the pad, key or button to use. Buttons that send CC work too (pressed = value ≥ 64).${MIDI.last?` Last received: ${esc(nm(MIDI.last))}.`:''}</div>
 <div style="display:grid;grid-template-columns:1fr auto auto;gap:6px 10px;align-items:center">${MIDI_ACTIONS.map(([k,l])=>`<span>${esc(l)}</span><span class="sub">${esc(nm(MIDI.map[k]))}</span><button data-midilearn="${k}">${MIDI.learn===k?'press it now…':'learn'}</button>`).join('')}</div>
 <div style="margin-top:10px;display:flex;gap:8px"><button id="midireset">reset to defaults</button><button onclick="$('modal').hidden=true">done</button></div></div>`);
 $('midireset').onclick=()=>{MIDI.map={play:'n:36',next:'n:37',prev:'n:38',star:'n:39',nope:'n:40',pad1:'n:44'};midiSave();midiPanel()}}
document.addEventListener('click',e=>{const b=e.target.closest('[data-midilearn]');if(!b)return;MIDI.learn=MIDI.learn===b.dataset.midilearn?null:b.dataset.midilearn;midiPanel();if(!MIDI.inputs.length)midiInit()});
midiBtn();if(navigator.requestMIDIAccess&&navigator.permissions)navigator.permissions.query({name:'midi'}).then(r=>{if(r.state==='granted')midiInit()}).catch(()=>{});
