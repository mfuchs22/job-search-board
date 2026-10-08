"""Build the demo dataset the public board runs on: web/demo/data.json.

Everything in it is invented. The companies, people, postings, notes and meetings are fictional and were written
to exercise every tab of the page (Overview, Inbox, Shortlist, In Process, Closed, Passed, Startups, Watchlist,
Network, To-dos, Map) with the same shapes the engine pushes to Supabase (docs/schema.md). Dates are written
relative to GENERATED; web/demo.js shifts them to the day the page is opened, so the demo never goes stale.

    py demo/make_demo.py            writes web/demo/data.json
"""
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path

GENERATED = date(2026, 10, 8)
OUT = Path(__file__).resolve().parents[1] / "web" / "demo" / "data.json"


def d(days_ago):
    return (GENERATED - timedelta(days=days_ago)).isoformat()


def ts(days_ago, hhmm="14:00"):
    return f"{d(days_ago)}T{hhmm}:00.000Z"


def jid(url):
    return hashlib.sha1(url.encode()).hexdigest()[:10]


def para(*lines):
    return "<p>" + "\n".join(lines) + "</p>"


# --------------------------------------------------------------------------------------------------------------
# Companies: fictional employers, all with a Boston connection so the Map tab has pins.
# --------------------------------------------------------------------------------------------------------------
COMPANIES = {
    "Northwind Labs": dict(url="https://northwindlabs.example.com", lat=42.3519, lng=-71.0470, address="12 Seaport Blvd, Boston, MA 02210",
        about=["AI-native workflow software for mid-market operations teams; about 320 people, Boston HQ, offices in Austin and London.",
               "Series C in spring; the agent product line is the growth bet and most of the hiring is around it."],
        growth=dict(read="growing", confidence="high", employees=dict(count="320", as_of=d(20), source="LinkedIn headcount"),
                    headcount_trend=dict(read="up", detail="+38% over twelve months, product and engineering leading", source="LinkedIn headcount"),
                    revenue=dict(latest="$48M ARR (reported)", growth="about 70% year over year", source="press, funding announcement"),
                    local_office=dict(detail="HQ in the Seaport; product, design and most of engineering sit here", source="careers page"))),
    "Beacon Health Systems": dict(url="https://beaconhealth.example.org", lat=42.3365, lng=-71.1058, address="330 Longwood Ave, Boston, MA 02115",
        about=["Regional hospital network: four hospitals and forty clinics, about 18,000 staff; a new chief digital officer is standing up an AI office.",
               "The posting is the first product seat in that office; the budget is for three in the first year."],
        growth=dict(read="stable", confidence="medium", employees=dict(count="18,000", as_of=d(40), source="annual report"),
                    headcount_trend=dict(read="flat", detail="clinical hiring steady, administrative flat", source="LinkedIn headcount"),
                    revenue=dict(latest="$3.1B operating revenue", growth="4% year over year", source="annual report"),
                    local_office=dict(detail="Longwood campus; the digital office sits with IT in the Fenway building", source="posting"))),
    "Tidewater Logistics": dict(url="https://tidewater.example.com", lat=None, lng=None, address=None,
        about=["Freight brokerage and 3PL, about 1,400 people, HQ in Jacksonville with a remote product organisation.",
               "Private-equity owned since last year; the thesis is margin through automation of the carrier desk."],
        growth=dict(read="growing", confidence="medium", employees=dict(count="1,400", as_of=d(30), source="LinkedIn headcount"),
                    headcount_trend=dict(read="up", detail="+12% over twelve months", source="LinkedIn headcount"),
                    revenue=dict(latest="about $900M gross revenue", growth="not disclosed", source="trade press"),
                    local_office=dict(detail="No Boston office; the product team is remote across the East Coast", source="posting"))),
    "Granite Peak Capital": dict(url="https://granitepeak.example.com", lat=42.3563, lng=-71.0558, address="100 Federal St, 30th Floor, Boston, MA 02110",
        about=["Middle-market private equity firm, about $6B under management, 70 people in Boston and New York.",
               "The CIO licensed the AI tools last year; this seat owns adoption across the deal teams and the portfolio operations group."],
        growth=dict(read="stable", confidence="high", employees=dict(count="70", as_of=d(15), source="team page"),
                    headcount_trend=dict(read="up", detail="six hires this year, four of them in portfolio operations", source="team page, archived copies"),
                    revenue=dict(latest="n/a (fund economics)", growth="Fund IV closed at $2.4B", source="press release"),
                    local_office=dict(detail="HQ on Federal Street; the technology group sits with finance", source="team page"))),
    "Meridian Software": dict(url="https://meridian.example.com", lat=42.3629, lng=-71.0868, address="245 First St, Cambridge, MA 02142",
        about=["Enterprise planning software, about 2,200 people, public since 2019; a new AI platform group is building the agent layer across the suite."],
        growth=dict(read="stable", confidence="high", employees=dict(count="2,200", as_of=d(25), source="10-K"),
                    headcount_trend=dict(read="flat", detail="a reduction in sales last year; engineering flat; the platform group is net new", source="LinkedIn headcount"),
                    revenue=dict(latest="$610M", growth="9% year over year", source="10-K"),
                    local_office=dict(detail="Kendall Square office; the platform group is hybrid, three days", source="posting"))),
    "Copperline Energy": dict(url="https://copperline.example.com", lat=None, lng=None, address=None,
        about=["Regulated utility serving two states, about 5,000 people; a transformation office reports to the COO."],
        growth=dict(read="stable", confidence="medium", employees=dict(count="5,000", as_of=d(60), source="annual report"),
                    headcount_trend=dict(read="flat", detail="", source="LinkedIn headcount"),
                    revenue=dict(latest="$2.4B", growth="3%", source="annual report"),
                    local_office=dict(detail="Remote, with quarterly travel to Hartford", source="posting"))),
    "Halcyon Insurance": dict(url="https://halcyon.example.com", lat=42.3516, lng=-71.0552, address="1 Post Office Sq, Boston, MA 02109",
        about=["Commercial lines insurer, about 3,800 people, Boston HQ; the claims organisation is the first to get an AI program of its own."],
        growth=dict(read="stable", confidence="high", employees=dict(count="3,800", as_of=d(30), source="LinkedIn headcount"),
                    headcount_trend=dict(read="flat", detail="", source="LinkedIn headcount"),
                    revenue=dict(latest="$4.2B premiums", growth="6%", source="annual report"),
                    local_office=dict(detail="HQ at Post Office Square; hybrid, two days", source="posting"))),
    "Orchard Analytics": dict(url="https://orchard.example.com", lat=42.3601, lng=-71.0589, address="50 Milk St, Boston, MA 02109",
        about=["Data and AI consultancy, about 400 people; forward-deployed teams embedded with clients for six to nine months."],
        growth=dict(read="growing", confidence="medium", employees=dict(count="400", as_of=d(20), source="LinkedIn headcount"),
                    headcount_trend=dict(read="up", detail="+25% over twelve months", source="LinkedIn headcount"),
                    revenue=dict(latest="not disclosed", growth="", source=""),
                    local_office=dict(detail="Milk Street office; engagements are mostly in the Northeast", source="posting"))),
    "Silverline Bank": dict(url="https://silverline.example.com", lat=42.3576, lng=-71.0574, address="75 State St, Boston, MA 02109",
        about=["Regional bank, about 6,500 people; the operations division is standing up an AI enablement team under the COO."],
        growth=dict(read="stable", confidence="high", employees=dict(count="6,500", as_of=d(35), source="10-K"),
                    headcount_trend=dict(read="flat", detail="", source="LinkedIn headcount"),
                    revenue=dict(latest="$1.9B", growth="5%", source="10-K"),
                    local_office=dict(detail="HQ on State Street; the team is hybrid, three days", source="posting"))),
    "Kestrel Aerospace": dict(url="https://kestrel.example.com", lat=42.5048, lng=-71.1956, address="25 Burlington Mall Rd, Burlington, MA 01803",
        about=["Avionics and drone systems, about 900 people; engineering-led, product management is new to the company."],
        growth=dict(read="growing", confidence="medium", employees=dict(count="900", as_of=d(28), source="LinkedIn headcount"),
                    headcount_trend=dict(read="up", detail="+18% over twelve months, engineering", source="LinkedIn headcount"),
                    revenue=dict(latest="not disclosed", growth="", source=""),
                    local_office=dict(detail="Burlington campus, on-site four days", source="posting"))),
    "Atlas Field Services": dict(url="https://atlasfield.example.com", lat=None, lng=None, address=None,
        about=["Field-service company for utilities and telecoms, about 7,000 technicians; wants an AI lead for dispatch and scheduling."],
        growth=dict(read="stable", confidence="low", employees=dict(count="7,000", as_of=d(50), source="company site"),
                    headcount_trend=dict(read="unknown", detail="", source=""), revenue=dict(latest="", growth="", source=""),
                    local_office=dict(detail="Remote with 50% travel to depots", source="posting"))),
    "Fathom Biotech": dict(url="https://fathombio.example.com", lat=42.3658, lng=-71.0922, address="400 Technology Sq, Cambridge, MA 02139",
        about=["Clinical-stage biotech, about 250 people; the posting is a program manager for the computational platform."],
        growth=dict(read="growing", confidence="medium", employees=dict(count="250", as_of=d(22), source="LinkedIn headcount"),
                    headcount_trend=dict(read="up", detail="+30% in twelve months", source="LinkedIn headcount"),
                    revenue=dict(latest="pre-revenue", growth="", source=""), local_office=dict(detail="Technology Square, on-site", source="posting"))),
    "Larkspur Consulting": dict(url="https://larkspur.example.com", lat=42.3540, lng=-71.0610, address="60 State St, Boston, MA 02109",
        about=["Management consultancy, about 1,200 people; the AI practice staffs client transformation programs."],
        growth=dict(read="growing", confidence="medium", employees=dict(count="1,200", as_of=d(30), source="LinkedIn headcount"),
                    headcount_trend=dict(read="up", detail="+15%", source="LinkedIn headcount"), revenue=dict(latest="", growth="", source=""),
                    local_office=dict(detail="State Street office; client travel most weeks", source="posting"))),
    "Juniper Education": dict(url="https://juniper.example.com", lat=42.3736, lng=-71.1097, address="1 Broadway, Cambridge, MA 02142",
        about=["Online learning platform, about 600 people; wants a product lead for AI tutoring."],
        growth=dict(read="stable", confidence="medium", employees=dict(count="600", as_of=d(40), source="LinkedIn headcount"),
                    headcount_trend=dict(read="flat", detail="", source="LinkedIn headcount"), revenue=dict(latest="$120M", growth="8%", source="press"),
                    local_office=dict(detail="Kendall Square, hybrid", source="posting"))),
    "Ironwood Manufacturing": dict(url="https://ironwood.example.com", lat=None, lng=None, address=None, about=["Industrial manufacturer, about 12,000 people, Ohio HQ."],
        growth=dict(read="stable", confidence="low", employees=dict(count="12,000", as_of=d(90), source="company site"), headcount_trend=dict(read="unknown", detail="", source=""),
                    revenue=dict(latest="$5B", growth="2%", source="annual report"), local_office=dict(detail="None; relocation to Columbus expected", source="posting"))),
    "Pinecrest Media": dict(url="https://pinecrest.example.com", lat=None, lng=None, address=None, about=["Digital media group, about 2,000 people, New York."],
        growth=dict(read="shrinking", confidence="medium", employees=dict(count="2,000", as_of=d(40), source="LinkedIn headcount"), headcount_trend=dict(read="down", detail="-9% in twelve months", source="LinkedIn headcount"),
                    revenue=dict(latest="", growth="", source=""), local_office=dict(detail="New York, on-site", source="posting"))),
    "Harborview Hotels": dict(url="https://harborview.example.com", lat=42.3600, lng=-71.0500, address="70 Rowes Wharf, Boston, MA 02110", about=["Hotel group, 40 properties, about 9,000 staff; a revenue-management AI program is in its second year."],
        growth=dict(read="stable", confidence="medium", employees=dict(count="9,000", as_of=d(45), source="company site"), headcount_trend=dict(read="flat", detail="", source=""),
                    revenue=dict(latest="$1.1B", growth="7%", source="press"), local_office=dict(detail="Rowes Wharf HQ, on-site", source="posting"))),
    "Summit Legal": dict(url="https://summitlegal.example.com", lat=42.3550, lng=-71.0600, address="28 State St, Boston, MA 02109", about=["Law firm, 600 lawyers; a knowledge-management AI program under the COO."],
        growth=dict(read="stable", confidence="medium", employees=dict(count="1,100", as_of=d(30), source="firm site"), headcount_trend=dict(read="flat", detail="", source=""),
                    revenue=dict(latest="", growth="", source=""), local_office=dict(detail="State Street, hybrid", source="posting"))),
    "Bluebird Retail": dict(url="https://bluebird.example.com", lat=None, lng=None, address=None, about=["Specialty retailer, 300 stores, about 11,000 staff, New Jersey HQ."],
        growth=dict(read="stable", confidence="low", employees=dict(count="11,000", as_of=d(60), source="company site"), headcount_trend=dict(read="unknown", detail="", source=""),
                    revenue=dict(latest="$2.2B", growth="1%", source="annual report"), local_office=dict(detail="Remote, monthly travel to New Jersey", source="posting"))),
    "Quarry Robotics": dict(url="https://quarry.example.com", lat=42.3800, lng=-71.1000, address="200 Inner Belt Rd, Somerville, MA 02143", about=["Warehouse robotics, about 500 people, Somerville."],
        growth=dict(read="growing", confidence="medium", employees=dict(count="500", as_of=d(20), source="LinkedIn headcount"), headcount_trend=dict(read="up", detail="+40%", source="LinkedIn headcount"),
                    revenue=dict(latest="", growth="", source=""), local_office=dict(detail="Somerville, on-site", source="posting"))),
}

