# DS Amazon Stock Management

A simple local web app for tracking Amazon seller inventory: current stock,
what's shipped, what's returned, and everything in between — with every
change attributed to the employee who made it. Runs on your own computer;
no cloud account, no monthly fee, no external service seeing your data.

> **Want this reachable from anywhere (not just your office computer/Wi-Fi),
> even when your computer is off?** See **DEPLOY.md** in this same folder
> for step-by-step hosting instructions. Everything below is for running it
> locally, which is also a good way to try it out first.

The whole idea: **stock never changes silently**. Instead of editing a
number, everyone logs a *movement* (received, shipped, returned, damaged,
or a manual adjustment). The app adds it up for you and shows the current
count automatically — so if something's out of stock, you'll see it on the
dashboard instead of finding out from a cancelled Amazon order.


## What it does

- **Dashboard** — total SKUs, total units on hand, and anything low or out
  of stock, at a glance.
- **Products** — your catalog: SKU, name, ASIN, category, reorder level.
  Add them one at a time, or **import them in bulk** from an Amazon
  "All Listings Report" — see below.
- **Log movement** — the main daily screen. Pick a product, pick what
  happened (received / shipped / returned / damaged / adjustment), enter
  a quantity. Current stock updates immediately.
- **History** — every movement ever logged, who logged it, filterable by
  product, type, and date. Exportable to CSV.
- **Daily orders** — a separate reference log for individual Amazon orders
  (order number, product, quantity, status: Pending / Shipped / Delivered /
  Returned / Damaged / Lost / Cancelled). This is for tracking order-level
  detail day to day — it does **not** change stock by itself. Each row has
  a one-click "Log movement" shortcut for when you're ready to record the
  matching stock change.
- **Employees** — each person gets their own login. Admins can add/remove
  employees and delete mistaken entries; everyone else can log stock and
  manage products.


## Requirements

- Python 3.9 or newer. Check with `python3 --version` (or `python
  --version` on Windows).
- That's it — everything else (Flask) installs in one step below.


## First-time setup

1. **Unzip** this folder wherever you'd like to keep it (Desktop, a work
   folder, etc.) — anywhere on the computer that will run the app.

2. **Open a terminal in that folder.**
   - Windows: open the folder in File Explorer, click the address bar,
     type `cmd`, press Enter.
   - Mac: right-click the folder → Services → New Terminal at Folder (or
     open Terminal and `cd` into the folder).

3. **Install the one dependency:**

   ```
   pip install -r requirements.txt
   ```

   If `pip` isn't recognized, try `pip3` instead.

4. **Start the app:**

   ```
   python app.py
   ```

   If `python` isn't recognized, try `python3`.

   You'll see a message with a default admin login the first time:

   ```
   Username: admin
   Password: admin123
   ```

5. **Open your browser** to **http://localhost:5000** and log in with
   the credentials above.

6. **Change the admin password immediately** (top-left of the sidebar,
   "Change password"), then go to **Employees** and add a login for each
   person on your team.

Leave the terminal window open — closing it stops the app. To stop it on
purpose, click into that terminal and press `Ctrl+C`.


## Letting your employees use it too

The app is already set up to be reachable from other computers on the
same Wi-Fi/network — you just need to tell them your computer's local IP
address instead of "localhost":

1. On the computer running the app, find its local IP:
   - **Windows:** open Command Prompt, run `ipconfig`, look for "IPv4
     Address" (something like `192.168.1.23`).
   - **Mac:** System Settings → Wi-Fi/Network → Details, or run
     `ifconfig | grep "inet "` in Terminal.
2. Each employee opens `http://<that-ip>:5000` in their own browser
   (e.g. `http://192.168.1.23:5000`) and logs in with their own account.
3. The computer running `python app.py` needs to stay on and awake for
   others to reach it. If your Wi-Fi router or laptop sleeps/changes IPs
   often, consider running it on a machine that stays on (e.g. an office
   desktop) or a small always-on PC.

