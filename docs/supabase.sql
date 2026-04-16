create table if not exists public.meetings (
  meeting_id text primary key,
  title text not null,
  mode text not null,
  started_at timestamptz,
  generated_at timestamptz default now(),
  summary text,
  report jsonb not null
);

create index if not exists meetings_generated_at_idx
  on public.meetings (generated_at desc);
