"""Conversation-led roles: a firm wants to talk, and there is no posting yet.

A conversation-led record is a normal jobs.json row with `kind` "conversation". Its id comes from a minted
identity URL (`https://conversation.local/<company>/<person>/<date>/<reason>`), so a later title or posting
does not mint a second record. `score` stays null and `score_kind` stays "conversation" until a deep pass
reads a real title, scope or JD. That is an explicit unscored state: nothing here invents rubric points
from the firm, the people or the call.

The morning build ingests data/conversations.json and any Opportunities page that has a stage, no Job ID,
and no posting (notion_sync keeps those on `untitled`). Creating that page is the Pursue. add_role.py
--conversation is the same decision and is only the fallback.

    py engine/add_role.py --upgrade --title "..." [--url <posting>] [--deep-pass out.json]

`intake` holds how it came in. `intake.upgraded` is the day a title or posting landed, or the day a rubric
score replaced the unscored state. `kind` stays "conversation" after that, so the origin is still on the record.

Skip, while there is no posting: posting checks (`skip_posting_check`), the deep-pass newcomer queue
(`needs_rubric` is false until upgraded), and tailored resume/cover (`skip_materials`, until `score_kind`
is `deep`). Diligence, the campaign, call prep, mail, human path and follow-up dates are unchanged.

Notion: `match_opportunity` finds an existing Opportunities page by Job ID, then by `intake.notion_page`,
then (only for a conversation, only when Job ID is empty) by a single company match. An ambiguous match or
a link that is not in the database is `stop`: the caller must not create a page.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from common import STAGES, canonical_url, job_id, new_record, same_company, slug

SEED = Path(__file__).resolve().parent.parent / "data" / "conversations.json"

KIND = "conversation"
SCORE_KIND = "conversation"
IDENTITY_HOST = "conversation.local"
# hand.local is add_role's minted URL for a hand role that has no posting. It is not a conversation, and it
# is still not an ad, so posting checks treat it the same way they treat this host.
IDENTITY_HOSTS = frozenset({IDENTITY_HOST, "hand.local"})
PRIORITIES = ("high", "normal")


def is_conversation(j):
    return (j or {}).get("kind") == KIND


def intake_of(j):
    raw = (j or {}).get("intake")
    return raw if isinstance(raw, dict) else {}


def title_is_placeholder(title):
    t = (title or "").strip()
    return (not t) or bool(re.search(r"title\s*tbd", t, re.I))


def is_identity_url(url):
    host = (urlsplit(canonical_url(url)).netloc if url else "") or ""
    return host in IDENTITY_HOSTS


def posting_url(j):
    """The record's URL when it is a real posting. A minted identity URL is not one."""
    url = (j or {}).get("url") or ""
    if not url or is_identity_url(url):
        return None
    return url


def awaiting_jd(j):
    """Unscored conversation: no rubric read yet, and no title or posting has been recorded."""
    if not is_conversation(j):
        return False
    if j.get("score_kind") == "deep":
        return False
    return not intake_of(j).get("upgraded")


def skip_posting_check(j):
    """Nothing to fetch until the record carries a real posting URL."""
    return is_conversation(j) and not posting_url(j)


def skip_materials(j):
    """No tailored resume or cover letter until a deep pass has scored a JD. The plan, diligence,
    call prep and mail steps are separate and still run."""
    return is_conversation(j) and j.get("score_kind") != "deep"


def materials_owed(j, answered, drafts_exist):
    return bool(answered and not drafts_exist and not skip_materials(j))


def needs_rubric(j, min_score):
    """Who the deep pass reads next. Open conversations are not in the newcomer queue. One that has
    been upgraded (a title or posting landed) is, even when the owner has already Pursued it: the morning
    queue's "no verdict" rule is for radar rows, and this role is already in motion."""
    if j.get("excluded") or j.get("deep_pass_date"):
        return False
    if (j.get("score_kind") == "title" and (j.get("score") or 0) >= int(min_score)
            and not j.get("verdict")):
        return True
    return is_conversation(j) and bool(intake_of(j).get("upgraded")) and j.get("score_kind") != "deep"


