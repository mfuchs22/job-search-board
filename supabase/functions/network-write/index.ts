// network-write: the board's edits to networking contacts, written to Notion first, then mirrored.
//
// Notion's Network database is the home for contacts (2026-09-15). The page calls this function with the signed-in
// owner's session; it checks is_board_owner(), writes the change to Notion with the integration token (a function
// secret, never in git or the page), then upserts the page Notion returns into public.contacts so the board updates
// at once. The engine's morning pull (engine/network_notion.py) rewrites every row the same way.
//
//   POST {action: "update", id, fields: {status?, hook?, next_type?, next_action?, next_date?, last_type?, last_date?,
//                                         last_note?, priority?, roles?, notes?}}
//   POST {action: "done",   id, fields: {date, last_type?, last_note?, next_type?, next_action?, next_date?, status?}}
//        moves the next touch into the last touch (dated `date`, the page's local today), sets the new next touch,
//        and appends "YYYY-MM-DD · Type · note" to the "Touch log" list in the page body (the touch history)
//   POST {action: "create", fields: {name, company?, role?, how?, status?, hook?, next_type?, next_action?, next_date?, roles?}}
//
// Secrets: NOTION_TOKEN (required), NOTION_NETWORK_DS (the Network data source id). SUPABASE_URL,
// SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY are provided by the platform.
import { createClient } from "jsr:@supabase/supabase-js@2";

const NOTION = "https://api.notion.com/v1";
const VERSION = "2025-09-03";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
// page field -> Notion property name
const PROPS: Record<string, string> = {
  name: "Name", company: "Company", role: "Role", how: "How Connected", status: "Status", priority: "Priority",
  hook: "Hook", last_type: "Last Touch Type", last_date: "Last Touch Date", last_note: "Last Touch Note",
  next_type: "Next Touch Type", next_action: "Next Action", next_date: "Next Action Date",
  roles: "Job board roles", linkedin: "LinkedIn", notes: "Notes",
};
const EDITABLE = new Set(["status", "priority", "hook", "last_type", "last_date", "last_note", "next_type", "next_action",
  "next_date", "roles", "notes", "linkedin", "how"]);

const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });

