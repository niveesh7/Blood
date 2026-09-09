# Username login and admin setup

## What this changes

Users see only a username and password. Behind the scenes, Supabase Auth keeps the password and session secure. The internal email identity is never shown in the website.

## One-time Supabase setup

1. Open your Supabase project, then open **SQL Editor**.
2. Run all of `supabase_schema.sql` once. It creates `profiles`, adds the authentication trigger, and preserves `prediction_history`.
3. Go to **Authentication > Sign In / Providers > Email** and turn **Confirm email** off. This is required because the app uses internal identities for username login.
4. In Render, remove `ADMIN_EMAIL` if it exists. It is no longer used. Keep `FLASK_SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` as server environment variables.
5. Redeploy after pushing the new code.

## Create the first admin

1. Create a normal account through the website using a username such as `niveesh_admin` and a strong password.
2. In Supabase SQL Editor, run:

```sql
update public.profiles
set role = 'admin'
where username = 'niveesh_admin';
```

3. Sign out and use the **Admin login** tab with `niveesh_admin` and its password.

## Manage admins

- Add another admin: create a normal website account, then update that profile's role to `admin` with the SQL above.
- Remove admin access: `update public.profiles set role = 'user' where username = 'name';`
- Change/reset/disable/delete an account: use **Authentication > Users** in Supabase. Supabase stores passwords securely; no password exists in the app code or database profile table.

## Important

Do not add the Supabase service-role key to browser code or GitHub. It belongs only in Render server environment variables.