def on_board(j, min_score):
    """Leaderboard membership. An open conversation is on the board with no score, ahead of the floor."""
    if j.get("excluded") or j.get("verdict") == "pass":
        return False
    if is_conversation(j) and j.get("score_kind") != "deep":
        return True
    return (j.get("score") or 0) >= int(min_score)


def score_text(j):
    """The leaderboard's Score cell. Never a number we did not score."""
    if is_conversation(j) and j.get("score_kind") != "deep":
        return "conversation"
    if j.get("score") is None:
        return ""
    return f"{j['score']}" + ("" if j.get("score_kind") == "deep" else " (title)")


def score_line(j):
    """The Notion body line. A conversation is named as unscored, not as a title-only rubric score."""
    if is_conversation(j) and j.get("score_kind") != "deep":
        return "Unscored, conversation-led (no rubric score until a title or JD is read)"
    kind = "deep pass" if j.get("score_kind") == "deep" else "title only"
    return f"Score {j.get('score')} ({kind})"


def identity_url(company, person, when, reason):
    """Stable for the life of the record. The title is not in it, so a later title keeps this id."""
    return (f"https://{IDENTITY_HOST}/{slug(company)}/{slug(person)}/{when}/{slug(reason)[:48]}")


def page_key(value):
    """32 hex chars from a Notion page id or URL. Empty when the value is not one."""
    raw = re.sub(r"[^0-9a-f]", "", (value or "").lower())
    if len(raw) < 32:
        return ""
    return raw[-32:]


def notion_id(value):
    """Hyphenated Notion page id, or None."""
    raw = page_key(value)
    if len(raw) != 32:
        return None
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def _require(pairs):
    missing = [name for name, value in pairs if not str(value or "").strip()]
    if missing:
        raise ValueError("conversation-led role needs " + ", ".join(missing))


def make_record(*, company, source, person, channel, reason, summary, when, title=None,
                contact=None, notion_page=None):
    """A new unscored conversation-led record. `source` is the existing recruiter/network/referral/hand value.
    person, channel, reason and summary are required: summary is the call notes standing in for the JD."""
    _require((("company", company), ("person", person), ("channel", channel),
              ("reason", reason), ("summary", summary), ("date", when)))
    title = (title or "").strip() or "Role (title TBD)"
    url = identity_url(company, person, when, reason)
    j = new_record(id=job_id(url), url=url, title=title, company=company.strip(),
                   company_key=company.strip(), source=source, date_first_seen=when)
    j["kind"] = KIND
    j["priority"] = "high"
    j["score"] = None
    j["score_kind"] = SCORE_KIND
    j["why"] = reason.strip()
    j["fetched"] = False
    j["card"] = {"math": None, "job": [summary.strip()], "note": None}
    j["intake"] = {
        "person": person.strip(),
        "channel": channel.strip(),
        "reason": reason.strip(),
        "summary": summary.strip(),
        "contact": slug(contact) if contact else None,
        "notion_page": notion_id(notion_page) if notion_page else None,
        "priority": "high",
        "upgraded": None,
        "title_at_intake": title,
        "url_at_intake": url,
    }
    if notion_page and not j["intake"]["notion_page"]:
        raise ValueError(f"not a Notion page id or URL: {notion_page}")
    if contact:
        j["contact"] = slug(contact)
    return j


