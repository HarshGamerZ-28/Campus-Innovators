from __future__ import annotations

import logging

from .config import settings

logger = logging.getLogger("campus_innovators.email")


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    """Send a password reset email.

    This is the single choke point for outbound email in the app — swapping in a
    real provider (Resend, SendGrid, SES, ...) later should only require changing
    the body of this function, not any of its callers.
    """
    if settings.email_provider == "console":
        logger.info("Password reset link for %s: %s", to_email, reset_link)
        return

    # Future providers (e.g. "resend", "smtp") would branch here. Fall back to
    # console logging for any unrecognized provider so the flow never silently
    # no-ops in an unconfigured environment.
    logger.warning(
        "EMAIL_PROVIDER=%s is not implemented yet; logging reset link instead.",
        settings.email_provider,
    )
    logger.info("Password reset link for %s: %s", to_email, reset_link)
