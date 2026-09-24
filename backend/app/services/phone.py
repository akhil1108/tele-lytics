"""Phone-number normalisation.

Numbers arrive from three places — the dashboard, the handset's call log, and
the recording policy table — and they only match if they are stored one way.
Everything is normalised to E.164 on the way in.

This is deliberately a small, dependency-free normaliser rather than full
libphonenumber: it handles the shapes a dialler actually produces (spaces,
dashes, brackets, `00` prefixes, national numbers with a known country) and
refuses anything it cannot make sense of.
"""

from __future__ import annotations

import re

_NON_DIGITS = re.compile(r"[^\d+]")
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")

# National trunk prefixes stripped before applying a country code.
_TRUNK_PREFIXES = {"91": "0", "44": "0", "61": "0", "49": "0", "33": "0", "1": "1"}


class InvalidPhoneNumber(ValueError):
    pass


def normalize(raw: str, *, default_country_code: str = "91") -> str:
    """Return the number in E.164 form, e.g. `+919876543210`.

    Raises `InvalidPhoneNumber` if the input cannot be resolved.
    """
    if raw is None:
        raise InvalidPhoneNumber("empty number")

    cleaned = _NON_DIGITS.sub("", str(raw).strip())
    if not cleaned:
        raise InvalidPhoneNumber("empty number")

    # "+" is only meaningful in the leading position.
    if cleaned.startswith("+"):
        candidate = "+" + cleaned[1:].replace("+", "")
    else:
        digits = cleaned.replace("+", "")
        if digits.startswith("00"):
            candidate = "+" + digits[2:]
        else:
            cc = default_country_code.lstrip("+")
            trunk = _TRUNK_PREFIXES.get(cc)
            if trunk and digits.startswith(trunk) and len(digits) > len(trunk):
                digits = digits[len(trunk) :]
            candidate = digits if digits.startswith(cc) and _plausible(digits) else cc + digits
            candidate = "+" + candidate

    if not _E164.match(candidate):
        raise InvalidPhoneNumber(f"cannot normalise {raw!r} to E.164")
    return candidate


def _plausible(digits: str) -> bool:
    """Guard against double-prefixing a number that merely starts with the
    country code (e.g. Indian numbers beginning `91...`)."""
    return 10 <= len(digits) <= 15


def try_normalize(raw: str | None, *, default_country_code: str = "91") -> str | None:
    if raw is None:
        return None
    try:
        return normalize(raw, default_country_code=default_country_code)
    except InvalidPhoneNumber:
        return None


def mask(e164: str, *, visible: int = 4) -> str:
    """`+919876543210` -> `+91••••••3210`, for display where PII is restricted."""
    if len(e164) <= visible + 3:
        return e164
    head = e164[:3]
    tail = e164[-visible:]
    return f"{head}{'•' * (len(e164) - len(head) - visible)}{tail}"
