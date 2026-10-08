/* Startups tab (2026-09-23): the Boston startup scene as its own screen, same shape as the Inbox
   (list on the left, one company open on the right), with its own map. Reads `startups` (engine-written,
   engine/startups.py) and `startup_verdicts` (written here: Interesting / Watch / Pass, flag, note).
   Loaded after index.html's main script; the five hooks there (load, realtime, nav, routing, maps) call in. */
let STARTUPS=[],byS={},SSUM={},sstate={};
function sv(id){return sstate[id]||(sstate[id]={v:"",note:"",flag:false,ts:""});}
function applySVerdict(x){const s=sv(x.id);if(tsNum(x.ts)>tsNum(s.ts))Object.assign(s,{v:x.v||"",note:x.note||"",flag:!!x.flag,ts:x.ts});}
function loadStartups(rows,meta,verdicts){STARTUPS=(rows||[]).map(r=>r.payload);byS={};STARTUPS.forEach(s=>byS[s.id]=s);SSUM=meta||{};sstate={};(verdicts||[]).forEach(applySVerdict);}
const svOf=s=>(sv(s.id).v||"").toLowerCase();
const STAGE_L={later:"Later",growth:"Growth",early:"Early",public:"Public"};
const TIER_L={look:"High",watch:"Mid",skip:"Low"}; /* engine pre-score bands (9+, 5 to 8, under 5); never the same words as the owner's call */
const STATUS_L={none:"To vet",interesting:"Interesting",watch:"Watch",pass:"Pass"};
const money=n=>!n?"":n>=1e9?"$"+(n/1e9).toFixed(1)+"B":"$"+Math.round(n/1e6)+"M";
const roundL=r=>(r||"").replace(/_/g," ").replace("series d plus","Series D+").replace(/\b\w/g,c=>c.toUpperCase());
/* Markdown links in the research cells ("[jobs](https://...)") become real links; everything else is escaped. */
function md(s){return esc(s).replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');}

/* ---------- filters (kept per browser) ---------- */
const SF_KEY="startups.filters.v3"; /* v3 (2026-09-23 night): a fresh key because the Map tab's chips briefly wrote into this state and left the review list filtered; v2 opened on To vet, the inbox */
let SF={stage:[],tag:[],tier:[],v:[],vert:"",theme:"",seat:false,path:false,research:false,q:""};
try{Object.assign(SF,JSON.parse(localStorage.getItem(SF_KEY)||"{}"));}catch(e){}
SF.seat=SF.path=SF.research=false;SF.v=[];SF.vert=SF.vert||"";SF.theme=SF.theme||""; /* Review is the unvetted only since 2026-09-25: no Call filter */
SF.tag=(SF.tag||[]).filter(k=>k==="AI"||k==="Applied AI"); /* retired filters (2026-09-24) must not stay on from a saved state */
function saveSF(){try{localStorage.setItem(SF_KEY,JSON.stringify(SF));}catch(e){}}
function sfToggle(spec){const [k,val]=spec.split(":");
  if(k==="seat"||k==="path"||k==="research"){SF[k]=!SF[k];}
  else{const i=SF[k].indexOf(val);if(i>=0)SF[k].splice(i,1);else SF[k].push(val);}
  saveSF();}
function sfPass(s,F){F=(F&&F.stage)?F:SF;const v=svOf(s); /* F may be a filter index when called through Array.filter: fall back to the tab's state (this broke the tab on 2026-09-23) */
  if(F.stage.length&&!F.stage.includes(s.stage))return false;
  if(F.tag.length&&!F.tag.includes(s.tag||""))return false;
  if(F.tier.length&&!F.tier.includes(s.screen.tier))return false;
  if(F.vert&&(s.vertical||"")!==F.vert)return false;
  if(F.theme&&(s.theme||"")!==F.theme)return false;
  if(F.v.length&&!F.v.includes(v||"none"))return false;
  if(F.seat&&!s.seat_posted)return false;
  if(F.path&&!((s.first_degree||[]).length||(s.research&&s.research.path)))return false;
  if(F.research&&!s.research)return false;
  if(F.q){const q=F.q.toLowerCase();const hay=[s.name,s.one_liner,s.description,s.hq,s.industry,(s.research||{}).what,(s.research||{}).sector].join(" ").toLowerCase();if(!hay.includes(q))return false;}
  return true;}
const bySScore=(a,b)=>(b.screen.score-a.screen.score)||a.name.localeCompare(b.name);

/* ---------- pieces ---------- */
/* Each company opens in the tab where it now lives (the owner, 2026-09-25): To vet on Review, kept on the Watchlist, passed on Passed startups. */
function sHref(s){const v=svOf(s);return v==="pass"?"#screened-startups/"+s.id:v==="interesting"||v==="watch"?"#watchlist/"+s.id:"#startups/"+s.id;}
function sChip(s){const v=svOf(s);if(v==="interesting")return'<span class="chip pursue">Interesting</span>';if(v==="watch")return'<span class="chip maybe">Watch</span>';if(v==="pass")return'<span class="chip pass">Pass</span>';
  return`<span class="chip${s.screen.tier==="look"?" look":""}">To vet</span>`;}
function sMeta(s){return[STAGE_L[s.stage]||s.stage,s.tag,s.hq,s.people?s.people+" people":"",s.round_type?roundL(s.round_type)+(s.round_date?" "+s.round_date.slice(0,7):""):""].filter(Boolean).map(esc).join(" · ");}
function sRow(s,sel){const cls=s.screen.score>=8?"hi":s.screen.tier==="watch"?"":"";const st=sv(s.id);
  return`<div class="lr ${cls}${sel?" on":""}" data-ssel="${s.id}"><div class="mono n">${s.screen.score}</div><div class="b"><div class="t">${esc(s.name)}</div><div class="m">${sMeta(s)}</div><div class="c">${sChip(s)}${s.seat_posted?'<span class="chip new">Seat posted</span>':""}${(s.first_degree||[]).length?'<span class="chip hp-reach">1st degree</span>':""}${(s.board_rows||[]).length?`<span class="chip">On board ${s.board_rows.length}</span>`:""}${st.flag?ICON.flagOn:""}</div></div></div>`;}
function sCounts(){const all=STARTUPS;const v=k=>all.filter(s=>svOf(s)===k).length;
  return{all:all.length,interesting:v("interesting"),watch:v("watch"),pass:v("pass"),unscreened:all.filter(s=>!svOf(s)).length,look:all.filter(s=>!svOf(s)&&s.screen.tier==="look").length,seats:all.filter(s=>s.seat_posted).length,pinned:all.filter(s=>s.office&&s.office.lat!=null).length};}
/* Stat tiles (the owner, 2026-09-24): how the vetting stands; a tile shows just that call. */
function sTiles(){const c=sCounts();const vetted=c.interesting+c.watch+c.pass;const pct=c.all?Math.round(100*vetted/c.all):0;
  const one=SF.v.length===1?SF.v[0]:"";
  const tile=(k,l,n,sub)=>`<button class="stile${one===k?" on":""}" data-sft="${k}"><span class="stl">${l}</span><span class="mono stn">${n}</span>${sub?`<span class="sts">${sub}</span>`:""}</button>`;
  return`<div class="stiles">${tile("none","To vet",c.unscreened,`${vetted} of ${c.all} vetted · ${pct}%`)}${tile("interesting","Interesting",c.interesting)}${tile("watch","Watch",c.watch)}${tile("pass","Passed",c.pass)}</div>
    <div class="sprog"><div style="width:${pct}%"></div></div>`;}
/* Sector (who buys) and theme (what it does) are Claude's sort from lenses.json; a select each, counts over the unvetted. */
function sSel(k,l,f){const m={};STARTUPS.filter(s=>!svOf(s)).forEach(s=>{const x=f(s);if(x)m[x]=(m[x]||0)+1;});
  return`<label class="ssel"><span class="hint">${l}</span><select data-sfsel="${k}"><option value="">All</option>${Object.entries(m).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])).map(([x,n])=>`<option value="${esc(x)}"${SF[k]===x?" selected":""}>${esc(x)} (${n})</option>`).join("")}</select></label>`;}
function sFilterBar(all,c){const chip=(spec,l,on,n)=>`<button class="pill${on?" on":""}" data-sf="${spec}">${l} <span class="mono">${n}</span></button>`;
  const cnt=f=>STARTUPS.filter(s=>!svOf(s)&&f(s)).length;const sep='<span class="sep"></span>';
  return`<div class="sfbar"><div class="shd"><h2>Startup Review</h2><span class="hint">${all.length} of ${c.unscreened} to vet · MGMT ${esc(SSUM.asof||"")}</span></div>
   <span class="hint">Stage</span>${["later","growth","early","public"].map(k=>chip("stage:"+k,STAGE_L[k],SF.stage.includes(k),cnt(s=>s.stage===k))).join("")}${sep}
   <span class="hint">Tag</span>${["AI","Applied AI"].map(k=>chip("tag:"+k,k,SF.tag.includes(k),cnt(s=>(s.tag||"")===k))).join("")}${sep}
   <span class="hint">Score</span>${["look","watch","skip"].map(k=>chip("tier:"+k,TIER_L[k],SF.tier.includes(k),cnt(s=>s.screen.tier===k))).join("")}${sep}
   ${sSel("vert","Sector",s=>s.vertical)}${sSel("theme","Theme",s=>s.theme)}${sep}
   <input data-sq="1" value="${esc(SF.q)}" placeholder="Search"><a class="pill lnk" href="#startups/map">Map</a></div>`;}
function sFilters(){const chip=(spec,l,on,n)=>`<button class="pill${on?" on":""}" data-sf="${spec}">${l}${n!=null?` <span class="mono">${n}</span>`:""}</button>`;
  const cnt=f=>STARTUPS.filter(s=>!svOf(s)&&f(s)).length; /* counts over the review queue */
  return`<div class="mapf"><span class="hint">Stage</span>${["later","growth","early","public"].map(k=>chip("stage:"+k,STAGE_L[k],SF.stage.includes(k),cnt(s=>s.stage===k))).join("")}<span class="sep"></span><span class="hint">Tag</span>${["AI","Applied AI"].map(k=>chip("tag:"+k,k,SF.tag.includes(k),cnt(s=>(s.tag||"")===k))).join("")}</div>
   <div class="mapf"><span class="hint">Score</span>${["look","watch","skip"].map(k=>chip("tier:"+k,TIER_L[k],SF.tier.includes(k),cnt(s=>s.screen.tier===k))).join("")}</div>
   <div class="mapf">${sSel("vert","Sector",s=>s.vertical)}${sSel("theme","Theme",s=>s.theme)}</div>
   <div class="mapf"><input data-sq="1" value="${esc(SF.q)}" placeholder="Search name, what they do, sector" style="max-width:360px"><a class="pill lnk" href="#startups/map">Map</a></div>`;}

function sControls(s){const st=sv(s.id);const v=st.v;
  return`<div class="ctl" data-sctl="${s.id}">
   <div class="vb"><button class="pursue${v==="Interesting"?" on":""}" data-sv="Interesting" data-id="${s.id}">Interesting</button><button class="maybe${v==="Watch"?" on":""}" data-sv="Watch" data-id="${s.id}">Watch</button><button class="${v==="Pass"?"on":""}" data-sv="Pass" data-id="${s.id}">Pass</button><button class="flag${st.flag?" on":""}" data-sflag="${s.id}" title="Excited about this one">${st.flag?ICON.flagOn:ICON.flag}</button></div>
   <div class="notewrap"><textarea data-snote="${s.id}" rows="1" placeholder="Why, or what to check next; Enter saves">${esc(st.note)}</textarea><span class="saved" data-saved="s:${s.id}" hidden></span></div>
   <div class="hint">${v?`Saved as ${esc(v)}${st.ts?" · "+fmtDate(st.ts):""}`:"Interesting means worth diligence or a founder conversation; Watch parks it for the Monday post; Pass hides it from the screen."}</div></div>`;}

/* The call (the owner, 2026-09-25): open controls while To vet or while editing; once made, read-only with Edit thoughts and Back to review. */
const SEDIT=new Set();
function sCallBlock(s){const st=sv(s.id);
  if(!st.v||SEDIT.has(s.id))return`<div class="dcall" id="sdecide"><h4>YOUR CALL${SEDIT.has(s.id)?` <button class="quiet" data-sedit="${s.id}" data-off="1">Done editing</button>`:""}</h4>${sControls(s)}</div>`;
  const cls=st.v==="Interesting"?"pursue":st.v==="Watch"?"maybe":"pass";
  return`<div class="dread"><h4>YOUR CALL</h4><div class="dr-row"><span class="chip ${cls}">${esc(st.v)}</span>${st.flag?ICON.flagOn:""}${st.ts?`<span class="hint mono">${esc(fmtDate(st.ts.slice(0,10)))}</span>`:""}
   <span class="dr-act"><button data-sedit="${s.id}">Edit thoughts</button>${st.v==="Pass"?`<button data-swatch="${s.id}">Move to Watchlist</button>`:`<button data-sreopen="${s.id}">Back to review</button>`}</span></div>
   <p class="dr-note">${viewText("startups",s.id,st.note)}</p></div>`;}
/* The fuller profile (the owner, 2026-09-25: the Watchlist profile "should go beyond the review profile"): why it is kept
   (Claude's theme, vertical, the theses it sits in and the look-again trigger), then everything the vault holds on it,
   the /diligence folder in tabs (brief first) and the company card. Engine: startups.py profile_extras. */
const DTAB={};
function sWhyKept(s){const v=svOf(s);if(v!=="interesting"&&v!=="watch")return"";
  const th=(SSUM.theses||[]).filter(t=>(t.members||[]).includes(s.id));
  return`<div class="sec card sp-why"><h4>Why it is on the watchlist</h4>
   <div class="sp-tags">${s.theme?`<span class="chip wl-tag">${esc(s.theme)}</span>`:""}${s.vertical?`<span class="chip">${esc(s.vertical)}</span>`:""}</div>
   ${th.map(t=>`<div class="sp-th"><b>${esc(t.title)}</b> <span class="chip pursue">${esc(t.kind||"")}</span><div class="hint" style="margin-top:3px">${esc(t.why||"")}</div></div>`).join("")||'<div class="hint">Not in a thesis yet; Claude places it at the next sort.</div>'}
   ${s.look_again?`<div class="sp-look"><span class="nw-lab">Look again when</span><span>${esc(s.look_again)}</span></div>`:""}</div>`;}
function sDeep(s){const d=s.diligence;
  const dil=d&&d.files&&d.files.length?(()=>{const k=DTAB[s.id]&&d.files.find(f=>f.k===DTAB[s.id])?DTAB[s.id]:d.files[0].k;const f=d.files.find(x=>x.k===k);
    return`<div class="sec card sp-dil"><div class="sp-dh"><h4>Diligence</h4><span class="hint">${esc(d.mode==="quick"?"quick pass":"full run")}${d.date?" · "+esc(fmtDate(d.date)):""} · ${esc(d.folder)}</span></div>
     <div class="scr-tabs">${d.files.map(x=>`<button class="pill${x.k===k?" on":""}" data-dtab="${s.id}:${x.k}">${esc(x.l)}</button>`).join("")}</div><div class="doc sp-doc">${f.html}</div></div>`;})()
    :`<div class="sec card dash"><h4>Diligence</h4>No research folder yet. A quick pass (/diligence quick) fills funding, people, news and paths in.</div>`;
  const card=s.card_html?`<details class="sec card sp-card"><summary><h4 style="display:inline">Company card</h4> <span class="hint">${esc(s.vault_card||"")}.md</span></summary><div class="doc">${s.card_html}</div></details>`:"";
  return`<div class="sp-more">${dil}${card}</div>`;}
function sDetail(id,opts){opts=opts||{};const s=byS[id];if(!s)return'<div class="emptybig"><b>Not on the board</b><span>This company is not in the current build.</span></div>';const r=s.research||{};const o=s.office||{};const st=sv(id);
  const links=[s.website?`<a class="post" href="${esc(s.website)}" target="_blank" rel="noopener">${esc(s.website.replace(/^https?:\/\/(www\.)?/,"").replace(/\/$/,""))} <span aria-hidden="true">↗</span></a>`:"",s.careers?`<a href="${esc(s.careers)}" target="_blank" rel="noopener">careers</a>`:"",s.mgmt?`<a href="${esc(s.mgmt)}" target="_blank" rel="noopener">MGMT profile</a>`:"",s.linkedin?`<a href="${esc(s.linkedin)}" target="_blank" rel="noopener">LinkedIn</a>`:"",s.lantern?`<a href="${esc(s.lantern)}" target="_blank" rel="noopener">The Lantern</a>`:""].filter(Boolean).join("<span> </span>");
  const facts=[STAGE_L[s.stage]||s.stage,s.tag,s.hq?esc(s.hq)+(s.expansion?" office"+(s.expansion_origin?" (HQ "+esc(s.expansion_origin)+")":""):" HQ"):"",s.founded?"founded "+s.founded:"",s.people?`<span class="mono">${esc(s.people)}</span> people`:"",s.raised?money(s.raised)+" raised":"",s.round_type?roundL(s.round_type)+(s.round_date?" "+s.round_date.slice(0,7):""):"",s.open_roles!=null?`<span class="mono">${s.open_roles}</span> open roles (MGMT)`:"",s.workplace?esc(s.workplace):""].filter(Boolean).join("<span> </span>");
  const pin=o.lat!=null?`<div class="sec card"><h4>Office</h4><div class="mapmini" data-map="s:${s.id}" data-lat="${o.lat}" data-lng="${o.lng}" data-z="${o.precision==="street"?15:12}" style="height:180px;border-radius:8px;overflow:hidden"></div><div style="margin-top:6px;color:var(--muted)">${esc(o.address||"")}${o.precision!=="street"||o.fallback?" (city-level)":""}</div></div>`:`<div class="sec card"><h4>Office</h4><span style="color:var(--faint)">${o.address?esc(o.address)+", not on the map yet":"No address known"}</span></div>`;
  return`<div class="detail">${opts.pane?"":`<div class="crumb"><a href="${(opts.crumb||["#startups"])[0]}">${esc((opts.crumb||[0,"Startup Review"])[1])}</a> <i>/</i> ${esc(s.name)}</div>`}
   <div class="dh"><div class="score"><div class="mono n">${s.screen.score}</div><div class="k">SCREEN</div></div>
    <div class="hb"><div class="tl"><span class="t" style="cursor:default">${esc(s.name)}</span>${st.flag?ICON.flagOn:""}${sChip(s)}${s.seat_posted?'<span class="chip new">Seat posted</span>':""}</div><div class="meta">${links}</div><div class="meta">${facts}</div>${s.one_liner?`<div class="why"><i style="background:var(--ghost)"></i><span>${esc(s.one_liner)}</span></div>`:""}</div>
    <div class="st">${st.v?`<span class="chip ${st.v==="Interesting"?"pursue":st.v==="Watch"?"maybe":"pass"}">${esc(st.v)}</span>`:'<span class="chip">To vet</span>'}${opts.pane?sPaneNav(s,opts):""}</div></div>
   ${sCallBlock(s)}
   ${opts.pane?"":sWhyKept(s)}
   <div class="dbody"><div class="dcol">
    <div class="sec"><h4>What they do</h4>${r.what?`<div>${md(r.what)}</div>`:""}${s.description?`<div style="color:var(--text2);margin-top:${r.what?"6px":"0"}">${esc(s.description)}</div>`:(r.what?"":'<span style="color:var(--faint)">MGMT has no description.</span>')}${s.industry?`<div style="margin-top:4px;color:var(--muted)">${esc(s.industry)}${r.sector?" · "+esc(r.sector):""}</div>`:""}</div>
    <div class="sec"><h4>Why it fits</h4>${r.fit?`<div class="why"><i></i><span>${md(r.fit)}</span></div>`:s.research?'<span style="color:var(--faint)">No fit written: the research pass found no angle.</span>':'<span style="color:var(--faint)">Not researched yet. Say "profile '+esc(s.name)+'" in #job-search.</span>'}${s.left_out?`<div class="why mis"><i></i><span>Left out of the tables: ${md(s.left_out)}</span></div>`:""}</div>
    <div class="sec card"><h4>Open roles on the archetype</h4>${r.roles?`<div>${md(r.roles)}</div>`:'<span style="color:var(--faint)">Not checked.</span>'}${(s.board_rows||[]).length?`<div class="kv" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border2)">${s.board_rows.map(b=>`<span class="mono">${b.score??""}</span><span><a href="#job/${esc(b.id)}">${esc(b.title)}</a>${b.verdict?` <span class="chip ${b.verdict}">${cap(b.verdict)}</span>`:' <span class="chip">To review</span>'}</span>`).join("")}</div>`:""}</div>
    <div class="sec card"><h4>Path in</h4>${(s.first_degree||[]).length?s.first_degree.map(x=>`<div class="li"><span class="path yes"><i></i></span><span><b style="font-weight:500">${esc(x.name)}</b>${x.title?", "+esc(x.title):""}</span></div>`).join(""):""}${r.path?`<div>${md(r.path)}</div>`:(s.first_degree||[]).length?"":'<span style="color:var(--faint)">No path found yet.</span>'}${s.investors&&s.investors.length?`<div style="margin-top:6px;color:var(--muted)">Investors: ${esc(s.investors.join(", "))}</div>`:""}${s.customers?`<div style="color:var(--muted)">Local customers: ${esc(s.customers)}</div>`:""}</div>
   </div><div class="dcol">
    ${pin}
    <div class="sec"><h4>Screen ${s.screen.score}</h4><div class="mono card" style="font-size:var(--fs-sm);padding:8px 10px">${esc(s.screen.math)}</div><div class="hint" style="margin-top:4px">A deterministic first sort (High 9+, Mid 5 to 8, Low under 5), not the rubric. Your call above is the screen.</div></div>
    ${r.board||s.vault_card?`<div class="sec card"><h4>In the vault</h4>${r.board?`<div>${md(r.board)}</div>`:""}${s.vault_card?`<div style="color:var(--muted)">${esc(s.vault_card)}.md</div>`:""}</div>`:""}
    ${r.stage_text?`<div class="sec card"><h4>Stage, as researched</h4><div>${md(r.stage_text)}</div></div>`:""}
   </div></div>${opts.pane&&!s.diligence?"":sDeep(s)}</div>`;}
function sPaneNav(s,opts){const ids=opts.order||[];const i=ids.indexOf(s.id);const p=ids[i-1],n=ids[i+1];
  return`<span class="hint">${i>=0?`<span class="mono">${i+1}</span> of <span class="mono">${ids.length}</span>`:""}${p?` · <a href="#startups/${p}">previous</a>`:""}${n?` · <a href="#startups/${n}">next</a>`:""}</span>`;}

/* ---------- views ---------- */
function startupsPool(){return STARTUPS.filter(s=>!svOf(s)&&sfPass(s)).sort(bySScore);} /* the review queue: no call yet (the owner, 2026-09-25) */
function viewStartups(arg){if(arg==="map")return viewStartupMap();
  const all=startupsPool();const c=sCounts();
  if(!SPLIT.matches){if(arg&&byS[arg])return sDetail(arg,{});
    return`<div class="sh"><h2>Startup Review <span>${all.length} of ${c.unscreened} to vet</span></h2><div class="hint">MGMT ${esc(SSUM.asof||"")}</div></div>${sFilters()}<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden">${all.map(s=>sRow(s,false)).join("")||'<div class="empty">Nothing matches these filters</div>'}</div>`;}
  const sel=arg&&byS[arg]?arg:all.length?all[0].id:null;
  const list=all.length?all.map(s=>sRow(s,s.id===sel)).join(""):'<div class="emptybig" style="margin:14px"><b>Nothing matches</b><span>Loosen a filter on the left.</span></div>';
  const pane=sel?sDetail(sel,{pane:true,order:all.map(s=>s.id)}):'<div class="emptybig" style="margin:32px"><b>Nothing selected</b><span>Pick a company on the left.</span></div>';
  return`${sFilterBar(all,c)}<div class="split" style="grid-template-columns:420px minmax(0,1fr)"><div class="lcol">${list}</div><div class="pane">${pane}</div></div>`;}

let SMAPS=[];
function viewStartupMap(){const all=startupsPool();const pinned=all.filter(s=>s.office&&s.office.lat!=null);SMAPS=pinned;const c=sCounts();
  const mr=s=>`<div class="mr" data-spin="${s.id}"><b><i class="${svOf(s)==="interesting"?"":svOf(s)==="watch"?"maybe":"none"}" style="${svOf(s)?"":"background:var(--ghost)"}"></i>${esc(s.name)}</b><span>${sMeta(s)} · <span class="mono">${s.screen.score}</span></span></div>`;
  return`<div class="sh"><h2>Startups on the map <span>${pinned.length} pinned · ${all.length-pinned.length} without an address</span></h2><div class="hint"><a href="#startups">‹ Back to the list</a></div></div>
   ${sFilters().replace('href="#startups/map"','href="#startups"').replace(">Map</a>",">List</a>")}
   <div class="mapgrid"><div class="mapwrap"><div class="bigmap" data-map="smap"></div></div><div class="mapside">${pinned.length?pinned.map(mr).join(""):'<div class="empty" style="margin:12px">No pinned companies match</div>'}</div></div>`;}
let SPINS={};
function sPinEl(arr){const el=document.createElement("div");el.className="mk";const n=arr.length;const v=arr.map(svOf);
  const col=v.includes("interesting")?"var(--accent)":v.includes("watch")?"var(--amber)":arr.some(s=>s.screen.tier==="look")?"var(--green)":"var(--ghost)";
  el.innerHTML=`<div class="mk-dot${n>1?" n":""}${arr.some(s=>sv(s.id).flag)?" f":""}" style="--c:${col}">${n>1?n:""}</div>`;return el;}
function sPreview(arr){return`<div class="hc">${arr.map(s=>`<div class="hj"><div class="co">${esc(s.name)}</div><div class="role"><span class="t">${esc(s.one_liner||"")}</span><div class="m"><span class="mono">${s.screen.score}</span>${sChip(s)}</div></div></div>`).join("")}<div class="addr">${esc(arr[0].office.address||"")}</div><div class="go">${arr.length>1?"Click to choose":"Click to open"}</div></div>`;}
function mountStartupMaps(){if(!window.maplibregl)return;
  view.querySelectorAll('[data-map^="s:"]').forEach(el=>{const lat=+el.dataset.lat,lng=+el.dataset.lng;const s=byS[el.dataset.map.slice(2)];
    const m=baseMap(el,el.dataset.map,lat+","+lng,{center:[lng,lat],zoom:+el.dataset.z||15});
    new maplibregl.Marker({element:sPinEl(s?[s]:[]),anchor:"center"}).setLngLat([lng,lat]).addTo(m);});
  const el=view.querySelector('[data-map="smap"]');if(!el)return;
  const m=BIG=baseMap(el,"smap","smap",{bounds:CORE});const groups={};SPINS={};
  SMAPS.forEach(s=>{const o=s.office;const k=o.lat.toFixed(5)+","+o.lng.toFixed(5);(groups[k]=groups[k]||[]).push(s);});
  const hover=new maplibregl.Popup({closeButton:false,closeOnClick:false,offset:18,maxWidth:"300px",className:"hover"});
  Object.values(groups).forEach(arr=>{const o=arr[0].office;const ll=[o.lng,o.lat];const node=sPinEl(arr);
    const mk=new maplibregl.Marker({element:node,anchor:"center"}).setLngLat(ll).addTo(m);
    node.addEventListener("mouseenter",()=>{if(HOVER.matches)hover.setLngLat(ll).setHTML(sPreview(arr)).addTo(m);});
    node.addEventListener("mouseleave",()=>hover.remove());
    node.addEventListener("click",e=>{e.stopPropagation();hover.remove();if(arr.length===1){location.hash="#startups/"+arr[0].id;return;}
      new maplibregl.Popup({offset:18,maxWidth:"300px",className:"hover"}).setLngLat(ll).setHTML(`<div class="hc">${arr.map(s=>`<div class="hj"><div class="co"><a href="#startups/${esc(s.id)}">${esc(s.name)}</a></div></div>`).join("")}</div>`).addTo(m);});
    arr.forEach(s=>{SPINS[s.id]=mk;});});}
function sFlyTo(id){const mk=SPINS[id];if(!BIG||!mk)return;if(!SPLIT.matches)BIG.getContainer().scrollIntoView({behavior:"smooth",block:"start"});BIG.flyTo({center:mk.getLngLat(),zoom:Math.max(BIG.getZoom(),14),duration:600});}

/* ---------- writes ---------- */
async function writeSVerdict(id,patch){const s=sv(id);Object.assign(s,patch);const ts=nowIso();s.ts=ts;const c=byS[id];
  const {error}=await sb.from("startup_verdicts").upsert({id,v:s.v,note:s.note,flag:!!s.flag,ts,name:c?c.name:null});
  if(error){setSync("err","write failed");toast("Not saved: "+error.message);markSaved("s:"+id,false);return false;}
  setSync("on","saved "+new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}));markSaved("s:"+id,true);return true;}
