// bot-action: the Grok career-coach bot records outreach the owner did through it (2026-11-02), so the board's line for
// that person resolves without a click. It only inserts a bot_actions row; engine/bot_actions.py fold writes Notion
// (board-sync and the nightly runs call it), and the mirror, the vault and Today follow from Notion.
//
//   POST, header x-bot-secret: <BOT_ACTIONS_SECRET>
//   {person, type?, date?, note?, next_type?, next_action?, next_date?, ext_id?}
//     person: the Network page id, the email address it went to, or the full name
//     type:   a Network touch type (Email, Message, Call, Meeting, Event, Intro ask, Thank-you, Share, Check-in)
//     date:   YYYY-MM-DD, default today in Boston
//   -> {id, status: "new"}; the same ext_id twice -> {id, status: "duplicate"}
//
// Secrets: BOT_ACTIONS_SECRET. SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY come from the platform.
// Deploy: supabase functions deploy bot-action --no-verify-jwt --use-api
import { createClient } from "jsr:@supabase/supabase-js@2";
import { timingSafeEqualStr } from "../_shared/notion_signature.ts";

const TYPES = new Set(["Email", "Message", "Call", "Meeting", "Event", "Intro ask", "Thank-you", "Share", "Check-in"]);
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const str = (v: unknown, n = 2000) => (typeof v === "string" && v.trim() ? v.trim().slice(0, n) : null);

Deno.serve(async (req) => {
  if (req.method !== "POST") return reply({ error: "POST only" }, 405);
  const secret = Deno.env.get("BOT_ACTIONS_SECRET") ?? "";
  if (!secret || !timingSafeEqualStr(req.headers.get("x-bot-secret") ?? "", secret)) return reply({ error: "bad secret" }, 401);
  // deno-lint-ignore no-explicit-any
  let b: any;
  try { b = await req.json(); } catch { return reply({ error: "body must be JSON" }, 400); }
  const person = str(b.person, 200);
  if (!person) return reply({ error: "person is required (page id, email or full name)" }, 400);
  const type = str(b.type, 40) ?? "Email";
  if (!TYPES.has(type)) return reply({ error: `type must be one of ${[...TYPES].join(", ")}` }, 400);
  for (const k of ["date", "next_date"]) if (b[k] != null && !DAY.test(String(b[k]))) return reply({ error: `${k} must be YYYY-MM-DD` }, 400);
  const row = {
    source: "grok", ext_id: str(b.ext_id, 200), person, type, note: str(b.note),
    next_type: str(b.next_type, 40), next_action: str(b.next_action), next_date: b.next_date ?? null,
    ...(b.date ? { date: b.date } : {}),
  };
  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data, error } = await db.from("bot_actions").insert(row).select("id").single();
  if (error?.code === "23505") {
    const { data: had } = await db.from("bot_actions").select("id").eq("source", "grok").eq("ext_id", row.ext_id).single();
    return reply({ id: had?.id ?? null, status: "duplicate" });
  }
  if (error) return reply({ error: error.message }, 500);
  return reply({ id: data.id, status: "new" });
});
