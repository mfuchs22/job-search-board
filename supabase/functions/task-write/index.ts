// task-write: the board's edits to a career task, written to Notion first, then mirrored.
//
// Notion's Tasks database is the only task list (2026-09-06). The To-dos tab (2026-09-22) shows the career tasks
// beside role next steps and people touches; Done and the snoozes here change the Notion page and nothing else.
// The page calls this function with the signed-in owner's session; it checks is_board_owner(), writes to Notion
// with the integration token (a function secret, never in git or the page), then upserts the page Notion returns
// into public.tasks so the board updates at once. The engine's morning pull (engine/notion_sync.py) rewrites every
// row the same way and drops the completed ones.
//
//   POST {action: "done",   id}                          Status = Complete
//   POST {action: "update", id, fields: {plan_day?, due?, status?}}
//        Today, Tomorrow and Next week write Plan day only, never Due: Due is the real deadline, Plan day is the day
//        the owner intends to do it (the rule /plan-week and the Task Board's Week tab follow, 2026-09-21). Later sends
//        plan_day "" and due null, clearing both (the owner, 2026-09-22: "you can't remove a due date and there are some
//        that I just don't even want to put a due date on"); `due` is only ever cleared here, never set.
//
// Secrets: NOTION_TOKEN (required), NOTION_TASKS_DS (the Tasks data source id). SUPABASE_URL, SUPABASE_ANON_KEY
// and SUPABASE_SERVICE_ROLE_KEY are provided by the platform.
import { createClient } from "jsr:@supabase/supabase-js@2";

const NOTION = "https://api.notion.com/v1";
const VERSION = "2025-09-03";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
// page field -> Notion property name
const PROPS: Record<string, string> = { plan_day: "Plan day", due: "Due", status: "Status" };
const STATUSES = new Set(["To Do", "In Progress", "Complete"]);

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

// A Notion property value as plain data. Keep in step with plain() in engine/notion.py.
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
    default: return v ?? null;
  }
}

// Keep in step with task() in engine/notion_sync.py.
// deno-lint-ignore no-explicit-any
function normalize(page: any) {
  const P = page.properties ?? {};
  const g = (k: string) => plain(P[k]);
  return {
    id: page.id, url: page.url, title: g("Task"), status: g("Status"), area: g("Area"), priority: g("Priority"),
    due: g("Due"), plan_day: g("Plan day"), waiting: g("Waiting on"), project: g("Project"), notes: g("Notes"),
    opps: g("Opportunities") ?? [], meetings: g("Meeting") ?? [], edited: page.last_edited_time,
  };
}

function propValue(type: string, value: unknown) {
  const s = value === null || value === undefined ? "" : String(value).trim();
  switch (type) {
    case "select": return { select: s ? { name: s } : null };
    case "status": return { status: s ? { name: s } : null };
    case "date": return { date: /^\d{4}-\d{2}-\d{2}$/.test(s) ? { start: s } : null };
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
    if (!id) throw new Error(`${action} needs id`);
    const ds = Deno.env.get("NOTION_TASKS_DS");
    if (!ds) throw new Error("NOTION_TASKS_DS is not set");
    const schema = await notion(`/data_sources/${ds}`);
    const types: Record<string, string> = Object.fromEntries(
      Object.entries(schema.properties ?? {}).map(([k, v]) => [k, (v as { type: string }).type]),
    );
    const properties: Record<string, unknown> = {};
    const put = (values: Record<string, unknown>) => {
      for (const [field, value] of Object.entries(values)) {
        const name = PROPS[field];
        if (!name || !types[name]) continue; // unknown field, or the property is missing in Notion
        properties[name] = propValue(types[name], value);
      }
    };
    if (action === "done") put({ status: "Complete" });
    else if (action === "update") {
      if (fields.status !== undefined && !STATUSES.has(String(fields.status))) throw new Error(`status ${fields.status} is not one of Notion's`);
      if (fields.due !== undefined && fields.due !== null && fields.due !== "") throw new Error("the board never sets Due, only clears it");
      put({ ...(fields.plan_day !== undefined ? { plan_day: fields.plan_day } : {}), ...(fields.due !== undefined ? { due: "" } : {}), ...(fields.status !== undefined ? { status: fields.status } : {}) });
    } else throw new Error(`unknown action ${action}`);
    if (!Object.keys(properties).length) throw new Error("nothing to write");
    const page = await notion(`/pages/${id}`, "PATCH", { properties });
    const task = normalize(page);
    const admin = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const { error } = await admin.from("tasks").upsert({ id: task.id, payload: task, updated_at: new Date().toISOString() });
    if (error) throw new Error(`saved to Notion, mirror failed: ${error.message}`);
    return reply({ task });
  } catch (e) {
    return reply({ error: e instanceof Error ? e.message : String(e) }, 400);
  }
});
