// The Supabase row for one Notion page. Keep in step with engine/notion_mirror.py
// (network_notion.person, notion_sync.opportunity / meeting / task, plan_page).
// tests/test_notion_mirror.py runs the same pages through both and fails if a row differs.
//
// This file is pure: no Deno, no network. notion-hook fetches the page and applies `planPage`.
// `updated_at` is the page's last_edited_time when present. A write is stale only when that
// instant is strictly older than the stored updated_at (see olderThan).

export const TABLES = ["contacts", "opportunities", "meetings", "tasks"] as const;
export const PAGE_CAP = 20;
const FIRST_LOOKBACK_MS = 6 * 60 * 60 * 1000;
const CAUGHT_UP_LAG_MS = 2 * 60 * 1000;

const PAGE_ID = /^[0-9a-fA-F]{32}$|^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const TOUCH = /^(\d{4}-\d{2}-\d{2})\s+·\s+(.+?)(?:\s+·\s+(.*))?$/s;

const STAGE: Record<string, string> = {
  Shortlist: "shortlist", Researching: "researching", Outreach: "outreach", Applied: "applied",
  Interviewing: "interviewing", Offer: "offer", Closed: "closed",
};
const OUTCOME: Record<string, string> = {
  "No response": "no_response", Rejected: "rejected", Withdrew: "withdrew", Accepted: "accepted",
  "Posting removed": "posting_removed",
};
const HP: Record<string, string | null> = {
  "Warm active": "warm active", "Warm reachable": "warm reachable", Cold: "cold", Unchecked: null,
};
const LANE: Record<string, string> = { Active: "active", Bench: "bench", Paused: "paused" };
const BALL: Record<string, string> = { the owner: "owner", Claude: "claude", Them: "them" };

type Obj = Record<string, unknown>;
type Touch = { date: string; type: string; note: string };
type Plan = {
  kind: "upsert" | "delete" | "skip";
  table: string | null;
  row: Obj | null;
  page_id: string | null;
  reason: string;
};

/** Python truthiness, so an empty dict or list falls through the same way `or` does. */
function pyTruthy(value: unknown): boolean {
  if (value == null || value === false || value === 0 || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value as Obj).length > 0;
  return true;
}

function mapped(table: Record<string, string | null>, value: unknown): string | null {
  if (typeof value !== "string" || !Object.prototype.hasOwnProperty.call(table, value)) return null;
  return table[value];
}

/** A Notion property as plain data. Keep in step with notion.plain. */
export function plain(prop: unknown): unknown {
  if (!pyTruthy(prop)) return null;
  const p = prop as Obj;
  const t = p.type as string | undefined;
  const v = t ? p[t] : null;
  if (t === "title" || t === "rich_text") {
    const s = ((v as Obj[]) || []).map((x) => (x?.plain_text as string) ?? "").join("");
    return s || null;
  }
  if (t === "select" || t === "status") return (v as Obj | null)?.name ?? null;
  if (t === "multi_select") {
    const s = ((v as Obj[]) || []).map((o) => o.name as string).join(", ");
    return s || null;
  }
  if (t === "date") return (v as Obj | null)?.start ?? null;
  if (t === "relation") return ((v as Obj[]) || []).map((x) => x.id);
  if (t === "formula") {
    const f = (v as Obj) || {};
    const ft = f.type as string | undefined;
    return ft && Object.prototype.hasOwnProperty.call(f, ft) ? f[ft] : null;
  }
  if (t === "rollup") {
    const r = (v as Obj) || {};
    if (r.type === "date") return (r.date as Obj | null)?.start ?? null;
    if (r.type === "number") return r.number ?? null;
    if (r.type === "array") {
      const vals = ((r.array as unknown[]) || [])
        .map((item) => plain(item))
        .filter((x) => pyTruthy(x))
        .map((x) => String(x))
        .sort();
      return vals.length ? vals[vals.length - 1] : null;
    }
    return null;
  }
  return v ?? null;
}

export function parseTouch(text: string): Touch | null {
  const m = TOUCH.exec((text || "").trim());
  if (!m) return null;
  return { date: m[1], type: m[2].trim(), note: (m[3] || "").trim() };
}

/** Touch-log lines in page blocks, newest first. Keep in step with network_notion.touches_from_blocks. */
export function touchesFromBlocks(blocks: unknown[] | null | undefined): Touch[] {
  const out: Touch[] = [];
  for (const block of blocks || []) {
    const b = block as Obj;
    const kind = b.type as string;
    if (kind !== "bulleted_list_item" && kind !== "paragraph") continue;
    const rich = ((b[kind] as Obj | undefined)?.rich_text as Obj[]) || [];
    const text = rich.map((x) => (x?.plain_text as string) ?? "").join("");
    const touch = parseTouch(text);
    if (touch) out.push(touch);
  }
  out.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  return out;
}

