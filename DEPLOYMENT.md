# Deployment Guide — Vercel + Neon

This guide walks through deploying the MACT Cooperative Ledger from a fresh
GitHub repo to a live app on Vercel, backed by Neon Postgres. It assumes
you've already followed the local setup in `README.md` and confirmed the
app runs on `localhost`.

Two Vercel projects are used — one for `backend/`, one for `frontend/` —
because they're different runtimes (Python vs. Node) that happen to live
in the same Git repo.

---

## Part A — Database (Neon)

### A1. Create the project

1. Go to https://neon.tech and sign up / log in (GitHub sign-in is fastest).
2. Click **New Project**.
3. Name it (e.g. `mact-cooperative`), pick a region close to where most
   users will be, Postgres version can stay at the default.
4. Click **Create Project**.

### A2. Get the connection string

1. On the project dashboard, find the **Connection string** box.
2. Make sure the toggle/dropdown is set to **Pooled connection** (this
   matters — the pooled endpoint handles serverless functions opening lots
   of short-lived connections; the direct endpoint does not).
3. Copy the string. It looks like:
   ```
   postgresql://<user>:<password>@ep-xxxx-pooler.<region>.aws.neon.tech/<db>?sslmode=require
   ```
4. Save it somewhere temporarily — you'll paste it into Vercel shortly.

### A3. Enable the extension the migration script needs

1. In the Neon dashboard, open the **SQL Editor**.
2. Run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   ```

   This enables `gen_random_uuid()`, used both by the migration script and
   as the default for the `members.id` column.

### A4. (Optional) Confirm autosuspend behavior

Neon's free tier suspends the database compute after a period of
inactivity and wakes it on the next query (sub-second). No action needed —
just know that the very first request after idle time may feel slightly
slower.

---

## Part B — Push the code to GitHub

Skip this if already done.

```bash
cd mact-app
git init
git add .
git commit -m "Initial scaffold: members module"
```

Create an empty repository on GitHub (no README/gitignore — you already
have them), then:

```bash
git remote add origin https://github.com/<your-username>/mact-app.git
git branch -M main
git push -u origin main
```

---

## Part C — Deploy the backend (FastAPI)

### C1. Import the project

1. Go to https://vercel.com/new.
2. Under **Import Git Repository**, select `mact-app`. If it's not listed,
   click **Adjust GitHub App Permissions** and grant Vercel access to it.
3. Vercel opens the project configuration screen — don't click Deploy yet.

### C2. Set the root directory

1. Find **Root Directory** and click **Edit**.
2. Select `backend`.
3. This tells Vercel to treat `backend/` as the project root — it will
   look for `vercel.json` and `requirements.txt` inside that folder.

### C3. Framework preset

- Vercel should detect Python automatically because of `backend/vercel.json`.
- If a **Framework Preset** dropdown appears, choose **Other**.
- Leave **Build Command** and **Output Directory** blank — the `vercel.json`
  routing handles this.

### C4. Environment variables

Still on the same configuration screen, expand **Environment Variables**
and add:

| Name                | Value                                                             |
| ------------------- | ----------------------------------------------------------------- |
| `DATABASE_URL`    | the pooled Neon connection string from A2                         |
| `SECRET_KEY`      | any long random string (e.g. run`openssl rand -hex 32` locally) |
| `ALLOWED_ORIGINS` | `http://localhost:3000` for now — you'll update this in Part E |

Apply these to all three environments (Production, Preview, Development)
unless you have a reason to split them.

### C5. Deploy

1. Click **Deploy**.
2. Vercel builds and deploys; watch the **Build Logs** panel for errors.
3. Once it says "Ready," click **Visit** to get the deployment URL, e.g.
   `https://mact-app-backend.vercel.app`.

### C6. Verify

Open `https://mact-app-backend.vercel.app/api/health` in a browser. You
should see:

```json
{"status": "ok"}
```

This request also triggers `Base.metadata.create_all()`, which creates the
`members` table in Neon if it doesn't exist yet.

