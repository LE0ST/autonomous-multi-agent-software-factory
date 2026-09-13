"""Secure password validator.

This module provides :func:`validate_password`, a small, dependency-free
helper that enforces minimal password strength requirements.

Security notes
--------------
* The password argument is treated as opaque: it is never written to disk,
  never logged, and never included in exception messages or other output.
* No credentials, secrets, tokens or keys are hardcoded in this module.
"""

from __future__ import annotations

MIN_LENGTH = 8


def validate_password(password: str) -> bool:
    """Return ``True`` when *password* satisfies the minimum policy.

    The policy requires that the password:

    * is a non-empty string,
    * has at least :data:`MIN_LENGTH` (8) characters,
    * contains at least one letter, and
    * contains at least one digit.

    The function never echoes, stores or otherwise exposes the supplied
    value; failures are reported solely through the boolean return value.

    Args:
        password: The candidate password to validate.

    Returns:
        ``True`` if the password meets the policy, ``False`` otherwise.
    """
    if not isinstance(password, str) or not password:
        return False

    if len(password) < MIN_LENGTH:
        return False

    has_letter = False
    has_digit = False

    for character in password:
        if not has_letter and character.isalpha():
            has_letter = True
        elif not has_digit and character.isdigit():
            has_digit = True

        if has_letter and has_digit:
            break

    return has_letter and has_digit
