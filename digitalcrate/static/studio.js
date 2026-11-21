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
render=function(){drawSBanner();if('CGY'.includes(st.tab)&&typeof drawCats==='function')drawCats();if(st.tab==='C'){paintWheel();drawBanner();return renderCrate()}if(st.tab==='G'){paintWheel();drawBanner();return renderGalaxy()}
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
// a non-loop lane repeats every N bars: the shortest of 1/2/4/8/16 that fits the whole clip (so it never piles up on itself)
const skEvery=dur=>[1,2,4,8,16].find(n=>n*barLen()>=0.85*dur)||16;  // covers most of the clip; the tail fades into the next pass
async function skAdd(i){if(!SERVED){toast('the sketchpad needs the local server');return}if(SK.lanes.length>=8){toast('the sketchpad holds 8 lanes');return}
 if(SK.lanes.some(l=>l.path===S[i][F.path])){toast('already in the sketch');return}
 const patch={};if(!PROJ.key&&S[i][F.cam])patch.key=keyFromCam(S[i][F.cam]);if(!PROJ.bpm)patch.bpm=S[i][F.bpm]||120;if(Object.keys(patch).length){Object.assign(PROJ,patch);try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(e){}drawProj()}
 const loop=S[i][F.kind]==='loop';
 const lane={i,path:S[i][F.path],db:0,mute:false,solo:false,every:loop?0:skEvery(S[i][F.dur]),offset:0,buf:null,state:'loading'};
 SK.lanes.push(lane);SK.open=true;drawSK();drawProj();await skLoad(lane);drawSK();toast(`added to the sketch (${SK.lanes.length})`)}
async function skLoad(lane){lane.state='loading';lane.att=null;try{const ab=await (await fetch(conformURL(lane.path,lane.nat?'':PROJ.key,PROJ.bpm))).arrayBuffer();lane.buf=await AC.decodeAudioData(ab);lane.norm=skNorm(lane.buf);lane.state='ok'}catch(e){lane.state='error'}
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
 const first=skOnsets(l).find(p=>p>=r0&&p<r0+Math.min(R,4));if(first!=null){const v=Math.max(0,first-r0-0.01);l.att={key,v};return v}const sr=l.buf.sampleRate,a=Math.floor(r0*sr),b=Math.min(l.buf.length,a+Math.floor(Math.min(R,4)*sr));
 let pk=0;const chs=[...Array(l.buf.numberOfChannels).keys()].map(c=>l.buf.getChannelData(c));for(const d of chs)for(let k=a;k<b;k+=2)pk=Math.max(pk,Math.abs(d[k]));
 let at=a;outer:for(let k=a;k<b;k+=2)for(const d of chs)if(Math.abs(d[k])>0.2*pk){at=k;break outer}
 const v=Math.min(1,Math.max(0,(at-a)/sr-0.01));l.att={key,v};return v}
let reloadSeq=0;
async function skReload(){if(!SK.lanes.length)return;const seq=++reloadSeq,was=SK.playing;if(was)skStop();SK.lanes.forEach(l=>l.state='loading');drawSK();
 await Promise.all(SK.lanes.map(skLoad));if(seq!==reloadSeq)return;drawSK();if(was)skPlay()}
function skGains(){const solo=SK.lanes.some(l=>l.solo);SK.lanes.forEach(l=>{if(l.g)l.g.gain.setTargetAtTime(l.mute||(solo&&!l.solo)?0:laneGain(l),AC.currentTime,0.02)})}
// a lane can be trimmed to part of its clip: trim = [from, to] as fractions of the (conformed) clip
const skRegion=l=>{const d=l.buf.duration,[a,b]=l.trim||[0,1];return [a*d,Math.max(0.01,(b-a)*d)]};
function skVoice(ctx,dest,l,t,dur,arr){const s=ctx.createBufferSource();s.buffer=l.buf;const g=ctx.createGain();s.connect(g);g.connect(dest);
 let off=skRegion(l)[0];const lead=l.every===0||l.free?0:skAttack(l);t+=l.nudge||0;
 if(lead>0){if(t-lead>=ctx.currentTime+0.005)t-=lead;else{off+=lead;dur=Math.max(0.01,dur-lead)}}
 const fi=Math.min(Math.max(0.004,(l.fin||0)/1000),dur/2),fo=Math.min(Math.max(0.004,(l.fout||0)/1000),dur/2);
 g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(1,t+fi);g.gain.setValueAtTime(1,Math.max(t+fi,t+dur-fo));g.gain.linearRampToValueAtTime(0,t+dur);s.start(t,off,dur);
 if(ctx===AC){(l.on||(l.on=[])).push({t0:t,off,dur});if(l.on.length>8)l.on.shift()}  /* remembered for the playhead */if(arr){arr.push(s);s.onended=()=>{const k=arr.indexOf(s);if(k>=0)arr.splice(k,1)}}}
function skBar(ctx,dest,l,bar,t,L,arr){if(!l.buf)return;const R=skRegion(l)[1];if(l.every===0){const n=Math.max(1,Math.round(R/L));if(bar%n)return;skVoice(ctx,dest,l,t,Math.min(R,n*L),arr)}
 else{if(bar%l.every)return;skVoice(ctx,dest,l,t+l.offset*L/4,Math.min(R,l.every*L),arr)}}  // a pass ends where the next begins
function skPlay(){if(SK.playing||!SK.lanes.length)return;AC.resume();
 stopAll();padsStopLoop();  // a sketch takes over from whatever was playing (clips over a running sketch still work)
SK.master=AC.createGain();SK.master.gain.value=0.9;SK.master.connect(AC.destination);
 SK.lanes.forEach(l=>{l.g=AC.createGain();l.g.connect(SK.master)});skGains();SK.start=linkNextBar();SK.nextBar=0;SK.playing=true;SK.voices=[];skTick();requestAnimationFrame(skAnim);drawSK()}
function skTick(){if(!SK.playing)return;const L=barLen();while(SK.start+SK.nextBar*L<AC.currentTime+1.2){const t=SK.start+SK.nextBar*L;SK.lanes.forEach(l=>{if(l.g)skBar(AC,l.g,l,SK.nextBar,t,L,SK.voices)});SK.nextBar++}SK.timer=setTimeout(skTick,90)}
function skStop(){SK.playing=false;clearTimeout(SK.timer);const now=AC.currentTime;if(SK.master){SK.master.gain.setTargetAtTime(0,now,0.015);const m=SK.master;setTimeout(()=>{try{m.disconnect()}catch(e){}},150)}
 SK.voices.forEach(s=>{try{s.stop(now+0.08)}catch(e){}});SK.voices=[];SK.lanes.forEach(l=>l.on=[]);drawSK()}
function skAnim(){skHeads();if(!SK.playing)return;const el=$('skpos');if(el){const L=barLen(),t=AC.currentTime-SK.start;el.textContent=t<0?'waiting for the bar…':`bar ${Math.floor(t/L)+1} · beat ${Math.floor(t%L/(L/4))+1}`}requestAnimationFrame(skAnim)}
function skWave(c,buf,trim){if(!c||!buf)return;const dpr=devicePixelRatio||1,W=c.clientWidth*dpr,H=30*dpr;c.width=W;c.height=H;const g=c.getContext('2d'),d=buf.getChannelData(0),st2=Math.max(1,Math.floor(d.length/W));
 const [ta,tb]=trim||[0,1],xa=ta*W,xb=tb*W;
 for(let x=0;x<W;x++){let m=0;for(let k=x*st2;k<Math.min(d.length,(x+1)*st2);k+=4)m=Math.max(m,Math.abs(d[k]));g.fillStyle=x>=xa&&x<=xb?'#8cc0da':'#3a4048';g.fillRect(x,H/2-m*H/2,1,Math.max(1,m*H))}
 const ln=SK.lanes[+c.dataset.skw];
 // the project's beats as this lane plays them: the attack (or a loop's start) sits on a beat, shifted by any nudge
 if(ln){const L=barLen(),bt=L/4,[r0]=skRegion(ln),o=r0+(ln.every===0?0:skAttack(ln))-(ln.nudge||0),X=p=>p/buf.duration*W;
  for(let k=Math.ceil(-o/bt);o+k*bt<=buf.duration;k++){const x=X(o+k*bt);if(x<0)continue;const bar=((k%4)+4)%4===0;g.fillStyle=bar?'rgba(224,164,88,.7)':'rgba(224,164,88,.22)';g.fillRect(x,0,(bar?1.5:1)*dpr,H)}
  g.fillStyle='rgba(255,255,255,.55)';skOnsets(ln).forEach(p=>g.fillRect(X(p)-0.5*dpr,H-5*dpr,dpr,5*dpr));
  const xo=X(o<0?o+Math.ceil(-o/bt)*bt:o);g.fillStyle='#e0a458';g.beginPath();g.moveTo(xo-4*dpr,0);g.lineTo(xo+4*dpr,0);g.lineTo(xo,6*dpr);g.fill()}  // ▼ = the point on the beat
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
 const v=[];let last=-1e9;for(let i=w;i<n-1;i++)if(f[i]>=4&&f[i]>=f[i-1]&&f[i]>=f[i+1]){if(i-last>gap){v.push(i*hop/sr);last=i}else if(f[i]>f[Math.round(v[v.length-1]*sr/hop)]){v[v.length-1]=i*hop/sr;last=i}}
 l.ons={buf:b,v};return v}
// re-align: try putting each attack near the start of the selection on the beat (and small shifts around it),
// keep the placement where the most of the clip's attacks fall on the project's 8th-note grid
function skAlign(l){const [r0,R]=skRegion(l),e8=barLen()/8,o0=r0+(l.every===0?0:skAttack(l));
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
function skHeads(){const now=AC.currentTime,dpr=devicePixelRatio||1;SK.lanes.forEach((l,k)=>{const c=document.querySelector(`[data-skw="${k}"]`);if(!c||!c._base||!l.buf)return;
 const g=c.getContext('2d');g.clearRect(0,0,c.width,c.height);g.drawImage(c._base,0,0);
 const v=(l.on||[]).filter(v=>now>=v.t0&&now<v.t0+v.dur).pop();if(!v||!SK.playing)return;
 const x=(v.off+(now-v.t0))/l.buf.duration*c.width;g.fillStyle='#fff';g.fillRect(x-dpr,0,2*dpr,c.height);g.fillStyle='rgba(255,255,255,.15)';g.fillRect(x-6*dpr,0,5*dpr,c.height)})}
function drawSK(){const el=$('sk');el.hidden=!SK.open;if(!SK.open)return;
 el.innerHTML=`<h3>🎛 Sketchpad <span class="sub">${esc(PROJ.key||'no key')} · ${PROJ.bpm||'—'} bpm — every lane conformed to the project${PROJ.link&&LINK.peers?' · starts on Live\'s next bar':''}</span>
 <button id="skplay" class="${SK.playing?'pill':''}">${SK.playing?'■ stop':'▶ play'}</button><span id="skpos" class="sub"></span><span style="flex:1"></span>
 <input id="skname" placeholder="sketch name" style="width:130px" value="${esc(SK.name||'')}"><button id="sksave">save</button><select id="skbars" title="bounce length"><option value="4">4 bars</option><option value="8" selected>8 bars</option><option value="16">16 bars</option></select><button id="skbounce" title="render the mix as a new sample (favourited, with provenance)">⤓ bounce</button>
 <button id="skstems" title="each lane as its own WAV, all the same length from bar 1, in the sketch's key and tempo: drop them into Live and they line up">⇩ stems</button><button id="skexp" title="export conformed copies + a Drum Rack to Ableton">⇩ Ableton</button><button id="skclear">clear</button><button id="skhide">▾</button></h3>
 ${SK.lanes.map((l,k)=>{const s=S[l.i]||[];const loop=s[F.kind]==='loop';const tags=[l.trim?`✂ ${Math.round((l.trim[1]-l.trim[0])*100)}%`:'',l.nat?'orig key':'',loop?'loop':`every ${l.every} · +${l.offset}`].filter(Boolean).join(' · ');
  return`<div class="lane${l.mute?' muted':''}" data-ln="${k}">
  <label class="onoff" title="turn this lane on or off"><input type="checkbox" data-skon="${k}" ${l.mute?'':'checked'}><span></span></label>
  <div class="lname" title="${esc(s[F.artist]||'')} — ${esc(s[F.title]||'')} · ${esc(s[F.sub]||'')} ${s[F.cam]||''}"><div class="name"><span class="badge" style="background:${col(s[F.cat])}">${AB[s[F.cat]]}</span>${esc(s[F.artist]||'')}</div><div class="meta">${esc(s[F.title]||'')} · ${tags}</div></div>
  <div class="lwave">${l.trim||l.nudge?`<button class="tbtn realign" data-skalign="${k}" title="put the first strong attack of the selection on the beat (clears any nudge)">↺ re-align</button>`:''}${l.state==='ok'?`<canvas data-skw="${k}"></canvas>`:`<span class="sub">${l.state==='loading'?'conforming…':'failed to load'}</span>`}</div>
  <div class="fader" title="volume relative to the other lanes (all start equally loud at 0 dB) · double-click for 0 dB"><input type="range" min="-24" max="6" step="0.5" value="${l.db||0}" data-skv="${k}"><output>${dbTxt(l.db||0)}</output></div>
  <button class="tbtn${l.solo?' on':''}" data-sks="${k}" title="solo">S</button><button class="tbtn${l.more?' on':''}" data-skmore="${k}" title="timing, key, fades, open, remove">⋯</button>
  ${l.more?`<div class="lmore">${loop?'<span class="sub">loop: locked to the bar</span>':`<label class="sub">repeat <select data-ske="${k}">${[1,2,4,8,16].map(n=>`<option value="${n}" ${l.every===n?'selected':''}>every ${n} bar${n>1?'s':''}</option>`).join('')}</select></label>
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
 if(t.id==='skclear'){skStop();SK.lanes=[];SK.name='';drawSK();drawProj();return}
 if(t.dataset.skm!=null){const l=SK.lanes[+t.dataset.skm];l.mute=!l.mute;skGains();drawSK();return}
 if(t.dataset.sks!=null){const l=SK.lanes[+t.dataset.sks];l.solo=!l.solo;skGains();drawSK();return}
 if(t.dataset.skalign!=null){const l=SK.lanes[+t.dataset.skalign];if(!l.buf)return;const r=skAlign(l);drawSK();toast(r);return}
 if(t.dataset.sknudge!=null){const l=SK.lanes[+t.dataset.sknudge],step=e.shiftKey?barLen()/16:0.01;l.nudge=Math.max(-2,Math.min(2,(l.nudge||0)+(+t.dataset.d)*step));drawSK();return}
 if(t.dataset.skmore!=null){const l=SK.lanes[+t.dataset.skmore];l.more=!l.more;drawSK();return}
 if(t.dataset.sknat!=null){const l=SK.lanes[+t.dataset.sknat];l.nat=!l.nat;drawSK();await skLoad(l);drawSK();return}
 if(t.dataset.skx!=null){SK.lanes.splice(+t.dataset.skx,1);if(!SK.lanes.length)skStop();drawSK();drawProj();return}
 if(t.dataset.go!=null){select(+t.dataset.go,'list');return}
 if(t.id==='sksave'){const name=($('skname').value||'').trim()||`Sketch ${new Date().toLocaleString()}`;SK.name=name;
  await api('api/sketch/save',{name,state:{key:PROJ.key,bpm:PROJ.bpm,lanes:SK.lanes.map(l=>({path:l.path,db:l.db||0,vol:+(0.8*Math.pow(10,(l.db||0)/20)).toFixed(3),mute:l.mute,solo:l.solo,every:l.every,offset:l.offset,trim:l.trim||null,fin:l.fin||0,fout:l.fout||0,nudge:l.nudge||0,nat:!!l.nat}))}}).then(()=>toast('sketch saved — find it in the Kits tab')).catch(err=>toast('error: '+err.message));return}
 if(t.id==='skexp'){const name=($('skname').value||'').trim()||'Sketch '+new Date().toISOString().slice(0,10);toast('exporting conformed copies + Drum Rack…');
  api('api/export',{scope:'paths',paths:SK.lanes.map(l=>l.path),name,key:PROJ.key,bpm:PROJ.bpm,rack:true,reveal:true}).then(r=>toast(`exported ${r.count} files + rack → ${name}`)).catch(err=>toast('error: '+err.message));return}
 if(t.id==='skbounce'){skBounce(+$('skbars').value);return}
 if(t.id==='skstems'){skStems(+$('skbars').value);return}});
// aligned stems: render every audible lane alone over the same N bars, so each file starts on bar 1 and they all line up
async function skStems(bars){if(!SK.lanes.length||SK.lanes.some(l=>!l.buf)){toast('wait for every lane to load');return}
 const L=barLen(),sr=44100,solo=SK.lanes.some(l=>l.solo),name=($('skname').value||'').trim()||SK.name||'Sketch '+new Date().toISOString().slice(0,10);
 const live=SK.lanes.filter(l=>!(l.mute||(solo&&!l.solo)));if(!live.length){toast('every lane is muted');return}toast(`rendering ${live.length} stems…`);
 const stems=[];for(const l of live){const ctx=new OfflineAudioContext(2,Math.ceil(bars*L*sr),sr),g=ctx.createGain();g.gain.value=laneGain(l);g.connect(ctx.destination);
  for(let b=0;b<bars;b++)skBar(ctx,g,l,b,b*L,L,null);const s=S[l.i];stems.push({label:`${AB[s[F.cat]]} ${s[F.artist]} - ${s[F.title]}`,wav:wavB64(await ctx.startRendering())})}
 try{const r=await api('api/stems',{name,key:PROJ.key,bpm:PROJ.bpm,stems});toast(`${r.files.length} stems → ${r.dest.split('/').slice(-2).join('/')} · set Live to ${PROJ.bpm} bpm, ⌘-drag them in to get one track each`)}catch(e){toast('stems failed: '+e.message)}}
$('sk').addEventListener('input',e=>{const t=e.target;
 if(t.dataset.skfi!=null||t.dataset.skfo!=null){const l=SK.lanes[+(t.dataset.skfi??t.dataset.skfo)];l[t.dataset.skfi!=null?'fin':'fout']=+t.value;
  const o=t.parentNode.querySelector('output');if(o)o.textContent=t.value+' ms';const k=SK.lanes.indexOf(l);skWave(document.querySelector(`[data-skw="${k}"]`),l.buf,l.trim);return}if(t.dataset.skv!=null){const l=SK.lanes[+t.dataset.skv];l.db=+t.value;skGains();const o=t.parentNode.querySelector('output');if(o)o.textContent=dbTxt(l.db)}});
$('sk').addEventListener('dblclick',e=>{const t=e.target;if(t.dataset&&t.dataset.skv!=null){const l=SK.lanes[+t.dataset.skv];l.db=0;skGains();drawSK()}});
$('sk').addEventListener('change',e=>{const t=e.target;if(t.dataset.skon!=null){const l=SK.lanes[+t.dataset.skon];l.mute=!t.checked;skGains();drawSK();return}if(t.dataset.ske!=null){SK.lanes[+t.dataset.ske].every=+t.value;drawSK();return}if(t.dataset.sko!=null){SK.lanes[+t.dataset.sko].offset=+t.value;drawSK();return}if(t.id==='skname')SK.name=t.value});
async function skBounce(bars){if(!SK.lanes.length||SK.lanes.some(l=>!l.buf)){toast('wait for every lane to load');return}
 const L=barLen(),sr=44100,len=bars*L,tail=SK.lanes.some(l=>l.every)?Math.min(4,Math.max(...SK.lanes.map(l=>l.buf.duration))):0;
 const ctx=new OfflineAudioContext(2,Math.ceil((len)*sr),sr),solo=SK.lanes.some(l=>l.solo);
 SK.lanes.forEach(l=>{if(l.mute||(solo&&!l.solo))return;const g=ctx.createGain();g.gain.value=laneGain(l);g.connect(ctx.destination);for(let b=0;b<bars;b++)skBar(ctx,g,l,b,b*L,L,null)});
 toast('bouncing…');const buf=await ctx.startRendering();const first=SK.lanes[0];
 try{const r=await api('api/bounce',{parent:first.path,wav:wavB64(buf),kind:'loop',bpm:PROJ.bpm,bars,key:PROJ.key,prefix:'Sketch',name:($('skname').value||'').trim(),
   tag:`sketch ${SK.lanes.length} layers`,ops:{key:PROJ.key,bpm:PROJ.bpm,lanes:SK.lanes.map(l=>({path:l.path,db:l.db||0,vol:+(0.8*Math.pow(10,(l.db||0)/20)).toFixed(3),mute:l.mute,every:l.every,offset:l.offset,trim:l.trim||null,fin:l.fin||0,fout:l.fout||0,nudge:l.nudge||0}))}});
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
 L.insertAdjacentHTML('afterbegin',`<div class="kit"><h3><span>Your sketches</span></h3>${sk.map(x=>{const s=JSON.parse(x.state);return`<div class="prow"><button class="play" data-skopen="${esc(x.name)}">▶</button><div style="min-width:0"><div class="name">${esc(x.name)}</div><div class="meta">${esc(s.key||'')} · ${s.bpm||'—'} bpm · ${s.lanes.length} lanes · ${esc(x.updated_at)}</div></div><button data-skdel="${esc(x.name)}">✕</button></div>`}).join('')}</div>`);
 L.querySelectorAll('[data-skopen]').forEach(b=>b.onclick=()=>{const x=sk.find(z=>z.name===b.dataset.skopen);skOpen(x.name,JSON.parse(x.state))});
 L.querySelectorAll('[data-skdel]').forEach(b=>b.onclick=async()=>{await api('api/sketch/delete',{name:b.dataset.skdel});render()})}
async function skOpen(name,s){skStop();Object.assign(PROJ,{key:s.key,bpm:s.bpm});try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(e){}drawProj();
 SK.name=name;SK.lanes=s.lanes.map(l=>({...l,i:byPath.get(l.path),buf:null,state:'loading'})).filter(l=>l.i!=null);
 const miss=s.lanes.length-SK.lanes.length;if(miss)toast(`${miss} lane${miss>1?'s are':' is'} newer than this page: run "digitalcrate build" and reload to hear the whole sketch`);SK.open=true;drawSK();drawProj();await Promise.all(SK.lanes.map(skLoad));drawSK();skPlay()}
document.addEventListener('click',async e=>{const kr=e.target.closest('[data-kitrack]');if(kr){e.stopPropagation();const k=D.kits[+kr.dataset.kitrack];kr.textContent='building…';
  try{const r=await api('api/export',{scope:'paths',paths:kitMembers(k).map(i=>S[i][F.path]),name:k.name,rack:true,reveal:true});kr.textContent=`rack ✓ (${r.count})`}catch(err){kr.textContent='error'}return}
 const ks=e.target.closest('[data-kitsk]');if(ks){e.stopPropagation();const k=D.kits[+ks.dataset.kitsk];skStop();SK.lanes=[];SK.name=k.name;
  // a kit was built around one key and tempo (they're in its name): use those, not whatever the project was last set to
  const m=k.name.match(/_(\d{1,2}[AB])-[^_]*_(\d+)bpm/);if(m){PROJ.key=keyFromCam(m[1].replace(/^0/,''));if(!(PROJ.link&&LINK.peers))PROJ.bpm=+m[2];
   try{localStorage.setItem('atlasProj',JSON.stringify(PROJ))}catch(err){}drawProj();toast(`sketch set to ${PROJ.key} · ${PROJ.bpm} bpm, from the kit`)}
  for(const i of kitMembers(k))await skAdd(i);skPlay();return}
 const a=e.target.closest('[data-sk]');if(a){e.stopPropagation();e.preventDefault();skAdd(+a.dataset.sk)}},true);

// ================= detail panel: ＋ sketch · pads · MIDI · project info =================
const _select=select;
select=function(i,from){_select(i,from);augment(i)};
function augment(i){const eo=$('edopen');if(!eo)return;eo.parentNode.style.flexWrap='wrap';
 eo.insertAdjacentHTML('afterend',` <button data-sk="${i}" title="add to the sketchpad">＋ sketch</button><button id="padsopen" title="play its syllables / notes from the keyboard, record a pattern">🎹 pads</button>${S[i][F.cat]!=='Percussion'&&S[i][F.cam]?'<button id="midiopen" title="notes & chords → MIDI">♪ MIDI</button>':''}`);
 eo.parentNode.insertAdjacentHTML('afterend','<div class="sub" id="pjinfo" style="margin:-4px 0 8px"></div>');
 $('editor').insertAdjacentHTML('afterend','<div class="ed" id="pads" hidden></div><div class="ed" id="midibox" hidden></div>');
 document.querySelectorAll('#detail [data-pair]').forEach(b=>b.insertAdjacentHTML('beforebegin',`<button data-sk="${b.dataset.pair}" title="add to the sketchpad">＋</button><button data-savepair="${b.dataset.pair}" title="save this pair as a sketch (Kits tab), ready to open or export as aligned stems">💾</button>`));
 if(PROJ.key||PROJ.bpm)projInfo(i);if(PADS.i!==i)padsClose()}
$('detail').addEventListener('click',async e=>{const sp=e.target.closest('[data-savepair]');if(sp){e.stopPropagation();const j=+sp.dataset.savepair;
  try{const r=await api('api/pair/save',{src:S[st.sel][F.path],partner:S[j][F.path]});sp.textContent='✓';toast(`saved “${r.name}” · open it from the Kits tab`)}catch(err){toast('error: '+err.message)}return}
 if(e.target.id==='padsopen'){openPads(st.sel);return}if(e.target.id==='midiopen'){openMidi(st.sel);return}});

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