function sNext(id){const ids=[...view.querySelectorAll("[data-ssel]")].map(e=>e.dataset.ssel);const i=ids.indexOf(id);return ids[i+1]||null;}

/* ---------- interactions (its own listeners; the main handler ignores these attributes) ---------- */
view.addEventListener("change",e=>{const t=e.target;if(t.matches("select[data-sfsel]")){SF[t.dataset.sfsel]=t.value;saveSF();paint();}});
view.addEventListener("click",async e=>{const t=e.target.closest("[data-ssel],[data-sv],[data-sflag],[data-sf],[data-spin],[data-sft],[data-sedit],[data-sreopen],[data-swatch],[data-dtab]");if(!t)return;
  if(t.dataset.dtab){const [id,k]=t.dataset.dtab.split(":");DTAB[id]=k;const y=window.scrollY;render();window.scrollTo(0,y);return;}
  if(t.dataset.swatch){const id=t.dataset.swatch;if(!await writeSVerdict(id,{v:"Watch"}))return;SEDIT.delete(id);toast("Moved to the Watchlist");render();return;}
  if(t.dataset.sedit){const id=t.dataset.sedit;if(t.dataset.off)SEDIT.delete(id);else SEDIT.add(id);render();return;}
  if(t.dataset.sreopen){const id=t.dataset.sreopen;if(t.dataset.armed!=="1"){t.dataset.armed="1";t.textContent="Confirm: back to review";setTimeout(()=>{if(t.isConnected){t.dataset.armed="";t.textContent="Back to review";}},4000);return;}
    if(!await writeSVerdict(id,{v:""}))return;SEDIT.delete(id);toast("Back in Startup Review; your note is kept");render();return;}
  if(t.dataset.sft){const k=t.dataset.sft;SF.v=(SF.v.length===1&&SF.v[0]===k)?[]:[k];saveSF();paint();return;}
  if(t.dataset.sf){sfToggle(t.dataset.sf);paint();return;}
  if(t.dataset.spin){sFlyTo(t.dataset.spin);return;}
  if(t.dataset.ssel){location.hash="#startups/"+t.dataset.ssel;return;}
  if(t.dataset.sflag){const id=t.dataset.sflag;await writeSVerdict(id,{flag:!sv(id).flag});render();return;}
  if(t.dataset.sv){const id=t.dataset.id;const v=sv(id).v===t.dataset.sv?"":t.dataset.sv;const note=view.querySelector(`textarea[data-snote="${CSS.escape(id)}"]`);
    if(!await writeSVerdict(id,{v,note:note?note.value:sv(id).note}))return;
    toast(v==="Interesting"?"Interesting. Kept on the screen.":v==="Watch"?"Watch. The Monday post tracks it.":v==="Pass"?"Pass.":"Verdict cleared");
    SEDIT.delete(id);const {r}=route();const n=v&&SPLIT.matches&&r==="startups"?sNext(id):null;if(n)location.hash="#startups/"+n;else if(v&&r==="startups"&&!SPLIT.matches)location.hash="#startups";else render();return;}});
