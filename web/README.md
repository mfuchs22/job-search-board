# web/

The board page: `index.html` (vanilla JavaScript, no build step) plus `startups.js` (the Startups tabs) and `config.js`.

Two ways to run it:

- **Demo mode** (what this repo ships): `config.js` is `{ demo: "demo/data.json" }`, and `demo.js` stands in for supabase-js. The page reads the ten tables from the JSON file, skips sign-in, and keeps every click in memory until the tab reloads. Dates in the file are shifted to today when it loads, so the demo never goes stale. Rebuild the file with `py demo/make_demo.py`.
- **Live mode**: copy `config.example.js` to `config.js` with a Supabase project URL and publishable key. The page signs the owner in (Google, an emailed link, or a password), reads the same ten tables through supabase-js, subscribes to realtime changes, and writes verdicts, stage moves, touches and task updates back (verdicts straight to a table; stages, people and tasks through the three edge functions in `supabase/functions/`, which write Notion first).

Run it locally: `py -m http.server 8742 --directory web`, then open http://localhost:8742.

Deploy: any static host. This repo's GitHub Action publishes `web/` to GitHub Pages; the original runs on Vercel.