ROLE_TYPES = {"transformation-owner": "Transformation owner", "ai-product-pm": "AI product PM", "internal-platform-pm": "Internal AI platform PM",
              "fde-embedded": "Forward-deployed / embedded", "enablement-adoption": "Enablement / adoption", "consulting-advisory": "Consulting / advisory",
              "program-project": "Program / project", "governance-risk": "Governance / risk", "other": "Other"}
STAGES = ["shortlist", "researching", "outreach", "applied", "interviewing", "offer", "closed"]
OUTCOMES = ["no_response", "rejected", "withdrew", "accepted", "posting_removed"]


def office(company, precision=None):
    c = COMPANIES[company]
    if c["lat"] is None:
        return {"label": None, "source": None, "address": None, "precision": precision or "remote"}
    return {"lat": c["lat"], "lng": c["lng"], "label": f"{company} HQ", "source": "company site", "address": c["address"], "geocoded": d(3), "precision": "street"}


def posting(state="active", since=12, checks=6, posted=None, http=200):
    ev = {"active": "JSON-LD datePosted present, apply button live", "closed": "No longer accepting applications", "removed": "HTTP 404",
          "unreachable": "bot wall (403)", "unknown": "'filled' text next to a fresh datePosted"}[state]
    p = {"state": state, "since": d(since), "checked": d(1), "checks": checks, "streak": checks, "method": "html", "http": http if state != "removed" else 404,
         "evidence": ev, "url_checked": "", "last_active": d(1 if state == "active" else since), "frozen": state in ("closed", "removed") and checks >= 2}
    if posted is not None:
        p["posted"] = d(posted)
    return p


def hp(verdict, people, days=4):
    return {"verdict": verdict, "qualifier": None, "people": people, "checked": d(days), "ref": None, "attached": None}


# --------------------------------------------------------------------------------------------------------------
# Roles. Each entry: the fields the record carries; the rest is filled in by make_job.
# --------------------------------------------------------------------------------------------------------------
JOBS = []


def add(**k):
    JOBS.append(k)


# In Process ---------------------------------------------------------------------------------------------------
add(title="Director, AI Product, Investment Platform", company="Granite Peak Capital", location="Boston, MA", score=11, role_type="internal-platform-pm",
    work_model="on-site, remote Fridays", travel=None, comp="About $240K base, 25% bonus, carry on the next fund (recruiter, by phone)",
    verdict="pursue", stage="interviewing", first=24, verdict_days=22, stage_days=5, flag=True, source="recruiter:harbor-search",
    url="https://granitepeak.example.com/careers/director-ai-product", posting=posting("active", since=24, checks=9, posted=26),
    why="Owns the deal teams' systems and AI at a firm that already licensed and governed the tools; the brief is find the use cases, ship the workflows, own adoption.",
    mismatch="On-site in Boston with days unstated; no private-equity background; one engineer reporting in is the whole team on day one.",
    math="base 5; enterprise and internal AI adoption +2; AI workflows built for a production business setting +2; employer in institutional investing +1; someone to learn from (an AI-savvy CIO two years in) +1 = 11",
    bullets=["Owns product priorities for the technology that supports the investment teams; director level, business-facing",
             "Turns deal-team needs into requirements, roadmaps and rollouts, then runs each initiative from prototype to adoption",
             "Finds and prioritises uses of generative AI across sourcing, diligence, investment committee prep and portfolio monitoring",
             "Works with one engineer, the CIO and outside vendors; reports to the CIO"],
    qualifications=["Experience in investment management, consulting or another analytical environment (meetable)",
                    "Strong product management experience: requirements, prioritisation, rollout (meetable; never with a software-company PM title)",
                    "Hands-on experience with AI and automation (meetable; the built-it-myself evidence has to lead)",
                    "Private equity experience preferred (not met)"],
    human_path=hp("warm active", "Dana Okafor (Harbor Search) runs the process and submitted the resume; Priya Natarajan (CIO) is the hiring manager and has met the owner twice. Second-degree route to the head of portfolio operations through Sam Delgado."),
    note="The most interesting seat on the board: build the thing, work with an engineer, a CIO who has already done the hard part.",
    calibration="About right", next_step="Second round with the CIO and the head of portfolio operations; prepare the 90-day plan one-pager", next_days=-2,
    in_process=True)

add(title="Lead Product Manager, Agent Platform", company="Northwind Labs", location="Boston, MA (hybrid)", score=10, role_type="ai-product-pm",
    work_model="hybrid, 3 days", travel="up to 10%", comp="$210-250K base plus equity", verdict="pursue", stage="applied", first=19, verdict_days=18, stage_days=6,
    flag=False, source="linkedin:ai-product-manager-boston", url="https://northwindlabs.example.com/jobs/lead-pm-agent-platform", posting=posting("active", since=19, checks=8, posted=21),
    why="Founding PM for the agent platform at an AI-native company that is growing fast; the role defines the human-approval line for autonomous agents.",
    mismatch="Wants a zero-to-one B2B SaaS record and the technical depth to argue architecture with senior engineers.",
    math="base 5; agent development in production +2; growing +1; AI-native company, works with founders +1; hybrid Boston +1 = 10",
    bullets=["Founding PM for the Agent Platform, the company's third product pillar and its biggest investment",
             "Defines the product, the sequencing and the approval model for agents that act on customer data",
             "Partners with a 12-person engineering group and the design lead; reports to the VP Product"],
    qualifications=["Zero-to-one track record, ideally B2B SaaS (partly met)", "Technical depth to debate architecture with senior engineers (partly met)",
                    "Experience shipping AI features to enterprise customers (met)"],
    human_path=hp("warm reachable", "Marcus Lind (VP Engineering) is a first-degree connection from a previous employer; not yet asked. Two second-degree routes to the VP Product."),
    note="Applied through the site after Marcus said the team is real and funded. The approval-line problem is exactly the thing I have built.",
    calibration="About right", next_step="Recruiter screen booked; ask Marcus for a word with the VP Product before it", next_days=1, in_process=True)

add(title="Head of AI Enablement, Operations", company="Silverline Bank", location="Boston, MA (hybrid)", score=9, role_type="enablement-adoption",
    work_model="hybrid, 3 days", travel=None, comp="Not in the posting", verdict="pursue", stage="applied", first=15, verdict_days=14, stage_days=3, flag=False,
    source="indeed:ai-enablement-boston", url="https://silverline.example.com/careers/head-ai-enablement-operations", posting=posting("active", since=15, checks=6, posted=16),
    why="Stands up the enablement team under the COO: training, playbooks, the intake for use cases, measurement of adoption.",
    mismatch="Enablement rather than build; the posting reads as change management first and product second.",
    math="base 5; enterprise and internal AI adoption +2; regulated industry, governance in scope +1; hybrid Boston +1 = 9",
    bullets=["Builds the AI enablement function for the operations division: 3,000 people across servicing, payments and lending ops",
             "Owns the use-case intake, prioritisation and the adoption measures the COO reports to the board",
             "Works with the model risk group on the control framework for generative AI"],
    qualifications=["Led adoption of new technology across a large operations organisation (met)", "Financial services experience (met)",
                    "Experience with generative AI tools in production (met)"],
    human_path=hp("cold", "No first-degree connection. The COO's chief of staff posted the role on LinkedIn; a note is drafted."),
    note="A safe-ish bank seat. Worth a conversation; the question is whether it is a build role or a training role.",
    calibration="Too high", next_step="Application acknowledged; chase the recruiter if nothing by Friday", next_days=2, in_process=True)

# Shortlist -----------------------------------------------------------------------------------------------------
add(title="VP, AI Transformation", company="Halcyon Insurance", location="Boston, MA (hybrid)", score=10, role_type="transformation-owner", work_model="hybrid, 2 days",
    travel="occasional", comp="$260-300K base plus bonus", verdict="pursue", stage="outreach", first=12, verdict_days=11, stage_days=4, flag=True,
    source="linkedin:ai-transformation-us", url="https://halcyon.example.com/careers/vp-ai-transformation", posting=posting("active", since=12, checks=5, posted=13),
    why="Owns the claims AI program end to end, with a budget and a team of eight; reports to the Chief Claims Officer.",
    mismatch="Insurance domain knowledge wanted; the claims organisation is 1,200 people and the role carries a lot of change management.",
    math="base 5; transformation owner with budget and team +3; regulated industry +1; hybrid Boston +1 = 10",
    bullets=["Owns the three-year AI roadmap for claims: intake triage, document extraction, fraud signals", "Leads a team of eight product and data people", "Reports to the Chief Claims Officer; sits on the operating committee"],
    qualifications=["Led a multi-year transformation program in a regulated business (met)", "Insurance experience preferred (not met)", "Executive presence with a board-level audience (met)"],
    human_path=hp("warm reachable", "Elena Marsh (Chief Claims Officer) is a second-degree connection through Sam Delgado; Sam offered an introduction."),
    note="This is the biggest seat on the board. Sam's intro to Elena is the move.", calibration="About right",
    next_step="Sam's introduction to Elena Marsh; send him the two-line blurb", next_days=-1)

add(title="Forward Deployed Product Lead", company="Orchard Analytics", location="Boston, MA", score=9, role_type="fde-embedded", work_model="on-site at clients, 4 days",
    travel="up to 50%", comp="$190-220K base plus bonus", verdict="pursue", stage="outreach", first=14, verdict_days=13, stage_days=6, flag=False,
    source="web:sweep", url="https://orchard.example.com/careers/forward-deployed-product-lead", posting=posting("active", since=14, checks=6, posted=15),
    why="Embedded with a client for six to nine months to ship an AI workflow and hand it over; the closest thing to the work itself.",
    mismatch="Half the time on the road; consultancy economics, utilisation targets.",
    math="base 5; forward-deployed AI delivery +2; AI workflows built for a production business +2; travel 50% -1; Boston +1 = 9",
    bullets=["Leads a three-person embedded team at one client at a time", "Owns the scope, the build plan and the handover", "Reports to the head of the AI practice"],
    qualifications=["Shipped AI workflows with business users (met)", "Consulting or client-facing delivery experience (partly met)", "Travel up to 50% (a concern)"],
    human_path=hp("warm active", "Jordan Pike (head of the AI practice) replied to a note and proposed a call."), note="Jordan replied. Travel is the gate.",
    calibration="About right", next_step="Call with Jordan Pike, Thursday", next_days=1)

add(title="Principal Product Manager, AI Platform", company="Meridian Software", location="Cambridge, MA (hybrid)", score=9, role_type="internal-platform-pm", work_model="hybrid, 3 days",
    travel=None, comp="$200-240K base plus RSUs", verdict="pursue", stage="researching", first=9, verdict_days=8, stage_days=8, flag=False,
    source="linkedin:ai-product-manager-boston", url="https://meridian.example.com/careers/principal-pm-ai-platform", posting=posting("active", since=9, checks=4, posted=10),
    why="Builds the agent layer across a planning suite used by 2,000 enterprises; a net-new group with executive backing.",
    mismatch="Public company, process-heavy; a principal title is below the level the search is aiming at.",
    math="base 5; agent development in production +2; large installed base +1; hybrid Cambridge +1 = 9",
    bullets=["Defines the agent framework the suite's product teams build on", "Partners with platform engineering and the AI research group", "Reports to the VP, AI Platform"],
    qualifications=["Platform PM experience at scale (partly met)", "Enterprise software background (met)", "Technical fluency with LLM tooling (met)"],
    human_path=hp("cold", "No path yet; three people at the company share a previous employer."), note=None, calibration=None,
    next_step="Read the platform group's engineering blog; find who runs the group", next_days=3)

add(title="Senior Director, Digital Transformation", company="Beacon Health Systems", location="Boston, MA", score=8, role_type="transformation-owner", work_model="on-site",
    travel=None, comp="Not in the posting", verdict="pursue", stage="researching", first=11, verdict_days=10, stage_days=10, flag=False,
    source="linkedin:ai-transformation-us", url="https://beaconhealth.example.org/careers/senior-director-digital-transformation", posting=posting("active", since=11, checks=5, posted=12),
    why="The first product seat in a new AI office at a hospital network; budget for three hires in year one.", mismatch="Healthcare experience wanted; on-site five days at Longwood.",
    math="base 5; transformation owner +2; new office with budget +1 = 8",
    bullets=["Stands up the AI office's product function: intake, prioritisation, delivery with IT", "First hire of three; builds the team", "Reports to the Chief Digital Officer"],
    qualifications=["Healthcare experience preferred (not met)", "Led technology adoption across a large organisation (met)", "Product management experience (met)"],
    human_path=hp("warm reachable", "Dr. Amara Osei (CMIO) is a first-degree connection from a board; not yet asked."), note="Interesting because it is new. Healthcare is a reach.",
    calibration="About right", next_step="Ask Amara what the CDO is actually trying to do", next_days=4)

add(title="Director of AI Programs", company="Juniper Education", location="Cambridge, MA (hybrid)", score=8, role_type="program-project", work_model="hybrid", travel=None,
    comp="$180-200K", verdict="pursue", stage="shortlist", first=7, verdict_days=6, stage_days=6, flag=False, source="builtin:sweep",
    url="https://juniper.example.com/careers/director-ai-programs", posting=posting("active", since=7, checks=3, posted=8),
    why="Runs the AI tutoring program across product, content and research.", mismatch="Program management more than product; consumer education.",
    math="base 5; AI program ownership +2; hybrid Cambridge +1 = 8", bullets=["Runs the AI tutoring program", "Coordinates product, content and research", "Reports to the CPO"],
    qualifications=["Program leadership (met)", "Education experience preferred (not met)"], human_path=hp("cold", "No path."), note=None, calibration=None, next_step=None)

