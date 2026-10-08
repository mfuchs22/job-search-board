// opportunity-write: the board's edits to a Pursue role, written to Notion first, then mirrored.
//
// Notion's Opportunities database is the home for a Pursue role's process state (2026-09-17): stage, outcome, next
// step, human path, and the links to people, meetings, tasks and its company. The page calls this function with the
// signed-in owner's session; it checks is_board_owner(), writes to Notion with the integration token (a function
// secret, never in git or the page), then upserts what Notion returns into public.opportunities so the board updates
// at once. The engine's morning pull (engine/notion_sync.py) rewrites every row the same way.
//
//   POST {action: "promote", id, fields: {title, company, score?, location?, url?, verdict_date?, flag?}}
//        the verdict just became Pursue: create the page (Stage Shortlist) and link or create its company
//   POST {action: "update",  id, fields: {stage?, outcome?, next?, next_date?, hp?, hp_people?, flag?}}
//   POST {action: "close",   id, fields: {outcome?}}          no longer a Pursue: Stage Closed, Outcome Withdrew
//   POST {action: "link" | "unlink", id, kind: "person"|"meeting"|"task"|"company", target: "<notion page id>"}
//
// `id` is always the board record id (jobs.id); the Notion page is found by its "Job ID" property.
// Secrets: NOTION_TOKEN, NOTION_OPPS_DS, NOTION_COMPANIES_DS. SUPABASE_URL, SUPABASE_ANON_KEY and
// SUPABASE_SERVICE_ROLE_KEY are provided by the platform.
import { createClient } from "jsr:@supabase/supabase-js@2";

const NOTION = "https://api.notion.com/v1";
const VERSION = "2025-09-03";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
// Keep these maps in step with STAGE / OUTCOME / HP in engine/notion_sync.py.
const STAGE: Record<string, string> = {
  shortlist: "Shortlist", researching: "Researching", outreach: "Outreach", applied: "Applied",
  interviewing: "Interviewing", offer: "Offer", closed: "Closed",
};
const OUTCOME: Record<string, string> = {
  no_response: "No response", rejected: "Rejected", withdrew: "Withdrew", accepted: "Accepted",
  posting_removed: "Posting removed",   // the ad was filled or taken down, confirmed on the board (2026-10-06)
};
const HP: Record<string, string> = {
  "warm active": "Warm active", "warm reachable": "Warm reachable", cold: "Cold", unchecked: "Unchecked",
};
const REL: Record<string, string> = { person: "People", meeting: "Meetings", task: "Tasks", company: "Company" };

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
    case "date": return v?.start ?? null;
    case "relation": return (v ?? []).map((x: { id: string }) => x.id);
    case "checkbox": return !!v;
    default: return v ?? null;
  }
}

const rich = (s: string) => (s ? [{ text: { content: s.slice(0, 2000) } }] : []);
const flip = (m: Record<string, string>, v: unknown) => m[String(v ?? "").toLowerCase()] ?? null;
const unflip = (m: Record<string, string>, name: unknown) =>
  Object.entries(m).find(([, v]) => v === name)?.[0] ?? null;

// Keep in step with opportunity() in engine/notion_sync.py. company_name is filled by the caller when known.
// deno-lint-ignore no-explicit-any
function normalize(page: any, companyName: string | null = null) {
  const P = page.properties ?? {};
  const g = (k: string) => plain(P[k]);
  const co = g("Company") ?? [];
  return {
    id: g("Job ID"), page: page.id, url: page.url,
    stage: unflip(STAGE, g("Stage")), outcome: unflip(OUTCOME, g("Outcome")),
    next: g("Next Step"), next_date: g("Next Step Date"),
    hp: g("Human Path") === "Unchecked" ? null : unflip(HP, g("Human Path")),
    hp_people: g("Human Path People"), flag: !!g("Flag"),
    company: co[0] ?? null, company_name: companyName,
    people: g("People") ?? [], meetings: g("Meetings") ?? [], tasks: g("Tasks") ?? [],
    edited: page.last_edited_time,
  };
}

async function findPage(ds: string, jobId: string) {
  const res = await notion(`/data_sources/${ds}/query`, "POST", {
    page_size: 1, filter: { property: "Job ID", rich_text: { equals: jobId } },
  });
  return res.results?.[0] ?? null;
}

