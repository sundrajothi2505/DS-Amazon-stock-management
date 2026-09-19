# Putting DS Amazon Stock Management online (reachable from anywhere)

This guide moves the app off your office computer and onto a small rented
server, so it works even when your computer is off, and your staff (and you)
can reach it from home, mobile data, anywhere — not just your office Wi-Fi.

We'll use two free-to-start services together:
- **Supabase** — a hosted PostgreSQL database. This is where your products,
  orders, and everything else actually lives.
- **Render** — runs the app itself and talks to that database. Costs
  roughly **$7/month** for the always-on tier (a free tier exists too, but
  it sleeps after inactivity and feels slow for real daily use).

This replaces the "run python app.py on your computer" approach — once this
is live, that's the version you and your staff should use day to day. Your
computer no longer needs to stay on.

You'll need three free accounts: **GitHub** (holds your project files),
**Supabase** (the database), and **Render** (runs the app).


## Part 1 — Put your project on GitHub

Render deploys from a GitHub repository. You don't need to know Git or any
commands — GitHub lets you upload files through your browser like any file
storage site.

1. Go to **github.com** and sign up for a free account (skip this if you
   already have one).
2. Once logged in, click the **+** icon (top right) → **New repository**.
3. Name it `ds-amazon-stock-management`. Set it to **Private** (so no one
   else can see your code). Leave everything else as default, then click
   **Create repository**.
4. On the new (empty) repository page, click **"uploading an existing
   file"** (a blue link in the middle of the page).
5. Open your unzipped project folder on your computer, select **all the
   files and folders inside it** (app.py, db.py, importer.py,
   requirements.txt, schema.sql, schema_postgres.sql, Procfile, README.md,
   the `static` folder, the `templates` folder — everything), and drag them
   into the browser window.
   - Don't worry about `stock.db` if you see one in that folder — that's
     local test data and doesn't need to go here.
6. Scroll down and click **Commit changes**.

If you're updating an existing repository instead of starting fresh, just
repeat steps 4–6 with the new files — GitHub will ask to confirm you're
replacing the older versions.


## Part 2 — Create your Supabase database

1. Go to **supabase.com** and sign up for a free account.
2. Click **New project**. Give it a name (e.g. `ds-amazon-stock`), set a
   database password (click **Generate a password** and **save it
   somewhere** — you won't need to remember it, but you will paste it into
   one connection string in a minute), pick the region closest to you, and
   click **Create new project**. Wait a minute or two for it to provision.
3. Once it's ready, go to **Project Settings → Database**.
4. Find **Connection string**, and switch to the **Transaction pooler**
   tab (not "Session pooler" or "Direct connection" — the transaction
   pooler is built for exactly this kind of app, where each web request
   opens its own short-lived database connection).
5. Copy that connection string. It looks like:
   ```
   postgresql://postgres.xxxxxxxxxxxx:[YOUR-PASSWORD]@aws-0-xx-xxxx-1.pooler.supabase.com:6543/postgres
   ```
6. Replace `[YOUR-PASSWORD]` in that string with the database password
   from step 2. Save this complete string somewhere — it's your
   `DATABASE_URL`, needed in Part 4.

That's it for Supabase — the app creates all its own tables automatically
the first time it starts up.


## Part 3 — Create the web service on Render

1. Go to **render.com** and sign up for a free account — choose **"Sign up
   with GitHub"** so the two are connected automatically.
2. From the Render dashboard, click **New +** → **Web Service**.
3. Choose **"Build and deploy from a Git repository"**, then find and
   select `ds-amazon-stock-management` (you may need to click "Configure
   account" and grant Render access to that repository first).
4. Fill in the settings:
   - **Name:** `ds-amazon-stock-management` (this becomes part of your web
     address)
   - **Region:** pick whichever is closest to you
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Instance Type:** Starter (~$7/month, stays on all the time — the
     Free tier works too, just expect ~30–60 second wake-up delays)


## Part 4 — Add your environment variables

Find **Environment Variables** on that same setup page (or under
**Environment** in the left sidebar if you're editing an existing service)
and add these two:

| Key | Value |
|---|---|
| `DATABASE_URL` | The full Supabase connection string from Part 2, password already filled in |
| `SECRET_KEY` | *(see below — generate your own)* |

**To generate a SECRET_KEY:** on your computer, open PowerShell and run:

```
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the long string it prints out and paste it as the value for
`SECRET_KEY`. This scrambles employee login sessions so they can't be
forged — keep this value private, don't share it or reuse it elsewhere.

You do **not** need a `DB_PATH` variable or a persistent disk for this
setup — Supabase is your database now, not a local file.


## Part 5 — Deploy

Click **Create Web Service** (or, if you're updating an existing service,
save the environment variables and trigger **Manual Deploy → Deploy latest
commit**). Render will build and start the app — this takes a few minutes.
When it's done, you'll see a green "Live" status and a web address like:

```
https://ds-amazon-stock-management.onrender.com
```

That's your permanent address — bookmark it.


## Part 6 — First login and going live

1. Log in with the default admin login (**admin / admin123**) — this is a
   brand new, empty database.
2. Change the password immediately (top-left, "Change password").
3. Go to **Products → Import from report** and upload your listings
   report, then **Daily orders → Import from Excel** for your order
   history — same files you've already used before.
4. Go to **Employees** and add a login for each staff member.
5. Share the `onrender.com` address with your team.


## Updating the app later

Re-upload the changed files to the same GitHub repository (Part 1, steps
4–6) — Render automatically re-deploys within a minute or two whenever the
GitHub repo changes. Your Supabase data is completely separate from this
and is untouched by any redeploy.


## Costs at a glance

- **Render Starter web service:** ~$7/month
- **Supabase:** free, for a project this size (their free tier covers a
  small database like this comfortably)


## If something goes wrong

Render's **Logs** tab (left sidebar of your service) shows exactly what the
running app is doing, including the full error text if something crashes —
that's the first place to look, and the most useful thing to screenshot if
you need help. Render also has a **Shell** tab that gives you a live
terminal into the running app, handy for checking exactly which files and
versions are actually deployed.
