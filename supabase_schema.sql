-- Run this once in Supabase SQL Editor. It preserves prediction_history data.
create table if not exists public.prediction_history (
  id bigint generated always as identity primary key, user_id uuid not null, user_email text not null, file_name text not null,
  blood_group text not null check (blood_group in ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
  confidence numeric(5,2) not null check (confidence >= 0 and confidence <= 100), created_at timestamptz not null default now()
);
do $$ begin create type public.app_role as enum ('user', 'admin'); exception when duplicate_object then null; end $$;
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade, username text unique, auth_email text unique,
  role public.app_role not null default 'user', created_at timestamptz not null default now(),
  constraint username_format check (username ~ '^[a-z][a-z0-9_]{2,29}$')
);
alter table public.profiles add column if not exists username text;
alter table public.profiles add column if not exists auth_email text;
alter table public.profiles add column if not exists role public.app_role not null default 'user';
create unique index if not exists profiles_username_unique on public.profiles (username);
create unique index if not exists profiles_auth_email_unique on public.profiles (auth_email);
create or replace function public.handle_new_user() returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, username, auth_email)
  values (new.id, lower(coalesce(new.raw_user_meta_data ->> 'username', split_part(new.email, '@', 1))), new.email)
  on conflict (id) do update set auth_email = excluded.auth_email;
  return new;
end; $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute procedure public.handle_new_user();
insert into public.profiles (id, username, auth_email)
select id, lower(split_part(email, '@', 1)), email from auth.users
on conflict (id) do update set auth_email = excluded.auth_email;
alter table public.profiles enable row level security;
alter table public.prediction_history enable row level security;
drop policy if exists "Users read their own profile" on public.profiles;
create policy "Users read their own profile" on public.profiles for select to authenticated using (auth.uid() = id);
drop policy if exists "Users read their own prediction history" on public.prediction_history;
create policy "Users read their own prediction history" on public.prediction_history for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Users insert their own prediction history" on public.prediction_history;
create policy "Users insert their own prediction history" on public.prediction_history for insert to authenticated with check (auth.uid() = user_id);
-- Promote an existing account after replacing the username:
-- update public.profiles set role = 'admin' where username = 'your_admin_username';
