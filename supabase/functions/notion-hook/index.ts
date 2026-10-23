// notion-hook: Notion → board mirror, in the cloud.
//
// A webhook (page created, properties or content updated, deleted, undeleted, moved) is
// signature-checked, then the page is fetched and written to contacts, opportunities,
// meetings or tasks. The row is planPage() in _shared/notion_mirror.ts, the same shape as
// engine/notion_mirror.py (the 04:30 rebuild). A write whose last_edited_time is strictly
// older than the stored updated_at is skipped, so a retry or an out-of-order delivery is safe.
// The fetch is always the current page: an old event does not replay old content.
//
// pg_cron calls this function every 5 minutes with {"mode":"reconcile"} and the header
// x-reconcile-secret. That pass queries the four data sources for pages edited since
// notion_mirror_state.watermark and applies the same row. The morning refresh stays the
// full rebuild, including deletes a query cannot see.
//
// The subscription handshake is {verification_token} and has no signature. The token is
// stored on notion_mirror_state and not echoed. the owner reads it in the SQL editor.
//
// Deploy: supabase functions deploy notion-hook --no-verify-jwt --use-api
// Secrets: NOTION_TOKEN, NOTION_NETWORK_DS, NOTION_OPPS_DS, NOTION_MEETINGS_DS,
// NOTION_TASKS_DS, NOTION_WEBHOOK_SECRET, NOTION_RECONCILE_SECRET.
// NOTION_COMPANIES_DS is not used; a company name is read from the related page.
import { createClient } from "jsr:@supabase/supabase-js@2";
import { timingSafeEqualStr, verifyNotionSignature } from "../_shared/notion_signature.ts";
import {
  editedFilter,
  idForms,
  olderThan,
  parseTs,
  planPage,
  plain,
  reconcileNext,
  reconcileSince,
  sourceKind,
  todayUtc,
  touchesFromBlocks,
  validPageId,
} from "../_shared/notion_mirror.ts";

const NOTION = "https://api.notion.com/v1";
const VERSION = "2025-09-03";
const MAX_BODY = 256_000;
const ACT = new Set([
  "page.created",
  "page.properties_updated",
  "page.content_updated",
  "page.deleted",
  "page.undeleted",
  "page.moved",
]);

const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let lastCall = 0;

