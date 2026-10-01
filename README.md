# Scanner Lease & Proposal Calculator

A small web app for a dental lab to work out the numbers on financing/leasing
an intraoral scanner package, decide what to charge a doctor, and generate a
proposal plus both lease agreements to send them. Every proposal is saved to
a local database so labs can come back to it.

## Who sees what

- **Anyone with the link** can open the public calculator (`/`), fill in
  their lab info once, and generate proposals. No login needed — that's by
  design, so labs can self-serve.
- **A lab only ever sees its own work.** The first time a lab generates a
  proposal, it's saved with a private, unguessable link back to a "My
  Proposals" dashboard (`/lab/<token>`). That link is the credential — there's
  no username/password for labs, but nothing is guessable or listed publicly,
  and one lab's link never shows another lab's data.
- **Each proposal and its two agreements** also live behind their own
  unguessable link (`/p/<token>`, `/p/<token>/agreement`,
  `/p/<token>/lab-agreement`) so a lab can email a specific deal to a doctor
  without exposing anything else.
- **Only `/admin`** sees every lab and every proposal across the whole
  system. It's gated by a single shared password (see Environment variables
  below) — set a real one before this goes live.

## What it does

1. **Your cost** — a read-only summary (Total Cost, Down Payment, Amount
   Financed, Term, Estimated Monthly Payment). These numbers are the same
   for every lab and every proposal, set once by the admin (see below) — a
   lab can't edit them, and the interest rate itself is never shown, only
   the resulting payment.
2. **Price to the doctor** — set the sell price, a sign-up discount, the
   doctor's down payment, rate and term; their monthly lease payment (rounded
   to the nearest $5 by default) recalculates automatically as you type, so
   the screen always matches what will be saved.
3. **Doctor's estimated spend** — enter what the doctor is expected to spend
   monthly, and see the % of that spend needed to fully cover their lease
   payment, with a button to use that % below.
4. **Monthly doctor invoice credit** — set what % of the doctor's monthly
   bill gets credited toward their lease payment, and the "no credit below
   this" threshold. Works out the break-even spend level (where the doctor
   owes $0) and a full schedule of bill levels vs. what's owed.
5. **Per unit profitability** (optional) — your cost/price per unit to this
   doctor, to show profit and net margin at each bill level.
6. **Generate a proposal and both lease agreements** — enter the client's
   info and it saves everything, then gives you: a printable proposal, a
   lease agreement between the lab and the doctor, and a lease agreement
   between the equipment supplier and the lab's owner personally (see
   "Personal liability on the lab-supplier lease" below) — all
   print-to-PDF from the browser.
7. **Email it** — from the proposal page, send yourself (or the doctor) an
   email with a spec-sheet summary and links to all three documents. Requires
   SMTP settings (see below) — without them the button shows a clear error
   instead of silently failing.