const sTimers={};
view.addEventListener("input",e=>{const t=e.target;if(t.matches("textarea[data-snote]")){autoGrow(t);const id=t.dataset.snote;clearTimeout(sTimers[id]);sTimers[id]=setTimeout(()=>{if(sv(id).note!==t.value)writeSVerdict(id,{note:t.value});},1200);}
  if(t.matches("input[data-sq]")){SF.q=t.value;saveSF();clearTimeout(sTimers.q);sTimers.q=setTimeout(()=>{const lc=view.querySelector(".lcol");const y=lc?lc.scrollTop:0;paint();const lc2=view.querySelector(".lcol");if(lc2)lc2.scrollTop=y;const q=view.querySelector("input[data-sq]");if(q){q.focus();q.setSelectionRange(q.value.length,q.value.length);}},350);}});
view.addEventListener("keydown",e=>{const t=e.target;if(e.key!=="Enter"||e.shiftKey)return;if(t.matches("textarea[data-snote]")){e.preventDefault();const id=t.dataset.snote;clearTimeout(sTimers[id]);writeSVerdict(id,{note:t.value});t.blur();}});
view.addEventListener("focusout",e=>{const t=e.target;if(t.matches("textarea[data-snote]")){const id=t.dataset.snote;clearTimeout(sTimers[id]);if(sv(id).note!==t.value)writeSVerdict(id,{note:t.value});}});