def upgrade(j, *, today, title=None, url=None):
    """Record a title or posting on this same record. The id does not change. The score stays unscored
    until a deep pass sets it. A placeholder title with no posting is not an upgrade."""
    if not is_conversation(j):
        raise ValueError(f"{j.get('id')} is not conversation-led")
    intake = j.setdefault("intake", {})
    if not isinstance(intake, dict):
        intake = j["intake"] = {}
    if title and title.strip() and title.strip() != j.get("title"):
        intake.setdefault("title_at_intake", j.get("title"))
        j["title"] = title.strip()
    if url:
        cu = canonical_url(url)
        if cu and cu != canonical_url(j.get("url") or ""):
            if is_identity_url(cu):
                raise ValueError("--url on an upgrade has to be the posting, not an identity URL")
            old = j.get("url")
            if old and old not in j.setdefault("aliases", []):
                j["aliases"].append(old)
            intake.setdefault("url_at_intake", old)
            j["url"] = cu
    if title_is_placeholder(j.get("title")) and not posting_url(j):
        raise ValueError("upgrade needs a real title or a posting URL; the score stays unscored until a deep pass")
    intake["upgraded"] = intake.get("upgraded") or today
    # Leave the record unscored until the rubric is applied. A title-level number would be a fake score.
    if j.get("score_kind") != "deep":
        j["score"] = None
        j["score_kind"] = SCORE_KIND
    return j


def mark_scored(j, today):
    """A deep pass just wrote a rubric score (or an exclusion) onto this record. The id and intake stay."""
    if not is_conversation(j):
        return j
    intake = j.setdefault("intake", {})
    if isinstance(intake, dict):
        intake["upgraded"] = intake.get("upgraded") or today
    return j


def _company_of(page, names, plain):
    props = page.get("properties") or {}
    rel = plain(props.get("Company")) or []
    if isinstance(rel, str):
        rel = [rel]
    for i in rel:
        if names.get(i):
            return names[i]
        key = page_key(i)
        for cid, name in names.items():
            if page_key(cid) == key and name:
                return name
    title = plain(props.get("Name")) or ""
    if " · " in title:
        return title.split(" · ", 1)[1].strip()
    return ""


def match_opportunity(j, pages, companies, plain):
    """The Opportunities page this record already has, if any.

    `pages` are Notion page objects. `companies` is [{id, name}]. `plain` is notion.plain.
    `how` is job_id, linked, company, none, missing_link or ambiguous.
    sync_action() says whether to update that page, create one, or stop.
    """
    names = {c["id"]: c.get("name") or "" for c in companies}
    by_job, by_page, untitled = {}, {}, []
    for pg in pages:
        props = pg.get("properties") or {}
        jid = (plain(props.get("Job ID")) or "").strip()
        pid = page_key(pg.get("id"))
        if pid:
            by_page[pid] = pg
        if jid:
            by_job.setdefault(jid, pg)
        else:
            untitled.append(pg)
    if j.get("id") and j["id"] in by_job:
        return {"page": by_job[j["id"]], "how": "job_id", "pages": []}
    want = page_key(intake_of(j).get("notion_page"))
    if want:
        if want in by_page:
            return {"page": by_page[want], "how": "linked", "pages": []}
        return {"page": None, "how": "missing_link", "pages": []}
    if is_conversation(j):
        hits = [pg for pg in untitled if same_company(_company_of(pg, names, plain), j.get("company"))]
        if len(hits) == 1:
            return {"page": hits[0], "how": "company", "pages": hits}
        if len(hits) > 1:
            return {"page": None, "how": "ambiguous", "pages": hits}
    return {"page": None, "how": "none", "pages": []}


def sync_action(match):
    """update: write the Job ID onto the page we found. create: there is no page. stop: creating would
    risk a duplicate, or the linked page is not in the database."""
    if match.get("how") in ("job_id", "linked", "company"):
        return "update"
    if match.get("how") in ("missing_link", "ambiguous"):
        return "stop"
    return "create"


def adopt_only(match):
    """A page we found by link or company name already has the owner's stage. Write the join key, not the stage."""
    return match.get("how") in ("linked", "company")


# ---------- intake: the morning build, not a hand-run command ----------