async function notion(path: string, method = "GET", body?: unknown) {
  const r = await fetch(NOTION + path, {
    method,
    headers: { Authorization: `Bearer ${Deno.env.get("NOTION_TOKEN")}`, "Notion-Version": VERSION, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json();
  if (!r.ok) throw new Error(`notion ${r.status}: ${j.message ?? "error"}`);
  return j;
}

// A Notion property value as plain data. Keep in step with plain() in engine/network_notion.py.
// deno-lint-ignore no-explicit-any
function plain(p: any): any {
  if (!p) return null;
  const v = p[p.type];
  switch (p.type) {
    case "title": case "rich_text": return (v ?? []).map((x: { plain_text: string }) => x.plain_text).join("") || null;
    case "select": case "status": return v?.name ?? null;
    case "multi_select": return (v ?? []).map((o: { name: string }) => o.name).join(", ") || null;
    case "date": return v?.start ?? null;
    case "relation": return (v ?? []).map((x: { id: string }) => x.id);
    case "formula": return v?.[v?.type] ?? null;
    case "rollup": {
      if (!v) return null;
      if (v.type === "date") return v.date?.start ?? null;
      if (v.type === "number") return v.number;
      if (v.type === "array") { const vals = (v.array ?? []).map(plain).filter(Boolean).map(String).sort(); return vals.at(-1) ?? null; }
      return null;
    }
    default: return v ?? null;
  }
}

// One touch-log line, "YYYY-MM-DD · Type · note". Keep in step with TOUCH and touches() in engine/network_notion.py.
const TOUCH = /^(\d{4}-\d{2}-\d{2})\s+·\s+(.+?)(?:\s+·\s+(.*))?$/s;
type Touch = { date: string; type: string; note: string };
const richText = (s: string) => [{ text: { content: s.slice(0, 2000) } }];

// The touch log in a Network page body, newest first, and whether the "Touch log" heading is already there.
async function touchLog(id: string) {
  const touches: Touch[] = [];
  let hasHeading = false, cursor = "";
  while (true) {
    const res = await notion(`/blocks/${id}/children?page_size=100${cursor ? `&start_cursor=${cursor}` : ""}`);
    for (const b of res.results ?? []) {
      const text = (b[b.type]?.rich_text ?? []).map((x: { plain_text: string }) => x.plain_text).join("").trim();
      if (String(b.type).startsWith("heading") && text === "Touch log") hasHeading = true;
      const m = b.type === "bulleted_list_item" || b.type === "paragraph" ? TOUCH.exec(text) : null;
      if (m) touches.push({ date: m[1], type: m[2].trim(), note: (m[3] ?? "").trim() });
    }
    if (!res.has_more) break;
    cursor = res.next_cursor;
  }
  touches.sort((a, b) => b.date.localeCompare(a.date));
  return { touches, hasHeading };
}

// Keep in step with person() in engine/network_notion.py.
// deno-lint-ignore no-explicit-any
function normalize(page: any, touches: Touch[] = []) {
  const P = page.properties ?? {};
  const g = (k: string) => plain(P[k]);
  const roles = String(g("Job board roles") ?? "").split(/[\s,;]+/).filter((x) => /^[0-9a-f]{10}$/.test(x));
  return {
    id: page.id, url: page.url, name: g("Name"), company: g("Company"), role: g("Role"), how: g("How Connected"),
    status: g("Status"), priority: g("Priority"), hook: g("Hook"),
    last_type: g("Last Touch Type"), last_date: g("Last Touch Date"), last_note: g("Last Touch Note"),
    next_type: g("Next Touch Type"), next_action: g("Next Action"), next_date: g("Next Action Date"),
    linkedin: g("LinkedIn"), notes: g("Notes"), last_met: g("Last met"), roles, edited: page.last_edited_time,
    touches,
  };
}

// A page field value in the shape its Notion property type wants.
function propValue(type: string, value: unknown) {
  const s = value === null || value === undefined ? "" : Array.isArray(value) ? value.join(", ") : String(value).trim();
  switch (type) {
    case "title": return { title: [{ text: { content: s } }] };
    case "rich_text": return { rich_text: s ? [{ text: { content: s.slice(0, 2000) } }] : [] };
    case "select": return { select: s ? { name: s } : null };
    case "status": return { status: s ? { name: s } : null };
    case "multi_select": return { multi_select: s ? s.split(/\s*,\s*/).map((name) => ({ name })) : [] };
    case "date": return { date: /^\d{4}-\d{2}-\d{2}$/.test(s) ? { start: s } : null };
    case "url": return { url: s || null };
    default: throw new Error(`property type ${type} is not writable from the board`);
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return reply({ error: "POST only" }, 405);
  const url = Deno.env.get("SUPABASE_URL")!;
  const auth = req.headers.get("Authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return reply({ error: "sign in first" }, 401);
  const asUser = createClient(url, Deno.env.get("SUPABASE_ANON_KEY")!, { global: { headers: { Authorization: auth } } });
  const { data: owner, error: ownerErr } = await asUser.rpc("is_board_owner");
  if (ownerErr || owner !== true) return reply({ error: "not the board owner" }, 401);

  try {
    const { action, id, fields = {} } = await req.json();
    const ds = Deno.env.get("NOTION_NETWORK_DS");
    if (!ds) throw new Error("NOTION_NETWORK_DS is not set");
    const schema = await notion(`/data_sources/${ds}`);
    const types: Record<string, string> = Object.fromEntries(
      Object.entries(schema.properties ?? {}).map(([k, v]) => [k, (v as { type: string }).type]),
    );
    const properties: Record<string, unknown> = {};
    const put = (values: Record<string, unknown>, only?: Set<string>) => {
      for (const [field, value] of Object.entries(values)) {
        if (only && !only.has(field)) continue;
        const name = PROPS[field];
        if (!name || !types[name]) continue; // unknown field, or the property is missing in Notion
        properties[name] = propValue(types[name], value);
      }
    };
    let page;
    if (action === "update") {
      if (!id) throw new Error("update needs id");
      put(fields, EDITABLE);
      page = await notion(`/pages/${id}`, "PATCH", { properties });
    } else if (action === "done") {
      if (!id) throw new Error("done needs id");
      const cur = normalize(await notion(`/pages/${id}`));
      const date = /^\d{4}-\d{2}-\d{2}$/.test(String(fields.date ?? "")) ? String(fields.date) : new Date().toISOString().slice(0, 10);
      put({
        last_type: fields.last_type ?? cur.next_type ?? "",
        last_date: date,
        last_note: fields.last_note ?? cur.next_action ?? "",
        next_type: fields.next_type ?? "",
        next_action: fields.next_action ?? "",
        next_date: fields.next_date ?? "",
        ...(fields.status ? { status: fields.status } : {}),
      });
      page = await notion(`/pages/${id}`, "PATCH", { properties });
      const log = await touchLog(id);
      const line = [date, String(fields.last_type ?? cur.next_type ?? "").trim() || "Touch", String(fields.last_note ?? cur.next_action ?? "").trim()]
        .filter(Boolean).join(" · ");
      await notion(`/blocks/${id}/children`, "PATCH", {
        children: [
          ...(log.hasHeading || log.touches.length ? [] : [{ type: "heading_3", heading_3: { rich_text: richText("Touch log") } }]),
          { type: "bulleted_list_item", bulleted_list_item: { rich_text: richText(line) } },
        ],
      });
    } else if (action === "create") {
      if (!String(fields.name ?? "").trim()) throw new Error("a new person needs a name");
      put(fields);
      page = await notion(`/pages`, "POST", { parent: { type: "data_source_id", data_source_id: ds }, properties });
    } else {
      throw new Error(`unknown action ${action}`);
    }
    const contact = normalize(page, action === "create" ? [] : (await touchLog(page.id)).touches);
    const admin = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const { error } = await admin.from("contacts").upsert({ id: contact.id, payload: contact, updated_at: new Date().toISOString() });
    if (error) throw new Error(`saved to Notion, mirror failed: ${error.message}`);
    return reply({ contact });
  } catch (e) {
    return reply({ error: e instanceof Error ? e.message : String(e) }, 400);
  }
});