/* ---------- the board's Map tab: a startups layer (2026-09-23) ----------
   Settled with the owner the same night after five renderings and five dot styles were tried on the page: dots only, every dot the
   role pins' size, colour by his call and nothing else. Interesting green, Watch magenta (the two hues farthest from the roles'
   indigo and amber). To vet and Pass are never drawn (the owner, 22:57: "leave out the To vet firms"); the map shows only what he has called. The filters are the Startups tab's criteria but the Map's own state (MSF):
   a tap here never changes the review list over there. A company whose address is a city only (most of MGMT's records) is not
   drawn, it would sit on the centroid with everyone else; it is listed instead. */
const MSF_KEY="startups.map";
let MSF={on:true,v:["interesting","watch"],stage:[],tag:[],tier:[],seat:false,path:false,research:false,q:""};
try{const x=JSON.parse(localStorage.getItem(MSF_KEY)||"{}");delete x.mode;delete x.dot;delete x.last;Object.assign(MSF,x);MSF.v=MSF.v.filter(k=>k!=="none");if(!MSF.v.length)MSF.v=["interesting","watch"];}catch(e){}
MSF.seat=false; /* the Seat posted chip left the Map on 2026-09-24 (as on the Startups tab); a saved state must not keep filtering */
function saveMSF(){try{localStorage.setItem(MSF_KEY,JSON.stringify(MSF));}catch(e){}}
const startupsMapPool=()=>!MSF.on?[]:STARTUPS.filter(s=>s.office&&s.office.lat!=null&&svOf(s)&&svOf(s)!=="pass"&&sfPass(s,MSF)).sort(bySScore);
const sCityOnly=s=>!!(s.office.fallback||!/\d/.test(((s.office.address||"").split(",")[0])));
function sMapBand(){const pool=startupsMapPool();const all=STARTUPS.filter(s=>svOf(s)&&svOf(s)!=="pass");const cnt=f=>all.filter(f).length;const city=pool.filter(sCityOnly).length;
  const chip=(spec,l,on,n,cls)=>`<button class="pill su${cls?" "+cls:""}${on?" on":""}" data-msf="${spec}">${l} <span class="mono">${n}</span></button>`;
  if(!MSF.on)return`<div class="mapf suband"><span class="hint" style="text-transform:none;letter-spacing:0">Hidden. Click the header to show the startups.</span></div>`;
  return`<div class="mapf suband"><span class="hint">Call</span>${[["interesting","Interesting","c-int"],["watch","Watch","c-watch"]].map(([k,l,c])=>chip("v:"+k,l,MSF.v.includes(k),cnt(s=>(svOf(s)||"none")===k),c)).join("")}<span class="sep"></span><span class="hint">Score</span>${["look","watch","skip"].map(k=>chip("tier:"+k,TIER_L[k],MSF.tier.includes(k),cnt(s=>s.screen.tier===k))).join("")}<span class="sep"></span>${chip("path:1","Path in",MSF.path,cnt(s=>(s.first_degree||[]).length||(s.research&&s.research.path)))}${chip("research:1","Researched",MSF.research,cnt(s=>s.research))}</div>
   <div class="mapf suband"><span class="hint">Stage</span>${["later","growth","early","public"].map(k=>chip("stage:"+k,STAGE_L[k],MSF.stage.includes(k),cnt(s=>s.stage===k))).join("")}<span class="sep"></span><span class="hint">Tag</span>${["AI","Applied AI"].map(k=>chip("tag:"+k,k,MSF.tag.includes(k),cnt(s=>(s.tag||"")===k))).join("")}<span class="sep"></span><input data-msq="1" value="${esc(MSF.q)}" placeholder="Search startups" style="max-width:240px">${city?`<span class="hint" style="text-transform:none;letter-spacing:0">${city} have a city only, listed on the right</span>`:""}</div>`;}
