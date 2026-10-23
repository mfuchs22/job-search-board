-- today_marks.note, note_at (2026-10-23): the owner's freeform note on a Today card ("sending this Sunday"). The page saves
-- it at once; a day named in it moves the item's date in Notion straight away and the card leaves the top until then.
alter table public.today_marks add column note text, add column note_at timestamptz;
