# Rubric template

The shape of the scoring rubric the engine expects, with the owner's specifics removed. The live rubric, its hard exclusions, and the verdict-by-verdict feedback log live in the vault (`jobs/rubric.md`), and the morning radar reads that file on every run.

## Order of operations

1. **Hard exclusions.** Anything that makes a role unpursuable regardless of fit: required on-site days outside commuting range, a commute over the owner's ceiling, travel above a percentage, a consulting motion built on multi-week client sites, roles centered on a product the owner will not work with, a company blocklist, hard requirements the owner cannot meet (years in a discipline they do not have, a vendor certification). An excluded role is never scored or ranked; it is kept with its reason.
2. **Company gate.** Trajectory (growing +1, shrinking or stalling -1), an "excitement" flag the owner sets, and, for small companies, a visible edge. Shown on every card next to the score.
3. **Role score.** Start at a base when the title alone confirms the target role shape in the owner's seniority band, then add and subtract:

| Adjustment | Criterion |
|---|---|
| +2 | the owner's primary role shape (for example: internal AI adoption, enablement, transformation ownership) |
| +2 | a second confirmed shape (for example: agentic workflows in a production business setting) |
| +1 | a domain adder (for example: employer in the owner's industry) |
| +1 | a demonstrable differentiator the owner is building (for example: evaluation and measurement as the spine) |
| +1 | a structural shape the owner wants (for example: forward-deployed or embedded pod) |
| -1 | scope confined to a single internal function |
| -1 | seat below the owner's seniority floor |
| -1 | deliverable is training or coaching rather than owning a roadmap and a build |
| -2 | the role's spine is a lane the owner has done and does not want again (for example: governance, risk, policy) |
| -2 | requires N+ years of formal experience in a discipline the owner lacks |
| -3 | requires an engineering degree or production coding |
| -3 | heavy people-management of engineers |

Title-level (radar) scores award a dimension only when the title shows it. Deep-pass scores read the posting.

## Review floor

Cards below `min_score` (config) never render. Pick the floor from data: after each batch of verdicts, compare the Pursue rate per score tier; when a tier converts at zero, cut it.

## Feedback log

Every verdict the owner gives is logged as `Date | Role | Routine's score | Owner's verdict | Rule learned`. When a rule repeats, promote it into the adjustments or the exclusions as a dated version (v1, v2, v3) so the rubric's history stays readable.