function db() {
  return createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function sourceList(): { env: string; id: string; kind: string }[] {
  const spec = [
    ["NOTION_NETWORK_DS", "contacts"],
    ["NOTION_OPPS_DS", "opportunities"],
    ["NOTION_MEETINGS_DS", "meetings"],
    ["NOTION_TASKS_DS", "tasks"],
  ] as const;
  return spec.map(([env, kind]) => {
    const id = Deno.env.get(env) ?? "";
    if (!id) throw new Error(`${env} is not set`);
    return { env, id, kind };
  });
}

async function notion(path: string, method = "GET", body?: unknown): Promise<{ status: number; json: any }> {
  const token = Deno.env.get("NOTION_TOKEN");
  if (!token) throw new Error("NOTION_TOKEN is not set");
  let last = 0;
  for (let attempt = 0; attempt < 3; attempt++) {
    const wait = 120 - (Date.now() - lastCall);
    if (wait > 0) await delay(wait);
    lastCall = Date.now();
    const res = await fetch(NOTION + path, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        "Notion-Version": VERSION,
        "Content-Type": "application/json",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 429 || res.status >= 500) {
      last = res.status;
      if (attempt < 2) {
        await delay(Math.min(Number(res.headers.get("retry-after") || 2 ** attempt), 4) * 1000);
        continue;
      }
      throw new Error(`notion HTTP ${res.status}`);
    }
    const text = await res.text();
    let json: any = null;
    if (text) {
      try {
        json = JSON.parse(text);
      } catch {
        json = null;
      }
    }
    return { status: res.status, json };
  }
  throw new Error(`notion HTTP ${last}`);
}

async function blocks(pageId: string): Promise<unknown[]> {
  const out: unknown[] = [];
  let cursor: string | null = null;
  for (let i = 0; i < 10; i++) {
    const q = cursor ? `&start_cursor=${encodeURIComponent(cursor)}` : "";
    const { status, json } = await notion(`/blocks/${pageId}/children?page_size=100${q}`);
    if (status === 404) return out;
    if (status !== 200) throw new Error(`notion blocks HTTP ${status}`);
    out.push(...(json?.results || []));
    if (!json?.has_more) return out;
    cursor = json.next_cursor || null;
    if (!cursor) return out;
  }
  throw new Error("notion blocks truncated");
}

async function companyName(pageId: string): Promise<string | null> {
  const { status, json } = await notion(`/pages/${pageId}`);
  if (status === 404) return null;
  if (status !== 200) throw new Error(`notion company HTTP ${status}`);
  const name = plain(json?.properties?.Name);
  return typeof name === "string" ? name : null;
}

async function readMatch(table: string, column: string, pageId: string) {
  let best: { id?: string; updated_at?: string; payload?: Record<string, unknown> } | null = null;
  let bestMs = -Infinity;
  for (const form of idForms(pageId)) {
    const { data, error } = await db().from(table).select("id,updated_at,payload").eq(column, form).limit(1);
    if (error) throw new Error(`${table} read failed`);
    const row = data?.[0];
    if (!row) continue;
    const ms = parseTs(row.updated_at) ?? 0;
    if (!best || ms >= bestMs) {
      best = row;
      bestMs = ms;
    }
  }
  return best;
}

async function deleteIds(table: string, pageId: string) {
  for (const form of idForms(pageId)) {
    const { error } = await db().from(table).delete().eq("id", form);
    if (error) throw new Error(`${table} delete failed`);
  }
}

async function deletePageIds(pageId: string, keepId?: string) {
  for (const form of idForms(pageId)) {
    let q = db().from("opportunities").delete().eq("page_id", form);
    if (keepId) q = q.neq("id", keepId);
    const { error } = await q;
    if (error) throw new Error("opportunities delete failed");
  }
}

async function deleteSiblings(keep: string, pageId: string) {
  for (const table of ["contacts", "meetings", "tasks"]) {
    if (table !== keep) await deleteIds(table, pageId);
  }
  if (keep !== "opportunities") await deletePageIds(pageId);
}

/** Drop the page from every mirror table unless that row is newer than `clock`. */
async function dropIfCurrent(pageId: string, clock: unknown) {
  for (const table of ["contacts", "meetings", "tasks"]) {
    const row = await readMatch(table, "id", pageId);
    if (olderThan(clock, row?.updated_at)) continue;
    await deleteIds(table, pageId);
  }
  const opp = await readMatch("opportunities", "page_id", pageId);
  if (!olderThan(clock, opp?.updated_at)) await deletePageIds(pageId);
}

async function applyPlan(plan: {
  kind: string;
  table: string | null;
  row: Record<string, unknown> | null;
  page_id: string | null;
}) {
  if (plan.kind === "skip" || !plan.table || !plan.page_id) return;
  if (plan.kind === "delete") {
    if (plan.table === "opportunities") await deletePageIds(plan.page_id);
    else await deleteIds(plan.table, plan.page_id);
    await deleteSiblings(plan.table, plan.page_id);
    return;
  }
  const row = plan.row!;
  const body: Record<string, unknown> = { id: row.id, payload: row.payload, updated_at: row.updated_at };
  if (plan.table === "opportunities") body.page_id = row.page_id;
  const { error } = await db().from(plan.table).upsert(body);
  if (error) throw new Error(`${plan.table} upsert failed`);
  if (plan.table === "opportunities") await deletePageIds(plan.page_id, String(row.id));
  await deleteSiblings(plan.table, plan.page_id);
}

async function mirrorPage(page: Record<string, unknown>, kind: string) {
  if (!validPageId(page.id)) {
    return { kind: "skip", table: null, row: null, page_id: page.id ?? null, reason: "bad page id" };
  }
  const pageId = page.id as string;
  const stored = await readMatch(kind === "opportunities" ? "opportunities" : kind,
    kind === "opportunities" ? "page_id" : "id", pageId);
  // Compare before any further Notion reads. Equal is not older: a retry rewrites the same row.
  if (olderThan(page.last_edited_time, stored?.updated_at)) {
    return { kind: "skip", table: kind, row: null, page_id: pageId, reason: "stale" };
  }
  const trashed = Boolean(page.in_trash || page.archived);
  let touches: { date: string; type: string; note: string }[] | null = null;
  let names: Record<string, string | null> = {};
  if (!trashed && kind === "contacts") touches = touchesFromBlocks(await blocks(pageId));
  if (!trashed && kind === "opportunities") {
    const co = plain((page.properties as Record<string, unknown> | undefined)?.Company);
    const companyId = Array.isArray(co) && typeof co[0] === "string" ? co[0] : "";
    if (companyId) names[companyId] = await companyName(companyId);
  }
  const plan = planPage(page, kind, {
    touches,
    company_names: names,
    live_opp: (stored?.payload as Record<string, unknown>) ?? null,
    vault_opp: null,
    today: todayUtc(Date.now()),
    built: (page.last_edited_time as string) || new Date().toISOString(),
  });
  await applyPlan(plan);
  return plan;
}

async function runReconcile() {
  const list = sourceList();
  const { data, error } = await db().from("notion_mirror_state").select("watermark").eq("id", 1).limit(1);
  if (error) throw new Error("watermark read failed");
  const now = Date.now();
  const since = reconcileSince(data?.[0]?.watermark ?? null, now);
  const sources: { has_more: boolean; newest: string | null }[] = [];
  let upserts = 0, deletes = 0, skipped = 0;
  for (const src of list) {
    const { status, json } = await notion(`/data_sources/${src.id}/query`, "POST", editedFilter(since));
    if (status !== 200) throw new Error(`notion query HTTP ${status}`);
    const results = (json?.results || []) as Record<string, unknown>[];
    let newest: string | null = null;
    let newestMs = -Infinity;
    for (const page of results) {
      const plan = await mirrorPage(page, src.kind);
      if (plan.kind === "upsert") upserts++;
      else if (plan.kind === "delete") deletes++;
      else skipped++;
      const ms = parseTs(page.last_edited_time);
      if (ms != null && ms >= newestMs) {
        newestMs = ms;
        newest = page.last_edited_time as string;
      }
    }
    sources.push({ has_more: Boolean(json?.has_more), newest });
  }
  const next = reconcileNext(sources, now, since);
  if (!next) throw new Error("reconcile cursor missing");
  const watermark = await saveWatermark(data?.[0]?.watermark ?? null, next);
  console.log(`notion-hook reconcile upserts=${upserts} deletes=${deletes} skipped=${skipped}`);
  return { ok: true, upserts, deletes, skipped, watermark };
}

/** Don't let a slow pass rewind a cursor a later pass already moved forward. */
async function saveWatermark(seen: unknown, next: string): Promise<string> {
  const { data, error } = await db().from("notion_mirror_state").select("watermark").eq("id", 1).limit(1);
  if (error) throw new Error("watermark read failed");
  const current = data?.[0]?.watermark ?? null;
  const currentMs = parseTs(current);
  const seenMs = parseTs(seen);
  const nextMs = parseTs(next);
  if (currentMs != null && nextMs != null && currentMs > nextMs && (seenMs == null || currentMs > seenMs)) {
    return typeof current === "string" ? current : new Date(currentMs).toISOString();
  }
  const { error: writeError } = await db().from("notion_mirror_state").upsert({
    id: 1,
    watermark: next,
    updated_at: new Date().toISOString(),
  });
  if (writeError) throw new Error("watermark upsert failed");
  return next;
}

async function runEvent(body: Record<string, unknown>) {
  const type = typeof body.type === "string" ? body.type : "";
  if (!ACT.has(type)) return { ok: true, skipped: "event type" };
  const entity = body.entity as { id?: unknown } | undefined;
  const entityId = typeof entity?.id === "string" ? entity.id : "";
  if (!idForms(entityId).length) return { ok: true, skipped: "bad page id" };
  const got = await notion(`/pages/${entityId}`);
  if (got.status === 404) {
    await dropIfCurrent(entityId, body.timestamp);
    return { ok: true, action: "delete", reason: "missing" };
  }
  if (got.status !== 200 || !got.json?.id) throw new Error(`notion page HTTP ${got.status}`);
  const page = got.json as Record<string, unknown>;
  const sources: Record<string, string> = {};
  for (const src of sourceList()) sources[src.id] = src.kind;
  const kind = sourceKind(page, sources);
  if (!kind) {
    if (type === "page.deleted" || type === "page.moved") {
      await dropIfCurrent(entityId, page.last_edited_time ?? body.timestamp);
      return { ok: true, action: "delete", reason: "left the board" };
    }
    return { ok: true, skipped: "other database" };
  }
  const plan = await mirrorPage(page, kind);
  return { ok: true, action: plan.kind, table: plan.table, reason: plan.reason };
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return reply({ error: "POST only" }, 405);
  const bytes = new Uint8Array(await req.arrayBuffer());
  if (bytes.byteLength > MAX_BODY) return reply({ error: "body too large" }, 413);
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return reply({ error: "not json" }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) return reply({ error: "not an object" }, 400);

  // Handshake. The token is not returned and not logged. A watermark upsert must not clear it,
  // and this upsert must not clear the watermark: both send only their own columns.
  if (typeof body.verification_token === "string" && body.verification_token && !body.type && body.mode !== "reconcile") {
    const { error } = await db().from("notion_mirror_state").upsert({
      id: 1,
      verification_token: body.verification_token,
      updated_at: new Date().toISOString(),
    });
    if (error) return reply({ error: "could not store the verification token" }, 500);
    console.log("notion-hook: verification token stored");
    return reply({ ok: true });
  }

  if (body.mode === "reconcile") {
    const secret = Deno.env.get("NOTION_RECONCILE_SECRET") ?? "";
    const got = req.headers.get("x-reconcile-secret") ?? "";
    if (!secret || !timingSafeEqualStr(got, secret)) return reply({ error: "bad reconcile secret" }, 401);
    try {
      return reply(await runReconcile());
    } catch {
      console.log("notion-hook reconcile failed");
      return reply({ error: "mirror failed" }, 500);
    }
  }

  const secret = Deno.env.get("NOTION_WEBHOOK_SECRET") ?? "";
  if (!secret) return reply({ error: "NOTION_WEBHOOK_SECRET is not set" }, 401);
  const trusted = await verifyNotionSignature(bytes, req.headers.get("x-notion-signature"), secret);
  if (!trusted) return reply({ error: "bad signature" }, 401);
  try {
    return reply(await runEvent(body));
  } catch {
    console.log("notion-hook event failed");
    return reply({ error: "mirror failed" }, 500);
  }
});
