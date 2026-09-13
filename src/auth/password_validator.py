"""Password validation utilities.

This module exposes a single, side-effect free helper used to check the
strength of a candidate password.

Security notes
--------------
* The received password is **never** stored in a module attribute, cache or
  global structure.
* The received password is **never** written to a file, to a log, to the
  standard output/error streams nor included in exception messages.
* No credentials, secrets, tokens or keys are hard-coded in this module.
"""

from __future__ import annotations

__all__ = ["MIN_PASSWORD_LENGTH", "validate_password"]

#: Minimal amount of characters accepted by the policy.
MIN_PASSWORD_LENGTH: int = 8


def validate_password(password: str) -> bool:
    """Return ``True`` when ``password`` satisfies the minimum policy.

    The policy requires that the candidate password:

    * is a non-empty string,
    * contains at least :data:`MIN_PASSWORD_LENGTH` characters,
    * contains at least one letter, and
    * contains at least one digit.

    The function is intentionally pure and stateless: it keeps no reference to
    the supplied value and only returns a boolean verdict. The password is
    never logged, printed, persisted or embedded in any error message.

    Args:
        password: Candidate password supplied by the caller.

    Returns:
        ``True`` if the candidate complies with the policy, ``False`` otherwise.
    """
    if not isinstance(password, str):
        return False

    if len(password) < MIN_PASSWORD_LENGTH:
        return False

    has_letter = any(character.isalpha() for character in password)
    has_number = any(character.isdigit() for character in password)

    return has_letter and has_number
