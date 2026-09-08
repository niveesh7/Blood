# Setup and deployment

## Supabase

1. Create a project at https://supabase.com/dashboard.
2. In **SQL Editor**, create a new query, paste the contents of `supabase_schema.sql`, and run it.
3. In **Authentication > Providers > Email**, keep Email enabled. For testing, email confirmation can be disabled; for production, leave it enabled.
4. Open **Project Settings > API** and copy the Project URL, anon/publishable key, and `service_role` secret key.
5. Copy `.env.example` to `.env`, then populate all fields. Set `ADMIN_EMAIL` to your own sign-in email.

The service-role key must remain server-only. Do not commit `.env` or put that key in browser code.

## Test locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Use `http://127.0.0.1:5000`.

## GitHub and Render

```powershell
git init
git add .
git commit -m "Build HemaScan Supabase dashboard"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

Then in Render: **New > Blueprint**, choose the GitHub repository, and add these secret environment variables: `FLASK_SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `ADMIN_EMAIL`. `render.yaml` has the build/start commands.

Fingerprint blood-group predictions are research-only and must be confirmed by laboratory testing.
