/* Calendar tab (2026-11-02, the owner: "a calendar tab. It just shows when things are happening"). Google Calendar's
   four views (Schedule, Day, Week, Month) over the board's dated items: a role's next step, a person's next touch, a
   career task, and Notion Meeting Notes. No filters on job items. Calendar is when; Today stays what to do now,
   ranked: nothing here ranks or sends anything.
   Moving a date writes Notion at once through the function that owns the field (opportunity-write, network-write,
   task-write: Plan day, never Due), the same as a day named in a Today note. Done stages like To-dos and Sync sends it.
   the owner's Google calendars (gcal_calendars, gcal_events, written by supabase/functions/gcal-sync) are grey blocks,
   title only, on Day and Week only, never on Schedule or Month. My calendars: a checkbox each and one All button
   that turns every calendar on, then off again; Personal is on to start; each device remembers its picks. A timed
   job item that overlaps a block that is switched on is marked Clash.
   Loaded after index.html's main script; the hooks there (load, realtime, nav, routing) call in. */
let GCALS=[],GEVENTS=[],GSEL=null;
const GSEL_KEY="board.calendar.gcals",GVIEW_KEY="board.calendar.view";
const CV={view:"schedule",cur:null,sel:null,open:null,mini:false,sheet:false,late:true,jump:true};
try{const v=localStorage.getItem(GVIEW_KEY);if(["schedule","day","week","month"].includes(v))CV.view=v;}catch(e){}
const gDefault=()=>{const d=GCALS.filter(c=>c.is_default);const p=GCALS.filter(c=>/personal/i.test(c.name||""));return new Set((d.length?d:p.length?p.slice(0,1):GCALS.slice(0,1)).map(c=>c.id));};
const gOn=id=>!!(GSEL&&GSEL.has(id));
const gSave=()=>{try{localStorage.setItem(GSEL_KEY,JSON.stringify([...GSEL]));}catch(e){}};
async function loadCalendar(){
  const [c,e]=await Promise.all([sb.from("gcal_calendars").select("id,name,ord,is_default,ok,synced_at").order("ord"),sb.from("gcal_events").select("id,calendar_id,title,starts,ends,all_day")]);
  GCALS=c.error?[]:(c.data||[]);GEVENTS=e.error?[]:(e.data||[]);
  if(!GSEL){let s=null;try{s=JSON.parse(localStorage.getItem(GSEL_KEY)||"null");}catch(x){}if(Array.isArray(s))GSEL=new Set(s);}
  if(!GSEL&&GCALS.length)GSEL=gDefault();}
/* gcal-sync touches each gcal_calendars row once a run; that is the signal, so a run of hundreds of events is one reload. */
let gcalT=null;
function subscribeCalendar(){sb.channel("gcal").on("postgres_changes",{event:"*",schema:"public",table:"gcal_calendars"},()=>{clearTimeout(gcalT);gcalT=setTimeout(async()=>{await loadCalendar();if(route().r==="calendar")render();},1500);}).subscribe();}