add(title="Head of Applied AI", company="Kestrel Aerospace", location="Burlington, MA", score=8, role_type="ai-product-pm", work_model="on-site, 4 days", travel="10%",
    comp="$220-260K", verdict="pursue", stage="shortlist", first=6, verdict_days=5, stage_days=5, flag=False, source="linkedin:ai-product-manager-boston",
    url="https://kestrel.example.com/careers/head-of-applied-ai", posting=posting("active", since=6, checks=3, posted=7),
    why="Builds the applied AI group at an engineering-led company that has never had product management.", mismatch="Burlington, four days on-site; defence clearances for some programs.",
    math="base 5; builds a new function +2; growing +1 = 8", bullets=["Builds the applied AI group from two people", "Owns the roadmap for autonomy features", "Reports to the CTO"],
    qualifications=["Built a function from scratch (met)", "Aerospace or defence experience preferred (not met)"], human_path=hp("cold", "No path."), note="Far, but a real build.", calibration=None, next_step=None)

add(title="AI Adoption Lead, Legal Operations", company="Summit Legal", location="Boston, MA (hybrid)", score=8, role_type="enablement-adoption", work_model="hybrid", travel=None,
    comp="Not in the posting", verdict="pursue", stage="shortlist", first=5, verdict_days=4, stage_days=4, flag=False, source="indeed:ai-enablement-boston",
    url="https://summitlegal.example.com/careers/ai-adoption-lead", posting=posting("active", since=5, checks=2, posted=6),
    why="Owns adoption of the firm's AI tools across 600 lawyers; reports to the COO.", mismatch="Law-firm culture; the role has no engineers.",
    math="base 5; enterprise AI adoption +2; hybrid Boston +1 = 8", bullets=["Owns rollout and adoption across practice groups", "Runs the knowledge-management AI program", "Reports to the COO"],
    qualifications=["Led adoption programs (met)", "Legal industry experience preferred (not met)"], human_path=hp("cold", "No path."), note=None, calibration=None, next_step=None)

add(title="Director, AI Product Management", company="Harborview Hotels", location="Boston, MA", score=8, role_type="ai-product-pm", work_model="on-site", travel="15%",
    comp="$190-210K", verdict="pursue", stage="shortlist", first=16, verdict_days=15, stage_days=15, flag=False, source="linkedin:ai-product-manager-boston",
    url="https://harborview.example.com/careers/director-ai-product", posting=posting("active", since=16, checks=7, posted=17),
    why="Second year of a revenue-management AI program with results to show; the role takes it to the properties.", mismatch="Hospitality; on-site at Rowes Wharf.",
    math="base 5; AI program in production +2; Boston +1 = 8", bullets=["Owns the AI product roadmap for revenue management", "Takes the program to 40 properties"],
    qualifications=["AI product experience (met)", "Hospitality experience preferred (not met)"], human_path=hp("cold", "No path."), note=None, calibration=None, next_step=None)

# Closed, engaged ------------------------------------------------------------------------------------------------
add(title="Head of AI Transformation", company="Larkspur Consulting", location="Boston, MA", score=9, role_type="consulting-advisory", work_model="hybrid, client travel",
    travel="most weeks", comp="$250K base plus bonus", verdict="pursue", stage="closed", outcome="rejected", first=40, verdict_days=38, stage_days=9, flag=False,
    source="recruiter:harbor-search", url="https://larkspur.example.com/careers/head-ai-transformation", posting=posting("closed", since=8, checks=4, posted=42),
    why="Leads the AI practice's transformation offering.", mismatch="Travel most weeks; consulting economics.",
    math="base 5; transformation practice lead +2; AI practice +1; Boston +1 = 9", bullets=["Leads the transformation offering", "Owns three client programs", "Reports to the practice head"],
    qualifications=["Consulting leadership (partly met)", "AI program delivery (met)"], human_path=hp("warm active", "Dana Okafor (Harbor Search) ran the process.", 10),
    note="Went to a second round; they chose an internal candidate.", calibration="About right", next_step=None, in_process=True)

# Closed, posting removed ---------------------------------------------------------------------------------------
add(title="Lead PM, AI Dispatch", company="Atlas Field Services", location="Remote (US)", score=8, role_type="ai-product-pm", work_model="remote", travel="50% to depots",
    comp="$180-200K", verdict=None, stage="closed", outcome="posting_removed", first=21, flag=False, source="linkedin:ai-product-manager-us",
    url="https://atlasfield.example.com/careers/lead-pm-ai-dispatch", posting=posting("removed", since=4, checks=3, posted=22),
    why="AI for dispatch and scheduling across 7,000 technicians.", mismatch="Half the time at depots.", math="base 5; AI product in operations +2; remote +1 = 8",
    bullets=["Owns the dispatch AI roadmap"], qualifications=["Field operations experience preferred"], human_path=None, note=None, calibration=None, next_step=None)

add(title="Director, Generative AI", company="Pinecrest Media", location="New York, NY", score=8, role_type="ai-product-pm", work_model="on-site", travel=None, comp="$200K",
    verdict=None, stage="closed", outcome="posting_removed", first=27, flag=False, source="linkedin:ai-product-manager-us", url="https://pinecrest.example.com/careers/director-generative-ai",
    posting=posting("removed", since=9, checks=4, posted=28), why="Generative AI across the newsroom and ad products.", mismatch="New York, on-site; shrinking company.",
    math="base 5; generative AI product +2; on-site New York 0; shrinking -0 = 8 (gate: location)", bullets=["Owns generative AI products"], qualifications=["Media experience preferred"],
    human_path=None, note=None, calibration=None, next_step=None)

# Inbox: unreviewed, deep-scored 8+ ------------------------------------------------------------------------------
add(title="VP Product, AI Workflows", company="Tidewater Logistics", location="Remote (US)", score=10, role_type="ai-product-pm", work_model="remote", travel="quarterly",
    comp="$230-270K base plus equity", verdict=None, stage=None, first=0, flag=False, source="linkedin:ai-product-manager-us", url="https://tidewater.example.com/careers/vp-product-ai-workflows",
    posting=posting("active", since=0, checks=1, posted=1), why="Owns the automation of the carrier desk at a PE-owned 3PL; the thesis of the deal is this role.",
    mismatch="Freight; remote team with no Boston presence; PE timelines.", math="base 5; AI workflows for a production business +2; owner with the mandate +2; remote +1 = 10",
    bullets=["Owns the product roadmap for the carrier desk automation", "Leads a team of six PMs and designers", "Reports to the Chief Product Officer; presents to the sponsor quarterly"],
    qualifications=["Led AI workflow products in operations (met)", "Logistics experience preferred (not met)", "PE-backed experience (not met)"],
    human_path=hp("warm reachable", "Ravi Menon (CPO) shares a previous employer; not yet asked.", 0), note=None, calibration=None, next_step=None)

add(title="Director, AI Transformation Office", company="Copperline Energy", location="Remote (US)", score=9, role_type="transformation-owner", work_model="remote", travel="quarterly to Hartford",
    comp="$190-220K", verdict=None, stage=None, first=0, flag=False, source="linkedin:ai-transformation-us", url="https://copperline.example.com/careers/director-ai-transformation-office",
    posting=posting("active", since=0, checks=1, posted=2), why="Runs the transformation office's AI portfolio under the COO at a regulated utility.",
    mismatch="Utility pace; the office is a PMO more than a product group.", math="base 5; transformation owner +2; regulated industry +1; remote +1 = 9",
    bullets=["Owns the AI portfolio of the transformation office", "Runs the intake and the business cases", "Reports to the COO"],
    qualifications=["Transformation program leadership (met)", "Utility experience preferred (not met)"], human_path=hp("cold", "No path.", 0), note=None, calibration=None, next_step=None)

add(title="Group Product Manager, Agents", company="Northwind Labs", location="Boston, MA (hybrid)", score=9, role_type="ai-product-pm", work_model="hybrid, 3 days", travel=None,
    comp="$190-220K plus equity", verdict=None, stage=None, first=0, flag=False, source="linkedin:ai-product-manager-boston", url="https://northwindlabs.example.com/jobs/gpm-agents",
    posting=posting("active", since=0, checks=1, posted=1), why="A second seat on the agent platform, a level below the lead role already applied to.",
    mismatch="A level below; the same company already has an application in.", math="base 5; agent development in production +2; growing +1; hybrid Boston +1 = 9",
    bullets=["Owns two agent squads", "Reports to the Lead PM, Agent Platform"], qualifications=["Agent product experience (met)"],
    human_path=hp("warm reachable", "Marcus Lind, as for the lead role.", 0), note=None, calibration=None, next_step=None, siblings=[("Lead Product Manager, Agent Platform", "pursue")])

add(title="Senior Manager, AI Enablement", company="Halcyon Insurance", location="Boston, MA (hybrid)", score=8, role_type="enablement-adoption", work_model="hybrid, 2 days", travel=None,
    comp="$150-170K", verdict=None, stage=None, first=1, flag=False, source="indeed:ai-enablement-boston", url="https://halcyon.example.com/careers/senior-manager-ai-enablement",
    posting=posting("active", since=1, checks=2, posted=2), why="Enablement seat under the VP being pursued.", mismatch="Two levels below the VP seat.",
    math="base 5; enterprise AI adoption +2; hybrid Boston +1 = 8", bullets=["Runs training and playbooks for the claims AI program"], qualifications=["Enablement experience (met)"],
    human_path=hp("warm reachable", "Same path as the VP role.", 1), note=None, calibration=None, next_step=None, siblings=[("VP, AI Transformation", "pursue")])

add(title="Director, Product Operations and AI", company="Fathom Biotech", location="Cambridge, MA", score=8, role_type="program-project", work_model="on-site", travel=None,
    comp="$200-230K", verdict=None, stage=None, first=1, flag=False, source="web:sweep", url="https://fathombio.example.com/careers/director-product-ops-ai",
    posting=posting("active", since=1, checks=2, posted=3), why="Runs the computational platform's program office and its AI tooling.", mismatch="Biotech; on-site; program office.",
    math="base 5; AI program +2; Cambridge +1 = 8", bullets=["Runs the platform program office", "Owns AI tooling adoption in research"], qualifications=["Biotech experience preferred (not met)"],
    human_path=hp("cold", "No path.", 1), note=None, calibration=None, next_step=None)

add(title="Head of Product, Autonomy", company="Quarry Robotics", location="Somerville, MA", score=8, role_type="ai-product-pm", work_model="on-site", travel=None, comp="$210-240K plus equity",
    verdict=None, stage=None, first=2, flag=False, source="builtin:sweep", url="https://quarry.example.com/careers/head-of-product-autonomy", posting=posting("active", since=2, checks=2, posted=3),
    why="Head of product at a growing robotics company.", mismatch="Hardware; robotics domain.", math="base 5; head of product +2; growing +1 = 8",
    bullets=["Owns the autonomy product line", "Reports to the CEO"], qualifications=["Robotics experience preferred (not met)"], human_path=hp("cold", "No path.", 2), note=None, calibration=None, next_step=None)

add(title="AI Program Director, Transformation", company="Bluebird Retail", location="Remote (US)", score=8, role_type="transformation-owner", work_model="remote", travel="monthly",
    comp="$170-190K", verdict=None, stage=None, first=2, flag=False, source="linkedin:ai-transformation-us", url="https://bluebird.example.com/careers/ai-program-director",
    posting=posting("unreachable", since=2, checks=2, http=403), why="Owns the AI program for store operations.", mismatch="Retail; thin description.", math="base 5; transformation owner +2; remote +1 = 8",
    bullets=["Owns the AI program for store operations"], qualifications=["Retail experience preferred (not met)"], human_path=hp("cold", "No path.", 2), note=None, calibration=None, next_step=None)

add(title="Director, AI Platform Adoption", company="Meridian Software", location="Cambridge, MA (hybrid)", score=8, role_type="enablement-adoption", work_model="hybrid, 3 days", travel="15%",
    comp="$180-210K", verdict=None, stage=None, first=3, flag=False, source="linkedin:ai-enablement-boston", url="https://meridian.example.com/careers/director-ai-platform-adoption",
    posting=posting("active", since=3, checks=2, posted=4), why="Customer-facing adoption of the agent layer across the installed base.", mismatch="Customer success in all but name.",
    math="base 5; AI adoption +2; hybrid Cambridge +1 = 8", bullets=["Owns adoption of the agent layer by the top 100 accounts"], qualifications=["Customer-facing experience (met)"],
    human_path=hp("cold", "No path.", 3), note=None, calibration=None, next_step=None, siblings=[("Principal Product Manager, AI Platform", "pursue")])

# Borderline: 7s ------------------------------------------------------------------------------------------------
add(title="Senior Product Manager, AI Features", company="Juniper Education", location="Cambridge, MA (hybrid)", score=7, role_type="ai-product-pm", work_model="hybrid", travel=None,
    comp="$150-170K", verdict=None, stage=None, first=1, flag=False, source="builtin:sweep", url="https://juniper.example.com/careers/senior-pm-ai-features", posting=posting("active", since=1, checks=2, posted=2),
    why="AI tutoring features.", mismatch="Senior PM is below the level.", math="base 5; AI product +1; hybrid +1 = 7", bullets=["Owns tutoring features"], qualifications=["AI product experience"],
    human_path=None, note=None, calibration=None, next_step=None)

add(title="Manager, AI Governance", company="Silverline Bank", location="Boston, MA (hybrid)", score=7, role_type="governance-risk", work_model="hybrid", travel=None, comp="$140-160K",
    verdict=None, stage=None, first=2, flag=False, source="indeed:ai-enablement-boston", url="https://silverline.example.com/careers/manager-ai-governance", posting=posting("active", since=2, checks=2, posted=3),
    why="Model risk for generative AI.", mismatch="Governance, not build; manager level.", math="base 5; regulated AI +1; hybrid Boston +1 = 7", bullets=["Owns the generative AI control framework"],
    qualifications=["Model risk experience preferred"], human_path=None, note=None, calibration=None, next_step=None)

