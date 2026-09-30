"""Sends the "email me these documents" message.

Three paths, tried in this order:

1. Brevo's HTTP API, if BREVO_API_KEY is set. Brevo has a genuinely free
   plan (300 emails/day, no time limit -- SendGrid's free plan no longer
   exists, it's now a 60-day trial only). Sends over a normal HTTPS
   request, the same kind of connection any web page makes -- so it works
   on hosts (Railway, Render, Heroku, ...) that block outbound SMTP
   entirely as an anti-spam measure. This is the recommended path.
2. SendGrid's HTTP API, if SENDGRID_API_KEY is set instead -- same idea,
   for anyone who already has a SendGrid account/trial.
3. Plain SMTP (smtplib), if EMAIL_HOST is set instead of either of the
   above. Works on a host that doesn't block outbound SMTP (e.g. a plain
   VPS). Any standard SMTP provider works -- Gmail app password, Office
   365, Rackspace, Mailgun, Postmark, etc.
"""

import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

import config


class MailerNotConfigured(Exception):
    pass


class MailerError(Exception):
    """A specific, user-facing reason sending failed (bad host/port, wrong
    login, server rejected the message, etc.) -- safe to show as-is."""
    pass


def send_proposal_email(to_addrs, subject, html_body, text_body):
    if config.BREVO_API_KEY:
        _send_via_brevo(to_addrs, subject, html_body, text_body)
        return
    if config.SENDGRID_API_KEY:
        _send_via_sendgrid(to_addrs, subject, html_body, text_body)
        return
    if config.EMAIL_HOST:
        _send_via_smtp(to_addrs, subject, html_body, text_body)
        return
    raise MailerNotConfigured(
        "Email sending isn't set up yet. Set BREVO_API_KEY (recommended, free) or "
        "SENDGRID_API_KEY or EMAIL_HOST / EMAIL_USERNAME / EMAIL_PASSWORD as "
        "environment variables on the host running this app."
    )


def _send_via_brevo(to_addrs, subject, html_body, text_body):
    from_addr = config.EMAIL_FROM or config.EMAIL_USERNAME
    if not from_addr:
        raise MailerNotConfigured(
            "BREVO_API_KEY is set, but EMAIL_FROM (the address to send from, already "
            "verified in Brevo) is not. Set EMAIL_FROM as an environment variable too."
        )

    sender = {"email": from_addr}
    if config.EMAIL_FROM_NAME:
        sender["name"] = config.EMAIL_FROM_NAME

    payload = {
        "sender": sender,
        "to": [{"email": a} for a in to_addrs],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": text_body,
    }
    if config.EMAIL_REPLY_TO:
        payload["replyTo"] = {"email": config.EMAIL_REPLY_TO}

    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": config.BREVO_API_KEY,
                "Content-Type": "application/json",
                "accept": "application/json",
            },
            json=payload,
            timeout=15,
        )
    except requests.RequestException as e:
        raise MailerError(f"Could not reach Brevo to send the email. Detail: {e}")

    if resp.status_code >= 400:
        # Brevo puts the real reason (bad API key, unverified sender, etc.) in
        # the response body -- surface it directly, it's the most useful
        # thing we can show.
        detail = resp.text.strip()
        if "sender" in detail.lower() and ("not valid" in detail.lower() or "not authorized" in detail.lower() or resp.status_code == 401):
            raise MailerError(
                f"Brevo rejected this. The most common cause: {from_addr} hasn't been "
                f"verified yet in Brevo (Senders, Domains & Dedicated IPs > Senders > "
                f"Add a Sender, then enter the code Brevo emails to that address). "
                f"Detail: {detail}"
            )
        raise MailerError(f"Brevo rejected the email (HTTP {resp.status_code}): {detail}")


