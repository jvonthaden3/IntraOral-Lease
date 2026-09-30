"""Sends the "email me these documents" message. Plain smtplib so it works
with any SMTP provider (Gmail app password, Office 365, Rackspace, SendGrid,
Mailgun, Postmark, ...) without adding a dependency.
"""

import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config


class MailerNotConfigured(Exception):
    pass


class MailerError(Exception):
    """A specific, user-facing reason sending failed (bad host/port, wrong
    login, server rejected the message, etc.) -- safe to show as-is."""
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
            f"or the hosting platform may be blocking outbound connections on this port. "
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
            server.sendmail(msg["From"], to_addrs, msg.as_string())
    except smtplib.SMTPException as e:
        raise MailerError(f"The email server rejected the message: {e}")
    except (socket.timeout, TimeoutError, OSError) as e:
        raise MailerError(
            f"Lost the connection to {config.EMAIL_HOST}:{config.EMAIL_PORT} while sending. "
            f"Detail: {e}"
        )