def untitled_is_conversation(row):
    """An Opportunities page the owner created for a conversation: a stage, no Job ID, no posting.

    notion_sync.pull keeps these off the opportunities mirror (that table is keyed on Job ID) and
    hands them to the build. As of 2026-10-29 the only such page is Battery Global Advisors.
    A page with a posting URL and no Job ID is not one of these; it is waiting for its id.
    """
    if not row:
        return False
    stage = (row.get("stage") or "").strip()
    return stage in STAGES and not (row.get("job_id") or "").strip() and not (row.get("posting") or "").strip()


def seed_path():
    return SEED


def load_seed(path=None):
    """The version-controlled list. Missing file means nothing to add, not an error."""
    f = Path(path) if path else SEED
    if not f.exists():
        return []
    raw = json.loads(f.read_text(encoding="utf-8"))
    rows = raw.get("conversations") if isinstance(raw, dict) else raw
    return list(rows or [])


def _split_name(name, company_name):
    name = (name or "").strip()
    if " · " in name:
        title, company = [x.strip() for x in name.split(" · ", 1)]
        return title or "Role (title TBD)", (company_name or company).strip()
    return name or "Role (title TBD)", (company_name or "").strip()


def _person(text):
    head = re.split(r"[:|(]", (text or "").strip(), maxsplit=1)[0].strip()
    return head


def entries_from_untitled(rows, today):
    """Notion pages with no Job ID, shaped as seed entries. A page the seed already names is still
    returned; ingest matches on the page id and does not create a second record."""
    out = []
    for row in rows or []:
        if not untitled_is_conversation(row):
            continue
        title, company = _split_name(row.get("name"), row.get("company_name"))
        if not company:
            continue
        person = _person(row.get("hp_people")) or "Unknown"
        when = str(row.get("pursued") or today or "")[:10]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", when):
            when = today
        reason = " ".join((row.get("next") or "wants to talk").split())[:120] or "wants to talk"
        summary = " ".join((row.get("hp_people") or row.get("next") or "Conversation, no posting yet.").split())
        entry = {
            "notion_page": row.get("page"),
            "company": company,
            "title": title,
            "source": "hand",
            "person": person,
            "channel": "notion",
            "reason": reason,
            "summary": summary,
            "stage": row.get("stage"),
            "next_step": row.get("next") or None,
            "next_step_date": (str(row.get("next_date") or "")[:10] or None),
            "date_first_seen": when,
            "location": row.get("location") or None,
            "job_file": f"jobs/{slug(company)}",
        }
        if row.get("hp") in ("warm active", "warm reachable", "cold"):
            entry["human_path"] = {"verdict": row["hp"], "qualifier": None,
                                   "people": row.get("hp_people") or None, "checked": when, "ref": None, "attached": None}
        out.append(entry)
    return out


