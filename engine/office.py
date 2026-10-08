"""Office: the office a role is hired into, pinned on the board's maps.

One `office` object per jobs.json record:

    {"address": "100 Summer St, Boston, MA 02110", "label": "Boston HQ", "precision": "street",
     "source": "https://example.com/contact", "lat": 42.3536, "lng": -71.0582, "geocoded": "2026-09-15"}

`precision` is street (a street address), city (the posting names a city and the building is not known), remote
(no office), or unknown. The deep pass (docs/deep-pass.md) supplies address, label, precision and source; this module
adds the coordinates. It geocodes through OpenStreetMap's Nominatim (free, no key, at most one request a second) and
caches every answer, hits and misses, in <vault>/jobs/geocache.json, so an address is looked up once. A street address
that does not resolve falls back to its city, and the record gets `fallback: true` (the board labels it city-level).
Changing the address clears the coordinates; the next geocode pins the new one.

    py engine/office.py set <id or job slug> --address "..." [--label ...] [--precision street|city] [--source ...]
                            [--remote] [--dry-run] [--no-build] [--no-push]
    py engine/office.py apply out-office-1.json [...]   fold [{id, office}] objects (a backfill) into jobs.json
    py engine/office.py geocode [--dry-run] [--retry]   pin every record with an address and no coordinates
    py engine/office.py show                            Pursue and Maybe counts by pin kind, and who is unpinned

build.py calls geocode_pending every run (cache only with --no-push). A failed lookup leaves the record pending and
never breaks the build.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, paths, load_jobs, save_jobs, by_id  # noqa: E402
from human_path import resolve  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PRECISIONS = ("street", "city", "remote", "unknown")
FACTS = ("address", "label", "precision", "source")
GEO = ("lat", "lng", "geocoded", "fallback")
NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "job-search-agent/1.0 (personal job board; office geocoder)"


def clean(office):
    """An office object from the deep pass or the command line, reduced to the four facts."""
    o = {k: office.get(k) or None for k in FACTS}
    for k in ("address", "label", "source"):
        if isinstance(o[k], str):
            o[k] = " ".join(o[k].split()) or None
    p = (o["precision"] or "").strip().lower()
    if p not in PRECISIONS:
        p = "unknown" if not o["address"] else "street" if re.match(r"\d", o["address"]) else "city"
    if p == "remote":
        o["address"] = None
    o["precision"] = p
    return o


def merge(j, office):
    """Set a record's office facts. Coordinates survive only while the address is unchanged. True when it changed."""
    new = clean(office)
    cur = j.get("office") or {}
    if all(cur.get(k) == new[k] for k in FACTS):
        return False
    if cur.get("address") and cur.get("address") == new["address"]:
        new.update({k: cur[k] for k in GEO if k in cur})
    j["office"] = new
    return True


def cache_key(q):
    return " ".join(re.sub(r"\s*,\s*", ", ", q.lower()).split())


_UNIT = re.compile(r"^(suite|ste\.?|floor|fl\.?|unit|room|#)\s*\S*$|^\d+(st|nd|rd|th)\s+floor$", re.I)


def geo_query(address):
    """What the geocoder is asked: floor, suite and unit parts dropped, and a leading building name
    ('Exchange Place, 53 State St, ...') dropped when the street follows it. The stored address keeps them."""
    parts = [x.strip() for x in address.split(",") if x.strip() and not _UNIT.match(x.strip())]
    if len(parts) > 3 and not re.search(r"\d", parts[0]) and re.match(r"\d", parts[1]):
        parts = parts[1:]
    return ", ".join(parts)


def city_of(address):
    """'100 Summer St, Boston, MA 02110' -> 'Boston, MA'; None when the address is already city-level."""
    parts = [x.strip() for x in address.split(",") if x.strip()]
    if parts and parts[-1].lower() in ("usa", "us", "united states"):
        parts = parts[:-1]
    if len(parts) < 3:
        return None
    state = re.sub(r"\s*\d{5}(-\d{4})?$", "", parts[-1]).strip()
    return f"{parts[-2]}, {state}" if state else parts[-2]


def is_pending(j):
    o = j.get("office") or {}
    return bool(o.get("address")) and o.get("lat") is None and o.get("precision") != "remote"