function prop(page: Obj, name: string): unknown {
  const properties = (page.properties as Obj) || {};
  return plain(properties[name]);
}

function rel(value: unknown): unknown[] {
  return Array.isArray(value) && value.length ? value : [];
}

/** Keep in step with network_notion.person. Touches are added by planPage. */
export function person(page: Obj): Obj {
  const g = (name: string) => prop(page, name);
  const roles = String(g("Job board roles") || "")
    .replaceAll(";", ",")
    .replaceAll(" ", ",")
    .split(",")
    .filter((x) => x.length === 10 && [...x].every((c) => "0123456789abcdef".includes(c)));
  return {
    id: page.id, url: page.url ?? null, name: g("Name"), company: g("Company"), role: g("Role"),
    how: g("How Connected"), status: g("Status"), priority: g("Priority"), hook: g("Hook"),
    last_type: g("Last Touch Type"), last_date: g("Last Touch Date"), last_note: g("Last Touch Note"),
    next_type: g("Next Touch Type"), next_action: g("Next Action"), next_date: g("Next Action Date"),
    linkedin: g("LinkedIn"), notes: g("Notes"), last_met: g("Last met"),
    check_before: g("Check Before Applying"), roles, edited: page.last_edited_time ?? null,
  };
}

/** Keep in step with notion_sync.opportunity. */
export function opportunity(page: Obj, companyNames: Record<string, string | null>): Obj {
  const g = (name: string) => prop(page, name);
  const co = rel(g("Company"));
  const company = co.length ? co[0] as string : null;
  return {
    id: g("Job ID"), page: page.id, url: page.url ?? null,
    stage: mapped(STAGE, g("Stage")), outcome: mapped(OUTCOME, g("Outcome")),
    next: g("Next Step"), next_date: g("Next Step Date"),
    hp: mapped(HP, g("Human Path")), hp_people: g("Human Path People"), flag: Boolean(g("Flag")),
    lane: mapped(LANE, g("Lane")), ball: mapped(BALL, g("Ball")),
    company, company_name: company ? (companyNames[company] ?? null) : null,
    people: rel(g("People")), meetings: rel(g("Meetings")), tasks: rel(g("Tasks")),
    edited: page.last_edited_time ?? null,
  };
}

/** Keep in step with notion_sync.meeting. `edited` is the clock olderThan compares. */
export function meeting(page: Obj): Obj {
  const g = (name: string) => prop(page, name);
  return {
    id: page.id, url: page.url ?? null, name: g("Name"), date: g("Date"), type: g("Type"),
    summary: g("Summary"), actions: g("Action Items"), status: g("Follow-up Status"),
    people: rel(g("People")), companies: rel(g("Company")), opps: rel(g("Opportunities")),
    edited: page.last_edited_time ?? null,
  };
}

/** Keep in step with notion_sync.task. */
export function task(page: Obj): Obj {
  const g = (name: string) => prop(page, name);
  return {
    id: page.id, url: page.url ?? null, title: g("Task"), status: g("Status"), area: g("Area"),
    priority: g("Priority"), due: g("Due"), plan_day: g("Plan day"), waiting: g("Waiting on"),
    project: g("Project"), notes: g("Notes"), opps: rel(g("Opportunities")),
    meetings: rel(g("Meeting")), edited: page.last_edited_time ?? null,
  };
}

export function taskOnBoard(payload: Obj): boolean {
  return payload.area === "career" && payload.status !== "Complete" && payload.project !== "Consulting";
}

export function carryLaneSince(opp: Obj, live: Obj | null, vault: Obj | null, today: string): Obj {
  const was = (pyTruthy(live) ? live : {}) as Obj;
  if (was.lane === opp.lane && pyTruthy(was.lane_since)) {
    opp.lane_since = was.lane_since;
    return opp;
  }
  const remembered = (pyTruthy(vault) ? vault : {}) as Obj;
  if (remembered.lane === opp.lane && pyTruthy(remembered.lane_since)) {
    opp.lane_since = remembered.lane_since;
    return opp;
  }
  if (pyTruthy(live) && was.lane === opp.lane) return opp;
  opp.lane_since = today;
  return opp;
}

export function normId(value: unknown): string {
  return String(value ?? "").replaceAll("-", "").toLowerCase();
}

export function sourceKind(page: Obj, sources: Record<string, string> | null): string | null {
  const parent = (page.parent as Obj) || {};
  const by = new Map<string, string>();
  for (const [key, value] of Object.entries(sources || {})) by.set(normId(key), value);
  for (const key of ["data_source_id", "database_id"]) {
    const kind = by.get(normId(parent[key]));
    if (kind) return kind;
  }
  return null;
}

