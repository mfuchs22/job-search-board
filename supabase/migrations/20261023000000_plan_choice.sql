-- plan_inputs.choice: which of the plan's options the owner picked on the Today card (2026-10-23, the owner: "it should give
-- you option A, option B, and if there's option C... the buttons should reference the paths"). A letter, A to C,
-- or null for an answer typed in the box. engine/pursue_followup.py folds it into campaign.md with the option's label.

alter table public.plan_inputs add column choice text check (choice in ('A', 'B', 'C'));
