# County Records Engine - Public Records & Real Estate Acquisitions Platform

A high-performance real estate acquisitions platform built for multi-state investors (Florida, Texas, and expanding). It cross-references master property appraiser databases across counties against raw distressed lead files (Lis Pendens, Code Violations, Tax Delinquent, Probate, Pre-Foreclosure).

---

## Supported Florida Counties

All county parcel databases and data files are unified inside the `data/` directory:

| County | Directory | Master Parcel File | Live Status |
| :--- | :--- | :--- | :---: |
| **Pinellas** | `data/pinellas/` | `RP_PROPERTY_INFO.parquet` | ✅ Installed (~437,500 parcels) |
| **Orange** | `data/orange/` | `RP_PROPERTY_INFO.parquet` | ✅ Installed (~496,700 parcels) |
| **Hillsborough** | `data/hillsborough/` | `RP_PROPERTY_INFO.parquet` | Ready for Download |
| **Pasco** | `data/pasco/` | `RP_PROPERTY_INFO.parquet` | Ready for Download |
| **Manatee** | `data/manatee/` | `RP_PROPERTY_INFO.parquet` | Ready for Download |
| **Polk** | `data/polk/` | `RP_PROPERTY_INFO.parquet` | Ready for Download |
| **Sarasota** | `data/sarasota/` | `RP_PROPERTY_INFO.parquet` | Ready for Download |

---

## Key Features

1. **High-Speed FastAPI Backend & Modern Glass UI**:
   - High-throughput asynchronous backend (`server.py`).
   - Clean, modern, responsive interface (`frontend/index.html` + `frontend/app.js`).
   - Dynamic real-time search, category distress filtering, and CSV export.

2. **Automated Human Defendant & Entity Filtering**:
   - Automatically detects bundled Clerk Lis Pendens filings.
   - Filters out institutional corporate entities (HOAs, Condo Associations, Banks, LLCs, Trusts).
   - Eliminates standard foreclosure placeholders (`JOHN DOE`, `UNKNOWN HEIRS`).
   - Isolates actual individual homeowners and heirs for wholesaling outreach.

3. **Multi-Tier Matching Engine**:
   - **Tier 1**: Exact Parcel ID / Strap number lookup.
   - **Tier 2**: Normalized Physical Street Address.
   - **Tier 3**: Exact Normalized Owner Name (`LAST FIRST` or `FIRST LAST`).
   - **Tier 4**: Legal Description Lot / Block / Unit / Subdivision matching.
   - **Tier 5**: Fuzzy Owner Name matching (via RapidFuzz).

4. **Multi-Channel $0.00 Outreach Suite**:
   - **📱 Android SMS Gateway**: Sends cellular SMS cash offers directly through your phone line for free.
   - **✉️ SMTP2GO Email Gateway**: Sends responsive HTML offer letters via `mail.smtp2go.com` (Port 2525) from `john@407flips.com`.
   - **🔄 Chrome Extension Helper**: 1-click TruePeopleSearch scraper pulling both phone numbers and emails straight into your leads table.

---

## How to Run

### Option 1: Batch Script (Recommended)
Double-click **`run_hub.bat`** to start Florida Lead Hub at `http://localhost:8505`.  
To stop the server, double-click **`stop_hub.bat`**.

The launcher uses the **Florida Lead Hub** Windows scheduled task. It starts at
your Windows sign-in, runs without an open terminal, and restarts the server if
the server process exits. Closing a terminal does not stop it. The computer must
remain awake and signed in to receive webhook traffic. The existing Cloudflare
tunnel service must also be running.

The seller inbox checks for incoming replies every two seconds and refreshes the
selected conversation automatically. Its connection indicator reports failures
and the page retries automatically. Reload an already-open page once after an
application update to load the latest JavaScript.

In **Saved Lists / My Leads**, **Start Auto SMS** queues imported contacts in the
current filtered table order across all pages in the selected county. Saved
Lists, counts, exports, SMS, follow-ups, and email use only that county's leads.
Switching counties switches the saved list without deleting contacts. Each lead is resolved
by its saved parcel ID and uses its own contact details. It sends the first text
when started, then waits 90 seconds after each send before dispatching the next.
It cycles the four configured SMS outreach templates, one message per lead.
An explicit county-scoped initial SMS reset allows previously contacted imported
leads one additional initial text without erasing their history. Pending resets
hide the Texted badge until the next send. Replies, blocked numbers, test leads,
and uncertain sends are excluded. Resets persist and are consumed on dispatch.
Missing, duplicate, previously contacted, and blocked numbers are skipped.
Copilot/Autopilot reply settings are independent of this initial outreach queue.

Initial SMS outreach uses one shared set of templates for every county. The
manual composer, Auto SMS, and Copilot initial suggestions all use the current
SMS templates in Outreach Templates. Copilot follows the selected template;
legacy opener IDs resolve to the updated shared messages. Gateway settings do
not override the shared first-touch messages. Leads retain their saved county
when contacted from a saved list containing properties in multiple counties.

**Start Follow Up**, beside **Start Auto SMS**, automatically follows up with
previously texted imported contacts in the current filtered list who have never
replied. It rotates ten messages asking whether the recipient owns the property,
inserts each lead's street address, and sends one SMS every 90 seconds. Replies
are rechecked before dispatch. Numbers already followed up, opted out, blocked,
duplicated, or missing an address are skipped. Each number receives at most one
automatic follow-up. Replies from follow-up recipients are handled manually in
the inbox, even when Autopilot is enabled for other contacts. Reply and follow-up
tracking persist across restarts and rolling inbox-history cleanup. Both types
of outreach share the same queue and Pause, Resume, and Stop controls.

