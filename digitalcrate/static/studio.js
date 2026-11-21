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
 <button id="pjlink" class="tbtn" title="follow Ableton Live's tempo via Link (turn on Link in Live's top bar)">🔗 Live</button>
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
document.getElementById('search').insertAdjacentHTML('afterend',`<button id="sndbtn" class="tbtn" title="search by what it sounds like (CLAP): e.g. “lonely female voice, distant” · add -word to push away">≈ by sound</button><button id="refbtn" class="tbtn" title="find samples that feel like a reference track (never sampled)">🎧 feels like…</button>`);
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
document.querySelector('.tabs').insertAdjacentHTML('beforeend',`<button id="tabC" title="today's crate: 20 picks for you + wildcards">🎲 Crate</button><button id="tabG" title="every sample on a map by sound">🌌 Galaxy</button><button id="tabY" title="scout YouTube for raw singing">🔭 Scout</button>`);
const MYTABS={C:'tabC',G:'tabG',Y:'tabY'};
function setTab(k){st.tab=k;document.querySelectorAll('.tabs button').forEach(b=>b.classList.remove('on'));const id=tabs[k]||MYTABS[k];if($(id))$(id).classList.add('on');render()}
Object.entries(MYTABS).forEach(([k,id])=>$(id).onclick=()=>setTab(k));
Object.values(tabs).forEach(id=>$(id).addEventListener('click',()=>Object.values(MYTABS).forEach(m=>$(m).classList.remove('on'))));
const _render=render;
render=function(){drawSBanner();if(st.tab==='C'){paintWheel();drawBanner();return renderCrate()}if(st.tab==='G'){paintWheel();drawBanner();return renderGalaxy()}
 if(st.tab==='Y'){paintWheel();drawBanner();return renderScout()}
 _render();if(st.tab==='K')renderKitExtras();if(st.tab==='S'&&SOUND&&SOUND.at)annotateAt()};
function annotateAt(){document.querySelectorAll('#list .row[data-i]').forEach(r=>{const p=S[+r.dataset.i][F.path],a=SOUND.at.get(p);const m=r.querySelector('.meta');
 if(a&&m&&!m.dataset.at){m.dataset.at=1;m.insertAdjacentHTML('beforeend',` · <span style="color:var(--acc)">like the reference @ ${a}</span>`)}})}
// rows get a ＋ (add to sketchpad)
const _rowHTML=rowHTML;
rowHTML=function(i){return _rowHTML(i).replace('<span class="id"',`<button class="xp" data-sk="${i}" title="add to the sketchpad">＋</button><span class="id"`)};

