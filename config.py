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
    "name": os.environ.get("SUPPLIER_NAME", "AMS Dental Technologies"),
    "address": os.environ.get("SUPPLIER_ADDRESS", ""),
}

# Password for the /admin pages (sees every lab and every proposal).
# CHANGE THIS -- set an ADMIN_PASSWORD environment variable on your host.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")

# Signs the admin login session cookie. CHANGE THIS in production -- set a
# SECRET_KEY environment variable to a long random string. If left on the
# default, anyone can forge an admin session.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-change-me")

# SMTP settings used to email labs their spec sheet/proposal/agreement
# links. Any standard SMTP provider works -- a Gmail account with an "app
# password", Office 365, SendGrid, Mailgun, Postmark, etc. Leave EMAIL_HOST
# blank to disable email sending (the "Email me these documents" button
# will show an error instead of silently failing).
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USERNAME = os.environ.get("EMAIL_USERNAME", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() != "false"
EMAIL_FROM = os.environ.get("EMAIL_FROM", EMAIL_USERNAME)