If you get a 500 error instead, open the project's **Deployments** tab →
click the deployment → **Functions** or **Logs** to see the traceback. The
most common cause at this stage is a malformed `DATABASE_URL` (missing
`?sslmode=require`, or using the direct endpoint instead of pooled).

---

## Part D — Deploy the frontend (Next.js)

### D1. Import the project (again, same repo)

1. Go to https://vercel.com/new again.
2. Select the same `mact-app` repository — Vercel allows importing it more
   than once as separate projects.

### D2. Set the root directory

- Set **Root Directory** to `frontend`.
- Framework Preset should auto-detect as **Next.js**. Leave build/output
  settings at their defaults.

### D3. Environment variables

| Name                    | Value                                                                |
| ----------------------- | -------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL` | the backend URL from C5, e.g.`https://mact-app-backend.vercel.app` |

### D4. Deploy

Click **Deploy** and wait for the build to finish. Visit the resulting
URL, e.g. `https://mact-app-frontend.vercel.app`.

### D5. Verify

Go to `https://mact-app-frontend.vercel.app/members`. The page will load
but the member list will likely fail to fetch — that's expected, and
fixed in Part E.

---

## Part E — Connect the two (fix CORS)

The backend currently only allows requests from `localhost:3000`. Update
it to also allow the live frontend:

1. Go to the **backend** Vercel project → **Settings** → **Environment
   Variables**.
2. Edit `ALLOWED_ORIGINS` to:
   ```
   https://mact-app-frontend.vercel.app
   ```

   (Add `http://localhost:3000` too, comma-separated, if you still want to
   test locally against the live backend: `http://localhost:3000,https://mact-app-frontend.vercel.app`)
3. Go to **Deployments** → find the latest deployment → click the **⋯**
   menu → **Redeploy**. Environment variable changes don't take effect
   until redeploy.

### Verify end-to-end

Reload `https://mact-app-frontend.vercel.app/members`. The member list
should load (empty, unless you've already migrated data), and adding a
member through the form should persist and reappear on refresh.

---

## Part F — Migrate existing member data into the live database

Run this from your local machine — it connects directly to Neon, not
through Vercel:

```bash
cd scripts
pip install openpyxl sqlalchemy psycopg2-binary
export DATABASE_URL="<the same pooled Neon connection string>"
python migrate_members_from_xlsx.py /path/to/MACT_COOPERATIVE_AUTOMATED_LEDGER.xlsx
```

Refresh the live `/members` page — the migrated rows should now appear.

---

## Part G — Ongoing deploys

- **Every `git push` to `main`** triggers a production redeploy of whichever
  project(s) have changed files under their root directory. Since backend
  and frontend have separate root directories, changing only frontend code
  won't redeploy the backend, and vice versa.
- **Pull requests / branches** automatically get their own **Preview**
  deployment with a unique URL — useful for testing the loans module
  before merging it into `main`. Preview deployments use the same
  environment variables unless you override them per-environment.
- **Rollbacks**: on the project's Deployments tab, any previous deployment
  can be promoted back to Production with one click if something breaks.

---

## Troubleshooting checklist

| Symptom                                                                          | Likely cause                                              | Fix                                                           |
| -------------------------------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------- |
| `/api/health` returns 500                                                      | Bad`DATABASE_URL`                                       | Confirm pooled connection string,`?sslmode=require` present |
| Frontend loads but member list never appears, browser console shows a CORS error | `ALLOWED_ORIGINS` doesn't include the frontend URL      | Update env var in backend project, redeploy                   |
| Frontend shows`Failed to fetch`                                                | `NEXT_PUBLIC_API_URL` wrong or backend not deployed yet | Confirm backend URL, redeploy frontend after fixing           |
| Migration script errors on`gen_random_uuid()`                                  | `pgcrypto` extension not enabled                        | Run the`CREATE EXTENSION` statement from A3                 |
| First request after idle is slow                                                 | Neon autosuspend + cold start                             | Expected on free tier; not an error                           |

---

## Next steps

Once the members module is verified live end-to-end, the same six-part
flow (push → deploy backend → deploy frontend → verify → migrate data)
repeats for each subsequent module — loans, deductions, cashbook,
dividends — with no changes to the deployment process itself, only to the
code being deployed.