// ---------- daily crate
function rng(seed){let a=0;for(const c of seed)a=(a*31+c.charCodeAt(0))|0;return()=>{a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function lsj(k,d){try{return JSON.parse(localStorage.getItem(k)||'null')??d}catch(e){return d}}
function buildCrate(force){const day=new Date().toLocaleDateString('en-CA');const saved=lsj('atlasCrate',null);
 if(!force&&saved&&saved.day===day&&saved.paths&&saved.paths.length)return saved;
 const n=(saved&&saved.day===day?saved.n||0:0)+(force?1:0),R=rng(day+':'+n),seen=new Set(lsj('atlasCrateSeen',[]));
 const rated=new Set([...FAV.keys(),...TASTE.disliked]);
 const pool=S.map((s,i)=>i).filter(i=>{const s=S[i];return !rated.has(s[F.path])&&!seen.has(s[F.path])&&!st.excl.has(s[F.genre])&&s[F.q]>=0.45&&!s[F.path].startsWith('_Reference')&&!s[F.parent]});
 const sc=i=>TASTE.score[S[i][F.path]]??(S[i][F.q]-1),ds=i=>TASTE.discover[S[i][F.path]]??R();
 const pick=(list,k,out,byT,byA)=>{for(const i of list){if(out.length>=k)break;const t=S[i][F.tid],a=S[i][F.artist];if(byT.has(t)||(byA.get(a)||0)>=2)continue;byT.add(t);byA.set(a,(byA.get(a)||0)+1);out.push(i)}return out};
 const byT=new Set(),byA=new Map();
 const you=pick(pool.slice().sort((a,b)=>sc(b)-sc(a)+(R()-.5)*0.15),14,[],byT,byA);
 const disc=pool.slice().sort((a,b)=>ds(b)-ds(a)).slice(30,900);for(let k=disc.length-1;k>0;k--){const j=Math.floor(R()*(k+1));[disc[k],disc[j]]=[disc[j],disc[k]]}
 const wild=pick(disc,6,[],byT,byA);
 const c={day,n,paths:you.map(i=>S[i][F.path]),wild:wild.map(i=>S[i][F.path])};try{localStorage.setItem('atlasCrate',JSON.stringify(c));
  localStorage.setItem('atlasCrateSeen',JSON.stringify([...seen,...c.paths,...c.wild].slice(-3000)))}catch(e){}return c}
function renderCrate(){const c=buildCrate(false),all=[...c.paths,...c.wild],ids=p=>p.map(x=>byPath.get(x)).filter(x=>x!=null);
 const done=all.filter(p=>FAV.has(p)||TASTE.disliked.has(p)).length;
 $('count').textContent=`today's crate · ${done}/${all.length} rated`+(TASTE.n?` · taste model: ${TASTE.n} ratings`:'');
 $('list').innerHTML=`<div class="crateprog"><i style="width:${done/all.length*100}%"></i></div>
 <div class="kit"><h3><span>For you — what the taste model rates highest that you haven't heard</span><button id="crnew" title="a fresh crate">↻ new crate</button></h3>${ids(c.paths).map(rowHTML).join('')||'<div class="empty">rate a few samples first</div>'}</div>
 <div class="kit"><h3><span>Wildcards — outside your usual, picked to teach the model fastest</span></h3>${ids(c.wild).map(rowHTML).join('')}</div>
 <div class="hint" style="margin:0 16px 16px">★ and ✕ train the taste model; a new crate appears each day. Already-crated samples don't come back.</div>`;
 $('crnew').onclick=()=>{buildCrate(true);renderCrate()};mark()}

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
 $('gll').innerHTML=`${GP.filter(p=>p[3]).length.toLocaleString()} samples by sound — nearby = similar · wheel zoom · drag pan · click opens<br>
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
let ytT=null,ytRes=[];
async function renderScout(){$('count').textContent='YouTube scout';const L=$('list');
 if(!SERVED){L.innerHTML='<div class="empty">The scout needs the local server.</div>';return}
 let d={presets:[],results:[]};try{d=await api('api/ytscout')}catch(e){}if(st.tab!=='Y')return;ytRes=d.results;
 L.innerHTML=`<div style="padding:12px 16px;display:grid;gap:8px"><div class="sub">Search YouTube for raw, private-feeling singing. A minute of each result is listened to and scored for clean, unaccompanied voice (and how close it is to your favourite vocals). Nothing enters the library until you press <b>add source</b>.</div>
 <div class="edrow"><input id="ytq" placeholder="e.g. acapella cover · singing in my car · choir rehearsal" style="flex:1;min-width:200px"><select id="ytn"><option>10</option><option selected>15</option><option>25</option></select><button id="ytgo" class="pill">scout</button></div>
 <div class="chips">${d.presets.map(p=>`<button data-ytp="${esc(p)}">${esc(p)}</button>`).join('')}</div><div id="ytjobs"></div>
 <label class="sub"><input type="checkbox" id="ytsk"> show skipped</label></div><div id="ytlist"></div>`;
 $('ytgo').onclick=()=>ytStart($('ytq').value.trim());$('ytq').onkeydown=e=>{if(e.key==='Enter')$('ytgo').click()};$('ytsk').onchange=ytDraw;
 ytDraw();ytPoll()}
function ytDraw(){const el=$('ytlist');if(!el)return;const sk=$('ytsk')&&$('ytsk').checked;const rows=ytRes.filter(r=>sk||r.status!=='skipped');
 const mx=Math.max(...rows.map(r=>r.score),1e-6);
 el.innerHTML=rows.length?rows.map(r=>`<div class="yt" style="${r.status==='skipped'?'opacity:.4':''}"><button class="play" data-ytsnip="${esc(r.snippet||'')}" data-ytt="${esc(r.title||'')}">▶</button>
  <div style="min-width:0"><div class="name">${r.status==='ingested'?'<span class="badge" style="background:var(--acc)">added</span>':''}<a href="${esc(r.url)}" target="_blank" rel="noopener" style="color:inherit">${esc(r.title||r.id)}</a></div>
  <div class="meta">${esc(r.channel||'')} · ${r.views!=null?Number(r.views).toLocaleString()+' views':''} · ${r.duration?Math.floor(r.duration/60)+':'+String(Math.round(r.duration%60)).padStart(2,'0'):''} · best moment @ ${Math.floor(r.best_at/60)}:${String(Math.round(r.best_at%60)).padStart(2,'0')} · “${esc(r.query||'')}”</div>
  <div class="bars"><span>voice</span><i style="width:${Math.max(2,r.vocal*120)}px"></i><span>band/talk</span><i style="width:${Math.max(2,r.neg*120)}px;background:#d96c6c"></i><span>your taste</span><i style="width:${Math.max(2,(r.taste||0)*120)}px;background:var(--acc)"></i></div></div>
  <div style="display:flex;gap:6px;align-items:center"><span class="score">${Math.round(r.score/mx*100)}</span>${r.status==='ingested'?'':`<button data-ytadd="${esc(r.url)}" data-ytid="${esc(r.id)}" class="pill">add source →</button>`}<button data-ytskip="${esc(r.id)}" title="skip">✕</button></div></div>`).join('')
  :'<div class="empty">No candidates yet — pick a preset or type a search.</div>'}
async function ytStart(q){if(!q)return;try{await api('api/ytscout',{query:q,n:+$('ytn').value});toast('scouting “'+q+'”…');ytPoll()}catch(e){toast('error: '+e.message)}}
async function ytPoll(){clearTimeout(ytT);if(st.tab!=='Y')return;let js=[];try{js=await api('api/jobs?kind=ytscout')}catch(e){}
 const el=$('ytjobs');if(!el)return;const run=js.filter(j=>j.running);
 el.innerHTML=js.slice(-2).reverse().map(j=>`<div class="prov"><b>${esc(j.target)}</b> — ${j.running?'listening…':'done'}<div class="meta" style="white-space:pre-wrap">${j.tail.slice(-3).map(esc).join('\n')}</div></div>`).join('');
 if(run.length||ytPoll.wasRunning){try{const d=await api('api/ytscout');ytRes=d.results;ytDraw()}catch(e){}}
 ytPoll.wasRunning=run.length>0;if(run.length)ytT=setTimeout(ytPoll,2500)}
document.addEventListener('click',async e=>{const p=e.target.closest('[data-ytp]');if(p){$('ytq').value=p.dataset.ytp;ytStart(p.dataset.ytp);return}
 const sn=e.target.closest('[data-ytsnip]');if(sn){if(!sn.dataset.ytsnip)return;if(players.has('yt')&&sn.classList.contains('playing')){stopAll();return}stopAll();
  const a=new Audio(url(sn.dataset.ytsnip));a.play();players.set('yt',a);a.onended=()=>{players.delete('yt');sn.classList.remove('playing');drawNP()};document.querySelectorAll('[data-ytsnip]').forEach(b=>b.classList.remove('playing'));sn.classList.add('playing');
  setNP(sn.dataset.ytsnip,null,'scout preview · '+sn.dataset.ytt,null);return}
 const ad=e.target.closest('[data-ytadd]');if(ad){ad.disabled=true;ad.textContent='adding…';try{await api('api/ingest',{target:ad.dataset.ytadd,drums:false});await api('api/ytscout/mark',{id:ad.dataset.ytid,status:'ingested'});
  ytRes.forEach(r=>{if(r.id===ad.dataset.ytid)r.status='ingested'});ytDraw();toast('added — downloading & mining in the background (progress under ＋ add source)')}catch(err){toast('error: '+err.message)}return}
 const skp=e.target.closest('[data-ytskip]');if(skp){await api('api/ytscout/mark',{id:skp.dataset.ytskip,status:'skipped'}).catch(()=>{});ytRes.forEach(r=>{if(r.id===skp.dataset.ytskip)r.status='skipped'});ytDraw()}});

// ================= sketchpad =================
const SK={lanes:[],playing:false,open:false,voices:[],timer:null,master:null,nextBar:0,start:0};window.SK=SK;
const np=$('np'),dock=document.createElement('div');dock.className='dock';np.parentNode.insertBefore(dock,np);
dock.insertAdjacentHTML('beforeend','<div class="sk" id="sk" hidden></div>');dock.appendChild(np);
$('skbtn').onclick=()=>{SK.open=!SK.open;drawSK();drawProj()};
const barLen=()=>240/(PROJ.bpm||120);
async function skAdd(i){if(!SERVED){toast('the sketchpad needs the local server');return}if(SK.lanes.length>=8){toast('the sketchpad holds 8 lanes');return}
 if(SK.lanes.some(l=>l.path===S[i][F.path])){toast('already in the sketch');return}
 const patch={};if(!PROJ.key&&S[i][F.cam])patch.key=keyFromCam(S[i][F.cam]);if(!PROJ.bpm)patch.bpm=S[i][F.bpm]||120;if(Object.keys(patch).length){Object.assign(PROJ,patch);try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(e){}drawProj()}
 const loop=S[i][F.kind]==='loop';
 const lane={i,path:S[i][F.path],vol:0.8,mute:false,solo:false,every:loop?0:(S[i][F.dur]>barLen()*2?4:S[i][F.dur]>barLen()?2:1),offset:0,buf:null,state:'loading'};
 SK.lanes.push(lane);SK.open=true;drawSK();drawProj();await skLoad(lane);drawSK();toast(`added to the sketch (${SK.lanes.length})`)}
async function skLoad(lane){lane.state='loading';try{const ab=await (await fetch(conformURL(lane.path,PROJ.key,PROJ.bpm))).arrayBuffer();lane.buf=await AC.decodeAudioData(ab);lane.state='ok'}catch(e){lane.state='error'}}
let reloadSeq=0;
async function skReload(){if(!SK.lanes.length)return;const seq=++reloadSeq,was=SK.playing;if(was)skStop();SK.lanes.forEach(l=>l.state='loading');drawSK();
 await Promise.all(SK.lanes.map(skLoad));if(seq!==reloadSeq)return;drawSK();if(was)skPlay()}
function skGains(){const solo=SK.lanes.some(l=>l.solo);SK.lanes.forEach(l=>{if(l.g)l.g.gain.setTargetAtTime(l.mute||(solo&&!l.solo)?0:l.vol,AC.currentTime,0.02)})}
function skVoice(ctx,dest,l,t,dur,arr){const s=ctx.createBufferSource();s.buffer=l.buf;const g=ctx.createGain();s.connect(g);g.connect(dest);const f=Math.min(0.004,dur/4);
 g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(1,t+f);g.gain.setValueAtTime(1,Math.max(t+f,t+dur-f));g.gain.linearRampToValueAtTime(0,t+dur);s.start(t,0,dur);if(arr){arr.push(s);s.onended=()=>{const k=arr.indexOf(s);if(k>=0)arr.splice(k,1)}}}
function skBar(ctx,dest,l,bar,t,L,arr){if(!l.buf)return;if(l.every===0){const n=Math.max(1,Math.round(l.buf.duration/L));if(bar%n)return;skVoice(ctx,dest,l,t,Math.min(l.buf.duration,n*L),arr)}
 else{if(bar%l.every)return;skVoice(ctx,dest,l,t+l.offset*L/4,l.buf.duration,arr)}}
function skPlay(){if(SK.playing||!SK.lanes.length)return;AC.resume();SK.master=AC.createGain();SK.master.gain.value=0.9;SK.master.connect(AC.destination);
 SK.lanes.forEach(l=>{l.g=AC.createGain();l.g.connect(SK.master)});skGains();SK.start=linkNextBar();SK.nextBar=0;SK.playing=true;SK.voices=[];skTick();requestAnimationFrame(skAnim);drawSK()}
function skTick(){if(!SK.playing)return;const L=barLen();while(SK.start+SK.nextBar*L<AC.currentTime+0.5){const t=SK.start+SK.nextBar*L;SK.lanes.forEach(l=>{if(l.g)skBar(AC,l.g,l,SK.nextBar,t,L,SK.voices)});SK.nextBar++}SK.timer=setTimeout(skTick,90)}
function skStop(){SK.playing=false;clearTimeout(SK.timer);const now=AC.currentTime;if(SK.master){SK.master.gain.setTargetAtTime(0,now,0.015);const m=SK.master;setTimeout(()=>{try{m.disconnect()}catch(e){}},150)}
 SK.voices.forEach(s=>{try{s.stop(now+0.08)}catch(e){}});SK.voices=[];drawSK()}
function skAnim(){if(!SK.playing)return;const el=$('skpos');if(el){const L=barLen(),t=AC.currentTime-SK.start;el.textContent=t<0?'waiting for the bar…':`bar ${Math.floor(t/L)+1} · beat ${Math.floor(t%L/(L/4))+1}`}requestAnimationFrame(skAnim)}
function skWave(c,buf){if(!c||!buf)return;const dpr=devicePixelRatio||1,W=c.clientWidth*dpr,H=30*dpr;c.width=W;c.height=H;const g=c.getContext('2d'),d=buf.getChannelData(0),st2=Math.max(1,Math.floor(d.length/W));
 g.fillStyle='#5b6370';for(let x=0;x<W;x++){let m=0;for(let k=x*st2;k<Math.min(d.length,(x+1)*st2);k+=4)m=Math.max(m,Math.abs(d[k]));g.fillRect(x,H/2-m*H/2,1,Math.max(1,m*H))}
 const L=barLen(),bars=buf.duration/L;g.fillStyle='rgba(224,164,88,.5)';for(let b=1;b<bars;b++)g.fillRect(b/bars*W,0,dpr,H)}
function drawSK(){const el=$('sk');el.hidden=!SK.open;if(!SK.open)return;
 el.innerHTML=`<h3>🎛 Sketchpad <span class="sub">${esc(PROJ.key||'no key')} · ${PROJ.bpm||'—'} bpm — every lane conformed to the project${PROJ.link&&LINK.peers?' · starts on Live\'s next bar':''}</span>
 <button id="skplay" class="${SK.playing?'pill':''}">${SK.playing?'■ stop':'▶ play'}</button><span id="skpos" class="sub"></span><span style="flex:1"></span>
 <input id="skname" placeholder="sketch name" style="width:130px" value="${esc(SK.name||'')}"><button id="sksave">save</button><select id="skbars" title="bounce length"><option value="4">4 bars</option><option value="8" selected>8 bars</option><option value="16">16 bars</option></select><button id="skbounce" title="render the mix as a new sample (favourited, with provenance)">⤓ bounce</button>
 <button id="skexp" title="export conformed copies + a Drum Rack to Ableton">⇩ Ableton</button><button id="skclear">clear</button><button id="skhide">▾</button></h3>
 ${SK.lanes.map((l,k)=>{const s=S[l.i]||[];const loop=s[F.kind]==='loop';return`<div class="lane${l.mute?' muted':''}" data-ln="${k}"><span class="badge" style="background:${col(s[F.cat])}">${AB[s[F.cat]]}</span>
  <div style="min-width:0"><div class="name">${esc(s[F.sub]||'')} · ${s[F.cam]||'—'}</div><div class="meta">${esc(s[F.artist]||'')} — ${esc(s[F.title]||'')}</div></div>
  <div>${l.state==='ok'?`<canvas data-skw="${k}"></canvas>`:`<span class="sub">${l.state==='loading'?'conforming…':'failed to load'}</span>`}</div>
  <div class="ctl"><button class="tbtn${l.mute?' on':''}" data-skm="${k}">M</button><button class="tbtn${l.solo?' on':''}" data-sks="${k}">S</button>
  <input type="range" min="0" max="1.2" step="0.01" value="${l.vol}" data-skv="${k}" title="volume">
  ${loop?`<span>loop</span>`:`<select data-ske="${k}" title="repeat every…">${[1,2,4,8,16].map(n=>`<option value="${n}" ${l.every===n?'selected':''}>every ${n} bar${n>1?'s':''}</option>`).join('')}</select>
  <select data-sko="${k}" title="start offset (beats)">${Array.from({length:32},(_,b)=>b/2).map(b=>`<option value="${b}" ${l.offset===b?'selected':''}>+${b} beat${b===1?'':'s'}</option>`).join('')}</select>`}
  <button data-go="${l.i}" title="open">→</button><button data-skx="${k}" title="remove">✕</button></div></div>`}).join('')||'<div class="sub">Empty — press ＋ on any sample (list, detail panel, “goes well with”) to add it.</div>'}
 <div class="hint">Loops lock to the bar; phrases and one-shots repeat every N bars at an offset. Change the project key/tempo above and every lane re-conforms.</div>`;
 SK.lanes.forEach((l,k)=>skWave(el.querySelector(`[data-skw="${k}"]`),l.buf))}
$('sk').addEventListener('click',async e=>{const t=e.target;
 if(t.id==='skplay'){SK.playing?skStop():skPlay();return}if(t.id==='skhide'){SK.open=false;drawSK();drawProj();return}
 if(t.id==='skclear'){skStop();SK.lanes=[];SK.name='';drawSK();drawProj();return}
 if(t.dataset.skm!=null){const l=SK.lanes[+t.dataset.skm];l.mute=!l.mute;skGains();drawSK();return}
 if(t.dataset.sks!=null){const l=SK.lanes[+t.dataset.sks];l.solo=!l.solo;skGains();drawSK();return}
 if(t.dataset.skx!=null){SK.lanes.splice(+t.dataset.skx,1);if(!SK.lanes.length)skStop();drawSK();drawProj();return}
 if(t.dataset.go!=null){select(+t.dataset.go,'list');return}
 if(t.id==='sksave'){const name=($('skname').value||'').trim()||`Sketch ${new Date().toLocaleString()}`;SK.name=name;
  await api('api/sketch/save',{name,state:{key:PROJ.key,bpm:PROJ.bpm,lanes:SK.lanes.map(l=>({path:l.path,vol:l.vol,mute:l.mute,solo:l.solo,every:l.every,offset:l.offset}))}}).then(()=>toast('sketch saved — find it in the Kits tab')).catch(err=>toast('error: '+err.message));return}
 if(t.id==='skexp'){const name=($('skname').value||'').trim()||'Sketch '+new Date().toISOString().slice(0,10);toast('exporting conformed copies + Drum Rack…');
  api('api/export',{scope:'paths',paths:SK.lanes.map(l=>l.path),name,key:PROJ.key,bpm:PROJ.bpm,rack:true,reveal:true}).then(r=>toast(`exported ${r.count} files + rack → ${name}`)).catch(err=>toast('error: '+err.message));return}
 if(t.id==='skbounce'){skBounce(+$('skbars').value);return}});
$('sk').addEventListener('input',e=>{const t=e.target;if(t.dataset.skv!=null){SK.lanes[+t.dataset.skv].vol=+t.value;skGains()}});
$('sk').addEventListener('change',e=>{const t=e.target;if(t.dataset.ske!=null)SK.lanes[+t.dataset.ske].every=+t.value;if(t.dataset.sko!=null)SK.lanes[+t.dataset.sko].offset=+t.value;if(t.id==='skname')SK.name=t.value});
async function skBounce(bars){if(!SK.lanes.length||SK.lanes.some(l=>!l.buf)){toast('wait for every lane to load');return}
 const L=barLen(),sr=44100,len=bars*L,tail=SK.lanes.some(l=>l.every)?Math.min(4,Math.max(...SK.lanes.map(l=>l.buf.duration))):0;
 const ctx=new OfflineAudioContext(2,Math.ceil((len)*sr),sr),solo=SK.lanes.some(l=>l.solo);
 SK.lanes.forEach(l=>{if(l.mute||(solo&&!l.solo))return;const g=ctx.createGain();g.gain.value=l.vol;g.connect(ctx.destination);for(let b=0;b<bars;b++)skBar(ctx,g,l,b,b*L,L,null)});
 toast('bouncing…');const buf=await ctx.startRendering();const first=SK.lanes[0];
 try{const r=await api('api/bounce',{parent:first.path,wav:wavB64(buf),kind:'loop',bpm:PROJ.bpm,bars,key:PROJ.key,prefix:'Sketch',name:($('skname').value||'').trim(),
   tag:`sketch ${SK.lanes.length} layers`,ops:{key:PROJ.key,bpm:PROJ.bpm,lanes:SK.lanes.map(l=>({path:l.path,vol:l.vol,mute:l.mute,every:l.every,offset:l.offset}))}});
  const j=addRow(first.i,r.row);toast('bounced → new sample (★ favourited)');select(j,'go')}catch(e){toast('bounce failed: '+e.message)}}
function addRow(i,n){const row=S[i].slice();Object.assign(row,{[F.id]:n.id,[F.path]:n.path,[F.cat]:n.category,[F.sub]:n.subtype,[F.kind]:n.kind,[F.cam]:n.cam,[F.key]:n.key,[F.bpm]:n.bpm,[F.dur]:n.dur,
 [F.env]:n.env,[F.note]:n.note,[F.bars]:n.bars,[F.start]:n.start,[F.parent]:n.parent,[F.root]:n.root,[F.ops]:n.ops});
 const j=S.push(row)-1;P.push(P[i]);BYID.set(n.id,j);byPath.set(n.path,j);(BYTRACK.get(row[F.tid])||[]).push(j);
 FAV.set(n.path,{path:n.path,sample_id:n.id,label:n.ops,added_at:new Date().toISOString()});return j}
function wavB64(buf){const n=buf.length,ch=2,sr=buf.sampleRate,b=new ArrayBuffer(44+n*ch*2),v=new DataView(b),w=(o,s)=>{for(let k=0;k<s.length;k++)v.setUint8(o+k,s.charCodeAt(k))};
 w(0,'RIFF');v.setUint32(4,36+n*ch*2,true);w(8,'WAVE');w(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,ch,true);v.setUint32(24,sr,true);v.setUint32(28,sr*ch*2,true);v.setUint16(32,ch*2,true);v.setUint16(34,16,true);w(36,'data');v.setUint32(40,n*ch*2,true);
 const Lc=buf.getChannelData(0),Rc=buf.numberOfChannels>1?buf.getChannelData(1):Lc;let o=44;for(let k=0;k<n;k++){v.setInt16(o,Math.max(-1,Math.min(1,Lc[k]))*32767,true);v.setInt16(o+2,Math.max(-1,Math.min(1,Rc[k]))*32767,true);o+=4}
 const u=new Uint8Array(b);let s='';for(let k=0;k<u.length;k+=0x8000)s+=String.fromCharCode.apply(null,u.subarray(k,k+0x8000));return btoa(s)}
// sketches + kit racks in the Kits tab
async function renderKitExtras(){const L=$('list');
 L.querySelectorAll('[data-kitexp]').forEach(b=>{const k=D.kits.findIndex(x=>x.name===b.dataset.kitexp);b.insertAdjacentHTML('afterend',` <button data-kitrack="${k}" title="export + Ableton Drum Rack">⇩ rack</button> <button data-kitsk="${k}" title="load into the sketchpad">🎛 sketch</button>`)});
 if(!SERVED)return;let sk=[];try{sk=await api('api/sketches')}catch(e){}if(st.tab!=='K'||!sk.length)return;
 L.insertAdjacentHTML('afterbegin',`<div class="kit"><h3><span>Your sketches</span></h3>${sk.map(x=>{const s=JSON.parse(x.state);return`<div class="prow"><button class="play" data-skopen="${esc(x.name)}">▶</button><div style="min-width:0"><div class="name">${esc(x.name)}</div><div class="meta">${esc(s.key||'')} · ${s.bpm||'—'} bpm · ${s.lanes.length} lanes · ${esc(x.updated_at)}</div></div><button data-skdel="${esc(x.name)}">✕</button></div>`}).join('')}</div>`);
 L.querySelectorAll('[data-skopen]').forEach(b=>b.onclick=()=>{const x=sk.find(z=>z.name===b.dataset.skopen);skOpen(x.name,JSON.parse(x.state))});
 L.querySelectorAll('[data-skdel]').forEach(b=>b.onclick=async()=>{await api('api/sketch/delete',{name:b.dataset.skdel});render()})}
async function skOpen(name,s){skStop();Object.assign(PROJ,{key:s.key,bpm:s.bpm});try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(e){}drawProj();
 SK.name=name;SK.lanes=s.lanes.map(l=>({...l,i:byPath.get(l.path),buf:null,state:'loading'})).filter(l=>l.i!=null);SK.open=true;drawSK();drawProj();await Promise.all(SK.lanes.map(skLoad));drawSK();skPlay()}
document.addEventListener('click',async e=>{const kr=e.target.closest('[data-kitrack]');if(kr){e.stopPropagation();const k=D.kits[+kr.dataset.kitrack];kr.textContent='building…';
  try{const r=await api('api/export',{scope:'paths',paths:k.m.map(i=>S[i][F.path]),name:k.name,rack:true,reveal:true});kr.textContent=`rack ✓ (${r.count})`}catch(err){kr.textContent='error'}return}
 const ks=e.target.closest('[data-kitsk]');if(ks){e.stopPropagation();const k=D.kits[+ks.dataset.kitsk];skStop();SK.lanes=[];for(const i of k.m)await skAdd(i);skPlay();return}
 const a=e.target.closest('[data-sk]');if(a){e.stopPropagation();e.preventDefault();skAdd(+a.dataset.sk)}},true);

// ================= detail panel: ＋ sketch · pads · MIDI · project info =================
const _select=select;
select=function(i,from){_select(i,from);augment(i)};
function augment(i){const eo=$('edopen');if(!eo)return;eo.parentNode.style.flexWrap='wrap';
 eo.insertAdjacentHTML('afterend',` <button data-sk="${i}" title="add to the sketchpad">＋ sketch</button><button id="padsopen" title="play its syllables / notes from the keyboard, record a pattern">🎹 pads</button>${S[i][F.cat]!=='Percussion'&&S[i][F.cam]?'<button id="midiopen" title="notes & chords → MIDI">♪ MIDI</button>':''}`);
 eo.parentNode.insertAdjacentHTML('afterend','<div class="sub" id="pjinfo" style="margin:-4px 0 8px"></div>');
 $('editor').insertAdjacentHTML('afterend','<div class="ed" id="pads" hidden></div><div class="ed" id="midibox" hidden></div>');
 document.querySelectorAll('#detail [data-pair]').forEach(b=>b.insertAdjacentHTML('beforebegin',`<button data-sk="${b.dataset.pair}" title="add to the sketchpad">＋</button>`));
 if(PROJ.key||PROJ.bpm)projInfo(i);if(PADS.i!==i)padsClose()}
$('detail').addEventListener('click',e=>{if(e.target.id==='padsopen'){openPads(st.sel);return}if(e.target.id==='midiopen'){openMidi(st.sel);return}});

// ---------- MIDI
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
 d.innerHTML=`<span>Tune to</span><select id="tnkey"><option value="">off</option>${PROJ.key?`<option value="${esc(PROJ.key)}">project · ${esc(PROJ.key)}</option>`:''}${own?`<option value="${esc(own)}">its own key · ${esc(own)}</option>`:''}${KEYS24.map(([c,n])=>`<option value="${n}">${c} ${n}</option>`).join('')}</select><span id="tnrep" class="sub"></span>
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
 box.innerHTML=`<div class="edrow"><b>🎹 pads</b><span class="sub">keys 1–4 · Q–R · A–F · Z–V (or click) · ${PADS.sl.length} slices${PROJ.on&&(PROJ.key||PROJ.bpm)?' · in the project key/tempo':''}</span></div>
 <div class="grid16">${PADS.sl.map(([a,b],k)=>`<div class="pad" data-pad="${k}"><b>${PADKEYS[k].toUpperCase()}</b><span>${a.toFixed(2)}s · ${(b-a).toFixed(2)}</span></div>`).join('')}</div>
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

window.CRATE={setTab,skAdd,skStop,drawSK,openPads,openMidi,PROJ};  // hooks for tools/screenshots.py and the console
drawProj();if(PROJ.link)linkPoll();render();
})();
