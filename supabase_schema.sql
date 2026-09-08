create table if not exists public.prediction_history (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  user_email text not null,
  file_name text not null,
  blood_group text not null check (blood_group in ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
  confidence numeric(5,2) not null check (confidence >= 0 and confidence <= 100),
  created_at timestamptz not null default now()
);
alter table public.prediction_history enable row level security;
create policy "Users read their own prediction history" on public.prediction_history for select to authenticated using (auth.uid() = user_id);
create policy "Users insert their own prediction history" on public.prediction_history for insert to authenticated with check (auth.uid() = user_id);