/* ---------- dates ---------- */
const gDow=d=>new Date(d+"T12:00:00").getDay();
const gWeek=d=>addDays(d,-gDow(d));
const gMon=d=>d.slice(0,8)+"01";
const gMonthAdd=(d,n)=>{const x=new Date(d.slice(0,8)+"01T12:00:00");x.setMonth(x.getMonth()+n);return x.toLocaleDateString("en-CA");};
const G_WD=["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
const gLong=d=>new Date(d+"T12:00:00").toLocaleDateString([],{weekday:"short",month:"short",day:"numeric"});
const gMonthName=d=>new Date(d+"T12:00:00").toLocaleDateString([],{month:"long",year:"numeric"});
const gNum=d=>+d.slice(8,10);
const gShort=d=>new Date(d+"T12:00:00").toLocaleDateString([],{month:"short",day:"numeric"});
/* A Notion date with a time ("2026-10-28T14:00:00.000-04:00") keeps its time; a bare date is any time that day. */
const gTime=raw=>{if(!raw||!String(raw).includes("T"))return"";const x=new Date(raw);return isNaN(x)?"":String(x.getHours()).padStart(2,"0")+":"+String(x.getMinutes()).padStart(2,"0");};
const gMin=t=>{const [h,m]=t.split(":").map(Number);return h*60+m;};
const gClock=t=>{if(!t)return"Any time";let [h,m]=t.split(":").map(Number);const ap=h>=12?"pm":"am";h=h%12||12;return m?`${h}:${String(m).padStart(2,"0")}${ap}`:h+ap;};
const gClockMin=n=>gClock(String(Math.floor(n/60)).padStart(2,"0")+":"+String(n%60).padStart(2,"0"));

/* ---------- job items ---------- */
const G_KIND={int:"Interview or call",move:"Role move",touch:"Follow-up or touch",wait:"Waiting on them",dec:"Decision date",task:"Career task"};
const G_HOME={opp:"Notion Opportunities",net:"Notion Network",task:"Notion Tasks",meet:"Notion Meeting Notes"};
const G_FIELD={opp:"Next Step Date",net:"Next Action Date",task:"Plan day"};
/* Meeting Notes are the booked calls (and, once past, the calls that happened); a person's Call or Meeting touch on
   the same day as one of their meetings is the same event and shows once. */
function calItems(){const out=[],today=todayIso(),seen=new Set();
  MEETINGS.forEach(m=>{if(!m.date)return;const d=String(m.date).slice(0,10);if(d<addDays(today,-62))return;const t=gTime(m.date);(m.people||[]).forEach(p=>seen.add(p+"|"+d));
    out.push({key:"meeting:"+m.id,kind:"int",src:"meet",title:m.name||"Meeting",sub:m.type||"Meeting",date:d,time:t,dur:45,fixed:true,done:d<today,url:m.url});});
  todoItems().forEach(i=>{if(i.nostep)return;let kind,src,raw="";
    if(i.kind==="role"){src="opp";const o=OPPS[i.id]||{};raw=o.next_date||"";kind=i.ball==="them"?"wait":/^(bench review|no response)/i.test(i.text)?"dec":"move";}
    else if(i.kind==="person"){src="net";raw=i.c.next_date||"";if(i.date&&seen.has(i.id+"|"+i.date))return;kind=isBooked(i.c)?"int":"touch";}
    else{src="task";raw=i.t.plan_day||i.t.due||"";kind="task";}
    const time=i.p&&i.p.date!==undefined?"":gTime(raw);
    out.push({key:i.key,kind,src,id:i.id,i,title:i.text,sub:[i.who,i.sub].filter(Boolean).join(" · "),date:i.date||"",time,dur:30,done:!!i.done,ball:i.ball||""});});
  out.forEach(x=>{x.late=!x.done&&!!x.date&&x.date<today;});
  /* Only what is on the calendar: an item shows on its own date and nowhere else; no date, no row (the owner, 2026-11-02). */
  return out.filter(x=>x.date).sort((a,b)=>(a.time?gMin(a.time):-1)-(b.time?gMin(b.time):-1)||a.title.localeCompare(b.title));}
const calCount=()=>calItems().filter(x=>!x.done&&x.date===todayIso()).length;
const gByDay=(items,d)=>items.filter(x=>x.date===d);

/* ---------- Google calendars ---------- */
/* An all-day event runs from its start day up to, not including, its end day. A timed one is cut to the day it falls on. */
function gOnDay(d){const s0=new Date(d+"T00:00:00"),e0=new Date(addDays(d,1)+"T00:00:00"),out=[];
  GEVENTS.forEach(ev=>{if(!gOn(ev.calendar_id))return;
    if(ev.all_day){if(ev.starts<=d&&d<(ev.ends||addDays(ev.starts,1)))out.push({ev,all:true});return;}
    const s=new Date(ev.starts),e=new Date(ev.ends||ev.starts);if(isNaN(s)||e<=s0||s>=e0)return;
    const a=Math.max(0,Math.round((Math.max(s,s0)-s0)/6e4)),b=Math.min(1440,Math.round((Math.min(e,e0)-s0)/6e4));if(b>a)out.push({ev,s:a,e:b});});
  return out;}
const gCalName=id=>(GCALS.find(c=>c.id===id)||{}).name||"Calendar";
const gClashes=x=>!x.time||!x.date||x.done?[]:gOnDay(x.date).filter(p=>!p.all&&p.s<gMin(x.time)+x.dur&&p.e>gMin(x.time));
/* Overlapping blocks sit side by side, as in Google: each run of overlaps shares its width. */
function gLayout(items,d){const ev=[...items.filter(x=>x.time).map(x=>({x,s:gMin(x.time),e:gMin(x.time)+x.dur,job:true})),...gOnDay(d).filter(p=>!p.all).map(p=>({x:p.ev,s:p.s,e:p.e,job:false}))]
  .sort((a,b)=>a.s-b.s||b.e-a.e||(b.job-a.job));
  const out=[];let run=[],end=-1;
  const flush=()=>{const cols=[];run.forEach(r=>{let c=cols.findIndex(e=>e<=r.s);if(c<0){c=cols.length;cols.push(0);}cols[c]=r.e;r.col=c;});run.forEach(r=>r.n=cols.length);out.push(...run);run=[];};
  ev.forEach(r=>{if(r.s>=end&&run.length)flush();run.push(r);end=Math.max(end,r.e);});if(run.length)flush();return out;}

/* ---------- pieces ---------- */
const gDrag=x=>SPLIT.matches&&!x.fixed&&!x.done?` draggable="true" data-gdrag="${esc(x.key)}"`:"";
const gCls=x=>`k-${x.late?"late":x.kind}${x.done?" done":""}`;
const gChip=x=>`<button class="gc-chip ${gCls(x)}" data-gopen="${esc(x.key)}"${gDrag(x)}>${x.time&&CV.view==="month"?`<span class="mono">${gClock(x.time)}</span> `:""}${esc(x.title)}</button>`;
function gRow(x){return`<button class="gc-row ${gCls(x)}" data-gopen="${esc(x.key)}"${gDrag(x)}><span class="gc-tm mono">${gClock(x.time)}</span><span class="gc-tx"><b>${esc(x.title)}</b><i>${esc(x.sub)}</i></span>${SPLIT.matches?`<span class="gc-home">${G_HOME[x.src]}</span>`:""}</button>`;}
function gMini(){const c=CV.cur,m=gMon(c),start=gWeek(m),mo=c.slice(0,7);const items=calItems();
  const inR=d=>CV.view==="week"?gWeek(d)===gWeek(c):CV.view==="day"?d===c:false;
  let h=`<div class="gc-mmh"><b>${esc(gMonthName(c))}</b><span><button class="gc-ico" data-gmnav="-1" aria-label="Previous month">&#8249;</button><button class="gc-ico" data-gmnav="1" aria-label="Next month">&#8250;</button></span></div><div class="gc-mm">${"SMTWTFS".split("").map(x=>`<span>${x}</span>`).join("")}`;
  for(let k=0;k<42;k++){const d=addDays(start,k);h+=`<button class="${d.slice(0,7)!==mo?"o ":""}${d===todayIso()?"gc-td ":""}${inR(d)?"in ":""}${items.some(x=>x.date===d&&!x.done)?"has":""}" data-gday="${d}">${gNum(d)}</button>`;}
  return h+"</div>";}
function gCalSet(){if(!GCALS.length)return`<div class="hint">Your Google calendars show here once gcal-sync has run. Setup is in the Calendar tab spec.</div>`;
  const all=GCALS.every(c=>gOn(c.id));
  return`<div class="gc-set"><button class="gc-all${all?" on":""}" data-gall="1">All</button><div class="gc-togs">${GCALS.map(c=>`<label class="gc-tog"><input type="checkbox" id="gcal-${esc(c.id)}" data-gcal="${esc(c.id)}"${gOn(c.id)?" checked":""}>${esc(c.name)}${c.ok===false?' <span class="hint">not read last time</span>':""}</label>`).join("")}</div>
   <div class="hint">Grey blocks on Day and Week only, title only.</div></div>`;}
function gSide(items){const und=items.filter(x=>!x.date&&!x.done);
  return`<aside class="gc-side">${gMini()}
   <div><div class="gc-sh"><span>No date yet</span><span>${und.length}</span></div><div class="gc-tray" data-gdrop="none">${und.map(gChip).join("")||'<div class="hint">Everything has a day.</div>'}</div>${und.length?'<div class="hint">Drag one onto a day to give it a date.</div>':""}</div>
   <div><div class="gc-sh"><span>My calendars</span><span>${GCALS.filter(c=>gOn(c.id)).length||""}</span></div>${gCalSet()}</div>
   <div><div class="gc-sh"><span>Kinds</span></div><div class="gc-leg">${Object.entries(G_KIND).map(([k,l])=>`<div class="k-${k}"><i></i>${l}</div>`).join("")}<div class="k-late"><i></i>Late</div><div><i class="gc-grey"></i>Your Google calendars</div></div></div></aside>`;}
function gHead(){const v=CV.view,c=CV.cur;let t;
  if(v==="day")t=SPLIT.matches?new Date(c+"T12:00:00").toLocaleDateString([],{weekday:"long",month:"long",day:"numeric",year:"numeric"}):new Date(c+"T12:00:00").toLocaleDateString([],{month:"short",year:"numeric"});
  else if(v==="week"&&SPLIT.matches){const a=gWeek(c),b=addDays(a,6);t=a.slice(0,7)===b.slice(0,7)?`${fmtDate(a)} to ${gNum(b)}, ${b.slice(0,4)}`:`${fmtDate(a)} to ${fmtDate(b)}`;}
  else if(v==="week")t=new Date(c+"T12:00:00").toLocaleDateString([],{month:"short",year:"numeric"});
  else t=gMonthName(c);
  const vs=[["schedule","Schedule"],["day","Day"],["week","Week"],["month","Month"]];
  if(SPLIT.matches)return`<div class="gc-hdr"><button class="gc-btn" data-gtoday="1">Today</button><button class="gc-ico" data-gnav="-1" aria-label="Previous">&#8249;</button><button class="gc-ico" data-gnav="1" aria-label="Next">&#8250;</button><h2 class="gc-ttl">${esc(t)}</h2><div class="gc-vsw">${vs.map(([k,l])=>`<button class="${v===k?"on":""}" data-gv="${k}">${l}</button>`).join("")}</div></div>`;
  return`<div class="gc-hdr"><button class="gc-ttl" data-gmini="1">${esc(t)} <span class="gc-car">${CV.mini?"&#9650;":"&#9660;"}</span></button><button class="gc-ico" data-gnav="-1" aria-label="Previous">&#8249;</button><button class="gc-ico" data-gnav="1" aria-label="Next">&#8250;</button><button class="gc-btn" data-gtoday="1">Today</button><button class="gc-ico" data-gsheet="1" aria-label="My calendars" title="My calendars">&#9783;</button></div>
   ${CV.mini?`<div class="gc-minidrop">${gMini()}</div>`:""}<div class="gc-psw">${vs.map(([k,l])=>`<button class="${v===k?"on":""}" data-gv="${k}">${l}</button>`).join("")}</div>`;}

/* ---------- views ---------- */
function gSchedule(items){const today=todayIso();let h=`<div class="gc-sched">`;
  const from=CV.cur<today&&CV.cur>=addDays(today,-6)?today:CV.cur;let lastM="",n=0;
  for(let k=0;k<45;k++){const d=addDays(from,k),xs=gByDay(items,d);if(!xs.length&&d!==today)continue;n+=xs.length;
    if(d.slice(0,7)!==lastM){h+=`<div class="gc-band">${esc(gMonthName(d))}</div>`;lastM=d.slice(0,7);}
    h+=`<div class="gc-sday${d===today?" today":""}" data-gdrop="${d}"><button class="gc-sdate" data-gday="${d}"><b class="mono">${gNum(d)}</b><span>${G_WD[gDow(d)]}</span></button><div class="gc-slist">${xs.length?xs.map(gRow).join(""):'<div class="hint gc-empty">Nothing scheduled today.</div>'}</div></div>`;}
  return h+`<div class="gc-band gc-end">${n?"That is everything with a date in the next six weeks.":"Nothing dated in these six weeks."}</div></div>`;}
function gGrid(items,days){const H=SPLIT.matches?48:44;let h0=7,h1=21;
  days.forEach(d=>gLayout(gByDay(items,d),d).forEach(r=>{h0=Math.min(h0,Math.floor(r.s/60));h1=Math.max(h1,Math.ceil(r.e/60));}));
  const n=days.length,today=todayIso();
  let h=`<div class="gc-tg" style="--n:${n};--H:${H}px"><div class="gc-tgh">`;
  if(n>1)h+=`<div class="gc-cols"><span></span>${days.map(d=>`<button class="gc-dhd${d===today?" today":""}${d<today?" past":""}" data-gday="${d}"><span>${G_WD[gDow(d)]}</span><b class="mono">${gNum(d)}</b></button>`).join("")}</div>`;
  h+=`<div class="gc-cols gc-ad"><span class="gc-adl mono">any<br>time</span>${days.map(d=>`<div class="gc-adc" data-gdrop="${d}">${gOnDay(d).filter(p=>p.all).map(p=>`<div class="gc-pchip" title="${esc(gCalName(p.ev.calendar_id))}">${esc(p.ev.title)}</div>`).join("")}${gByDay(items,d).filter(x=>!x.time).map(gChip).join("")}</div>`).join("")}</div></div>`;
  h+=`<div class="gc-cols gc-tb"><div class="gc-hrs">${Array.from({length:h1-h0},(_,k)=>`<div>${k?gClockMin((h0+k)*60):""}</div>`).join("")}</div>`;
  const nowM=new Date().getHours()*60+new Date().getMinutes();
  h+=days.map(d=>`<div class="gc-dcol${[0,6].includes(gDow(d))?" wknd":""}" data-gdrop="${d}" style="height:${(h1-h0)*H}px">${gLayout(gByDay(items,d),d).map(r=>{
      const pos=`top:${(r.s-h0*60)/60*H}px;height:${Math.max(r.job?22:16,(r.e-r.s)/60*H-2)}px;left:calc(${r.col*100/r.n}% + 2px);width:calc(${100/r.n}% - 4px)`;
      if(!r.job)return`<div class="gc-pblk" style="${pos}" title="${esc(gCalName(r.x.calendar_id))}: ${esc(r.x.title)}">${esc(r.x.title)}</div>`;
      const x=r.x,cl=gClashes(x).length;
      return`<button class="gc-blk ${gCls(x)}${cl?" clash":""}" style="${pos}" data-gopen="${esc(x.key)}"${gDrag(x)}><b>${esc(x.title)}</b><span class="mono">${gClock(x.time)}${cl?' <em>Clash</em>':""}</span></button>`;}).join("")}${d===today&&nowM>=h0*60&&nowM<=h1*60?`<div class="gc-now" style="top:${(nowM-h0*60)/60*H}px"></div>`:""}</div>`).join("");
  return{html:h+`</div></div>`,top:(Math.max(h0,8)-h0)*H};}
function gDay(items){const d=CV.cur,today=todayIso();let h="";
  if(!SPLIT.matches){const a=gWeek(d);h+=`<div class="gc-wstrip">${Array.from({length:7},(_,k)=>{const x=addDays(a,k),xs=gByDay(items,x).filter(y=>!y.done);
    return`<button class="${x===d?"sel":""}${x===today?" gc-td":""}" data-gday="${x}">${G_WD[gDow(x)][0]}<b class="mono">${gNum(x)}</b><span class="gc-dots">${xs.slice(0,4).map(y=>`<i class="${gCls(y)}"></i>`).join("")}</span></button>`;}).join("")}</div>`;}
  const n=gByDay(items,d).length;
  h+=`<div class="gc-dayhd${d===today?" today":""}"><b class="mono">${gNum(d)}</b><div><div><b>${esc(gLong(d))}</b></div><span class="hint">${n?`${n} item${n>1?"s":""}`:"Nothing scheduled"}</span></div></div>`;
  const g=gGrid(items,[d]);return{html:h+g.html,top:g.top};}
function gWeekView(items){const a=gWeek(CV.cur);return gGrid(items,Array.from({length:7},(_,k)=>addDays(a,k)));}
function gMonth(items){const c=CV.cur,m=gMon(c),start=gWeek(m),mo=c.slice(0,7),today=todayIso();
  const dim=new Date(+c.slice(0,4),+c.slice(5,7),0).getDate(),weeks=Math.ceil((gDow(m)+dim)/7);
  let h=`<div class="gc-month"><div class="gc-mhd">${G_WD.map(w=>`<span>${SPLIT.matches?w:w[0]}</span>`).join("")}</div><div class="gc-mgrid">`;
  for(let k=0;k<weeks*7;k++){const d=addDays(start,k),xs=gByDay(items,d);const cls=`gc-mcell${d.slice(0,7)!==mo?" o":""}${d===today?" gc-td":""}${!SPLIT.matches&&d===CV.sel?" sel":""}`;
    if(SPLIT.matches)h+=`<div class="${cls}" data-gdrop="${d}" data-gday="${d}"><span class="gc-n mono">${gNum(d)}</span>${xs.slice(0,3).map(gChip).join("")}${xs.length>3?`<span class="gc-more">+${xs.length-3} more</span>`:""}</div>`;
    else h+=`<button class="${cls}" data-gsel="${d}"><span class="gc-n mono">${gNum(d)}</span><span class="gc-dots">${xs.filter(x=>!x.done).slice(0,4).map(x=>`<i class="${gCls(x)}"></i>`).join("")}</span></button>`;}
  h+=`</div>`;
  if(!SPLIT.matches){const xs=gByDay(items,CV.sel);h+=`<div class="gc-mlist"><div class="gc-lh2"><b>${esc(gLong(CV.sel))}</b><button class="gc-btn" data-gday="${CV.sel}">Open day</button></div>${xs.length?xs.map(gRow).join(""):'<div class="hint gc-empty">Nothing on this day.</div>'}</div>`;}
  return h+`</div>`;}
function gPanel(items){const x=items.find(y=>y.key===CV.open);if(!x)return"";const k=esc(x.key),today=todayIso();
  const base=x.date&&x.date>today?x.date:today;const nextDow=n=>{let d=addDays(today,1);while(gDow(d)!==n)d=addDays(d,1);return d;};
  const opts=[["Today",today],["Tomorrow",addDays(today,1)],["Fri",nextDow(5)],["Next Mon",nextDow(1)],["+1 week",addDays(base,7)]].filter(([,d],i,a)=>d!==x.date&&a.findIndex(o=>o[1]===d)===i);
  let move="";
  if(x.done)move=`<div class="gc-note">Done. It stays on its day, greyed out.</div>`;
  else if(x.fixed)move=`<div class="gc-note">A booked call moves in Google Calendar and comes back through Meeting Notes.</div>`;
  else move=`<div class="gc-mv"><div class="gc-sh"><span>${x.date?"Move to":"Give it a day"}</span></div><div class="gc-mvb">${opts.map(([l,d])=>`<button data-gmove="${k}" data-d="${d}">${l} <span class="mono">${esc(gShort(d))}</span></button>`).join("")}<label>Pick <input type="date" id="gpick" data-gpick="${k}" value="${esc(x.date||today)}" aria-label="Pick a date"></label>${x.date?`<button data-gmove="${k}" data-d="">No date</button>`:""}</div><div class="hint">Saves ${G_FIELD[x.src]} in ${G_HOME[x.src]} now.</div></div>`;
  const b=typeof BRIEFS!=="undefined"&&BRIEFS[x.key]&&BRIEFS[x.key].for===x.title;
  const open=x.src==="meet"?(x.url?`<a class="chip" href="${esc(x.url)}" target="_blank" rel="noopener">Open in Notion</a>`:""):x.src==="opp"?`<a class="chip pursue" href="#job/${esc(x.id)}">Open the role</a>`:x.src==="net"?`<a class="chip" href="#people/${esc(x.id)}">Open the person</a>`:(x.i.t.url?`<a class="chip" href="${esc(x.i.t.url)}" target="_blank" rel="noopener">Open in Notion</a>`:"");
  return`${SPLIT.matches?"":'<div class="gc-scrim" data-gclose="1"></div>'}<div class="gc-panel" role="dialog" aria-label="${esc(x.title)}">${SPLIT.matches?"":'<div class="gc-grab"></div>'}
   <div class="gc-tags"><span class="gc-tag k-${x.kind}">${G_KIND[x.kind]}</span>${x.late?'<span class="gc-tag k-late">Late</span>':""}${x.i&&x.i.p?'<span class="gc-tag k-task">Staged</span>':""}</div>
   <h3>${esc(x.title)}</h3><div class="gc-when">${x.date?esc(gLong(x.date))+" · "+(x.time?gClock(x.time):"Any time"):"No date yet"}</div>
   ${gClashes(x).map(p=>`<div class="gc-clash">Clashes with ${esc(gCalName(p.ev.calendar_id))}: ${esc(p.ev.title)}, ${gClockMin(p.s)} to ${gClockMin(p.e)}.</div>`).join("")}
   <dl class="gc-kv"><dt>About</dt><dd>${esc(x.sub)}</dd>${x.ball?`<dt>Whose move</dt><dd>${esc(x.ball==="owner"?"You":cap(x.ball))}</dd>`:""}<dt>Lives in</dt><dd>${G_HOME[x.src]}</dd></dl>
   ${move}<div class="gc-acts">${x.done||x.fixed?"":`<button class="go" data-gdone="${k}">${x.src==="net"?"Log the touch":"Mark done"}</button>`}${b?`<a class="chip pursue" href="#brief/${k}">Open brief</a>`:""}${open}<button data-gclose="1">Close</button></div></div>`;}
function gSheet(){if(!CV.sheet||SPLIT.matches)return"";
  return`<div class="gc-scrim" data-gsheet="1"></div><div class="gc-panel" role="dialog" aria-label="My calendars"><div class="gc-grab"></div><h3>My calendars</h3>${gCalSet()}<div class="gc-acts"><button class="go" data-gsheet="1">Done</button></div></div>`;}
let gTop=null;
function viewCalendar(){const today=todayIso();if(!CV.cur){CV.cur=today;CV.sel=today;}
  const items=calItems();const v=CV.view;
  let body;gTop=null;
  if(v==="schedule")body=gSchedule(items);else if(v==="month")body=gMonth(items);
  else{const g=v==="day"?gDay(items):gWeekView(items);body=g.html;}
  if(CV.jump)gTop=0;CV.jump=false;
  return`${pendN()?tdBar():""}<div class="gc${SPLIT.matches?" desk":" phone"}">${gHead()}${SPLIT.matches?gSide(items):""}<div class="gc-main" data-gview="${v}">${body}</div></div>${gPanel(items)}${gSheet()}`;}
/* A switch of view or day stays locked at the top of the page (the owner, 2026-11-02: Day and Week used to jump to 8am). */
function gJump(){if(gTop==null)return;window.scrollTo(0,0);gTop=null;}

/* ---------- writes ---------- */
async function calMove(key,d){const x=calItems().find(y=>y.key===key);if(!x||x.fixed)return;let ok=false;
  if(x.src==="net")ok=!!await netWrite({action:"update",id:x.id,fields:{next_date:d}});
  else if(x.src==="opp")ok=!!await oppWrite({action:"update",id:x.id,fields:{next_date:d}});
  else if(x.src==="task")ok=!!await taskWrite({action:"update",id:x.id,fields:d?{plan_day:d}:{plan_day:"",due:null}});
  if(!ok)return;
  const p=PEND[key];if(p&&p.date!==undefined){delete p.date;if(!Object.keys(p).filter(k=>k!=="text"&&k!=="err").length)unstage(key);else savePend();}
  CV.open=null;toast(d?`Moved to ${fmtDate(d)} in Notion`:"Date cleared in Notion");paint();}
/* Done is the To-dos path: a role or a task stages Done and Sync sends it; a person's touch is logged on the To-dos form. */
function calDone(key){const x=calItems().find(y=>y.key===key);if(!x)return;CV.open=null;
  if(x.src==="net"){location.hash="#todos/"+key;setTimeout(()=>todoDone(key),120);return;}
  stage(key,{done:true,text:x.title});toast(x.src==="opp"?"Done staged. Sync sends it; set the following step on the role":"Done staged. Sync sends it");paint();}

/* ---------- events ---------- */
view.addEventListener("click",e=>{if(route().r!=="calendar")return;
  const t=e.target.closest("[data-gv],[data-gnav],[data-gtoday],[data-gopen],[data-gclose],[data-gmove],[data-gday],[data-gsel],[data-gmini],[data-gsheet],[data-gall],[data-gdone],[data-glate],[data-gmnav]");if(!t)return;
  const ds=t.dataset;
  if(ds.gv){CV.view=ds.gv;CV.open=null;CV.jump=true;if(ds.gv==="month")CV.sel=CV.cur;try{localStorage.setItem(GVIEW_KEY,ds.gv);}catch(x){}}
  else if(ds.gtoday){CV.cur=CV.sel=todayIso();CV.jump=true;}
  else if(ds.gnav){const n=+ds.gnav,v=CV.view;CV.cur=v==="day"?addDays(CV.cur,n):v==="month"?gMonthAdd(CV.cur,n):addDays(CV.cur,7*n);CV.sel=CV.cur;}
  else if(ds.gmnav){CV.cur=gMonthAdd(CV.cur,+ds.gmnav);}
  else if(ds.gday){CV.cur=CV.sel=ds.gday;CV.view="day";CV.mini=false;CV.jump=true;}
  else if(ds.gsel){CV.sel=ds.gsel;}
  else if(ds.gmini){CV.mini=!CV.mini;}
  else if(ds.gsheet){CV.sheet=!CV.sheet;}
  else if(ds.glate){CV.late=!CV.late;}
  else if(ds.gall){GSEL=GCALS.every(c=>gOn(c.id))?new Set():new Set(GCALS.map(c=>c.id));gSave();}
  else if(ds.gopen){e.stopPropagation();CV.open=ds.gopen;}
  else if(ds.gclose){CV.open=null;}
  else if(ds.gmove!==undefined){calMove(ds.gmove,ds.d||"");return;}
  else if(ds.gdone){calDone(ds.gdone);return;}
  render();setTimeout(gJump,90);});
view.addEventListener("change",e=>{if(route().r!=="calendar")return;
  const p=e.target.closest("[data-gpick]");if(p&&p.value){calMove(p.dataset.gpick,p.value);return;}
  const c=e.target.closest("[data-gcal]");if(c){if(!GSEL)GSEL=new Set();if(c.checked)GSEL.add(c.dataset.gcal);else GSEL.delete(c.dataset.gcal);gSave();render();}});
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&route().r==="calendar"&&(CV.open||CV.sheet)){CV.open=null;CV.sheet=false;render();}});
/* Desktop drag: an item onto another day, or out of No date yet onto the calendar. */
view.addEventListener("dragstart",e=>{const t=e.target.closest&&e.target.closest("[data-gdrag]");if(!t)return;e.dataTransfer.setData("text/plain",t.dataset.gdrag);e.dataTransfer.effectAllowed="move";});
view.addEventListener("dragover",e=>{const z=e.target.closest&&e.target.closest("[data-gdrop]");if(!z)return;e.preventDefault();view.querySelectorAll(".gc-over").forEach(x=>x!==z&&x.classList.remove("gc-over"));z.classList.add("gc-over");});
view.addEventListener("dragleave",e=>{const z=e.target.closest&&e.target.closest("[data-gdrop]");if(z&&!z.contains(e.relatedTarget))z.classList.remove("gc-over");});
view.addEventListener("drop",e=>{const z=e.target.closest&&e.target.closest("[data-gdrop]");if(!z)return;e.preventDefault();z.classList.remove("gc-over");const key=e.dataTransfer.getData("text/plain");if(!key)return;
  const x=calItems().find(y=>y.key===key);const d=z.dataset.gdrop==="none"?"":z.dataset.gdrop;if(x&&x.date!==d)calMove(key,d);});
