-- plan_inputs: the owner's answer to a role's plan card on the Today page (2026-10-20). The nightly pursue-followup
-- routine writes the plan into the vault (opportunities/<slug>/campaign.md, ## Plan); the owner approves it or changes
-- the route and adds notes here; engine/pursue_followup.py folds each row into campaign.md under ## the owner's input
-- and stamps folded_at. Rows are kept as the record of what he said.
-- Same access pattern as verdicts: RLS on, owner-only through is_board_owner(), no deletes through the API.

create table public.plan_inputs (
  id        bigint generated always as identity primary key,
  job_id    text not null,                  -- the board's record id
  version   int  not null default 1,        -- the plan version answered
  approve   boolean not null default false, -- true: the plan as proposed; false: changed, see note
  note      text,
  ts        timestamptz not null default now(),
  folded_at timestamptz
);
create index plan_inputs_job on public.plan_inputs (job_id, version);

alter table public.plan_inputs enable row level security;
revoke all on public.plan_inputs from anon;

create policy "owner reads plan_inputs"   on public.plan_inputs for select to authenticated using ((select public.is_board_owner()));
create policy "owner inserts plan_inputs" on public.plan_inputs for insert to authenticated with check ((select public.is_board_owner()));

alter publication supabase_realtime add table public.plan_inputs;