def _send_via_sendgrid(to_addrs, subject, html_body, text_body):
    from_addr = config.EMAIL_FROM or config.EMAIL_USERNAME
    if not from_addr:
        raise MailerNotConfigured(
            "SENDGRID_API_KEY is set, but EMAIL_FROM (the address to send from, "
            "already verified in SendGrid) is not. Set EMAIL_FROM as an "
            "environment variable too."
        )

    from_field = {"email": from_addr}
    if config.EMAIL_FROM_NAME:
        from_field["name"] = config.EMAIL_FROM_NAME

    payload = {
        "personalizations": [{"to": [{"email": a} for a in to_addrs]}],
        "from": from_field,
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text_body},
            {"type": "text/html", "value": html_body},
        ],
    }
    if config.EMAIL_REPLY_TO:
        payload["reply_to"] = {"email": config.EMAIL_REPLY_TO}

    try:
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {config.SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
    except requests.RequestException as e:
        raise MailerError(f"Could not reach SendGrid to send the email. Detail: {e}")

    if resp.status_code >= 400:
        # SendGrid puts the real reason (bad API key, unverified sender, etc.)
        # in the response body -- surface it directly, it's the most useful
        # thing we can show.
        detail = resp.text.strip()
        if "does not match a verified Sender Identity" in detail or resp.status_code == 403:
            raise MailerError(
                f"SendGrid rejected this. The most common cause: {from_addr} hasn't been "
                f"verified yet in SendGrid (Settings > Sender Authentication > Verify a "
                f"Single Sender). Detail: {detail}"
            )
        raise MailerError(f"SendGrid rejected the email (HTTP {resp.status_code}): {detail}")


def _send_via_smtp(to_addrs, subject, html_body, text_body):
    from_addr = config.EMAIL_FROM or config.EMAIL_USERNAME
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{config.EMAIL_FROM_NAME} <{from_addr}>" if config.EMAIL_FROM_NAME else from_addr
    msg["To"] = ", ".join(to_addrs)
    if config.EMAIL_REPLY_TO:
        msg["Reply-To"] = config.EMAIL_REPLY_TO
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    # Port 465 is "implicit TLS" -- the whole connection is encrypted from
    # the first byte, so it needs SMTP_SSL. Port 587 (or 25) starts in the
    # clear and upgrades via STARTTLS. Using the wrong one for the port is a
    # very common cause of a connection that just hangs until it times out,
    # instead of failing with a clear error -- so pick the right one
    # automatically based on the configured port.
    connect_timeout = 12  # fail fast rather than hang the request
    is_implicit_tls = config.EMAIL_PORT == 465

    try:
        if is_implicit_tls:
            server = smtplib.SMTP_SSL(config.EMAIL_HOST, config.EMAIL_PORT, timeout=connect_timeout)
        else:
            server = smtplib.SMTP(config.EMAIL_HOST, config.EMAIL_PORT, timeout=connect_timeout)
    except (socket.timeout, TimeoutError, ConnectionRefusedError, OSError) as e:
        raise MailerError(
            f"Could not reach the email server at {config.EMAIL_HOST}:{config.EMAIL_PORT} "
            f"(connection timed out or was refused). Double-check EMAIL_HOST and EMAIL_PORT, "
            f"or the hosting platform may be blocking outbound connections on this port -- "
            f"if so, switch to SENDGRID_API_KEY instead (see config.py). "
            f"Detail: {e}"
        )

    try:
        with server:
            if config.EMAIL_USE_TLS and not is_implicit_tls:
                server.starttls()
            if config.EMAIL_USERNAME:
                try:
                    server.login(config.EMAIL_USERNAME, config.EMAIL_PASSWORD)
                except smtplib.SMTPAuthenticationError as e:
                    raise MailerError(
                        f"The email server rejected the username/password for "
                        f"{config.EMAIL_USERNAME}. Double-check EMAIL_USERNAME and "
                        f"EMAIL_PASSWORD. Detail: {e}"
                    )
            server.sendmail(from_addr, to_addrs, msg.as_string())
    except smtplib.SMTPException as e:
        raise MailerError(f"The email server rejected the message: {e}")
    except (socket.timeout, TimeoutError, OSError) as e:
        raise MailerError(
            f"Lost the connection to {config.EMAIL_HOST}:{config.EMAIL_PORT} while sending. "
            f"Detail: {e}"
        )
