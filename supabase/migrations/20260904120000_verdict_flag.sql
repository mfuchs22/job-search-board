-- The owner's flag ("excited about this one") rides on the verdict row, independent of verdict and stage.
alter table public.verdicts add column if not exists flag boolean not null default false;