add(title="Technical Program Manager, AI", company="Kestrel Aerospace", location="Burlington, MA", score=7, role_type="program-project", work_model="on-site", travel=None, comp="$160-180K",
    verdict=None, stage=None, first=3, flag=False, source="linkedin:ai-product-manager-boston", url="https://kestrel.example.com/careers/tpm-ai", posting=posting("active", since=3, checks=2, posted=4),
    why="TPM for the applied AI group.", mismatch="TPM; Burlington.", math="base 5; AI program +1; growing +1 = 7", bullets=["Runs the applied AI group's programs"], qualifications=["TPM experience"],
    human_path=None, note=None, calibration=None, next_step=None)

# Maybe ---------------------------------------------------------------------------------------------------------
add(title="Director, Enterprise AI Strategy", company="Larkspur Consulting", location="Boston, MA", score=8, role_type="consulting-advisory", work_model="hybrid, client travel", travel="most weeks",
    comp="$220K", verdict="maybe", stage=None, first=10, verdict_days=9, flag=False, source="linkedin:ai-transformation-us", url="https://larkspur.example.com/careers/director-enterprise-ai-strategy",
    posting=posting("active", since=10, checks=4, posted=11), why="Strategy work in the AI practice.", mismatch="Travel most weeks; strategy, not build.", math="base 5; AI practice +2; Boston +1 = 8",
    bullets=["Leads strategy engagements"], qualifications=["Consulting experience (partly met)"], human_path=hp("warm active", "Dana Okafor knows the practice head.", 9),
    note="Parked: the firm just rejected me for the transformation seat; wait a quarter.", calibration="About right", next_step=None)

# Passed --------------------------------------------------------------------------------------------------------
PASSES = [
    ("Chief of Staff, AI", "Ironwood Manufacturing", "Columbus, OH", 8, "other", "on-site", 30, 29, "Relocation to Columbus. Not doing that.", "About right", "linkedin:ai-transformation-us"),
    ("Director, Product Marketing, AI", "Meridian Software", "Cambridge, MA", 8, "other", "hybrid", 26, 25, "Product marketing, not product. Pass.", "Too high", "linkedin:ai-product-manager-boston"),
    ("AI Solutions Engineer", "Northwind Labs", "Boston, MA", 8, "fde-embedded", "hybrid", 23, 22, "Individual contributor engineering seat; the rubric likes the company too much.", "Too high", "builtin:sweep"),
    ("Senior Director, IT Strategy", "Beacon Health Systems", "Boston, MA", 8, "transformation-owner", "on-site", 20, 19, "IT strategy, not AI; the title matched and the body did not.", "Too high", "linkedin:ai-transformation-us"),
    ("Head of Data Science", "Silverline Bank", "Boston, MA", 8, "other", "hybrid", 18, 17, "Data science leadership; needs a PhD and ten years of modelling.", "Too high", "indeed:ai-enablement-boston"),
    ("Product Manager, AI Tutoring", "Juniper Education", "Cambridge, MA", 7, "ai-product-pm", "hybrid", 17, 16, "Too junior.", "About right", "builtin:sweep"),
    ("VP Engineering, AI", "Quarry Robotics", "Somerville, MA", 8, "other", "on-site", 13, 12, "Engineering leadership. Not me.", "Too high", "builtin:sweep"),
    ("Consultant, AI Practice", "Larkspur Consulting", "Boston, MA", 7, "consulting-advisory", "hybrid", 12, 11, "Consultant level.", "About right", "linkedin:ai-transformation-us"),
    ("Director, Claims Operations", "Halcyon Insurance", "Boston, MA", 7, "other", "hybrid", 8, 7, "Operations line role; AI is a line in the posting.", "About right", "indeed:ai-enablement-boston"),
]
for t, co, loc, sc, rt, wm, first, vd, note, cal, src in PASSES:
    add(title=t, company=co, location=loc, score=sc, role_type=rt, work_model=wm, travel=None, comp="Not in the posting", verdict="pass", stage=None, first=first, verdict_days=vd, flag=False,
        source=src, url=f"{COMPANIES[co]['url']}/careers/{t.lower().replace(',', '').replace(' ', '-')}", posting=posting("active", since=first, checks=5, posted=first + 1),
        why=f"{t} at {co}.", mismatch=note, math=f"base 5; title match +2; Boston +1 = {sc}", bullets=[f"{t}: the posting's bullets"], qualifications=["As posted"], human_path=None,
        note=note, calibration=cal, next_step=None)

# Excluded by the rubric's gates --------------------------------------------------------------------------------
add(title="Director, AI Product", company="Pinecrest Media", location="New York, NY (on-site)", score=8, role_type="ai-product-pm", work_model="on-site", travel=None, comp="$190K",
    verdict=None, stage=None, first=9, flag=False, source="linkedin:ai-product-manager-us", url="https://pinecrest.example.com/careers/director-ai-product", posting=posting("active", since=9, checks=4, posted=10),
    why="AI product at a media group.", mismatch="New York on-site, five days.", math="base 5; AI product +2; shrinking company 0 = 8; gate: location (on-site outside Boston)", bullets=["Owns AI products"],
    qualifications=["Media experience"], human_path=None, note=None, calibration=None, next_step=None, excluded="Location gate: on-site five days in New York")
add(title="Global Head of AI Transformation", company="Ironwood Manufacturing", location="Columbus, OH", score=9, role_type="transformation-owner", work_model="on-site", travel="30%", comp="$300K",
    verdict=None, stage=None, first=14, flag=False, source="linkedin:ai-transformation-us", url="https://ironwood.example.com/careers/global-head-ai-transformation", posting=posting("active", since=14, checks=6, posted=15),
    why="A big transformation seat.", mismatch="Columbus, relocation required.", math="base 5; transformation owner +3; travel 30% 0 = 9; gate: location (relocation)", bullets=["Owns the global AI program"],
    qualifications=["Manufacturing experience"], human_path=None, note=None, calibration=None, next_step=None, excluded="Location gate: relocation to Columbus required")


# --------------------------------------------------------------------------------------------------------------
# Build the records
# --------------------------------------------------------------------------------------------------------------
def doc_html(j):
    """The role's job file, rendered as the engine renders markdown: the front door, then notes."""
    lines = [f"<strong>Company:</strong> {j['company']}", f"<strong>Job posting:</strong> <a href=\"{j['url']}\" target=\"_blank\" rel=\"noopener\">{j['url']}</a>",
             f"<strong>Status:</strong> {j.get('stage', '') and j['stage'].capitalize() or 'To review'}",
             f"<strong>Verdict:</strong> {(j.get('verdict') or '').capitalize() or 'none'}" + (f" (the owner, {d(j['verdict_days'])})" if j.get("verdict_days") is not None else "")]
    if j.get("human_path"):
        lines.append(f"<strong>Human path:</strong> {j['human_path']['verdict']}. {j['human_path']['people']}")
    out = para(*lines)
    if j.get("in_process"):
        out += "<h2>Notes</h2>" + para(f"{j['why']} The owner's read after the first conversation: {j.get('note') or ''}") + \
            para("<strong>What we learned:</strong> the hiring manager has the budget and the mandate; the risk is the timeline, which depends on a board meeting at the end of the month.")
    return out


def campaign(j):
    if not j.get("in_process") or j.get("stage") == "closed":
        return None
    who = {"Granite Peak Capital": ["Priya Natarajan (CIO)", "Theo Brandt (Head of Portfolio Operations)"], "Northwind Labs": ["Casey Whitfield (recruiter)"], "Silverline Bank": ["Recruiting team"]}[j["company"]]
    stake = {"Priya Natarajan (CIO)": ("CIO; hiring manager", "that the owner will ship inside her governance, not around it", "a product person who talks and does not build"),
             "Theo Brandt (Head of Portfolio Operations)": ("runs the portfolio operations group", "that his team's time will be respected", "another tool nobody uses"),
             "Casey Whitfield (recruiter)": ("recruiter", "a clean story in three sentences", "a candidate the VP will not want to meet")}
    return {"updated": d(1), "stale": "" if j["company"] != "Silverline Bank" else "the brief predates the application; regenerate once a recruiter screen is booked",
            "next": {"who": who, "when": {"Granite Peak Capital": d(-2) + ", 10:00", "Northwind Labs": d(-1) + ", 15:30", "Silverline Bank": "not yet booked"}[j["company"]],
                     "format": {"Granite Peak Capital": "in person, 60 minutes, two interviewers", "Northwind Labs": "video, 30 minutes", "Silverline Bank": ""}[j["company"]],
                     "before": "send the 90-day one-pager the night before" if j["company"] == "Granite Peak Capital" else ""},
            "ball": {"side": "you" if j["company"] == "Granite Peak Capital" else "them", "text": {"Granite Peak Capital": "send Priya the 90-day plan before the second round", "Northwind Labs": "Casey books the screen", "Silverline Bank": "the recruiter acknowledges the application"}[j["company"]], "since": d(2)},
            "people": [{"name": w, "role": stake.get(w, ("", "", ""))[0], "hear": stake.get(w, ("", "", ""))[1], "fear": stake.get(w, ("", "", ""))[2]} for w in who],
            "get_across": ["\"I built it\" in the first two sentences: originated the AI program at the previous employer and built its flagship workflow personally",
                           "The approval line: agents propose, people approve, and the audit trail is the product", "Comfortable being the only product person in the room"],
            "ask": ["Which workflows run every week today, and which did not stick?", "Who is the engineer, and what are they building right now?", "What would you call success at twelve months?", "What does on-site mean day to day?"],
            "avoid": ["Opening with governance or training; lead with the build", "Apologising for the lack of a software-company PM title"],
            "settled": [f"Title and level: {j['title']}", f"Location: {j['location']}", f"Comp: {j['comp']}"],
            "open": ["Who the role reports to day to day", "Whether the engineer reports in or is borrowed", "The timeline past the second round"],
            "fix": ["Say the numbers: the size of the program, the number of users, the time saved", "Ask about the team before the roadmap"],
            "pages": [{"label": "Prep: 90-day plan", "url": "#"}] if j["company"] == "Granite Peak Capital" else []}


def timeline(j):
    if not j.get("in_process"):
        return []
    co = j["company"]
    if co == "Granite Peak Capital":
        return [{"date": d(1), "what": "Second round confirmed for Thursday: the CIO and the head of portfolio operations, in person"},
                {"date": d(5), "what": "First round with Priya Natarajan (CIO), 45 minutes by video; went well, she asked for the 90-day plan"},
                {"date": d(9), "what": "Resume submitted by Dana Okafor (Harbor Search); the firm confirmed receipt the same day"},
                {"date": d(12), "what": "Call with Dana Okafor: the seat, the comp, the CIO's two years in; the owner inclined to move forward"},
                {"date": d(22), "what": "Verdict Pursue; deep pass run; scored 11"}]
    if co == "Northwind Labs":
        return [{"date": d(2), "what": "Recruiter screen booked with Casey Whitfield for next week"}, {"date": d(6), "what": "Applied through the careers site; resume v4, the agent-platform cover note"},
                {"date": d(8), "what": "Coffee with Marcus Lind: the team is real, funded through next year; he will mention the application to the VP Product"}, {"date": d(18), "what": "Verdict Pursue; scored 10"}]
    if co == "Silverline Bank":
        return [{"date": d(3), "what": "Applied through the careers site; acknowledgement email the same hour"}, {"date": d(14), "what": "Verdict Pursue; scored 9, the owner called it too high"}]
    if co == "Larkspur Consulting":
        return [{"date": d(9), "what": "Dana Okafor called: the practice chose an internal candidate; the door stays open for the strategy seat"},
                {"date": d(16), "what": "Second round with the practice head and two partners"}, {"date": d(25), "what": "First round by video"}, {"date": d(38), "what": "Verdict Pursue; Dana submitted the resume"}]
    return []


def log_rows(j):
    if not j.get("in_process"):
        return []
    co = j["company"]
    base = [{"url": "", "date": d(12), "time": "2:30 PM", "type": "Call", "what": "Harbor Search raised the seat; the owner inclined to move forward", "with": "Dana Okafor (Harbor Search)",
             "assets": [{"url": "#", "path": "meetings/" + d(12) + "-dana-okafor.md", "label": "Dana Okafor (Harbor Search), the seat raised"}]},
            {"url": "", "date": d(9), "time": "9:10 AM", "type": "Email", "what": "Go-ahead to Dana; resume v5 submitted unchanged", "with": "Dana Okafor", "assets": [{"url": "#", "path": "assets/resume-v5.pdf", "label": "Resume v5"}]},
            {"url": "", "date": d(5), "time": "11:00 AM", "type": "Meeting", "what": "First round with the CIO", "with": "Priya Natarajan", "assets": []},
            {"url": "", "date": d(4), "time": "8:05 PM", "type": "Sent", "what": "Thank-you note to Priya with the two follow-up links", "with": "Priya Natarajan", "assets": [{"url": "#", "path": "assets/thank-you-priya.md", "label": "Thank-you note"}]}]
    if co == "Granite Peak Capital":
        return base
    if co == "Northwind Labs":
        return [{"url": "", "date": d(8), "time": "8:00 AM", "type": "Meeting", "what": "Coffee with Marcus Lind", "with": "Marcus Lind", "assets": []},
                {"url": "", "date": d(6), "time": "10:40 PM", "type": "Sent", "what": "Application: resume v4 and the cover note", "with": "Northwind careers site", "assets": [{"url": "#", "path": "assets/resume-v4.pdf", "label": "Resume v4"}, {"url": "#", "path": "assets/cover-northwind.md", "label": "Cover note"}]},
                {"url": "", "date": d(2), "time": "4:15 PM", "type": "Email", "what": "Casey Whitfield proposes times for a screen", "with": "Casey Whitfield", "assets": []}]
    if co == "Silverline Bank":
        return [{"url": "", "date": d(3), "time": "9:30 PM", "type": "Sent", "what": "Application through the careers site", "with": "Silverline careers site", "assets": [{"url": "#", "path": "assets/resume-v5.pdf", "label": "Resume v5"}]}]
    return [{"url": "", "date": d(9), "time": "3:00 PM", "type": "Call", "what": "Dana: internal candidate chosen", "with": "Dana Okafor", "assets": []}]


