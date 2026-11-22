# Madhurima Family Restaurant — Billing, GST, Inventory & Accounts

A complete restaurant application that runs **only on this computer** (no cloud, no subscription, works offline).
Backend: **Python FastAPI** · Frontend: **React (Vite)** · Database: **PostgreSQL 17** (in Docker) or SQLite (without Docker).

One local web server serves both the API and the web UI:

- On this PC: **http://localhost:8090**
- From other phones / PCs on the same Wi-Fi/LAN: **http://<this-PC-IP>:8090** (allow port 8090 in Windows Firewall if asked)

## Install (Docker — recommended)

1. Start **Docker Desktop**.
2. Double-click **`install.bat`**. It creates `.env` with random passwords, builds the containers and opens the browser.
3. On first open you create the **admin account** (optionally load a sample menu), then fill **Settings → Restaurant & GST**
   (address, GSTIN, FSSAI, state, invoice series, printer size).

Containers (Compose project `madhurima`): `madhurima-db` (PostgreSQL) and `madhurima-app` (API + UI). Data lives in Docker
volumes `madhurima_pgdata` / `madhurima_appdata`; backups are written to the **`backups`** folder next to this README.

| Script | What it does |
|---|---|
| `install.bat` | First-time install / rebuild |
| `scripts\start.bat` | Start (waits for Docker Desktop) and open the browser |
| `scripts\stop.bat` | Stop the app (data kept) |
| `scripts\enable-autostart.bat` | Start automatically when Windows starts (Startup-folder shortcut). Also enable Docker Desktop → Settings → General → *Start Docker Desktop when you sign in* |
| `scripts\disable-autostart.bat` | Remove autostart |
| `scripts\update.bat` | Rebuild the app after code changes (database untouched) |
| `scripts\run-without-docker.bat` | Alternative: run with local Python 3.12+ / Node 20+ and SQLite |

The containers use `restart: unless-stopped`, so once Docker Desktop starts, the app comes back by itself.

## Modules

| Module | Highlights |
|---|---|
| Dashboard | Sales, cash, UPI, GST, purchases, expenses, stock value, low stock, bills, cancelled, profit estimate, supplier outstanding; daily / monthly / cash-vs-UPI / purchase-vs-sales / GST / expense / top items charts; today / month / quarter / FY filters |
| POS Billing | Search or tap items, categories, tables & running orders, KOT printing, item & bill discounts (permission-based), price change (permission-based), CGST+SGST / IGST, Cash / UPI / split payment with UTR, change calculation, keyboard F2 / F8 / F9 |
| Sales & Bills | History, reprint, duplicate invoice, A4 invoice, cancellation with reason (stock restored), credit notes (sales return), UPI verification |
| GST | Configuration, rate-wise output / input tax, credit & debit notes, 19 GST reports incl. GSTR-1 and GSTR-3B preparation summaries, B2B, B2CS, B2CL, HSN/SAC, monthly & FY summaries |
| Purchases | Supplier invoice entry with GST, discounts, other charges, auto stock-in, payment status, cash/UPI payment, invoice attachment (PDF/JPG/PNG), cancellation, purchase return (debit note) |
| Stock & Movement | Opening stock, addition, reduction, wastage, damage, expiry, correction, manual adjustment, physical reconciliation, minimum-stock alerts, full movement register (opening / added / reduced / closing / reference / user) |
| Recipes | Selling a dish deducts its ingredients (e.g. 1 Chicken Biriyani → rice, chicken, masala, oil, onion) and gives food-cost % |
| Cash & UPI | Daily cash book, other cash in/out, UPI register with verification |
| Expenses | Categories, cash / UPI |
| Customers / Suppliers | GSTIN, state; customer bill history; supplier ledger & outstanding |
| Financial years | April–March, numbering restarts each year, close/reopen |
| Daily closing | Opening cash (carried forward), denomination counting, expected vs actual, difference, remarks; locks the day |
| Monthly closing | Month summary snapshot, requires all billed days closed; locks the month |
| Reports | 40+ reports (sales, GST, purchase, stock, finance, P&L estimate) — every report exports to **Excel and PDF** |
| Settings | Restaurant & GST details, invoice series, printer (thermal 58 / 80 mm, A4), rounding, negative stock, recipe deduction, users & permissions, tables, audit log |
| Backup & Restore | Automatic daily backup + backup on every day closing, manual backup, download, restore from list or uploaded file (a safety backup is taken first) |

**Expected closing cash** = Opening cash + Cash sales + Other cash in − Cash expenses − Cash supplier payments − Cash refunds − Other cash out.

### GST notes
- Rates, HSN/SAC and taxable / exempt / nil / zero-rated status are configured **per product**; nothing is hard-coded.
- Intra-state → CGST + SGST; inter-state (customer GSTIN / state differs, or chosen explicitly) → IGST.
- Composition / unregistered businesses print a *Bill of Supply* without tax.
- The application **does not file returns**. Export the reports, reconcile, and file on the official GST portal.
  Confirm restaurant GST rates and ITC eligibility with your tax consultant.

### Printing
Bills print through the browser to any installed printer. Choose 80 mm / 58 mm thermal or A4 in Settings; for thermal printers set the
paper size in the Windows printer driver and turn off headers/footers and margins in the browser print dialog. For one-click printing
without the dialog, start Chrome/Edge with `--kiosk-printing`.

## Users & roles
- **Admin** — everything, including settings, users, backup/restore, closing/reopening.
- **Manager** — all operations except settings, users and backup.
- **Cashier** — POS, bills, expenses, cash view, customers. Price change, discounts and bill cancellation are per-user permissions.

Passwords are stored as PBKDF2-SHA512 hashes; 5 wrong attempts lock the account for 10 minutes. Every important action is written to the audit log.

## Development
```
cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000     # API docs at /api/docs
cd frontend && npm install && npm run dev                                # http://localhost:5173 (proxies /api)
```
### Automated tests
`backend/tests` holds a pytest suite: GST engine unit tests plus API tests for login and permissions, billing, purchases, stock,
daily / monthly / financial-year locks, backup & restore and every report export. Each test starts from a brand-new empty
database in a temporary folder, so it never touches the live install.
```
cd backend && .venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest                                          # uses a temporary SQLite database
```
To test against PostgreSQL, start a throwaway container and point `TEST_DATABASE_URL` at it (the database name must contain
`test`; the container keeps nothing on disk and is removed when stopped):
```
docker run --rm -d --name madhurima-test-db -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=madhurima_test -p 127.0.0.1:55432:5432 --tmpfs /var/lib/postgresql/data postgres:17-alpine
set TEST_DATABASE_URL=postgresql+psycopg://test:test@127.0.0.1:55432/madhurima_test
.venv\Scripts\python -m pytest
docker stop madhurima-test-db
```
GitHub Actions (`.github/workflows/ci.yml`) runs the suite on SQLite and PostgreSQL, builds the React UI and builds the Docker
image on every push to `main` and every pull request.

`backend/smoke_test.py` is an end-to-end API test against a running server. Run it only against an **empty** test install: it
creates an admin with a test password, sample data, bills, purchases, notes and a backup/restore.
