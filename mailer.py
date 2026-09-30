"""Sends the "email me these documents" message. Plain smtplib so it works
with any SMTP provider (Gmail app password, Office 365, SendGrid, Mailgun,
Postmark, ...) without adding a dependency.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config


class MailerNotConfigured(Exception):
    pass


def send_proposal_email(to_addrs, subject, html_body, text_body):
    if not config.EMAIL_HOST:
        raise MailerNotConfigured(
            "Email sending isn't set up yet. Set EMAIL_HOST / EMAIL_USERNAME / "
            "EMAIL_PASSWORD (and optionally EMAIL_FROM) as environment variables "
            "on the host running this app."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM or config.EMAIL_USERNAME
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(config.EMAIL_HOST, config.EMAIL_PORT, timeout=15) as server:
        if config.EMAIL_USE_TLS:
            server.starttls()
        if config.EMAIL_USERNAME:
            server.login(config.EMAIL_USERNAME, config.EMAIL_PASSWORD)
        server.sendmail(msg["From"], to_addrs, msg.as_string())