If a firewall prompt appears the first time you run it, allow access —
that's what lets other computers on your network connect.


## Restarting later

Every time you want to use it again, open a terminal in the project
folder and run `python app.py`. Your data (products, stock, history,
employee logins) is saved in a file called `stock.db` in this folder and
will still be there.


## Backing up your data

All of your data lives in one file: **`stock.db`**. To back it up, just
copy that file somewhere safe (an external drive, cloud storage folder,
etc.) while the app isn't running. To restore it, stop the app, replace
`stock.db` with your backup copy, and start the app again.

You can also export a snapshot any time from the **Products** page
("Export CSV") or the **History** page ("Export CSV") — handy for
spreadsheets or sharing with someone outside the app.


## Employee roles

- **Staff** — can log movements, add/edit products, view history and the
  dashboard. This is enough for day-to-day warehouse/shipping work.
- **Admin** — everything Staff can do, plus managing employee logins and
  deleting products or movement entries. Deleting a movement recalculates
  stock automatically. There must always be at least one admin.

Deleting an employee's login removes their ability to sign in, but their
past movement history stays exactly as it was, with their name still
attached — nothing about what already happened gets erased.


## Importing products from Amazon

On the **Products** page, click **"Import from report"** and upload a
report exported from Seller Central — **Reports → Inventory → All
Listings Report** works best, because it includes each SKU's current
quantity. (An Active Listings Report also works, just without the stock
sync part, since that report doesn't include quantity.)

What happens on import:
- A SKU that doesn't exist yet is **added** as a new product, with its
  starting stock taken from the report.
- A SKU that already exists gets its **name/ASIN refreshed** if Amazon's
  listing changed.
- If the report's quantity doesn't match what's tracked here, the
  difference is reconciled with a **logged adjustment** — the same kind
  of entry as if someone had typed it into Log Movement — so it always
  shows up in History with a note that it came from an import. Nothing
  is ever silently overwritten.

It's safe to re-run this every time you export a fresh report — rows
that already match are simply left alone.


## Importing your order history from Excel

If you've been tracking daily orders in your own spreadsheet, go to
**Daily orders → Import from Excel** and upload it. This is built for
real-world messy sheets, not a fixed template — it scans every sheet in
the workbook for anything that looks like an order table (a title row
above the real headers, slightly different column names each month, and
so on), and reports back exactly what it found in each sheet.

What happens on import:
- Each order is matched by its **order number**. Already-imported orders
  are left alone, so it's safe to re-run this later or re-upload an
  updated copy of your sheet — nothing gets duplicated.
- Delivery/return status columns are mapped onto this app's status list,
  and your exact original wording is kept in the order's notes so nothing
  is lost in translation.
- Product descriptions are imported as plain text rather than
  auto-matched to a specific catalog SKU — when a spreadsheet just says
  "Black Bump Cap" and your catalog has six near-identical black bump cap
  variants, guessing which one would risk attaching history to the wrong
  product. You can link a specific product afterward from an order's Edit
  page if you want to; it's optional.
- This only adds order records — it never changes any stock numbers.


## Troubleshooting

- **"Address already in use" when starting the app** — something else is
  already running on port 5000 (maybe the app is already running in
  another window). Either close that, or run it on a different port:
  `PORT=5001 python app.py` (Mac/Linux) or set the `PORT` environment
  variable on Windows before running.
- **Employees can't reach it from their computer** — double check you
  gave them your IP address (not "localhost"), that both computers are
  on the same network, and that your firewall isn't blocking incoming
  connections to Python.
- **Forgot the admin password** — log in with another admin account and
  use "Reset password" on the Employees page. If there's truly no admin
  login left, stop the app, delete `stock.db`, and restart — this creates
  a fresh default admin account, but note it also wipes all existing
  data, so only do this as a last resort (back up `stock.db` first if
  you want to keep it for later).


## A note on this being a local tool

This app is meant to run on one computer on your own network — it's not
built to be exposed to the public internet. Don't forward port 5000
through your router to the outside world; keep it on your local
network only.
