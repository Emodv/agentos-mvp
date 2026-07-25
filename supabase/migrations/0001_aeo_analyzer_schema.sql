-- AEO Analyzer: reports (scan results) and leads (contact capture) tables.

create table aeo_reports (
  id uuid primary key default gen_random_uuid(),
  domain text not null,
  score integer not null check (score >= 0 and score <= 100),
  status text not null,
  checks jsonb not null,
  created_at timestamptz not null default now()
);

create table aeo_leads (
  id uuid primary key default gen_random_uuid(),
  domain text not null,
  email text not null,
  name text,
  phone text,
  selected_tier text,
  report_id uuid references aeo_reports(id),
  created_at timestamptz not null default now()
);

create index on aeo_reports (domain, created_at desc);
create index on aeo_leads (created_at desc);
create index on aeo_leads (report_id);

-- Daily analytics: scans, leads, conversion rate, and average score per day.
create view daily_stats as
select
  d.day,
  d.scans,
  coalesce(l.leads, 0) as leads,
  case when d.scans > 0 then round(coalesce(l.leads, 0)::numeric / d.scans, 4) else 0 end as conversion_rate,
  d.avg_score
from (
  select
    date_trunc('day', created_at) as day,
    count(*) as scans,
    round(avg(score), 1) as avg_score
  from aeo_reports
  group by 1
) d
left join (
  select date_trunc('day', created_at) as day, count(*) as leads
  from aeo_leads
  group by 1
) l on l.day = d.day
order by d.day desc;

-- RLS: reports are non-sensitive scan results and safe to read publicly.
-- Leads contain contact info; anon clients may only insert (lead capture form),
-- never read, update, or delete. All other access goes through the service role key.
alter table aeo_reports enable row level security;
alter table aeo_leads enable row level security;

create policy "Public can read reports" on aeo_reports
  for select to anon using (true);

create policy "Public can submit leads" on aeo_leads
  for insert to anon with check (true);