function sMapSide(){const pool=startupsMapPool();if(!pool.length)return"";
  const byCall=(a,b)=>(["interesting","watch",""].indexOf(svOf(a))-["interesting","watch",""].indexOf(svOf(b)))||bySScore(a,b);
  const row=s=>`<div class="mr" data-spin="${s.id}"><b><i class="su ${svOf(s)||"none"}"></i>${esc(s.name)}</b><span>${esc(STATUS_L[svOf(s)||"none"])} \u00b7 <span class="mono">${s.screen.score}</span> ${esc(TIER_L[s.screen.tier])} \u00b7 ${esc(STAGE_L[s.stage]||s.stage||"")}${s.tag?" \u00b7 "+esc(s.tag):""}</span></div>`;
  const on=pool.filter(s=>!sCityOnly(s)).sort(byCall),city=pool.filter(sCityOnly).sort(byCall);
  return`${on.length?`<div class="day"><b>Startups</b><span>${on.length}</span></div>${on.map(row).join("")}`:""}${city.length?`<div class="day"><b>Startups, city only</b><span>${city.length}</span></div>${city.map(row).join("")}`:""}`;}
function sLayerEl(arr){const el=document.createElement("div");el.className="mk";const v=svOf(arr[0])||"none";el.innerHTML=`<div class="mk-su ${v}">${arr.length>1?`<b>${arr.length}</b>`:""}</div>`;return el;}
function mountStartupLayer(m){if(!m||!window.maplibregl||!MSF.on)return;const pool=startupsMapPool().filter(s=>!sCityOnly(s));SPINS={};
  const groups={};pool.forEach(s=>{const o=s.office;const k=o.lat.toFixed(5)+","+o.lng.toFixed(5);(groups[k]=groups[k]||[]).push(s);});
  const hover=new maplibregl.Popup({closeButton:false,closeOnClick:false,offset:14,maxWidth:"300px",className:"hover"});
  const chooser=(ll,arr)=>new maplibregl.Popup({offset:14,maxWidth:"300px",className:"hover"}).setLngLat(ll).setHTML(`<div class="hc">${arr.map(s=>`<div class="hj"><div class="co"><a href="${sHref(s)}">${esc(s.name)}</a></div><div class="role"><span class="t">${esc(s.one_liner||"")}</span><div class="m"><span class="mono">${s.screen.score}</span>${sChip(s)}</div></div></div>`).join("")}</div>`).addTo(m);
  Object.values(groups).forEach(arr=>{const o=arr[0].office;const ll=[o.lng,o.lat];const node=sLayerEl(arr);
    const mk=new maplibregl.Marker({element:node,anchor:"center"}).setLngLat(ll).addTo(m);
    node.addEventListener("mouseenter",()=>{if(HOVER.matches)hover.setLngLat(ll).setHTML(sPreview(arr)).addTo(m);});
    node.addEventListener("mouseleave",()=>hover.remove());
    node.addEventListener("click",e=>{e.stopPropagation();hover.remove();if(arr.length===1){location.hash=sHref(arr[0]);return;}chooser(ll,arr);});
    arr.forEach(s=>{SPINS[s.id]=mk;});});}
