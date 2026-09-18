# Putting DS Amazon Stock Management online (reachable from anywhere)

This guide moves the app off your office computer and onto a small rented
server, so it works even when your computer is off, and your staff (and you)
can reach it from home, mobile data, anywhere — not just your office Wi-Fi.

We'll use **Render.com**. It costs roughly **$7–8/month total** (a small
web service plus a small persistent disk to keep your data safe between
restarts), handles HTTPS automatically, and doesn't require any server
knowledge on your end.

This replaces the "run python app.py on your computer" approach — once this
is live, that's the version you and your staff should use day to day. Your
computer no longer needs to stay on.

You'll need two free accounts: **GitHub** (just to hold your project files
— no coding knowledge needed, we're only using its "upload files" button)
and **Render** (the actual hosting).


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
5. Open your `stock-manager` folder on your computer, select **all the
   files and folders inside it** (app.py, db.py, requirements.txt,
   schema.sql, Procfile, README.md, the `static` folder, the `templates`
   folder — everything), and drag them into the browser window.
   - Don't upload `stock.db` if you see one in that folder — that's your
     local test data and doesn't need to go here. It's fine if you
     accidentally include it too, it just isn't necessary.
6. Scroll down and click **Commit changes**.

Your code is now on GitHub. You won't need to touch GitHub again unless you
want to update the app later.


## Part 2 — Create the web service on Render

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
   - **Instance Type:** Starter (the cheapest paid tier — the Free tier
     works for testing but sleeps after inactivity and has no persistent
     disk, so your data wouldn't survive a restart)


## Part 3 — Add a persistent disk (so your data is never lost)

Still on that same setup page, find **Advanced** and click it to expand:

1. Click **Add Disk**.
2. **Name:** `data`
3. **Mount Path:** `/var/data`
4. **Size:** 1 GB (plenty for this app)

This is the piece that makes sure your products and movement history
survive restarts and updates — without it, Render would wipe the database
every time it redeploys.


## Part 4 — Add your environment variables

Still under **Advanced**, find **Environment Variables** and add these two:

| Key | Value |
|---|---|
| `DB_PATH` | `/var/data/stock.db` |
| `SECRET_KEY` | *(see below — generate your own)* |

**To generate a SECRET_KEY:** on your computer, open PowerShell and run:

```
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the long string it prints out and paste it as the value for
`SECRET_KEY`. This scrambles employee login sessions so they can't be
forged — keep this value private, don't share it or reuse it elsewhere.


## Part 5 — Deploy

Click **Create Web Service**. Render will build and start the app —
this takes a few minutes the first time. When it's done, you'll see a
green "Live" status and a web address like:

```
https://ds-amazon-stock-management.onrender.com
```

That's your permanent address — bookmark it. Open it, and you should see
the same login screen as before.


## Part 6 — First login and going live

1. Log in with the default admin login (**admin / admin123**) — this is a
   brand new, empty database, separate from anything on your computer.
2. Change the password immediately (top-left, "Change password").
3. Go to **Products** and re-add your products (or if you kept your
   computer's version running, you can look up what you had there first).
4. Go to **Employees** and add a login for each staff member.
5. Share the `onrender.com` address with your team — that's what they'll
   use from now on, from anywhere, any time.

You can stop using the "Start Stock Manager" shortcut and the office
computer entirely — this new address is now the one and only source of
truth.


## Updating the app later

If you ever want changes made to the app, the new files just need to be
re-uploaded to the same GitHub repository (Part 1, step 4–6) — Render
automatically re-deploys within a minute or two whenever the GitHub repo
changes. Your data on the persistent disk is untouched by this.


## Costs and limits, at a glance

- **Starter web service:** ~$7/month
- **1 GB persistent disk:** ~$0.25–1/month
- No usage limits for a small team like yours — it stays on 24/7.

If you'd rather test everything for free first before paying anything,
Render's **Free** instance type works for a trial — just skip the
persistent disk step and know that the app will sleep after inactivity
(the first request after a while takes ~30–60 seconds to wake up) and any
data entered will be lost whenever it restarts. It's meant for kicking the
tyres, not for real day-to-day use.