def assets(j):
    if not j.get("in_process"):
        return []
    co = j["company"]
    rows = [{"url": "#", "date": "", "kind": "doc", "path": f"opportunities/{j['slug']}/campaign.md", "group": "Campaign", "label": f"Campaign: {j['title']} ({co})"},
            {"url": "#", "date": "", "kind": "doc", "path": f"opportunities/{j['slug']}/log.md", "group": "Opportunity", "label": f"Log: {co}, {j['title']}"},
            {"url": "#", "date": d(9), "kind": "pdf", "path": "assets/resume-v5.pdf", "group": "Resume", "label": "Resume v5", "sent": d(9) + " to Dana Okafor"}]
    if co == "Granite Peak Capital":
        rows += [{"url": "#", "date": d(1), "kind": "doc", "path": f"opportunities/{j['slug']}/roadmap/first-90-days.md", "group": "Prep", "label": "First 90 days, one page"},
                 {"url": "#", "date": d(4), "kind": "doc", "path": "assets/thank-you-priya.md", "group": "Sent", "label": "Thank-you note to Priya", "sent": d(4) + " to Priya Natarajan"}]
    if co == "Northwind Labs":
        rows = rows[:2] + [{"url": "#", "date": d(6), "kind": "pdf", "path": "assets/resume-v4.pdf", "group": "Resume", "label": "Resume v4", "sent": d(6) + " through the careers site"},
                           {"url": "#", "date": d(6), "kind": "doc", "path": "assets/cover-northwind.md", "group": "Cover", "label": "Cover note", "sent": d(6) + " through the careers site"}]
    return rows


def meetings_vault(j):
    if not j.get("in_process"):
        return []
    if j["company"] == "Granite Peak Capital":
        return [{"url": "#", "date": d(12), "kind": "Meeting", "what": "Dana Okafor (Harbor Search), the seat raised"}, {"url": "#", "date": d(5), "kind": "Meeting", "what": "Priya Natarajan (CIO), first round"}]
    if j["company"] == "Northwind Labs":
        return [{"url": "#", "date": d(8), "kind": "Meeting", "what": "Marcus Lind, coffee"}]
    return []


def make_job(j):
    rid = jid(j["url"])
    j["id"] = rid
    j["slug"] = j["company"].lower().replace(" ", "-") + "-" + j["title"].lower().replace(",", "").replace(" ", "-")[:40]
    pursue = j.get("verdict") == "pursue"
    rec = {
        "id": rid, "url": j["url"], "title": j["title"], "company": j["company"], "company_key": j["company"], "location": j["location"], "comp": j.get("comp"),
        "source": j["source"], "date_first_seen": d(j["first"]), "score": j["score"], "score_kind": "deep", "why": j["why"], "mismatch": j["mismatch"], "math": j["math"],
        "bullets": j["bullets"], "qualifications": j["qualifications"], "alert": "new this morning" if j["first"] == 0 else None, "note": j.get("note"),
        "work_model": j["work_model"], "travel": j.get("travel"), "role_type": j["role_type"], "deep_pass_date": d(j["first"]), "rubric_version": "v3.2",
        "flag": j.get("flag", False), "verdict": j.get("verdict"), "verdict_date": d(j["verdict_days"]) if j.get("verdict_days") is not None else None,
        "verdict_ts": ts(j["verdict_days"], "22:15") if j.get("verdict_days") is not None else None, "calibration": j.get("calibration"), "status_note": None,
        "stage": j.get("stage"), "stage_date": d(j["stage_days"]) if j.get("stage_days") is not None else (d(j["first"]) if j.get("stage") else None),
        "stage_ts": ts(j["stage_days"], "23:40") if j.get("stage_days") is not None else (ts(j["first"] - 0, "14:00") if j.get("stage") else None),
        "outcome": j.get("outcome"), "next_step": j.get("next_step"), "next_step_date": d(j["next_days"]) if j.get("next_days") is not None else None,
        "job_file": f"jobs/{j['slug']}" if (pursue or j.get("verdict")) else None, "excluded": j.get("excluded"),
        "office": office(j["company"]), "human_path": j.get("human_path"), "posting": j["posting"], "siblings": [],
        "doc": doc_html(j) if (pursue or j.get("verdict") == "maybe") else "", "campaign": campaign(j), "timeline": timeline(j), "assets": assets(j), "meetings_vault": meetings_vault(j), "log": log_rows(j),
    }
    rec["posting"]["url_checked"] = j["url"]
    return rec


RECORDS = [make_job(j) for j in JOBS]
BY_TITLE = {r["title"]: r for r in RECORDS}
for j in JOBS:
    for t, what in j.get("siblings", []):
        s = BY_TITLE[t]
        BY_TITLE[j["title"]]["siblings"].append({"id": s["id"], "title": s["title"], "what": f"{what} {s['verdict_date']}"})

# --------------------------------------------------------------------------------------------------------------
# People (the Network tab), opportunities, meetings, tasks: the Notion mirrors
# --------------------------------------------------------------------------------------------------------------
CONTACTS = [
    dict(id="c-dana-okafor", name="Dana Okafor", company="Harbor Search", role="Partner, technology practice", how="Inbound recruiter", status="In conversation", priority="High",
         hook="Runs the Granite Peak process; placed two CIOs the owner knows", notes="Straight talker. Prefers a call to email. Sends the JD within the hour.",
         linkedin="https://www.linkedin.com/in/example-dana-okafor", touches=[dict(date=d(12), type="Call", note="The Granite Peak seat raised"), dict(date=d(9), type="Email", note="Go-ahead; resume submitted")],
         last_date=d(9), last_type="Email", last_note="Go-ahead; resume submitted", next_date=d(-1), next_type="Call", next_action="Ask where the second round decision sits and who else is in it", roles=["Director, AI Product, Investment Platform"]),
    dict(id="c-priya-natarajan", name="Priya Natarajan", company="Granite Peak Capital", role="Chief Information Officer", how="Hiring manager, through Harbor Search", status="In conversation", priority="High",
         hook="Two years into the AI program; built the governance herself", notes="Direct, builds things, wants a peer. Asked for the 90-day plan without prompting.",
         linkedin="https://www.linkedin.com/in/example-priya-natarajan", touches=[dict(date=d(5), type="Meeting", note="First round, 45 minutes"), dict(date=d(4), type="Email", note="Thank-you note with two links")],
         last_date=d(4), last_type="Email", last_note="Thank-you note", next_date=d(-2), next_type="Meeting", next_action="Second round, in person, with Theo Brandt", roles=["Director, AI Product, Investment Platform"]),
    dict(id="c-marcus-lind", name="Marcus Lind", company="Northwind Labs", role="VP Engineering", how="Former colleague", status="In conversation", priority="High",
         hook="Ran platform engineering at the previous employer; moved to Northwind last year", notes="Will put in a word with the VP Product. Rides on Sundays.",
         linkedin="https://www.linkedin.com/in/example-marcus-lind", touches=[dict(date=d(8), type="Coffee", note="The agent team is real and funded")],
         last_date=d(8), last_type="Coffee", last_note="The agent team is real and funded", next_date=d(0), next_type="Message", next_action="Tell him the screen is booked; ask him to mention it to the VP Product", roles=["Lead Product Manager, Agent Platform"]),
    dict(id="c-sam-delgado", name="Sam Delgado", company="Independent", role="Board member, Halcyon Insurance; former COO", how="Friend", status="In conversation", priority="High",
         hook="Sits on Halcyon's board; knows Elena Marsh well", notes="Offered the introduction to Elena. Wants the two-line blurb first.",
         linkedin="https://www.linkedin.com/in/example-sam-delgado", touches=[dict(date=d(6), type="Call", note="Offered the Elena intro")],
         last_date=d(6), last_type="Call", last_note="Offered the Elena intro", next_date=d(1), next_type="Email", next_action="Send the two-line blurb for the Elena Marsh introduction", roles=["VP, AI Transformation"]),
    dict(id="c-elena-marsh", name="Elena Marsh", company="Halcyon Insurance", role="Chief Claims Officer", how="Via Sam Delgado", status="Not contacted", priority="High",
         hook="Owns the claims AI program; the VP seat reports to her", notes="Spoke at an industry conference about claims triage; the talk is on the conference site.",
         linkedin="https://www.linkedin.com/in/example-elena-marsh", touches=[], last_date=None, last_type=None, last_note=None, next_date=d(-3), next_type="Email", next_action="Wait for Sam's introduction, then reply within the hour", roles=["VP, AI Transformation"]),
    dict(id="c-jordan-pike", name="Jordan Pike", company="Orchard Analytics", role="Head of AI Practice", how="Cold note on LinkedIn", status="In conversation", priority="Medium",
         hook="Replied to a cold note within a day", notes="Wants to talk about the forward-deployed model before the role.",
         linkedin="https://www.linkedin.com/in/example-jordan-pike", touches=[dict(date=d(4), type="Message", note="Replied; proposed Thursday")],
         last_date=d(4), last_type="Message", last_note="Proposed Thursday", next_date=d(-1), next_type="Call", next_action="Call: the embedded model, the travel, the client mix", roles=["Forward Deployed Product Lead"]),
    dict(id="c-amara-osei", name="Amara Osei", company="Beacon Health Systems", role="Chief Medical Information Officer", how="Served on a nonprofit board together", status="Dormant", priority="Medium",
         hook="Knows the CDO; can say what the AI office is really for", notes="Last spoke in the spring.", linkedin="https://www.linkedin.com/in/example-amara-osei",
         touches=[dict(date=d(150), type="Coffee", note="Spring catch-up")], last_date=d(150), last_type="Coffee", last_note="Spring catch-up", next_date=d(4), next_type="Email", next_action="Ask what the CDO is actually trying to do with the AI office", roles=["Senior Director, Digital Transformation"]),
    dict(id="c-ravi-menon", name="Ravi Menon", company="Tidewater Logistics", role="Chief Product Officer", how="Former employer, different division", status="Not contacted", priority="Medium",
         hook="Shares a previous employer; posted the VP role himself", notes="", linkedin="https://www.linkedin.com/in/example-ravi-menon", touches=[], last_date=None, last_type=None, last_note=None,
         next_date=d(0), next_type="Message", next_action="Note on LinkedIn: the shared employer, the carrier desk problem", roles=["VP Product, AI Workflows"]),
    dict(id="c-theo-brandt", name="Theo Brandt", company="Granite Peak Capital", role="Head of Portfolio Operations", how="Second-round interviewer", status="Not contacted", priority="Medium",
         hook="The internal customer for the seat", notes="Joined from an operating role at a portfolio company.", linkedin="https://www.linkedin.com/in/example-theo-brandt", touches=[],
         last_date=None, last_type=None, last_note=None, next_date=d(-2), next_type="Meeting", next_action="Second round", roles=["Director, AI Product, Investment Platform"]),
    dict(id="c-casey-whitfield", name="Casey Whitfield", company="Northwind Labs", role="Senior Recruiter", how="Application", status="In conversation", priority="Low",
         hook="", notes="", linkedin="", touches=[dict(date=d(2), type="Email", note="Proposed times for the screen")], last_date=d(2), last_type="Email", last_note="Proposed times",
         next_date=d(-1), next_type="Call", next_action="Recruiter screen", roles=["Lead Product Manager, Agent Platform"]),
    dict(id="c-lena-fischer", name="Lena Fischer", company="Fischer Advisory", role="Principal", how="Former client", status="Working together", priority="Medium",
         hook="A small consulting engagement, not job search", notes="Monthly check-in; the engagement runs to year end.", linkedin="", touches=[dict(date=d(10), type="Call", note="Monthly check-in")],
         last_date=d(10), last_type="Call", last_note="Monthly check-in", next_date=d(-20), next_type="Call", next_action="Monthly check-in", roles=[]),
    dict(id="c-owen-hart", name="Owen Hart", company="Meridian Software", role="Director, Platform Engineering", how="Conference", status="Dormant", priority="Low",
         hook="Met at a conference two years ago; works near the AI platform group", notes="", linkedin="https://www.linkedin.com/in/example-owen-hart", touches=[],
         last_date=None, last_type=None, last_note=None, next_date=d(6), next_type="Message", next_action="Ask who runs the AI platform group and whether the principal seat is a build", roles=["Principal Product Manager, AI Platform"]),
]
for c in CONTACTS:
    c["roles"] = [BY_TITLE[t]["id"] for t in c["roles"]]
    c["url"] = "#"
    c["last_met"] = None
    c["edited"] = ts(1, "16:00")

OPPS = {}
MEET_IDS = {"m-dana-1": ("Director, AI Product, Investment Platform",), "m-priya-1": ("Director, AI Product, Investment Platform",), "m-marcus-1": ("Lead Product Manager, Agent Platform",),
            "m-sam-1": ("VP, AI Transformation",), "m-dana-larkspur": ("Head of AI Transformation",)}
for r in RECORDS:
    if r["verdict"] == "pursue":
        people = [c["id"] for c in CONTACTS if r["id"] in c["roles"]]
        OPPS[r["id"]] = {"id": r["id"], "page": "page-" + r["id"], "url": "#", "flag": r["flag"], "stage": r["stage"], "outcome": r["outcome"], "next": r["next_step"], "next_date": r["next_step_date"],
                         "company": "co-" + r["company_key"].lower().replace(" ", "-"), "company_name": r["company"], "people": people, "meetings": [m for m, t in MEET_IDS.items() if t[0] == r["title"]],
                         "tasks": [], "hp": r["human_path"]["verdict"] if r.get("human_path") else None, "hp_people": r["human_path"]["people"] if r.get("human_path") else None, "edited": ts(1, "12:00")}