view.addEventListener("click",e=>{const t=e.target.closest("[data-msf],[data-slayer]");if(!t)return;
  if(t.dataset.slayer){MSF.on=!MSF.on;saveMSF();paint();return;}
  const [k,val]=t.dataset.msf.split(":");
  if(k==="seat"||k==="path"||k==="research")MSF[k]=!MSF[k];else{const i=MSF[k].indexOf(val);if(i>=0)MSF[k].splice(i,1);else MSF[k].push(val);}
  saveMSF();paint();});
view.addEventListener("input",e=>{const t=e.target;if(!t.matches("input[data-msq]"))return;MSF.q=t.value;saveMSF();clearTimeout(sTimers.__msq);sTimers.__msq=setTimeout(()=>{const pos=t.selectionStart;paint();const el=view.querySelector("input[data-msq]");if(el){el.focus();el.setSelectionRange(pos,pos);}},250);});

/* ---------- Startup Watchlist (2026-09-24, draft): the kept companies (Interesting and Watch) in two looks, Themes
   (a column per theme) and Theses (Claude's groupings with why each fits). the owner picked these two out of five the same
   night; table, look-again and landscape were dropped. Vertical (who buys), theme (what it does) and the theses come
   from the engine (vault research/boston-startups/lenses.json, Claude's sorting). Read-only: the call is still made
   on Startup Review. ---------- */
const WL_KEY="watchlist.layout";const WL_LAYOUTS=[["themes","Themes"],["theses","Theses"]];
let WL={layout:"themes"};try{Object.assign(WL,JSON.parse(localStorage.getItem(WL_KEY)||"{}"));}catch(e){}
function saveWL(){try{localStorage.setItem(WL_KEY,JSON.stringify(WL));}catch(e){}}
const kept=()=>STARTUPS.filter(s=>{const v=svOf(s);return v==="interesting"||v==="watch";});
const UNK="Not enough to tell";
const groupBy=(arr,f)=>{const m={};arr.forEach(s=>{const k=f(s)||UNK;(m[k]=m[k]||[]).push(s);});return Object.entries(m).sort((a,b)=>(a[0]===UNK)-(b[0]===UNK)||b[1].length-a[1].length||a[0].localeCompare(b[0]));};
const byKept=(a,b)=>(svOf(a)==="interesting"?0:1)-(svOf(b)==="interesting"?0:1)||(sv(b.id).flag?1:0)-(sv(a.id).flag?1:0)||a.name.localeCompare(b.name);
function wlName(s){return`<span><a href="${sHref(s)}"><b style="font-weight:500">${esc(s.name)}</b></a>${sv(s.id).flag?" "+ICON.flagOn:""}</span>`;} /* one span, so the flag sits by the name in a spaced row */
function wlRound(s){return s.round_type?roundL(s.round_type)+(s.round_date?" "+s.round_date.slice(0,7):""):"";}
function wlTag(t){return t?`<span class="chip wl-tag">${esc(t)}</span>`:"";}

function wlThemes(arr){return`<div class="wl-cols">${groupBy(arr,s=>s.theme).map(([k,xs])=>`<div class="wl-col"><div class="wl-ch">${esc(k)} <span class="mono">${xs.length}</span></div>${xs.sort(byKept).map(s=>`<div class="wl-card"><div class="wl-cn">${wlName(s)}${sChip(s)}</div><div class="wl-ol">${esc(s.one_liner||"")}</div><div class="wl-cm">${wlTag(s.vertical)}<span class="hint">${esc([STAGE_L[s.stage],wlRound(s)].filter(Boolean).join(" · "))}</span></div></div>`).join("")}</div>`).join("")}</div>`;}

function wlTheses(arr){const T=SSUM.theses||[];const ids=new Set(arr.map(s=>s.id));const placed=new Set();
  const cards=T.map(t=>{const xs=t.members.filter(id=>ids.has(id)).map(id=>byS[id]);xs.forEach(s=>placed.add(s.id));if(!xs.length)return"";
    return`<div class="sec card wl-th"><div class="wl-thh"><h3>${esc(t.title)}</h3><span class="chip pursue">${esc(t.kind)}</span></div><div class="why"><i></i><span>${esc(t.why)}</span></div>
     <div class="wl-thm">${xs.sort(byKept).map(s=>`<div class="wl-thr">${wlName(s)}${sChip(s)}<span class="hint">${esc(s.one_liner||"")}</span></div>`).join("")}</div>
     <div class="hint">${[...new Set(xs.map(s=>s.vertical).filter(Boolean))].map(esc).join(" · ")}</div></div>`;}).join("");
  const loose=arr.filter(s=>!placed.has(s.id));
  return`<div class="wl-ths">${cards}</div>${loose.length?`<div class="sec card"><h4>Not in a thesis yet <span class="mono hint">${loose.length}</span></h4>${loose.map(s=>`<div class="wl-thr">${wlName(s)}${sChip(s)}<span class="hint">${esc(s.theme||"")}</span></div>`).join("")}<div class="hint" style="margin-top:6px">Claude places these at the next sort.</div></div>`:""}`;}