8. **Admin dashboard** (`/admin`) — every lab and every proposal, password
   gated. **Admin → Equipment & Financing Settings** is where the numbers in
   item 1 above are set (equipment cost components, supplier markup, the
   lab's own down payment/rate/term) — change them there and every lab's
   calculator picks up the new figures immediately.

The math lives in one place (`calc.py`) and is mirrored in
`static/calculator.js` for the live on-page preview, but whatever gets saved
is always recomputed on the server, so nothing in the browser can fake the
numbers that end up on a signed agreement.

## Running it locally

```bash
cd scanner-calculator
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5050. Data is stored in `data/app.db` (SQLite) —
delete that file to start fresh. Locally, the admin password defaults to
`changeme` and email sending is disabled until you set the environment
variables below.

## Environment variables (set these before going public)

| Variable | What it's for | Required? |
|---|---|---|
| `ADMIN_PASSWORD` | Password for `/admin`. **Change this** — the default is `changeme`. | Yes |
| `SECRET_KEY` | Signs the admin login session cookie. **Change this** to a long random string, or anyone can forge an admin session. | Yes |
| `SUPPLIER_NAME` | Your business name, shown on the lab-supplier lease agreement. | Recommended |
| `SUPPLIER_ADDRESS` | Your business address, same agreement. | Optional |
| `BREVO_API_KEY`, `EMAIL_FROM` | **Recommended** way to enable the "email me these documents" button. Sends over Brevo's HTTPS API, which works on hosts (Railway, Render, Heroku, ...) that block outbound SMTP entirely. Brevo's free plan (300 emails/day, no expiration) is plenty for this. `EMAIL_FROM` must be a verified sender in Brevo — either a single address confirmed by a 6-digit emailed code, or any address on a domain you've fully authenticated with Brevo (a domain with a strict DMARC policy requires the latter). | Optional (feature disabled without it) |
| `EMAIL_FROM_NAME` | Optional display name shown next to `EMAIL_FROM` (e.g. "AmericaSmiles Sales"). Purely cosmetic — doesn't need to be verified anywhere. | Optional |
| `EMAIL_REPLY_TO` | Optional. If a doctor hits "Reply," it goes here instead of `EMAIL_FROM`. Useful when `EMAIL_FROM` has to be an already-verified address on a different domain (e.g. your main domain's DMARC policy is blocking sender verification there) — set this to the address you actually want replies to land in. | Optional |
| `SENDGRID_API_KEY`, `EMAIL_FROM` | Same idea as Brevo above, if you'd rather use SendGrid (note: SendGrid's free plan no longer exists, it's a 60-day trial only now). Used only if `BREVO_API_KEY` is not set. | Optional |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_FROM` | Classic SMTP settings, used only if neither `BREVO_API_KEY` nor `SENDGRID_API_KEY` is set. Only works on a host that allows outbound SMTP (most cloud PaaS hosts, Railway included, block it). | Optional |

On Render/Railway/Fly.io these go in the service's "Environment" tab. Locally
you can `export ADMIN_PASSWORD=...` before running, or use a `.env` file with
a tool like `python-dotenv` if you add one.

## Deploying it for real

This is a plain Flask app with a SQLite file for storage, so it runs
anywhere that runs Python:

- **Render / Railway / Fly.io**: push this folder to a GitHub repo, point
  any of those at it, and set the start command to `gunicorn app:app`
  (already in `requirements.txt`). Attach a persistent disk (all three offer
  one) mounted at `data/` so the database survives restarts and deploys. Set
  the environment variables above in the host's dashboard.
- **A VPS**: `gunicorn -w 2 -b 0.0.0.0:8000 app:app` behind nginx.
- **Moving off SQLite**: if you outgrow a single file (multiple labs writing
  at once, need backups/replicas), swap `db.py` for Postgres — the only
  file that touches storage, everything else is unaffected.

## Project layout

```
app.py                       Flask routes
calc.py                      All the math (PMT, credit schedule, margins)
config.py                    Site settings, all overridable by env vars
db.py                        SQLite storage (labs, proposals, access tokens)
mailer.py                    SMTP email sending
templates/
  index.html                 Public calculator
  proposal.html              Printable proposal + email form
  agreement.html             Doctor <-> lab lease agreement
  lab_agreement.html         Lab <-> supplier lease agreement
  lab_dashboard.html         A lab's own proposals (token-gated)
  admin.html                 Every lab/proposal (password-gated)
  admin_login.html           Admin password form
  email_proposal.html        HTML email body
static/
  calculator.js              Live client-side preview (mirrors calc.py)
  style.css
data/app.db                  SQLite database (created on first run)
```

## Personal liability on the lab-supplier lease

The equipment lease between the supplier and the lab (`lab_agreement.html`)
is written to make the lab's **owner personally and individually liable**,
not just the lab entity — the opposite of the doctor-facing lease, which
explicitly disclaims personal liability. To do that, it names the owner
individually throughout the agreement text and signature block.

Only the owner's full legal name is collected through the calculator (see
the "Lab owner" field on `/`), so the agreement text can be personalized —
it's stored with the lab's profile and never shown on any page other than
the generated agreements. The owner's **home address and Social Security
Number are never collected through the web form at all.** They appear only
as blank fill-in lines in the signature block of the printed agreement
(`/p/<token>/lab-agreement`), to be filled in by hand at the time of actual
signing — nothing sensitive is typed into the app or stored in the
database.

## Notes / things to fill in before using a generated agreement for real

- **Early termination fee, Scanner Lease Agreement** (Section 7, Cancellation):
  cancellation requires sixty (60) days' notice, with the two Lease Payments
  covering that notice period plus a fee equal to one full Lease Payment due
  on top.
- **Early termination fee, Equipment Lease Agreement** (Section 6,
  Cancellation): unchanged — thirty (30) days' notice, one Lease Payment for
  the notice period, plus a fee equal to half of one Lease Payment.
- **Governing law, Scanner Lease Agreement** (Section 12): now a per-lab
  field (`lab.state`, set on the "Your Lab" form) instead of hardcoded —
  shows `[Lab State]` until a lab fills it in.
- **Governing law, Equipment Lease Agreement** (Section 11): still hardcoded
  to Illinois.
- **Doctor end-of-lease-term** (Section 8 of the doctor agreement): the lab
  decides at its own discretion between a quoted upgrade or month-to-month
  continuation — the former one-payment buyout option was removed — no
  fixed dollar blank to fill in.
- **Lab end-of-lease-term** (Section 7 of the lab-supplier agreement): a
  final payment (one Lease Payment) buys out the equipment, or the lab can
  take a quoted upgrade between month `lab_term` and month `doctor_term` and
  swap the doctor's equipment.
- This isn't legal advice — have counsel review both agreement templates
  before using them with real customers.