class Geocoder:
    def __init__(self, p, network=True, retry=False):
        self.file = p.geocache
        self.cache = json.loads(self.file.read_text(encoding="utf-8")) if self.file.exists() else {}
        self.network, self.retry = network, retry
        self.last = 0.0
        self.calls = 0
        self.dirty = False

    def missed(self, q):
        return bool((self.cache.get(cache_key(q)) or {}).get("miss"))

    def lookup(self, q):
        k = cache_key(q)
        hit = self.cache.get(k)
        if hit and not (hit.get("miss") and self.retry):
            return None if hit.get("miss") else hit
        if not self.network:
            return None
        wait = 1.1 - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        url = NOMINATIM + "?" + urlencode({"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "us"})
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"}), timeout=20) as r:
                res = json.loads(r.read().decode("utf-8"))
        except (URLError, OSError, ValueError) as e:
            print(f"  geocoder unreachable ({e}); remaining addresses stay pending")
            self.network = False
            return None
        finally:
            self.last = time.monotonic()
        self.calls += 1
        today = date.today().isoformat()
        if res:
            hit = {"lat": round(float(res[0]["lat"]), 6), "lng": round(float(res[0]["lon"]), 6),
                   "display": res[0].get("display_name"), "ts": today}
        else:
            hit = {"miss": True, "ts": today}
        self.cache[k] = hit
        self.dirty = True
        return None if hit.get("miss") else hit

    def save(self):
        if self.dirty:
            self.file.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                 encoding="utf-8", newline="\n")


def geocode_pending(p, data, network=True, retry=False):
    """Pin every pending record. Returns ([(record, used_city_fallback)], network_calls)."""
    g = Geocoder(p, network, retry)
    done = []
    for j in data["jobs"]:
        if not is_pending(j):
            continue
        o = j["office"]
        q = geo_query(o["address"])
        hit, fallback = g.lookup(q), False
        city = city_of(q)
        if not hit and city and g.missed(q):
            hit, fallback = g.lookup(city), True
        if not hit:
            continue
        o.update(lat=hit["lat"], lng=hit["lng"], geocoded=date.today().isoformat())
        if fallback:
            o["fallback"] = True
        else:
            o.pop("fallback", None)
        done.append((j, fallback))
    g.save()
    return done, g.calls


def pin_kind(j):
    o = j.get("office") or {}
    if o.get("precision") == "remote":
        return "remote"
    if o.get("lat") is not None:
        return "city pin" if o.get("fallback") or o.get("precision") == "city" else "street pin"
    return "not geocoded" if o.get("address") else "no office"


# ---------- commands ----------

def build(a):
    if a.no_build:
        print("build skipped; run py engine/build.py")
        return
    cmd = [sys.executable, str(REPO / "engine" / "build.py")] + (["--no-push"] if a.no_push else [])
    raise SystemExit(subprocess.call(cmd, cwd=str(REPO)))


def cmd_set(a):
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    j = resolve(data, a.role)
    if a.remote:
        office = {"precision": "remote", "label": a.label, "source": a.source}
    elif a.address:
        office = {"address": a.address, "label": a.label, "precision": a.precision, "source": a.source}
    else:
        raise SystemExit("pass --address, or --remote")
    print(f"{j['id']} {j['company']}: {j['title']}")
    if a.dry_run:
        print(json.dumps(clean(office), ensure_ascii=False))
        print("dry run: nothing written")
        return
    merge(j, office)
    geocode_pending(p, {"jobs": [j]})
    save_jobs(p, data)
    o = j["office"]
    print(json.dumps(o, ensure_ascii=False))
    if is_pending(j):
        print("  not pinned: no geocoder match (or it is unreachable); the card shows the address without a map")
    build(a)


def cmd_apply(a):
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    idx = by_id(data)
    n = 0
    for f in a.files:
        for r in json.loads(Path(f).read_text(encoding="utf-8")):
            j = idx.get(r.get("id"))
            if not j:
                print(f"  unknown id {r.get('id')}; skipped")
                continue
            if not isinstance(r.get("office"), dict):
                print(f"  {r['id']}: no office object; skipped")
                continue
            n += merge(j, r["office"])
    done, calls = geocode_pending(p, data)
    save_jobs(p, data)
    left = [j for j in data["jobs"] if is_pending(j)]
    print(f"applied {n} office changes; pinned {len(done)} ({calls} lookups); {len(left)} addresses unpinned; run build.py next")


def cmd_geocode(a):
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    if a.dry_run:
        g = Geocoder(p, network=False)
        pend = [j for j in data["jobs"] if is_pending(j)]
        for j in pend:
            addr = geo_query(j["office"]["address"])
            state = "cached miss" if g.missed(addr) else "cached" if cache_key(addr) in g.cache else "lookup"
            print(f"  {j['id']} {state:<11} {addr}  ({j['company']})")
        print(f"dry run: {len(pend)} pending")
        return
    done, calls = geocode_pending(p, data, retry=a.retry)
    for j, fallback in done:
        o = j["office"]
        print(f"  {j['id']} {o['lat']:.5f},{o['lng']:.5f}{' (city fallback)' if fallback else ''}  {j['company']}")
    if done:
        save_jobs(p, data)
    print(f"pinned {len(done)} ({calls} network lookups)")


def cmd_show(a):
    cfg = load_config()
    p = paths(cfg)
    data = load_jobs(p)
    js = [j for j in data["jobs"] if j.get("verdict") in ("pursue", "maybe") and not j.get("excluded")]
    by = {}
    for j in js:
        by.setdefault(pin_kind(j), []).append(j)
    print(f"{len(js)} Pursue and Maybe: " + ", ".join(f"{k} {len(v)}" for k, v in sorted(by.items())))
    for k in ("not geocoded", "no office"):
        for j in by.get(k, []):
            print(f"  {k}: {j['id']} {j['verdict']:<6} {j['company']}: {j['title']} ({j.get('location') or 'no location'})")


def main():
    ap = argparse.ArgumentParser(description="The hiring office on jobs.json records, geocoded for the board's maps.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set", help="set one role's office by hand, pin it, and rebuild")
    s.add_argument("role", help="10-hex record id or job file slug")
    s.add_argument("--address", help="street address, or 'City, ST' when the building is not known")
    s.add_argument("--label", help='short name, e.g. "Boston HQ" or "Seaport or Kendall (posting does not say)"')
    s.add_argument("--precision", choices=("street", "city", "unknown"), help="default: street when the address starts with a number")
    s.add_argument("--source", help="where the address came from, a URL when there is one")
    s.add_argument("--remote", action="store_true", help="the role has no office")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--no-build", action="store_true")
    s.add_argument("--no-push", action="store_true")
    ap_apply = sub.add_parser("apply", help="fold [{id, office}] JSON files into jobs.json and pin them")
    ap_apply.add_argument("files", nargs="+")
    g = sub.add_parser("geocode", help="pin every record with an address and no coordinates")
    g.add_argument("--dry-run", action="store_true", help="list what is pending, no network")
    g.add_argument("--retry", action="store_true", help="look up cached misses again")
    sub.add_parser("show", help="Pursue and Maybe counts by pin kind")
    a = ap.parse_args()
    {"set": cmd_set, "apply": cmd_apply, "geocode": cmd_geocode, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