def _entry(raw):
    """One intake row, from the seed file or from an untitled Notion page."""
    stage = (raw.get("stage") or "shortlist").strip().lower()
    if stage not in STAGES:
        raise ValueError(f"conversation stage must be one of {', '.join(STAGES)}, got {stage}")
    when = str(raw.get("date_first_seen") or "")[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", when):
        raise ValueError("a conversation needs date_first_seen YYYY-MM-DD")
    company = (raw.get("company") or "").strip()
    person = (raw.get("person") or "").strip()
    channel = (raw.get("channel") or "").strip()
    reason = (raw.get("reason") or "").strip()
    summary = (raw.get("summary") or "").strip()
    if not all((company, person, channel, reason, summary)):
        raise ValueError(f"conversation for {company or '?'} needs company, person, channel, reason, and summary")
    nxt = str(raw.get("next_step_date") or "")[:10]
    return {
        "company": company,
        "title": (raw.get("title") or "").strip() or None,
        "source": (raw.get("source") or "hand").strip(),
        "person": person,
        "channel": channel,
        "reason": reason,
        "summary": summary,
        "when": when,
        "contact": (raw.get("contact") or "").strip() or None,
        "notion_page": raw.get("notion_page"),
        "stage": stage,
        "next_step": (raw.get("next_step") or "").strip() or None,
        "next_step_date": nxt if re.match(r"^\d{4}-\d{2}-\d{2}$", nxt) else None,
        "location": (raw.get("location") or "").strip() or None,
        "job_file": (raw.get("job_file") or "").strip() or f"jobs/{slug(company)}",
        "human_path": raw.get("human_path") if isinstance(raw.get("human_path"), dict) else None,
    }


def find_conversation(jobs, entry):
    """The record this intake row already became, by Notion page or by the identity URL."""
    page = notion_id(entry.get("notion_page")) if entry.get("notion_page") else None
    url = canonical_url(identity_url(entry["company"], entry["person"], entry["when"], entry["reason"]))
    for j in jobs:
        if page and notion_id(intake_of(j).get("notion_page")) == page:
            return j
        known = [canonical_url(j.get("url"))] + [canonical_url(a) for a in j.get("aliases") or []]
        if url and url in known:
            return j
    return None


def record_from_entry(entry):
    """A Pursue. Creating the role is the decision; the stage is the one the page or the seed already has."""
    e = entry if "when" in entry else _entry(entry)
    j = make_record(company=e["company"], source=e["source"], person=e["person"], channel=e["channel"],
                    reason=e["reason"], summary=e["summary"], when=e["when"], title=e.get("title"),
                    contact=e.get("contact"), notion_page=e.get("notion_page"))
    j["verdict"] = "pursue"
    j["verdict_date"] = e["when"]
    j["stage"] = e["stage"]
    j["stage_date"] = e["when"]
    if e.get("location"):
        j["location"] = e["location"]
    if e.get("next_step"):
        j["next_step"] = e["next_step"]
    if e.get("next_step_date"):
        j["next_step_date"] = e["next_step_date"]
    if e.get("job_file"):
        j["job_file"] = e["job_file"]
    hp = e.get("human_path")
    if isinstance(hp, dict) and hp.get("verdict") in ("warm active", "warm reachable", "cold"):
        j["human_path"] = {"verdict": hp["verdict"], "qualifier": hp.get("qualifier"),
                           "people": hp.get("people"), "checked": hp.get("checked") or e["when"],
                           "ref": hp.get("ref"), "attached": hp.get("attached")}
    return j


def ingest(data, entries):
    """Add each conversation that is not already a record. Returns the new records. Never edits one
    that exists: stage after that belongs to the Notion pull, the same as every other Pursue."""
    added = []
    for raw in entries or []:
        e = _entry(raw)
        if find_conversation(data["jobs"], e):
            continue
        j = record_from_entry(e)
        data["jobs"].append(j)
        added.append(j)
    return added


def link_pages(cfg, jobs):
    """Write Job ID onto each conversation's Notion page when the page has none. Stage, lane, and the
    next step stay as the owner left them. Returns how many pages were patched."""
    import notion
    from notion import plain, prop
    ncfg = cfg.get("notion") or {}
    if not (ncfg.get("token_file") or ncfg.get("token")):
        return 0
    tok = notion.token(cfg)
    board = (ncfg.get("board_url") or "").rstrip("/")
    n = 0
    for j in jobs:
        page = intake_of(j).get("notion_page")
        if not (is_conversation(j) and page):
            continue
        pg = notion.call(tok, f"/pages/{page}")
        existing = (plain((pg.get("properties") or {}).get("Job ID")) or "").strip()
        if existing == j["id"]:
            continue
        if existing:
            print(f"conversation: {page} already has Job ID {existing}; left it (this record is {j['id']})")
            continue
        props = {"Job ID": prop("rich_text", j["id"])}
        if board:
            props["Board"] = prop("url", f"{board}/#job/{j['id']}")
        notion.call(tok, f"/pages/{pg.get('id') or page}", {"properties": props}, "PATCH")
        n += 1
    return n