function viewWatchlist(arg){if(arg&&byS[arg])return sProfile(arg,{crumb:["#watchlist","Startup Watchlist"]});const arr=kept();const L=WL.layout==="theses"?"theses":"themes";const c=sCounts();
  const sw=`<div class="scr-tabs">${WL_LAYOUTS.map(([k,l])=>`<button class="pill${L===k?" on":""}" data-wll="${k}">${esc(l)}</button>`).join("")}</div>`;
  const body=!arr.length?'<div class="emptybig"><b>Nothing kept yet</b><span>Mark a company Interesting or Watch on Startup Review.</span></div>':L==="theses"?wlTheses(arr):wlThemes(arr);
  return`<div class="sh"><h2>Startup Watchlist <span>${c.interesting} interesting · ${c.watch} watch</span></h2><div class="hint">Claude sorts the themes and theses · open a company for its profile</div></div>${sw}${body}`;}

view.addEventListener("click",e=>{const t=e.target.closest("[data-wll]");if(!t)return;WL.layout=t.dataset.wll;saveWL();paint();});

/* ---------- The company profile (Watchlist, 2026-09-25; the owner picked Workspace of five the same night) ----------
   His call sits at the foot of the rail (the end of the page on a phone), not under the header: "I said those things
   quickly with a quick glance ... not the headline that I reread over and over again."
   the owner: "one cohesive deep dive ... like it was designed to be this way, not bolted onto the side." One content model,
   eight chapters that each merge every source on their subject (MGMT's record, the research row, Claude's lenses, the
   /diligence sections split by the engine, the vault card, the screen), and five layouts over the same chapters behind a
   switch, for the owner to pick from: Memo (tabs), Scorecard (the decision first), Report (one read with a contents rail),
   Workspace (a summary rail beside the tabs), Next move (what to do first, background below). */
const PTAB={};
const dsec=(s,f,k)=>(((s.diligence||{}).s||{})[f]||{})[k]||null;
const dhtml=(s,f,k)=>{const x=dsec(s,f,k);return x?x.html:"";};
function pfSub(title,html,note){return html?`<div class="pf-sub"><h4>${esc(title)}${note?` <span class="hint">${esc(note)}</span>`:""}</h4><div class="doc">${html}</div></div>`:"";}
/* The stat tiles merge two sources (2026-09-25): the research's reconciled facts (research/<slug>/facts.json) where it has
   a figure, MGMT's record where it does not. Each tile says which, so a stale MGMT number never passes as current. */
function pfFacts(s){const F=((s.diligence||{}).facts)||{};
  const t=(l,res,mg,mgSub)=>{const x=res&&res.v?res:null;const v=x?x.v:mg;if(!v)return"";
    return`<div class="pf-fact${x?"":" mg"}" title="${esc(x?(x.note||""):"MGMT record")}"><span class="nw-lab">${l}</span><b>${esc(String(v))}</b><span class="hint">${esc(x?(x.note||"research"):(mgSub||"MGMT"))}</span></div>`;};
  return`<div class="pf-facts">${t("Last round",F.round,s.round_type?roundL(s.round_type)+(s.round_date?" "+s.round_date.slice(0,7):""):"")}${t("Raised",F.raised,s.raised?money(s.raised):"")}${t("Valuation",F.valuation,"")}
   ${t("People",F.people,s.people?String(s.people):"")}${t("Revenue",F.revenue,"")}${t("Customers",F.customers,"")}${t("Based",F.based,s.hq||"",s.workplace||"MGMT")}${t("Founded",F.founded,s.founded?String(s.founded):"")}</div>
   ${F.asof?`<div class="hint">Figures from the research of ${esc(fmtDate(F.asof))} unless marked MGMT.</div>`:""}`;}
/* The gate read, as four cards; the dossier's version first, the brief's if the dossier has none. */
const GATES=[["growth","Growth"],["excitement","Excitement"],["edge","Edge"],["learning","Learning"]];
function pfGateItems(s){const g=dsec(s,"dossier","gate")||dsec(s,"brief","gate");const items=(g&&g.items)||[];
  return GATES.map(([k,l])=>{const it=items.find(i=>i.label.toLowerCase().startsWith(k));return{k,l,html:it?it.html:""};}).filter(x=>x.html);}
function pfGate(s,cls){const it=pfGateItems(s);if(!it.length)return"";
  return`<div class="pf-gates ${cls||""}">${it.map(x=>`<div class="pf-gate card"><span class="nw-lab">${esc(x.l)}</span><div class="doc">${x.html}</div></div>`).join("")}</div><div class="hint" style="margin-top:6px">Evidence from the research; the call is yours.</div>`;}
function pfFive(s){const h=dhtml(s,"brief","five");return h?`<div class="pf-five"><span class="nw-lab">The firm in five lines</span><div class="doc">${h}</div></div>`:"";}
function pfDesc(s){const r=s.research||{};
  return`${s.one_liner?`<p class="pf-lede">${esc(s.one_liner)}</p>`:""}${r.what?`<div class="doc">${md(r.what)}</div>`:""}${s.description?`<p class="hint" style="margin-top:6px">${esc(s.description)}</p>`:""}`;}
