"""Site-wide settings. Values come from environment variables so real
secrets never have to live in this file / get committed to git -- set them
on your host (Render/Railway/Fly all have an "Environment" tab). Anything
left unset falls back to a clearly-fake default so the app still runs
locally, but you MUST set real values before this goes public.
"""

import os

# Whoever is running this tool -- the equipment supplier that leases to
# each lab -- is a single entity, unlike labs and doctors which vary per
# proposal. Edit these values (or set them as env vars) for your own business.
SUPPLIER = {
    "name": os.environ.get("SUPPLIER_NAME", "United Dental Resources Corporation"),
    "address": os.environ.get("SUPPLIER_ADDRESS", ""),
}

# Password for the /admin pages (sees every lab and every proposal).
# CHANGE THIS -- set an ADMIN_PASSWORD environment variable on your host.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")

# Signs the admin login session cookie. CHANGE THIS in production -- set a
# SECRET_KEY environment variable to a long random string. If left on the
# default, anyone can forge an admin session.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-change-me")

# Email sending for the "email me these documents" button. Three ways to
# send, tried in this order:
#
# 1. BREVO_API_KEY (recommended for most cloud hosts, including Railway):
#    sends over a regular HTTPS API call instead of a raw SMTP connection.
#    Many hosts (Railway, Render, Heroku, ...) block outbound SMTP entirely
#    as an anti-spam measure, which shows up as a connection that hangs and
#    times out no matter what SMTP settings you use -- Brevo's API sends
#    over the same kind of connection as any normal web request, so it
#    isn't affected by that. Brevo has a genuinely free plan (300
#    emails/day, no expiration). Sign up free at brevo.com, verify the
#    single "from" address you want to send as (Senders, Domains &
#    Dedicated IPs > Senders > Add a Sender, then enter the 6-digit code
#    Brevo emails to that address -- no DNS changes needed), create an API
#    key (Settings > SMTP & API > API Keys), and set BREVO_API_KEY +
#    EMAIL_FROM.
#
# 2. SENDGRID_API_KEY: same idea, for anyone who already has a SendGrid
#    account or trial (SendGrid's own free plan no longer exists -- it's a
#    60-day trial only now).
#
# 3. EMAIL_HOST / EMAIL_PORT / etc. (classic SMTP): works for a host that
#    doesn't block outbound SMTP (e.g. running this on your own VPS). Any
#    standard SMTP provider works -- Gmail app password, Office 365,
#    Rackspace, Mailgun, Postmark, etc.
#
# Whichever of BREVO_API_KEY / SENDGRID_API_KEY is set takes priority over
# the SMTP settings below. Leave all of them unset to disable email sending
# (the button shows a clear error instead of silently failing).
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")

EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USERNAME = os.environ.get("EMAIL_USERNAME", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() != "false"
EMAIL_FROM = os.environ.get("EMAIL_FROM", EMAIL_USERNAME)

# Optional: the display name shown next to EMAIL_FROM (e.g. "AmericaSmiles
# Sales") -- purely cosmetic, doesn't need to be verified anywhere.
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "")

# Optional: where replies should go, if different from EMAIL_FROM. Useful
# when EMAIL_FROM has to be an already-verified address on a different
# domain (e.g. a strict DMARC policy on your real domain is blocking sender
# verification there) -- set EMAIL_REPLY_TO to the address you actually want
# replies to land in, and doctors hitting "Reply" will go there instead of
# whatever EMAIL_FROM is.
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", "")
