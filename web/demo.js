/* Demo mode: a stand-in for supabase-js that serves the board from one static JSON file, so the page runs
   anywhere static files are hosted (GitHub Pages, a local folder) with no database, no sign-in and no secrets.
   config.js turns it on: window.BOARD_CONFIG = { demo: "demo/data.json" }.

   The file holds the same ten tables the live page reads (see docs/schema.md) plus a `generated` date. Every
   date in it is shifted forward by the days since it was generated, so the demo always reads as today: the
   freshness banner says Current, overdue next steps are overdue by the same margin, ages on cards hold.
   Writes (a verdict, a stage move, a touch, a task done) land in memory and survive until the tab reloads;
   the edge functions the live page calls (opportunity-write, network-write, task-write) are answered here
   the way they answer in production, so every control on the page works. */
window.demoClient = function (src) {
  let D = null, ready = null;
  const DATE = /\d{4}-\d{2}-\d{2}/g;
  const dayMs = 864e5;
  function shiftDate(s, delta) {
    if (!delta) return s;
    return s.replace(DATE, m => { const t = Date.parse(m + "T12:00:00Z"); if (isNaN(t)) return m; return new Date(t + delta * dayMs).toISOString().slice(0, 10); });
  }
  function shift(v, delta) {
    if (typeof v === "string") return shiftDate(v, delta);
    if (Array.isArray(v)) return v.map(x => shift(x, delta));
    if (v && typeof v === "object") { const o = {}; for (const k in v) o[shiftDate(k, delta)] = shift(v[k], delta); return o; }
    return v;
  }
  function load() {
    if (!ready) ready = fetch(src).then(r => { if (!r.ok) throw new Error("demo data " + r.status); return r.json(); }).then(d => {
      const gen = Date.parse((d.generated || "1970-01-01") + "T12:00:00Z");
      const today = new Date(); today.setUTCHours(12, 0, 0, 0);
      const delta = Math.round((today.getTime() - gen) / dayMs);
      D = shift(d, delta); D.tables = D.tables || {}; return D;
    });
    return ready;
  }
  const now = () => new Date().toISOString();
  const user = { email: "demo@example.com" }, session = { user, access_token: "demo" };

  function table(t) {
    let op = "select", payload = null, single = false, orderKey = null, desc = false, lim = null;
    const p = {
      select() { return p; }, eq() { return p; }, order(k, o) { orderKey = k; desc = !!(o && o.ascending === false); return p; },
      limit(n) { lim = n; return p; }, single() { single = true; return p; }, maybeSingle() { single = true; return p; },
      upsert(r) { op = "upsert"; payload = r; return p; }, insert(r) { op = "insert"; payload = r; return p; }, update(r) { op = "update"; payload = r; return p; },
      then(res, rej) {
        return load().then(() => {
          const T = D.tables[t] || (D.tables[t] = []); let out;
          const rows = payload == null ? [] : (Array.isArray(payload) ? payload : [payload]);
          if (op === "upsert") { rows.forEach(r => { const i = T.findIndex(x => x.id === r.id); if (i >= 0) T[i] = Object.assign({}, T[i], r); else T.push(r); }); out = rows; }
          else if (op === "insert") {
            rows.forEach(r => {
              if (r.id == null) r.id = T.reduce((m, x) => Math.max(m, +x.id || 0), 0) + 1;
              if (t === "sync_requests") Object.assign(r, { requested_at: now(), status: "done", host: "demo", started_at: now(), finished_at: now(), result: "demo build: nothing to fold, the board is a static snapshot" });
              T.push(r);
            }); out = rows;
          }
          else if (op === "update") { T.forEach((x, i) => { T[i] = Object.assign({}, x, payload); }); out = T.slice(); }
          else { out = T.slice(); if (orderKey) out.sort((a, b) => (a[orderKey] > b[orderKey] ? 1 : a[orderKey] < b[orderKey] ? -1 : 0) * (desc ? -1 : 1)); if (lim != null) out = out.slice(0, lim); }
          return { data: single ? (out[0] || null) : out, error: null };
        }).then(res, rej);
      }
    };
    return p;
  }

  /* The three edge functions, answered the way production answers them: the page gets back the row it should show. */
  function mirror(t, id) { const T = D.tables[t] || (D.tables[t] = []); let r = T.find(x => x.id === id); if (!r) { r = { id, payload: { id } }; T.push(r); } return r; }
  const fns = {
    "opportunity-write": b => {
      const f = b.fields || {}, r = mirror("opportunities", b.id), o = r.payload;
      if (b.action === "promote") Object.assign(o, { stage: "shortlist", outcome: null, next: null, next_date: null, company_name: f.company || o.company_name || "", company: null, people: [], meetings: [], tasks: [], flag: !!f.flag, url: "", page: "demo-" + b.id });
      if (b.action === "update") { ["stage", "outcome", "next", "next_date", "flag", "hp"].forEach(k => { if (f[k] !== undefined) o[k] = f[k]; }); }
      if (b.action === "close") Object.assign(o, { stage: "closed", outcome: f.outcome || "withdrew" });
      if (b.action === "link") { const k = b.kind === "person" ? "people" : b.kind === "meeting" ? "meetings" : b.kind === "task" ? "tasks" : null; if (k) { o[k] = o[k] || []; if (b.target && !o[k].includes(b.target)) o[k].push(b.target); } if (b.kind === "company") o.company = b.target; }
      o.edited = now(); return { opportunity: o };
    },
    "network-write": b => {
      const f = b.fields || {};
      if (b.action === "create") { const id = "demo-" + Math.random().toString(16).slice(2, 10); const c = Object.assign({ id, name: "", company: "", status: "Not contacted", priority: "Medium", touches: [], roles: [], edited: now() }, f); mirror("contacts", id).payload = c; return { contact: c }; }
      const c = mirror("contacts", b.id).payload;
      if (b.action === "done") { const t = { date: f.date || now().slice(0, 10), type: f.type || "Message", note: f.note || "" }; c.touches = (c.touches || []).concat([t]); Object.assign(c, { last_date: t.date, last_type: t.type, last_note: t.note, next_date: f.next_date || null, next_type: f.next_type || null, next_action: f.next_action || null }); if (c.status === "Not contacted") c.status = "In conversation"; }
      else Object.assign(c, f);
      c.edited = now(); return { contact: c };
    },
    "task-write": b => {
      const f = b.fields || {}, t = mirror("tasks", b.id).payload;
      if (b.action === "done") t.status = "Complete"; else Object.assign(t, f);
      t.edited = now(); return { task: t };
    }
  };

  const ch = { on() { return ch; }, subscribe(cb) { if (cb) setTimeout(() => cb("SUBSCRIBED"), 0); return ch; }, unsubscribe() {} };
  return {
    from: table, channel: () => ch, removeChannel() {}, rpc: async () => ({ data: null, error: null }),
    functions: { invoke: (name, opts) => load().then(() => ({ data: fns[name] ? fns[name]((opts || {}).body || {}) : { error: "no such function in the demo: " + name }, error: null })) },
    auth: {
      getSession: async () => ({ data: { session } }), getUser: async () => ({ data: { user } }),
      onAuthStateChange(cb) { setTimeout(() => cb("SIGNED_IN", session), 0); return { data: { subscription: { unsubscribe() {} } } }; },
      signOut: async () => ({ error: null }), signInWithPassword: async () => ({ error: null }), signInWithOtp: async () => ({ error: null }), signInWithIdToken: async () => ({ error: null })
    }
  };
};