MEETINGS = [
    dict(id="m-dana-1", name="Call with Dana Okafor (Harbor Search), the Granite Peak seat", date=d(12), type="External", status="Complete", people=["c-dana-okafor"], opps=["page-" + BY_TITLE["Director, AI Product, Investment Platform"]["id"]],
         companies=["co-granite-peak-capital"], summary="Dana raised the Granite Peak seat: the CIO two years into the AI program, an engineer reporting in, base about $240K. The owner inclined to move forward.",
         actions="Dana submits the resume unchanged. The owner reads the firm's team page and drafts questions for the CIO."),
    dict(id="m-priya-1", name="First round with Priya Natarajan (CIO), Granite Peak", date=d(5), type="External", status="Complete", people=["c-priya-natarajan"], opps=["page-" + BY_TITLE["Director, AI Product, Investment Platform"]["id"]],
         companies=["co-granite-peak-capital"], summary="45 minutes by video. Priya walked through the two years: the tools licensed, the governance written, the three workflows that stuck and the five that did not. She asked for a 90-day plan.",
         actions="Send the 90-day plan before the second round. Prepare for Theo Brandt: what his team needs to hear."),
    dict(id="m-marcus-1", name="Coffee with Marcus Lind (Northwind Labs)", date=d(8), type="External", status="Complete", people=["c-marcus-lind"], opps=["page-" + BY_TITLE["Lead Product Manager, Agent Platform"]["id"]],
         companies=["co-northwind-labs"], summary="The agent platform team is real, funded through next year, twelve engineers. The VP Product is new and hiring her first PMs.", actions="Apply through the site; Marcus mentions it to the VP Product."),
    dict(id="m-sam-1", name="Call with Sam Delgado about Halcyon", date=d(6), type="External", status="In Progress", people=["c-sam-delgado"], opps=["page-" + BY_TITLE["VP, AI Transformation"]["id"]],
         companies=["co-halcyon-insurance"], summary="Sam knows Elena Marsh well and offered the introduction. He wants a two-line blurb first.", actions="Send Sam the blurb. Read Elena's conference talk."),
    dict(id="m-dana-larkspur", name="Call with Dana Okafor: Larkspur outcome", date=d(9), type="External", status="Complete", people=["c-dana-okafor"], opps=["page-" + BY_TITLE["Head of AI Transformation"]["id"]],
         companies=["co-larkspur-consulting"], summary="Larkspur chose an internal candidate. Dana thinks the strategy seat is a better fit and will raise it in a quarter.", actions="Park the strategy seat as Maybe."),
]
for m in MEETINGS:
    m["url"] = "#"

TASKS = [
    dict(id="t-1", title="Send Priya the 90-day plan one-pager", due=d(-1), plan_day=d(0), priority="P1", status="In Progress", project="Job Pipeline", opps=["page-" + BY_TITLE["Director, AI Product, Investment Platform"]["id"]], notes="Draft in opportunities/granite-peak/roadmap/first-90-days.md. Keep it to one page."),
    dict(id="t-2", title="Send Sam the two-line blurb for the Elena Marsh intro", due=d(1), plan_day=d(0), priority="P1", status="To Do", project="Networking", opps=["page-" + BY_TITLE["VP, AI Transformation"]["id"]], notes="Two lines: what the owner built, what the claims program needs."),
    dict(id="t-3", title="Prep for Jordan Pike: the embedded model and the travel", due=d(-1), plan_day=d(-1), priority="P2", status="To Do", project="Job Pipeline", opps=["page-" + BY_TITLE["Forward Deployed Product Lead"]["id"]], notes="Three questions on the client mix; one on utilisation."),
    dict(id="t-4", title="Publish the AI approval-line post", due=d(-4), plan_day=d(-3), priority="P2", status="To Do", project="Portfolio and Writing", opps=[], notes="The piece Marcus asked for; useful for the Northwind screen."),
    dict(id="t-5", title="Run the monthly job title audit", due=d(-6), plan_day=None, priority="P3", status="To Do", project="Job Pipeline", opps=[], notes="Check which titles the radar is catching and which it is missing."),
    dict(id="t-6", title="Chase the Silverline recruiter if nothing by Friday", due=d(-2), plan_day=None, priority="P3", status="To Do", project="Job Pipeline", opps=["page-" + BY_TITLE["Head of AI Enablement, Operations"]["id"]], notes=""),
    dict(id="t-7", title="Read Meridian's platform engineering blog; find who runs the group", due=d(3), plan_day=None, priority="P3", status="To Do", project="Job Pipeline", opps=["page-" + BY_TITLE["Principal Product Manager, AI Platform"]["id"]], notes=""),
    dict(id="t-8", title="Update the master resume with the agent pipeline numbers", due=d(2), plan_day=d(1), priority="P2", status="To Do", project="Portfolio and Writing", opps=[], notes="Users, time saved, the audit trail."),
    dict(id="t-9", title="Thank-you note to Marcus after the screen", due=None, plan_day=None, priority="P3", status="To Do", project="Networking", opps=["page-" + BY_TITLE["Lead Product Manager, Agent Platform"]["id"]], notes=""),
]
for t in TASKS:
    t.update(url="#", area="career", waiting=None, meetings=[], edited=ts(1, "09:00"))
for t in TASKS:
    for pg in t["opps"]:
        for o in OPPS.values():
            if o["page"] == pg:
                o["tasks"].append(t["id"])

# --------------------------------------------------------------------------------------------------------------
# board_meta: summary, companies, paths, views, stage history, pulse, org chart, network pages
# --------------------------------------------------------------------------------------------------------------
PATHS = {
    "Northwind Labs": {"first": [{"id": "marcus-lind", "url": "https://www.linkedin.com/in/example-marcus-lind", "name": "Marcus Lind", "tags": ["former-colleague"], "since": "2019", "title": "VP Engineering", "vault": "people/marcus-lind"}],
                       "second": [{"name": "Nia Ortega", "title": "VP Product", "via": "Marcus Lind", "url": ""}, {"name": "Ben Castellano", "title": "Director of Design", "via": "a former colleague", "url": ""}], "vault": ["people/marcus-lind"], "affinity_only": []},
    "Granite Peak Capital": {"first": [], "second": [{"name": "Theo Brandt", "title": "Head of Portfolio Operations", "via": "Sam Delgado", "url": ""}], "vault": ["people/priya-natarajan"],
                             "affinity_only": [{"name": "Rosa Lindqvist", "title": "Managing Director", "tags": ["alumni"], "url": ""}]},
    "Halcyon Insurance": {"first": [], "second": [{"name": "Elena Marsh", "title": "Chief Claims Officer", "via": "Sam Delgado", "url": ""}], "vault": ["people/elena-marsh"], "affinity_only": []},
    "Beacon Health Systems": {"first": [{"id": "amara-osei", "url": "https://www.linkedin.com/in/example-amara-osei", "name": "Amara Osei", "tags": ["nonprofit-board"], "since": "2021", "title": "Chief Medical Information Officer", "vault": ""}], "second": [], "vault": [], "affinity_only": []},
    "Tidewater Logistics": {"first": [{"id": "ravi-menon", "url": "https://www.linkedin.com/in/example-ravi-menon", "name": "Ravi Menon", "tags": ["former-employer"], "since": "2016", "title": "Chief Product Officer", "vault": ""}], "second": [], "vault": [], "affinity_only": []},
    "Orchard Analytics": {"first": [], "second": [], "vault": ["people/jordan-pike"], "affinity_only": []},
    "Meridian Software": {"first": [{"id": "owen-hart", "url": "https://www.linkedin.com/in/example-owen-hart", "name": "Owen Hart", "tags": ["conference"], "since": "2024", "title": "Director, Platform Engineering", "vault": ""}], "second": [], "vault": [], "affinity_only": []},
    "Larkspur Consulting": {"first": [], "second": [{"name": "Practice head", "title": "Head of AI Practice", "via": "Dana Okafor", "url": ""}], "vault": [], "affinity_only": []},
}

VIEWS = {"jobs": {}, "startups": {}}
for r in RECORDS:
    if r.get("note"):
        VIEWS["jobs"][r["id"]] = {"src": r["note"], "view": r["note"]}

STAGE_HIST = {"asof": d(0), "roles": {}}
for r in RECORDS:
    if r["verdict"] == "pursue":
        hist = [{"date": r["verdict_date"], "stage": "shortlist", "source": "seed"}]
        order = STAGES.index(r["stage"])
        for i in range(1, order + 1):
            hist.append({"date": d(max(0, (GENERATED - date.fromisoformat(r["stage_date"])).days + (order - i) * 3)), "stage": STAGES[i], "source": "push"})
        STAGE_HIST["roles"][r["id"]] = hist

