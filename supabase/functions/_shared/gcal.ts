// the owner's Google calendars, read from each calendar's secret iCal address, as rows for gcal_events.
// The Calendar tab shows them grey, title only, on Day and Week. Only the title, start and end are kept:
// never descriptions, guests, places or links.
//
// A secret iCal address needs no Google sign-in and never expires, where an OAuth app in testing mode loses
// its refresh token after seven days. ical.js is passed in (Deno imports it from npm:, the node test from a
// local install) so this file has no imports of its own and both can load it.

export type CalSpec = { name: string; url: string; default?: boolean };
export type EventRow = { id: string; calendar_id: string; title: string; starts: string; ends: string; all_day: boolean };

/** "Sophie's soccer" -> "sophies-soccer": the calendar's id, stable while its name is. */
export function calendarId(name: string): string {
  return name.toLowerCase().replace(/['’]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "calendar";
}

/** GCAL_ICS: a JSON list of {name, url, default?}. Bad entries are dropped; duplicate names keep the first. */
export function parseSpecs(raw: string | undefined): CalSpec[] {
  let list: unknown;
  try { list = JSON.parse(raw || "[]"); } catch { return []; }
  if (!Array.isArray(list)) return [];
  const seen = new Set<string>();
  const out: CalSpec[] = [];
  for (const x of list) {
    if (!x || typeof x !== "object") continue;
    const { name, url } = x as Record<string, unknown>;
    if (typeof name !== "string" || !name.trim() || typeof url !== "string" || !/^https:\/\//.test(url)) continue;
    const id = calendarId(name);
    if (seen.has(id)) continue;
    seen.add(id);
    out.push({ name: name.trim(), url, default: (x as Record<string, unknown>).default === true });
  }
  return out;
}

const DAY = 864e5;
const ymd = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/**
 * Every event in the calendar that overlaps [fromMs, toMs], recurring ones expanded, cancelled ones left out.
 * A timed event's starts and ends are UTC ISO strings; an all-day event's are YYYY-MM-DD, ends exclusive.
 */
// deno-lint-ignore no-explicit-any
export function expandIcs(ICAL: any, text: string, calId: string, fromMs: number, toMs: number, maxSteps = 20000): EventRow[] {
  const comp = new ICAL.Component(ICAL.parse(text));
  for (const tz of comp.getAllSubcomponents("vtimezone")) ICAL.TimezoneService.register(tz);
  // deno-lint-ignore no-explicit-any
  const events: any[] = comp.getAllSubcomponents("vevent").map((v: unknown) => new ICAL.Event(v));
  // deno-lint-ignore no-explicit-any
  const masters = new Map<string, any>();
  for (const e of events) if (!e.isRecurrenceException()) masters.set(e.uid, e);
  for (const e of events) {
    if (!e.isRecurrenceException()) continue;
    const m = masters.get(e.uid);
    if (m) m.relateException(e);
    else masters.set(`${e.uid}|${e.recurrenceId}`, e); // a moved instance whose series is gone
  }
  const out = new Map<string, EventRow>();
  // deno-lint-ignore no-explicit-any
  const add = (item: any, start: any, end: any) => {
    if (String(item.component.getFirstPropertyValue("status") || "").toUpperCase() === "CANCELLED") return;
    const title = String(item.summary || "Busy").replace(/\s+/g, " ").trim().slice(0, 200) || "Busy";
    let row: EventRow;
    if (start.isDate) {
      const s = start.toString().slice(0, 10);
      let e = end ? end.toString().slice(0, 10) : "";
      if (!e || e <= s) e = ymd(Date.parse(s + "T00:00:00Z") + DAY);
      if (Date.parse(e + "T00:00:00Z") < fromMs - DAY || Date.parse(s + "T00:00:00Z") > toMs) return;
      row = { id: "", calendar_id: calId, title, starts: s, ends: e, all_day: true };
    } else {
      const s = start.toJSDate().getTime();
      let e = end ? end.toJSDate().getTime() : s;
      if (e < s) e = s;
      if (e < fromMs || s > toMs) return;
      row = { id: "", calendar_id: calId, title, starts: new Date(s).toISOString(), ends: new Date(e).toISOString(), all_day: false };
    }
    row.id = `${calId}:${item.uid}:${row.starts}`;
    out.set(row.id, row);
  };
  for (const e of masters.values()) {
    if (!e.isRecurring()) { add(e, e.startDate, e.endDate); continue; }
    const it = e.iterator();
    let steps = 0;
    for (let next = it.next(); next && steps < maxSteps; next = it.next(), steps++) {
      const d = e.getOccurrenceDetails(next);
      if (d.startDate.toJSDate().getTime() > toMs) break;
      add(d.item, d.startDate, d.endDate);
    }
  }
  return [...out.values()].sort((a, b) => a.starts.localeCompare(b.starts));
}