// The Companies page for a name: an exact title match, else created. "X via Recruiter" links to the recruiter,
// the same rule engine/notion_opps.py uses.
async function companyPage(ds: string, raw: string) {
  const name = (raw.includes(" via ") ? raw.split(" via ")[1] : raw).trim();
  if (!name) return null;
  const res = await notion(`/data_sources/${ds}/query`, "POST", {
    page_size: 1, filter: { property: "Name", title: { equals: name } },
  });
  if (res.results?.[0]) return { id: res.results[0].id, name };
  const made = await notion(`/pages`, "POST", {
    parent: { type: "data_source_id", data_source_id: ds },
    properties: { Name: { title: rich(name) }, "Date Added": { date: { start: new Date().toISOString().slice(0, 10) } } },
  });
  return { id: made.id, name };
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
    const { action, id, fields = {}, kind, target } = await req.json();
    const ds = Deno.env.get("NOTION_OPPS_DS");
    const coDs = Deno.env.get("NOTION_COMPANIES_DS");
    if (!ds) throw new Error("NOTION_OPPS_DS is not set");
    if (!id) throw new Error("every action needs the board record id");
    let page = await findPage(ds, id);
    let companyName: string | null = null;

    if (action === "promote") {
      if (page) {  // already there (an un-pursue and pursue again): reopen it on the shortlist
        page = await notion(`/pages/${page.id}`, "PATCH", {
          properties: { Stage: { select: { name: "Shortlist" } }, Outcome: { select: null } },
        });
      } else {
        const co = coDs && fields.company ? await companyPage(coDs, String(fields.company)) : null;
        companyName = co?.name ?? null;
        page = await notion(`/pages`, "POST", {
          parent: { type: "data_source_id", data_source_id: ds },
          icon: { type: "emoji", emoji: "🎯" },
          properties: {
            Name: { title: rich(`${fields.title ?? "Role"} · ${fields.company ?? ""}`.trim()) },
            "Job ID": { rich_text: rich(id) },
            Stage: { select: { name: "Shortlist" } },
            "Human Path": { select: { name: "Unchecked" } },
            Score: { number: typeof fields.score === "number" ? fields.score : null },
            Location: { rich_text: rich(String(fields.location ?? "")) },
            Posting: { url: fields.url ?? null },
            Board: { url: fields.board ?? null },
            Flag: { checkbox: !!fields.flag },
            "Pursued On": { date: { start: String(fields.verdict_date ?? new Date().toISOString().slice(0, 10)) } },
            ...(co ? { Company: { relation: [{ id: co.id }] } } : {}),
          },
        });
      }
    } else if (!page) {
      throw new Error(`no Notion opportunity for ${id}; mark it Pursue first`);
    } else if (action === "update" || action === "close") {
      const f = action === "close" ? { stage: "closed", outcome: fields.outcome ?? "withdrew" } : fields;
      const properties: Record<string, unknown> = {};
      if (f.stage !== undefined) properties["Stage"] = { select: flip(STAGE, f.stage) ? { name: flip(STAGE, f.stage) } : null };
      if (f.outcome !== undefined) properties["Outcome"] = { select: flip(OUTCOME, f.outcome) ? { name: flip(OUTCOME, f.outcome) } : null };
      if (f.next !== undefined) properties["Next Step"] = { rich_text: rich(String(f.next ?? "")) };
      if (f.next_date !== undefined) {
        properties["Next Step Date"] = { date: /^\d{4}-\d{2}-\d{2}$/.test(String(f.next_date ?? "")) ? { start: f.next_date } : null };
      }
      if (f.hp !== undefined) properties["Human Path"] = { select: { name: flip(HP, f.hp) ?? "Unchecked" } };
      if (f.hp_people !== undefined) properties["Human Path People"] = { rich_text: rich(String(f.hp_people ?? "")) };
      if (f.flag !== undefined) properties["Flag"] = { checkbox: !!f.flag };
      if (!Object.keys(properties).length) throw new Error("nothing to update");
      page = await notion(`/pages/${page.id}`, "PATCH", { properties });
    } else if (action === "link" || action === "unlink") {
      const name = REL[String(kind)];
      if (!name) throw new Error(`unknown kind ${kind}`);
      if (!target) throw new Error(`${action} needs target`);
      const have: string[] = plain(page.properties?.[name]) ?? [];
      const ids = action === "link"
        ? (name === "Company" ? [target] : [...new Set([...have, target])])
        : have.filter((x) => x !== target);
      page = await notion(`/pages/${page.id}`, "PATCH", { properties: { [name]: { relation: ids.map((i) => ({ id: i })) } } });
    } else {
      throw new Error(`unknown action ${action}`);
    }

    const opp = normalize(page, companyName);
    if (opp.company && !opp.company_name) {  // the mirror carries the name so the board needs no second read
      const co = await notion(`/pages/${opp.company}`);
      opp.company_name = plain(co.properties?.["Name"]);
    }
    const admin = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const { error } = await admin.from("opportunities").upsert({
      id: opp.id ?? id, page_id: opp.page, payload: opp, updated_at: new Date().toISOString(),
    });
    if (error) throw new Error(`saved to Notion, mirror failed: ${error.message}`);
    return reply({ opportunity: opp });
  } catch (e) {
    return reply({ error: e instanceof Error ? e.message : String(e) }, 400);
  }
});
