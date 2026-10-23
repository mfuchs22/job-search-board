-- today_marks.draft_asked (2026-10-23): when the owner opened a Today item that had no brief, so the board asked Claude to
-- draft one. engine/draft_now.py (board-sync on the mini) reads it and starts a run that writes the brief and pushes it.
alter table public.today_marks add column draft_asked timestamptz;
