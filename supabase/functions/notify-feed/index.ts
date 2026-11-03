// notify-feed: the routines' messages for the owner, for his career coach bot (2026-11-02).
//
// The routines write public.notifications (engine/notify.py). The bot calls this with the shared secret and gets
// the messages it has not taken yet, oldest first; each one returned is stamped read_at, so a second call does not
// repeat it. `?peek=1` returns them without stamping; `?since=<ISO>` returns everything since then, taken or not.
//
//   GET /functions/v1/notify-feed            header x-feed-secret: <NOTIFY_FEED_SECRET>   (or ?key=)
//   -> {"messages": [{"id", "created_at", "source", "channel", "text", "ping"}], "count"}
//
// Secrets: NOTIFY_FEED_SECRET. SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are provided by the platform.
// Deploy: supabase functions deploy notify-feed --no-verify-jwt --use-api (the bot has no Supabase session).
import { createClient } from "jsr:@supabase/supabase-js@2";

const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function same(a: string, b: string) {
  if (!a || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const secret = Deno.env.get("NOTIFY_FEED_SECRET") ?? "";
  const given = req.headers.get("x-feed-secret") ?? url.searchParams.get("key") ?? "";
  if (!secret || !same(given, secret)) return reply({ error: "unauthorized" }, 401);

  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const since = url.searchParams.get("since");
  const peek = url.searchParams.get("peek") === "1" || !!since;
  let q = db.from("notifications").select("id,created_at,source,channel,text,ping").order("created_at").limit(200);
  q = since ? q.gte("created_at", since) : q.is("read_at", null);
  const channel = url.searchParams.get("channel");
  if (channel) q = q.eq("channel", channel);
  const { data, error } = await q;
  if (error) return reply({ error: error.message }, 500);
  const rows = data ?? [];
  if (!peek && rows.length) {
    const { error: e2 } = await db.from("notifications").update({ read_at: new Date().toISOString() })
      .in("id", rows.map((r) => r.id));
    if (e2) return reply({ error: e2.message }, 500);
  }
  return reply({ messages: rows, count: rows.length });
});