Saved leads retain a permanent county parcel link and a snapshot of their recorded
distress types, case/document references, source files, and last-checked date.
Imports reuse these links; opening or searching the saved list does not rematch
addresses. Original and imported contacts for a linked property appear as one row,
while their contact IDs and outreach history remain intact. **View source records**
shows the supporting references. **Refresh Distress Details** explicitly updates
the snapshots from the latest local county cache and backs up contacts first.
Ambiguous address matches remain unlinked rather than being guessed.

Double Distress requires at least two distinct recorded distress types. Search
keeps the selected category filter applied. Probate email defaults require an
explicit probate record; trust ownership, a stack flag, or a death certificate
alone does not qualify. Other records default to foreclosure, code violation, or
general cash-offer emails as appropriate.

**Start Auto Email**, beside the SMS buttons in Saved Lists / My Leads, processes
the current filtered list in order across all pages. It sends one email, waits
90 seconds, then continues. Each property uses its saved distress details to
select the configured foreclosure, confirmed probate, code violation, or general
offer template. The subject and full plain-text/HTML message use that property's
name, address, county, and the configured sender contact details. Replies go to
the configured reply-to mailbox for manual handling.

**Check Eligible Emails** previews counts without sending. Missing/malformed
addresses, duplicate addresses or linked properties, previously emailed
addresses/properties, test leads, and known blocked contacts are skipped. Known
email opt-outs/bounces can be stored on contacts (`email_opt_out`, `unsubscribed`,
`email_bounced`) or in `data/email_suppression.json` (a list of email strings or
objects with an `email` field). Existing phone suppression/DNC flags also apply.
Incoming email replies and later bounces are not automatically imported.

Auto Email has its own Pause, Resume, Stop, and progress controls. Its server-side
queue persists in `data/auto_email_queue.json` and continues when the browser
closes. Failed/uncertain sends pause for review and are never blindly retried;
Resume continues with the next contact. Pause/Stop allows an email already being
dispatched to finish. SMTP acceptance is recorded as sent, not proof of inbox
delivery. The computer and email gateway must remain available.

The progress panel provides Pause, Resume, and Stop. Switching pages or closing
the browser does not stop the server-side queue. Its state is persisted in
`data/auto_sms_queue.json`; a restart preserves progress and spacing. Failed or
interrupted sends pause for review and are not automatically retried. Pause/Stop
allows an SMS already being dispatched to finish. The computer and SMS gateway
must remain available while the queue runs.

### Option 2: Command Line (PowerShell)
```bash
python server.py
```
The application runs on `http://localhost:8505`.

## Automatic inbound CSV pulls

The **Florida Lead Hub** sign-in task also starts and restarts the chokidar
watcher. Install its small Node dependency once with `npm install` (Node.js
22.9+), then configure the project-root `.env` from `.env.example`:

```dotenv
INBOUND_PULL_DIR="I:\My Drive\deal-finder-list-drops"
```

Keep that Drive for Desktop folder available offline. The watcher creates
`processed/` and `quarantine/`. It polls only root CSV files, waits two seconds
after writes settle, and processes files serially. Files synced while the app
was stopped are recovered on startup with the same stability check.

Supported filename orders are `lis-pendens-orange-2026-10-19.csv` and Pepper's
existing `orange-county-lis-pendens-2026-10-19.csv`; county names come from the
existing Florida county registry. The recognized types are `lis-pendens`,
`probate`, `code-violations`, and `tax-lien`. Only lis pendens currently has a
verified schema, with these exact columns in this order:

```text
recording_date,instrument_number,book_page,grantor,grantee,property_address,legal_description
```

Unknown filenames, header differences, missing instrument numbers, and types
whose schema has not yet been defined go to quarantine with an explanation.
Define future verified schemas in `src/inbound_pull.py`; do not infer them.
Empty legal descriptions are allowed. Legal descriptions stay in the existing
legal matching field, including the clerk's `Lot:` / `Block:` syntax.

The bridge calls the **same CSV parser and cross-reference/cache functions as
Load List** (`read_lead_upload` and `match_lead_dataframe` in `server.py`).
Matches land in the existing county lead table for review and contact enrichment.
This does not start Auto SMS or Auto Email. Their existing sending and compliance
controls remain unchanged.

`data/inbound_pulls.sqlite3` stores durable `(list_type, county,
instrument_number)` keys, shared with manual uploads using this clerk schema.
Keep this local file across restarts. Failed imports roll back their keys; cache
writes are atomic. Archived filenames never overwrite previous pulls. An archive
failure leaves the original inbound CSV in place and is reported; restart the
watcher after resolving it to archive the file without reingesting its rows.

One JSON audit line per file is appended to `data/inbound_watcher.log`, including
filename, type, county, timestamp, rows ingested, duplicate rows skipped, and rows
quarantined. A row count is `null` when the CSV could not be parsed. Startup,
Drive availability, or process errors also appear in this log and
`data/lead_hub_supervisor.log`; the supervisor retries the watcher after 30 seconds.

For a standalone foreground troubleshooting session, stop the background task
first to avoid competing watchers, then run `npm run watch:inbound`.
`INBOUND_PYTHON` optionally selects the Python executable; the background task
automatically uses the same Python as the server. To activate an update, restart
the existing Florida Lead Hub scheduled task (or use `stop_hub.bat`, then
`run_hub.bat`).

Validation: `npm run test:inbound` and
`python -m unittest discover -s tests -p test_inbound_pull.py` use temporary files
and do not send messages or modify live lead data.