export function validPageId(value: unknown): boolean {
  return typeof value === "string" && PAGE_ID.test(value);
}

export function idForms(pageId: unknown): string[] {
  if (!validPageId(pageId)) return [];
  const id = pageId as string;
  const raw = id.replaceAll("-", "").toLowerCase();
  const dashed = `${raw.slice(0, 8)}-${raw.slice(8, 12)}-${raw.slice(12, 16)}-${raw.slice(16, 20)}-${raw.slice(20)}`;
  const out: string[] = [];
  for (const form of [id, dashed, raw]) if (!out.includes(form)) out.push(form);
  return out;
}

function clock(payload: Obj, built: string): string {
  return (payload.edited as string) || built;
}

export function planPage(page: Obj, kind: string | null, opt: {
  touches?: Touch[] | null;
  company_names?: Record<string, string | null> | null;
  live_opp?: Obj | null;
  vault_opp?: Obj | null;
  today: string;
  built: string;
}): Plan {
  const pageId = (page.id as string) ?? null;
  if (!validPageId(pageId)) {
    return { kind: "skip", table: null, row: null, page_id: pageId, reason: "bad page id" };
  }
  if (page.in_trash || page.archived) {
    return { kind: "delete", table: kind, row: null, page_id: pageId, reason: "trashed" };
  }
  if (kind === "contacts") {
    const payload = person(page);
    const touches = [...(opt.touches || [])];
    touches.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
    payload.touches = touches;
    const row = { id: payload.id, payload, updated_at: clock(payload, opt.built) };
    return { kind: "upsert", table: "contacts", row, page_id: pageId, reason: "contact" };
  }
  if (kind === "meetings") {
    const payload = meeting(page);
    const row = { id: payload.id, payload, updated_at: clock(payload, opt.built) };
    return { kind: "upsert", table: "meetings", row, page_id: pageId, reason: "meeting" };
  }
  if (kind === "tasks") {
    const payload = task(page);
    if (!taskOnBoard(payload)) {
      return { kind: "delete", table: "tasks", row: null, page_id: pageId, reason: "not an open career task" };
    }
    const row = { id: payload.id, payload, updated_at: clock(payload, opt.built) };
    return { kind: "upsert", table: "tasks", row, page_id: pageId, reason: "task" };
  }
  if (kind === "opportunities") {
    const payload = opportunity(page, opt.company_names || {});
    if (!pyTruthy(payload.id)) {
      return { kind: "delete", table: "opportunities", row: null, page_id: pageId, reason: "no job id" };
    }
    carryLaneSince(payload, opt.live_opp ?? null, opt.vault_opp ?? null, opt.today);
    const row = { id: payload.id, page_id: payload.page, payload, updated_at: clock(payload, opt.built) };
    return { kind: "upsert", table: "opportunities", row, page_id: pageId, reason: "opportunity" };
  }
  return { kind: "skip", table: null, row: null, page_id: pageId, reason: "unknown database" };
}

export function parseTs(value: unknown): number | null {
  if (value == null || value === "") return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const ms = Date.parse(String(value));
  return Number.isNaN(ms) ? null : ms;
}

export function isoMs(ms: number): string {
  return new Date(ms).toISOString();
}

export function olderThan(incoming: unknown, stored: unknown): boolean {
  const a = parseTs(incoming);
  const b = parseTs(stored);
  if (a == null || b == null) return false;
  return a < b;
}

export function reconcileSince(watermark: unknown, now: unknown): string {
  const nowMs = parseTs(now);
  if (nowMs == null) throw new Error("reconcile now");
  const mark = parseTs(watermark);
  if (mark == null) return isoMs(nowMs - FIRST_LOOKBACK_MS);
  return isoMs(mark);
}

export function reconcileNext(
  sources: { has_more?: boolean; newest?: unknown }[],
  now: unknown,
  since?: unknown,
): string | null {
  const nowMs = parseTs(now);
  if (nowMs == null) throw new Error("reconcile now");
  const incomplete = sources.filter((s) => s.has_more);
  if (incomplete.length) {
    const times: number[] = [];
    for (const s of incomplete) {
      const t = parseTs(s.newest);
      if (t == null) return null;
      times.push(t);
    }
    let next = Math.min(...times);
    const floor = parseTs(since);
    if (floor != null && next <= floor) next = floor + 1;
    return isoMs(next);
  }
  return isoMs(nowMs - CAUGHT_UP_LAG_MS);
}

export function editedFilter(since: string): Obj {
  return {
    page_size: PAGE_CAP,
    filter: { timestamp: "last_edited_time", last_edited_time: { on_or_after: since } },
    sorts: [{ timestamp: "last_edited_time", direction: "ascending" }],
  };
}

export function todayUtc(nowMs: number): string {
  return new Date(nowMs).toISOString().slice(0, 10);
}
