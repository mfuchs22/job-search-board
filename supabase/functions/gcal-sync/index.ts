// gcal-sync (2026-11-02): the owner's Google calendars into gcal_calendars and gcal_events, the grey layer on the
// board's Calendar tab (Day and Week only). It is the only writer of both tables.
//
// pg_cron calls it every 15 minutes (migration 20261102000000_gcal.sql) with the header x-sync-secret. Each
// calendar is read from its secret iCal address, one week back to seven weeks ahead, recurring events expanded.
// A calendar that fails to load keeps its last events and is marked ok=false; a calendar taken out of the list
// is deleted with its events. Each run touches every gcal_calendars row, which is what the page listens for.
//
// Secrets: GCAL_ICS (JSON: [{"name":"Personal","url":"https://calendar.google.com/calendar/ical/.../basic.ics",
// "default":true}, ...], in the order the page lists them; "default" is on before the owner picks), GCAL_SYNC_SECRET.
// The addresses never leave this function: the tables hold the calendar's name, never its URL.
// Deploy: supabase functions deploy gcal-sync --no-verify-jwt --use-api

import { createClient } from "jsr:@supabase/supabase-js@2";
import ICAL from "npm:ical.js@1.5.0";
import { timingSafeEqualStr } from "../_shared/notion_signature.ts";
import { calendarId, expandIcs, parseSpecs } from "../_shared/gcal.ts";

const DAY = 864e5;

function reply(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function db() {
  return createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
    auth: { persistSession: false },
  });
}

async function fetchIcs(url: string): Promise<string> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 20000);
  try {
    const r = await fetch(url, { signal: ctl.signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.text();
  } finally {
    clearTimeout(t);
  }
}

async function run() {
  const specs = parseSpecs(Deno.env.get("GCAL_ICS"));
  if (!specs.length) throw new Error("GCAL_ICS is empty or not a list of {name, url}");
  const sb = db();
  const now = Date.now();
  const runTs = new Date(now).toISOString();
  const from = now - 7 * DAY, to = now + 49 * DAY;
  const result: Record<string, number | string> = {};
  for (const [ord, spec] of specs.entries()) {
    const id = calendarId(spec.name);
    const base = { id, name: spec.name, ord, is_default: !!spec.default, synced_at: runTs };
    let rows;
    try {
      rows = expandIcs(ICAL, await fetchIcs(spec.url), id, from, to);
    } catch (e) {
      // The message names the failure, never the address.
      const msg = e instanceof Error ? e.message.replace(/https?:\/\/\S+/g, "the address") : "read failed";
      await sb.from("gcal_calendars").upsert({ ...base, ok: false, error: msg.slice(0, 200) });
      result[spec.name] = "failed: " + msg.slice(0, 80);
      continue;
    }
    const { error: ce } = await sb.from("gcal_calendars").upsert(base); // the row the events hang on; ok and error stay as they were
    if (ce) throw new Error(`gcal_calendars: ${ce.message}`);
    for (let i = 0; i < rows.length; i += 500) {
      const { error } = await sb.from("gcal_events").upsert(rows.slice(i, i + 500).map((r) => ({ ...r, synced_at: runTs })));
      if (error) throw new Error(`gcal_events: ${error.message}`);
    }
    const { error: de } = await sb.from("gcal_events").delete().eq("calendar_id", id).lt("synced_at", runTs);
    if (de) throw new Error(`gcal_events delete: ${de.message}`);
    await sb.from("gcal_calendars").upsert({ ...base, ok: true, error: null, events: rows.length });
    result[spec.name] = rows.length;
  }
  const keep = specs.map((s) => calendarId(s.name));
  const { error: ge } = await sb.from("gcal_calendars").delete().not("id", "in", `(${keep.map((k) => `"${k}"`).join(",")})`);
  if (ge) throw new Error(`gcal_calendars cleanup: ${ge.message}`);
  console.log(`gcal-sync ${JSON.stringify(result)}`);
  return { ok: true, calendars: result };
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return reply({ error: "POST only" }, 405);
  const secret = Deno.env.get("GCAL_SYNC_SECRET") ?? "";
  const got = req.headers.get("x-sync-secret") ?? "";
  if (!secret || !timingSafeEqualStr(got, secret)) return reply({ error: "bad sync secret" }, 401);
  try {
    return reply(await run());
  } catch (e) {
    console.error("gcal-sync failed", e);
    return reply({ error: e instanceof Error ? e.message : String(e) }, 500);
  }
});