function pfMap(s,h){const o=s.office||{};return o.lat!=null?`<div class="mapmini" data-map="s:${s.id}" data-lat="${o.lat}" data-lng="${o.lng}" data-z="${o.precision==="street"?15:12}" style="height:${h||160}px;border-radius:8px;overflow:hidden"></div><div class="hint" style="margin-top:4px">${esc(o.address||"")}</div>`:(o.address?`<div class="hint">${esc(o.address)}</div>`:"");}
/* The chapters: every source on a subject in one place, in the order a reader evaluating the company wants them. */
const PF_CH=[["overview","Overview"],["business","The business"],["momentum","Momentum"],["people","People and paths"],["seat","The seat"],["risks","Risks and unknowns"],["talk","The conversation"],["sources","Sources"]];
function pfChapter(s,k){const r=s.research||{};
  if(k==="overview")return`${pfFive(s)}${pfGate(s)}`;
  if(k==="business")return`${pfSub("What they do",pfDesc(s)+dhtml(s,"dossier","what"))}${pfSub("Market position",dhtml(s,"dossier","market"))}${pfSub("Customers and successes",(s.customers?`<p>Local customers: ${esc(s.customers)}</p>`:"")+dhtml(s,"dossier","portfolio"))}${pfSub("How they operate",dhtml(s,"dossier","operate"))}${pfSub("Office",pfMap(s,200))}`;
  if(k==="momentum")return`${pfSub("Snapshot",dhtml(s,"dossier","snapshot"))}${pfSub("Size and trajectory",dhtml(s,"dossier","size"))}${pfSub("Investors",s.investors&&s.investors.length?`<p>${esc(s.investors.join(", "))}</p>`:"")}${pfSub("News",dhtml(s,"dossier","news"))}${pfSub("The last 30 days",dhtml(s,"dossier","signal"))}`;
  if(k==="people"){const fd=(s.first_degree||[]).map(x=>`<div class="li"><span class="path yes"><i></i></span><span><b style="font-weight:500">${esc(x.name)}</b>${x.title?", "+esc(x.title):""}</span></div>`).join("");
    return`${pfSub("Your paths in",dhtml(s,"connections","summary")+(fd?`<div style="margin-top:6px">${fd}</div>`:"")+(r.path?`<div class="doc">${md(r.path)}</div>`:""))}${pfSub("Suggested sequence",dhtml(s,"connections","sequence"))}${pfSub("First degree",dhtml(s,"connections","first"))}${pfSub("Second degree and affinity",dhtml(s,"connections","second"))}
     ${pfSub("Leadership and ownership",dhtml(s,"dossier","ownership"))}${pfSub("Who matters",dhtml(s,"people","who"))}${pfSub("How the org looks",dhtml(s,"people","org"))}${pfSub("Trajectories",dhtml(s,"people","trajectory"))}${dhtml(s,"people","profiles")?`<details class="pf-sub"><summary><h4 style="display:inline">Profiles</h4></summary><div class="doc">${dhtml(s,"people","profiles")}</div></details>`:""}`;}
  if(k==="seat"){const rows=(s.board_rows||[]).length?`<div class="kv">${s.board_rows.map(b=>`<span class="mono">${b.score??""}</span><span><a href="#job/${esc(b.id)}">${esc(b.title)}</a>${b.verdict?` <span class="chip ${b.verdict}">${cap(b.verdict)}</span>`:' <span class="chip">To review</span>'}</span>`).join("")}</div>`:"";
    return`${pfSub("What it means for you",dhtml(s,"dossier","seat"))}${pfSub("Open roles on your kind of work",(r.roles?`<div class="doc">${md(r.roles)}</div>`:"")+rows)}${pfSub("Hiring",dhtml(s,"dossier","hiring"))}${pfSub("The seat and the sponsor",dhtml(s,"brief","sponsor"))}${s.look_again?pfSub("Look again when",`<p>${esc(s.look_again)}</p>`):""}`;}
  if(k==="risks")return`${pfSub("Failures and friction",dhtml(s,"dossier","failures"))}${pfSub("Culture and reviews",dhtml(s,"dossier","culture"))}${pfSub("Still unknown",dhtml(s,"brief","unknown"))}${pfSub("Open questions",dhtml(s,"dossier","questions"))}${pfSub("Numbers to treat with care",dhtml(s,"dossier","flags"))}`;
  if(k==="talk")return`${pfSub("What to say",dhtml(s,"brief","say"))}${pfSub("What to ask",dhtml(s,"brief","ask"))}${pfSub("What to avoid",dhtml(s,"brief","avoid"))}${pfSub("Paths to use first",dhtml(s,"brief","paths"))}`;
  if(k==="sources"){const src=((s.diligence||{}).s||{}).sources;const sh=src?src._order.map(x=>pfSub(src[x].t,src[x].html)).join(""):"";
    return`${pfSub("How it scored",`<div class="mono card" style="font-size:var(--fs-sm);padding:8px 10px">${esc(s.screen.math)}</div>`)}${sh}${pfSub("Change log",dhtml(s,"dossier","changelog"))}${s.card_html?`<details class="pf-sub"><summary><h4 style="display:inline">Company card</h4> <span class="hint">${esc(s.vault_card||"")}.md</span></summary><div class="doc">${s.card_html}</div></details>`:""}${s.diligence?`<p class="hint">Research folder ${esc(s.diligence.folder)}, ${esc(s.diligence.mode==="quick"?"quick pass":"full run")}${s.diligence.date?" "+esc(fmtDate(s.diligence.date)):""}.</p>`:""}`;}
  return"";}
const pfHas=(s,k)=>k==="overview"||!!pfChapter(s,k).replace(/<[^>]+>/g,"").trim();
function pfTabs(s,skip){const ks=PF_CH.map(x=>x[0]).filter(k=>!(skip||[]).includes(k)&&pfHas(s,k));const cur=ks.includes(PTAB[s.id])?PTAB[s.id]:ks[0];
  return`<div class="pf-tabs">${ks.map(k=>`<button class="pf-tab${k===cur?" on":""}" data-ptab="${s.id}:${k}">${esc(PF_CH.find(x=>x[0]===k)[1])}</button>`).join("")}</div><div class="pf-body">${pfChapter(s,cur)}</div>`;}
function pfWhy(s){const th=(SSUM.theses||[]).filter(t=>(t.members||[]).includes(s.id));
  return`<div class="pf-why">${[s.theme,s.vertical].filter(Boolean).map(x=>`<span class="chip wl-tag">${esc(x)}</span>`).join("")}${th.map(t=>`<span class="chip pursue" title="${esc(t.why||"")}">${esc(t.title)}</span>`).join("")}</div>
   ${th.length?`<div class="hint" style="margin-top:4px">${th.map(t=>esc(t.why||"")).join(" ")}</div>`:""}`;}
function pfHead(s,opts){const st=sv(s.id);
  const links=[s.website?`<a href="${esc(s.website)}" target="_blank" rel="noopener">${esc(s.website.replace(/^https?:\/\/(www\.)?/,"").replace(/\/$/,""))} ↗</a>`:"",s.careers?`<a href="${esc(s.careers)}" target="_blank" rel="noopener">careers</a>`:"",s.linkedin?`<a href="${esc(s.linkedin)}" target="_blank" rel="noopener">LinkedIn</a>`:"",s.mgmt?`<a href="${esc(s.mgmt)}" target="_blank" rel="noopener">MGMT</a>`:""].filter(Boolean).join(" · ");
  return`<div class="crumb"><a href="${opts.crumb[0]}">${esc(opts.crumb[1])}</a> <i>/</i> ${esc(s.name)}</div>
   <div class="pf-head"><div class="pf-id"><h1>${esc(s.name)}</h1>${sChip(s)}${st.flag?ICON.flagOn:""}</div><div class="hint">${esc(s.one_liner||"")}</div><div class="pf-links">${links}${s.diligence?`<span class="hint">· researched ${esc(fmtDate(s.diligence.date||""))}, ${esc(s.diligence.mode==="quick"?"quick pass":"full run")}</span>`:""}</div>${pfWhy(s)}</div>
`;}

function pfWorkspace(s){const st=sv(s.id);
  return`<div class="pf-ws"><aside class="pf-rail">${pfFacts(s).replace('class="pf-facts"','class="pf-facts col"')}
    ${s.look_again?`<div class="pf-look"><span class="nw-lab">Look again when</span><b>${esc(s.look_again)}</b></div>`:""}
    ${dhtml(s,"connections","summary")?`<div class="pf-rsec"><span class="nw-lab">Paths in</span><div class="doc">${dhtml(s,"connections","summary")}</div></div>`:""}
    ${dhtml(s,"brief","unknown")?`<div class="pf-rsec"><span class="nw-lab">Still unknown</span><div class="doc">${dhtml(s,"brief","unknown")}</div></div>`:""}
<div class="pf-call pf-desk">${sCallBlock(s)}</div></aside><div class="pf-main">${pfTabs(s)}<div class="pf-call pf-phone">${sCallBlock(s)}</div></div></div>`;}
function sProfile(id,opts){const s=byS[id];if(!s)return'<div class="emptybig"><b>Not on the board</b><span>This company is not in the current build.</span></div>';
  return`<div class="detail pf">${pfHead(s,opts)}${pfWorkspace(s)}</div>`;}
view.addEventListener("click",e=>{const t=e.target.closest("[data-ptab]");if(!t)return;
  const [id,k]=t.dataset.ptab.split(":");PTAB[id]=k;const y=window.scrollY;paint();window.scrollTo(0,y);});