PULSE = {"days": {}}
for i in range(21, -1, -1):
    PULSE["days"][d(i)] = {"shortlist": 7 + (i // 7), "in_process": 3 if i < 6 else 2 if i < 15 else 1, "tasks_open": 8 + (i % 3), "tasks_week": 3, "touches_7d": 4 + (i % 4),
                           "tasks_overdue": 2 if i < 5 else 1, "people_overdue": 3 if i < 4 else 2, "people_due_week": 4}

TIERS = [{"key": "chair", "label": "Founder and Chairman"}, {"key": "heads", "label": "C-suite and functional heads"}, {"key": "smd", "label": "Senior Managing Director, Partner, Vice Chairman"},
         {"key": "md", "label": "Managing Director"}, {"key": "principal", "label": "Director, Principal, SVP"}, {"key": "vp", "label": "Vice President"}, {"key": "sr_assoc", "label": "Senior Associate"},
         {"key": "assoc", "label": "Associate"}, {"key": "analyst", "label": "Analyst"}, {"key": "staff", "label": "Staff and support"}, {"key": "advisors", "label": "Operating partners and senior advisors"}]
ORG_PEOPLE = [
    ("Harold Finch", "Founder and Chairman", "chair", "Investments", "Boston", True, None), ("Priya Natarajan", "Chief Information Officer", "heads", "Technology", "Boston", True, ["process", "network", "vault"]),
    ("Yusuf Adeyemi", "Chief Financial Officer", "heads", "Finance", "Boston", True, None), ("Grace Holloway", "General Counsel", "heads", "Legal", "Boston", True, None),
    ("Theo Brandt", "Head of Portfolio Operations", "heads", "Portfolio Operations", "Boston", True, ["process", "network"]), ("Rosa Lindqvist", "Managing Director", "md", "Investments", "Boston", False, ["linkedin"]),
    ("Daniel Mbeki", "Managing Director", "md", "Investments", "New York", False, None), ("Claire Fontaine", "Senior Managing Director", "smd", "Investments", "Boston", False, None),
    ("Ivan Petrov", "Managing Director, Investor Relations", "md", "Investor Relations", "New York", False, None), ("Mei Tanaka", "Principal", "principal", "Investments", "Boston", False, None),
    ("Noah Feldman", "Principal", "principal", "Investments", "New York", False, None), ("Sofia Reyes", "Director, Portfolio Operations", "principal", "Portfolio Operations", "Boston", False, None),
    ("Liam O'Connor", "Vice President", "vp", "Investments", "Boston", False, None), ("Hana Kowalski", "Vice President", "vp", "Investments", "Boston", False, None),
    ("Arjun Mehta", "Vice President, Technology", "vp", "Technology", "Boston", False, None), ("Zoe Laurent", "Senior Associate", "sr_assoc", "Investments", "New York", False, None),
    ("Felix Wagner", "Senior Associate", "sr_assoc", "Investments", "Boston", False, None), ("Maya Singh", "Associate", "assoc", "Investments", "Boston", False, None),
    ("Oscar Nilsson", "Associate", "assoc", "Investments", "New York", False, None), ("Ruth Abara", "Analyst", "analyst", "Investments", "Boston", False, None),
    ("Tom Becker", "Analyst", "analyst", "Investments", "Boston", False, None), ("Isla Grant", "Software Engineer", "staff", "Technology", "Boston", False, None),
    ("Pedro Alves", "Controller", "staff", "Finance", "Boston", False, None), ("Nora Quinn", "Investor Relations Associate", "assoc", "Investor Relations", "New York", False, None),
    ("Victor Hale", "Operating Partner", "advisors", "Portfolio Operations", "Boston", False, None), ("Judith Marlow", "Senior Advisor", "advisors", "Investments", "Boston", False, None),
]
ORG = {"slug": "granite-peak-capital", "company": "Granite Peak Capital", "status": "approved", "count": len(ORG_PEOPLE), "tiers": TIERS, "sources": ["https://granitepeak.example.com/team"],
       "fetched_at": d(3), "approved_at": d(2), "filters": {"offices": ["Boston", "New York"], "departments": sorted({p[3] for p in ORG_PEOPLE})}, "not_on_site": ["Dana Okafor (Harbor Search, the recruiter)"],
       "people": [], "flagged": 0}
for name, title, tier, dept, off, head, kinds in ORG_PEOPLE:
    p = {"name": name, "title": title, "tier": tier, "head": head, "department": dept, "departments": [dept], "office": off, "offices": [off], "url": "https://granitepeak.example.com/team/" + name.lower().replace(" ", "-").replace("'", ""),
         "summary": f"{name.split()[0]} joined the firm and works in {dept.lower()}.", "joined": ""}
    if kinds:
        line = {"Priya Natarajan": "Hiring manager; first round done, second round Thursday", "Theo Brandt": "Second-round interviewer; the internal customer", "Rosa Lindqvist": "First-degree connection (alumni)"}[name]
        p["flag"] = {"kinds": kinds, "line": line, "refs": ["contacts/" + name.lower().replace(" ", "-")]}
        ORG["flagged"] += 1
    ORG["people"].append(p)

NPAGES = {
    "c-marcus-lind": {"file": "people/marcus-lind", "html": para("<strong>Role:</strong> VP Engineering", "<strong>Company:</strong> Northwind Labs", "<strong>Status:</strong> Warm") +
                      para("<strong>How I got the conversation:</strong> former colleague; we ran the platform migration together", "<strong>Linked jobs:</strong> Lead Product Manager, Agent Platform") +
                      para("<strong>Last talked:</strong> " + d(8) + " (coffee)", "<strong>Next:</strong> tell him the screen is booked") + "<h2>Notes</h2>" + para("Said the VP Product is new and hiring her first PMs; the agent team is twelve engineers and funded through next year.")},
    "c-priya-natarajan": {"file": "people/priya-natarajan", "html": para("<strong>Role:</strong> Chief Information Officer", "<strong>Company:</strong> Granite Peak Capital", "<strong>Status:</strong> In process") +
                          "<h2>Notes</h2>" + para("Two years into the AI program. Licensed the tools, wrote the governance, shipped three workflows that stuck. Wants a peer who builds. Asked for the 90-day plan without prompting.")},
    "c-elena-marsh": {"file": "people/elena-marsh", "html": para("<strong>Role:</strong> Chief Claims Officer", "<strong>Company:</strong> Halcyon Insurance", "<strong>Status:</strong> Not contacted") +
                      "<h2>Notes</h2>" + para("Conference talk on claims triage: intake first, document extraction second, fraud signals last. The VP seat reports to her. Sam Delgado sits on the board and offered the introduction.")},
}

# --------------------------------------------------------------------------------------------------------------
# Startups: a Boston scene, screened
# --------------------------------------------------------------------------------------------------------------
STARTUPS_SRC = [
    # id, name, one_liner, tag, stage, theme, vertical, sector, hq, lat, lng, address, people, raised, round_type, round_date_days_ago, founded, tier, score, call, note
    ("lumen-agents", "Lumen Agents", "Agents that run the back office for mid-market finance teams", "Applied AI", "early", "Agents for the front and back office", "Cross-industry", "fintech", "Boston", 42.3505, -71.0498, "1 Seaport Ln, Boston, MA 02210", 42, 18000000, "series_a", 120, 2023, "look", 11, "Interesting", "Exactly the shape of work: agents, approvals, a real business buying it."),
    ("hearthstone-health", "Hearthstone Health", "AI intake and triage for specialty clinics", "AI", "early", "Clinical workflow", "Healthcare", "healthtech", "Cambridge", 42.3625, -71.0862, "1 Kendall Sq, Cambridge, MA 02139", 35, 12000000, "seed", 200, 2023, "look", 10, "Interesting", "Clinical workflow with a product seat open; the founder is a former clinician."),
    ("ferrous", "Ferrous", "Agentic procurement for industrial buyers", "Applied AI", "growth", "Agents for the front and back office", "Industrial", "supply chain", "Boston", 42.3660, -71.0620, "50 Causeway St, Boston, MA 02114", 120, 65000000, "series_b", 90, 2021, "look", 10, "Interesting", "Growth stage, Boston, a real GTM; worth a founder conversation."),
    ("mapleleaf-ai", "Mapleleaf AI", "AI copilots for insurance underwriters", "AI", "growth", "Insurance and risk", "Insurance", "insurtech", "Boston", 42.3540, -71.0570, "100 High St, Boston, MA 02110", 95, 48000000, "series_b", 150, 2020, "look", 9, "Interesting", "Underwriting is the adjacent problem to claims; strong team."),
    ("cobblestone", "Cobblestone", "Property operations platform with AI maintenance scheduling", "AI", "growth", "Operations", "Real estate", "proptech", "Boston", 42.3480, -71.0450, "22 Boston Wharf Rd, Boston, MA 02210", 140, 70000000, "series_b", 300, 2019, "watch", 7, "Watch", "Fine business; the AI is a feature, not the product."),
    ("brightwater", "Brightwater", "AI for utility field operations", "AI", "early", "Operations", "Energy", "energy", "Somerville", 42.3876, -71.0995, "100 Assembly Row, Somerville, MA 02145", 28, 9000000, "seed", 60, 2024, "watch", 7, "Watch", "Too early; watch for the Series A."),
    ("kindred-care", "Kindred Care", "Care coordination for home health agencies", "AI", "early", "Clinical workflow", "Healthcare", "healthtech", "Boston", 42.3400, -71.0900, "1 Brigham Cir, Boston, MA 02120", 22, 6000000, "seed", 240, 2023, "watch", 6, "Watch", "Mission fit; too small for a product seat today."),
    ("saltmarsh", "Saltmarsh", "Agentic customer support for logistics providers", "Applied AI", "growth", "Agents for the front and back office", "Logistics", "logistics", "Boston", 42.3590, -71.0540, "200 State St, Boston, MA 02109", 80, 30000000, "series_a", 180, 2022, "watch", 8, "Watch", "Good company; the open roles are engineering only."),
    ("northstar-legal", "Northstar Legal", "AI document review for mid-size law firms", "AI", "growth", "Knowledge work", "Legal", "legaltech", "Boston", 42.3560, -71.0600, "60 State St, Boston, MA 02109", 110, 55000000, "series_b", 100, 2020, "watch", 8, "Watch", "Crowded space; strong distribution though."),
    ("verdant-robotics", "Verdant Robotics", "Autonomous weeding robots for farms", "AI", "growth", "Robotics", "Agriculture", "robotics", "Somerville", 42.3800, -71.1000, "200 Inner Belt Rd, Somerville, MA 02143", 150, 90000000, "series_c", 200, 2018, "skip", 3, "Pass", "Hardware and agriculture; not my search."),
    ("quantum-leap", "Quantum Leap", "Quantum computing software", "AI", "early", "Deep tech", "Cross-industry", "deep tech", "Cambridge", 42.3620, -71.0930, "245 Main St, Cambridge, MA 02142", 30, 20000000, "series_a", 400, 2021, "skip", 2, "Pass", "Research company; no product seat for years."),
    ("open-ledger", "Open Ledger", "Open-source accounting platform", "AI", "early", "Fintech", "Cross-industry", "fintech", "Boston", 42.3520, -71.0640, "745 Atlantic Ave, Boston, MA 02111", 25, 8000000, "seed", 300, 2022, "skip", 3, "Pass", "I do not understand how an open-source company at this size pays a product team."),
    ("pixelforge", "Pixelforge", "Generative video for marketing teams", "AI", "early", "Creative tools", "Media", "martech", "Boston", 42.3500, -71.0700, "500 Boylston St, Boston, MA 02116", 40, 15000000, "series_a", 90, 2023, "skip", 4, "Pass", "Consumer-ish creative tools; not the archetype."),
    ("bedrock-security", "Bedrock Security", "Agents that triage security alerts", "Applied AI", "growth", "Security and identity", "Cross-industry", "security", "Boston", 42.3507, -71.0707, "10 St James Ave, Boston, MA 02116", 78, 120000000, "series_b", 60, 2022, "look", 9, None, None),
    ("tillage", "Tillage", "Procurement copilots for hospital systems", "Applied AI", "early", "Clinical workflow", "Healthcare", "healthtech", "Boston", 42.3365, -71.1058, "330 Longwood Ave, Boston, MA 02115", 30, 14000000, "series_a", 45, 2023, "look", 9, None, None),
    ("harbor-ml", "Harbor ML", "Evaluation and monitoring for production LLM apps", "AI", "early", "Developer tools", "Cross-industry", "devtools", "Cambridge", 42.3640, -71.0860, "1 Broadway, Cambridge, MA 02142", 26, 11000000, "seed", 100, 2024, "watch", 6, None, None),
    ("castle-rock", "Castle Rock", "AI underwriting for small-business lending", "AI", "growth", "Fintech", "Financial services", "fintech", "Boston", 42.3580, -71.0575, "75 State St, Boston, MA 02109", 90, 40000000, "series_b", 220, 2020, "watch", 7, None, None),
    ("elm-street", "Elm Street", "Agents for property management leasing", "Applied AI", "early", "Agents for the front and back office", "Real estate", "proptech", "Boston", 42.3490, -71.0460, "63 Melcher St, Boston, MA 02210", 18, 5000000, "seed", 30, 2024, "watch", 6, None, None),
    ("ridgeline-bio", "Ridgeline Bio", "AI for antibody design", "AI", "growth", "Deep tech", "Life sciences", "biotech", "Cambridge", 42.3658, -71.0922, "400 Technology Sq, Cambridge, MA 02139", 60, 85000000, "series_b", 150, 2020, "skip", 3, None, None),
    ("tidepool", "Tidepool", "Marine data platform", "AI", "early", "Climate", "Climate", "climate", "Boston", 42.3620, -71.0510, "20 Atlantic Ave, Boston, MA 02110", 15, 4000000, "seed", 300, 2023, "skip", 2, None, None),
    ("granary", "Granary", "AI demand planning for food distributors", "Applied AI", "growth", "Operations", "Food", "supply chain", "Boston", 42.3450, -71.0400, "10 Fan Pier Blvd, Boston, MA 02210", 70, 25000000, "series_a", 120, 2021, "watch", 8, None, None),
    ("wrenfield", "Wrenfield", "Copilots for wealth advisors", "Applied AI", "growth", "Fintech", "Financial services", "fintech", "Boston", 42.3565, -71.0560, "100 Federal St, Boston, MA 02110", 85, 38000000, "series_b", 80, 2021, "look", 9, None, None),
    ("beacon-ops", "Beacon Ops", "Workforce scheduling AI for hospitals", "AI", "early", "Clinical workflow", "Healthcare", "healthtech", "Boston", 42.3380, -71.1000, "75 Francis St, Boston, MA 02115", 24, 7000000, "seed", 150, 2023, "watch", 6, None, None),
    ("ironclad-robotics", "Ironclad Robotics", "Warehouse picking robots", "AI", "growth", "Robotics", "Logistics", "robotics", "Wilmington", 42.5584, -71.1737, "", 200, 150000000, "series_c", 250, 2017, "skip", 3, None, None),
    ("parchment", "Parchment", "AI contract analysis for in-house legal", "Applied AI", "early", "Knowledge work", "Legal", "legaltech", "Boston", 42.3555, -71.0605, "28 State St, Boston, MA 02109", 32, 13000000, "series_a", 70, 2023, "look", 9, None, None),
    ("clearwater-grid", "Clearwater Grid", "Grid optimisation software for utilities", "AI", "growth", "Climate", "Energy", "energy", "Boston", 42.3630, -71.0580, "1 Boston Pl, Boston, MA 02108", 65, 32000000, "series_b", 180, 2019, "watch", 7, None, None),
    ("stackhouse", "Stackhouse", "Internal developer platform", "AI", "early", "Developer tools", "Cross-industry", "devtools", "Cambridge", 42.3700, -71.0800, "", 20, 6000000, "seed", 200, 2024, "skip", 4, None, None),
    ("orbit-health", "Orbit Health", "Remote patient monitoring", "AI", "growth", "Clinical workflow", "Healthcare", "healthtech", "Boston", 42.3350, -71.1100, "", 110, 60000000, "series_b", 260, 2019, "watch", 6, None, None),
    ("sable", "Sable", "Agentic collections for lenders", "Applied AI", "early", "Agents for the front and back office", "Financial services", "fintech", "Boston", 42.3530, -71.0580, "125 High St, Boston, MA 02110", 27, 10000000, "seed", 40, 2024, "look", 9, None, None),
    ("summitview", "Summitview", "AI tutoring for K-12", "AI", "growth", "Education", "Education", "edtech", "Cambridge", 42.3736, -71.1097, "", 55, 22000000, "series_a", 140, 2021, "skip", 4, None, None),
]


def dil_section(t, html, items=None):
    s = {"t": t, "html": html}
    if items:
        s["items"] = items
    return s


def diligence(name, one_liner):
    first = name.split()[0]
    return {"folder": f"research/{name.lower().replace(' ', '-')}", "mode": "quick", "date": d(6),
            "facts": {"asof": d(6), "round": {"v": "Series A", "note": "press release"}, "raised": {"v": "$18M", "note": "press release"}, "people": {"v": "42", "note": "LinkedIn headcount"}, "customers": {"v": "about 60", "note": "founder interview"}, "valuation": None, "revenue": None, "based": None, "founded": None},
            "files": [{"k": "brief", "l": "Brief", "html": f"<h3>Brief</h3><p>{name}: {one_liner.lower()}. A product seat is open and the founder has written about wanting someone who has run an adoption program inside a real business.</p><ol><li>Ask how the approval model works today.</li><li>Ask who owns the customer's rollout.</li></ol>"},
                      {"k": "dossier", "l": "Dossier", "html": f"<h3>Dossier</h3><p>{first} sells to finance and operations leaders at mid-market companies. Two rounds since founding, the last led by a top-tier fund. Hiring in product and go-to-market; engineering steady.</p>"},
                      {"k": "people", "l": "People", "html": f"<h3>People</h3><p>The founder was a VP at a public software company; the head of product left in the spring and has not been replaced. Two first-degree connections on the engineering team.</p>"}],
            "s": {"brief": {"_order": ["gate", "five", "ask", "say", "avoid", "paths", "sponsor", "unknown", "files"],
                            "gate": dil_section("The gate", "<p>Growth, excitement and learning all clear; edge is the question.</p>", [{"label": "Growth", "html": "<p>Two rounds in three years; headcount up 60% in twelve months.</p>"}, {"label": "Excitement", "html": "<p>The product is the agent approval line; the owner has built one.</p>"}, {"label": "Edge", "html": "<p>Crowded category; distribution through accounting firms is the differentiator.</p>"}, {"label": "Learning", "html": "<p>A founder who has scaled a product organisation before.</p>"}]),
                            "five": dil_section("Five things", "<ol><li>Series A led by a top-tier fund.</li><li>Head of product seat open since spring.</li><li>Sixty customers, mid-market.</li><li>Boston HQ, Seaport.</li><li>Two first-degree connections.</li></ol>"),
                            "ask": dil_section("What to ask", "<ol><li>How is the approval model built today?</li><li>Who owns the customer's rollout?</li><li>What did the last head of product get wrong?</li></ol>"),
                            "say": dil_section("What to say", "<p>Lead with the build: the approval line, the audit trail, the adoption numbers.</p>"),
                            "avoid": dil_section("What to avoid", "<p>Talking about governance before product.</p>"),
                            "paths": dil_section("Paths in", "<p>Two engineers are first-degree connections; the founder follows the owner's writing.</p>"),
                            "sponsor": dil_section("Sponsor", "<p>The founder.</p>", [{"label": "Who", "html": "<p>The founder, directly.</p>"}]),
                            "unknown": dil_section("Unknown", "<p>Burn and runway.</p>"), "files": dil_section("Files", "<p>brief.md, dossier.md, people.md</p>")},
                  "people": {"_order": ["who", "profiles", "org", "trajectory", "alumni", "gaps"], "who": dil_section("Who matters", "<p>The founder and the VP Engineering.</p>"),
                             "profiles": dil_section("Profiles", "<p>Founder: VP at a public software company for six years. VP Engineering: ex-platform lead at a payments company.</p>"),
                             "org": dil_section("Org shape", "<p>Forty-two people: 28 engineering, 6 go-to-market, 4 customer success, 4 operations; no product leader.</p>"),
                             "trajectory": dil_section("Trajectories", "<p>Engineering steady; go-to-market doubling this year.</p>"), "alumni": dil_section("Alumni", "<p>None known.</p>"), "gaps": dil_section("Gaps", "<p>Product leadership.</p>")},
                  "dossier": {"_order": ["snapshot", "what", "market", "signal", "size", "hiring", "seat", "news", "culture", "operate", "ownership", "failures", "flags", "questions", "portfolio", "changelog", "gate"],
                              "snapshot": dil_section("Snapshot", f"<p>{name}, founded 2023, Boston, 42 people, $18M raised.</p>"), "what": dil_section("What they do", f"<p>{one_liner}.</p>"),
                              "market": dil_section("Market", "<p>Mid-market finance operations; a crowded category with weak incumbents.</p>"), "signal": dil_section("Signal", "<p>Customer count tripled in a year.</p>"),
                              "size": dil_section("Size", "<p>42 people, 60 customers, revenue not disclosed.</p>"), "hiring": dil_section("Hiring", "<p>Head of product, two account executives, one solutions engineer.</p>"),
                              "seat": dil_section("The seat", "<p>Head of product, reporting to the founder, owning the roadmap and the first two PM hires.</p>"), "news": dil_section("News", "<p>Series A announced in the summer.</p>"),
                              "culture": dil_section("Culture", "<p>Engineering-led; in the office four days.</p>"), "operate": dil_section("How they operate", "<p>Two-week cycles; the founder runs product reviews.</p>"),
                              "ownership": dil_section("Leadership and ownership", "<p>Founder-led; the Series A fund holds a board seat.</p>", [{"label": "Board", "html": "<p>Founder, the Series A partner, one independent.</p>"}]),
                              "failures": dil_section("Failure modes", "<p>Runs out of runway before distribution works.</p>", [{"label": "Runway", "html": "<p>Not disclosed; assume 24 months.</p>"}]),
                              "flags": dil_section("Flags", "<p>No product leader for six months.</p>"), "questions": dil_section("Questions", "<p>See the brief.</p>"), "portfolio": dil_section("Portfolio", "<p>n/a</p>"),
                              "changelog": dil_section("Change log", f"<p>{d(6)}: quick pass.</p>"),
                              "gate": dil_section("The gate", "<p>See the brief.</p>", [{"label": "Growth", "html": "<p>Clear.</p>"}, {"label": "Excitement", "html": "<p>Clear.</p>"}, {"label": "Edge", "html": "<p>Open.</p>"}, {"label": "Learning", "html": "<p>Clear.</p>"}])},
                  "sources": {"_order": ["firm-site", "press-and-news", "people-sources"], "firm-site": dil_section("Firm site", "<p>Site, careers page, blog.</p>"), "press-and-news": dil_section("Press and news", "<p>Funding announcement, one founder interview.</p>"), "people-sources": dil_section("People sources", "<p>LinkedIn profiles.</p>")}}}


STARTUPS = []
for (sid, name, one, tag, stage, theme, vert, sector, hq, lat, lng, addr, people, raised, rtype, rdays, founded, tier, score, call, note) in STARTUPS_SRC:
    rec = {"id": sid, "name": name, "one_liner": one, "tag": tag, "stage": stage, "theme": theme, "vertical": vert, "sector": sector, "industry": sector, "hq": hq, "boston_hq": hq in ("Boston", "Cambridge", "Somerville"),
           "office": {"lat": lat, "lng": lng, "address": addr or f"{hq}, MA", "precision": "street" if addr else "city", "fallback": not addr}, "people": people, "raised": raised, "round_type": rtype, "round_date": d(rdays), "round_count": 2 if rtype != "seed" else 1,
           "founded": founded, "website": f"https://{sid}.example.com", "careers": f"https://{sid}.example.com/careers", "mgmt": None, "linkedin": f"https://www.linkedin.com/company/{sid}", "logo": None, "lantern": None,
           "investors": ["Example Ventures", "Harbor Capital"] if rtype != "seed" else ["Harbor Capital"], "description": f"{name} builds {one[0].lower() + one[1:]}.", "customers": None, "workplace": None, "expansion": False, "expansion_origin": None,
           "left_out": None, "look_again": "A product seat opens, or the Series B closes" if tier == "watch" else None, "open_roles": 3 if tier == "look" else None, "pct_local": None, "people_source": "demo", "seat_posted": tier == "look",
           "first_degree": [{"name": "Alex Chen", "title": "Staff Engineer"}] if sid in ("lumen-agents", "ferrous", "bedrock-security") else [],
           "board_rows": [], "vault_card": f"companies/{sid}" if call else None, "card_html": f"<p><strong>Website:</strong> <a href=\"https://{sid}.example.com\">{sid}.example.com</a>\n<strong>Stage:</strong> {rtype.replace('_', ' ').title()}</p><p>{one}.</p>" if call else None,
           "research": {"name": name, "what": one, "fit": {"look": "On the archetype: agents sold into a real business, with an approval line and an adoption problem to own.", "watch": "Adjacent; worth watching for a product seat.", "skip": ""}[tier],
                        "path": "First-degree: Alex Chen (Staff Engineer)" if sid in ("lumen-agents", "ferrous", "bedrock-security") else "", "board": "", "roles": f"3 open: Head of Product, Solutions Engineer, Account Executive. [jobs](https://{sid}.example.com/careers)" if tier == "look" else "",
                        "sector": sector, "stage_text": f"{rtype.replace('_', ' ').title()}, {d(rdays)[:7]}"} if tier != "skip" else None,
           "screen": {"score": score, "tier": tier, "version": 2, "math": f"round in the last 18 months +2; Boston +1; {tag} tag +1; {stage} +1; {people} people +1; fit written +1; path in +1; seat posted +1" if tier == "look" else f"round in the last 18 months +1; Boston +1; {stage} +1; {people} people +1" if tier == "watch" else f"Boston +1; {sector} -2; hardware or research -1"},
           "diligence": diligence(name, one) if sid in ("lumen-agents", "hearthstone-health", "ferrous") else None}
    STARTUPS.append(rec)
SVERDICTS = [{"id": s[0], "v": s[19], "note": s[20], "flag": s[0] == "lumen-agents", "ts": ts(5 + i, "17:30"), "name": s[1]} for i, s in enumerate(STARTUPS_SRC) if s[19]]
for s in STARTUPS:
    if s["id"] in ("lumen-agents", "ferrous"):
        VIEWS["startups"][s["id"]] = {"src": next(v["note"] for v in SVERDICTS if v["id"] == s["id"]), "view": next(v["note"] for v in SVERDICTS if v["id"] == s["id"])}

SSUM = {"asof": d(0), "built_at": ts(0, "10:35"), "count": len(STARTUPS), "seats": sum(1 for s in STARTUPS if s["seat_posted"]), "pinned": sum(1 for s in STARTUPS if s["office"]["precision"] == "street"),
        "by_tag": {"AI": sum(1 for s in STARTUPS if s["tag"] == "AI"), "Applied AI": sum(1 for s in STARTUPS if s["tag"] == "Applied AI")},
        "by_tier": {t: sum(1 for s in STARTUPS if s["screen"]["tier"] == t) for t in ("look", "watch", "skip")}, "by_stage": {t: sum(1 for s in STARTUPS if s["stage"] == t) for t in ("early", "growth", "later", "public")},
        "on_board": 0, "researched": sum(1 for s in STARTUPS if s["research"]), "first_degree": sum(1 for s in STARTUPS if s["first_degree"]),
        "theses": [{"id": "front-office", "kind": "Solutions and forward-deployed", "title": "Agents that run the front and back office", "why": "AI-native software that does the work, not just logs it; the closest match to the owner's build.", "members": ["lumen-agents", "ferrous", "saltmarsh", "elm-street", "sable"]},
                   {"id": "clinical", "kind": "Transformation and enablement", "title": "Clinical workflow", "why": "Adoption inside a hospital is the transformation problem in its hardest form.", "members": ["hearthstone-health", "kindred-care", "tillage", "beacon-ops"]},
                   {"id": "risk", "kind": "AI product and platform", "title": "Insurance and lending", "why": "Underwriting and claims are the regulated-industry version of the approval line.", "members": ["mapleleaf-ai", "castle-rock", "wrenfield"]}]}

# --------------------------------------------------------------------------------------------------------------
# Summary and health
# --------------------------------------------------------------------------------------------------------------
pursue = [r for r in RECORDS if r["verdict"] == "pursue"]
SUMMARY = {"title": "Job Board (demo)", "asof": d(0), "data_asof": d(0), "built_at": ts(0, "10:31"), "radar_last": d(0), "first_seen": d(40), "tracked": len(RECORDS), "unscored": 0,
           "excluded": sum(1 for r in RECORDS if r["excluded"]), "below_floor": 212, "reposted": 0, "min_score": 7, "board_floor": 7, "review_floor": 8, "waiting_deep_pass": 0,
           "closed_gone": sum(1 for r in RECORDS if r["outcome"] == "posting_removed"), "closed_engaged": sum(1 for r in pursue if r["stage"] == "closed"),
           "postings_gone": sum(1 for r in RECORDS if r["posting"]["state"] in ("removed", "closed") and r["verdict"] == "pursue"), "postings_unknown": sum(1 for r in RECORDS if r["posting"]["state"] == "unreachable"),
           "stages": STAGES, "outcomes": OUTCOMES, "role_types": ROLE_TYPES, "sources": sorted({r["source"].split(":")[0] for r in RECORDS}),
           "health": {"host": "demo", "inbox_newest": d(0), "pages": {"ok": True, "detail": "notion pages: 12 current"},
                      "radar": {"at": ts(0, "08:02"), "date": d(0), "mail": 11, "rows": 54, "above_floor": 3, "status": "ok", "note": "label:job-alerts returned 11 new threads; 54 rows appended, 3 at 7+"},
                      "notion": {"ok": True, "detail": f"notion {len(CONTACTS)} people, {sum(len(c['touches']) for c in CONTACTS)} touches, {len(OPPS)} opportunities, {len(MEETINGS)} meetings, {len(TASKS)} career tasks"}}}

VERDICTS = [{"id": r["id"], "v": r["verdict"].capitalize(), "cal": r["calibration"] or "", "note": r["note"] or "", "flag": r["flag"], "ts": r["verdict_ts"], "title": r["title"], "company": r["company"], "pkeep": None}
            for r in RECORDS if r["verdict"]]

DATA = {
    "generated": GENERATED.isoformat(),
    "tables": {
        "jobs": [{"id": r["id"], "company_key": r["company_key"], "payload": r, "updated_at": ts(0, "10:31")} for r in RECORDS],
        "board_meta": [{"key": k, "payload": v} for k, v in {"summary": SUMMARY, "companies": {k: {"url": v["url"], "about": v["about"], "growth": v["growth"]} for k, v in COMPANIES.items()}, "paths": PATHS, "views": VIEWS,
                                                               "stage_history": STAGE_HIST, "pulse_history": PULSE, "org_charts": {"Granite Peak Capital": ORG}, "network_pages": NPAGES, "startups_summary": SSUM}.items()],
        "verdicts": VERDICTS,
        "contacts": [{"id": c["id"], "payload": c, "updated_at": ts(1, "16:00")} for c in CONTACTS],
        "opportunities": [{"id": o["id"], "page_id": o["page"], "payload": o, "updated_at": ts(1, "12:00")} for o in OPPS.values()],
        "meetings": [{"id": m["id"], "payload": m, "updated_at": ts(1, "12:00")} for m in MEETINGS],
        "sync_requests": [{"id": 1, "requested_at": ts(1, "13:02"), "requested_by": "demo@example.com", "note": "after the morning verdicts", "status": "done", "host": "demo", "started_at": ts(1, "13:03"), "finished_at": ts(1, "13:04"), "result": "4 verdicts folded, board rebuilt"}],
        "tasks": [{"id": t["id"], "payload": t, "updated_at": ts(1, "09:00")} for t in TASKS],
        "startups": [{"id": s["id"], "name": s["name"], "payload": s, "updated_at": ts(0, "10:35")} for s in STARTUPS],
        "startup_verdicts": SVERDICTS,
    },
}

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(DATA, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB): {len(RECORDS)} roles, {len(CONTACTS)} people, {len(OPPS)} opportunities, {len(STARTUPS)} startups")
