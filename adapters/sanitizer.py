"""
adapters/sanitizer.py - Centralized secret sanitization and redaction utility.
Guarantees that sensitive credentials (GEMINI_API_KEY, DEEPSEEK_API_KEY, GLM_API_KEY)
and credential patterns in URLs/headers are redacted before being logged, persisted, or displayed.
"""

import os
import re
from typing import Any

REDACTED_REPLACEMENT = "[REDACTED_API_KEY]"

SECRET_ENV_KEYS = ("GEMINI_API_KEY", "DEEPSEEK_API_KEY", "GLM_API_KEY")

# Compiled regex patterns for defensive in-depth redaction:
# 1. Query parameters in URLs: ?key=... or &key=...
PATTERN_URL_KEY = re.compile(r"([?&]key=)[^&\s'\"`]+", re.IGNORECASE)
# 2. HTTP headers: x-goog-api-key: ... (with or without quotes)
PATTERN_HEADER_GOOG = re.compile(
    r"((?:['\"]?(?:x-goog-api-key|api-key)['\"]?)\s*[:=]\s*['\"]?)[^\s'\"`,]+",
    re.IGNORECASE
)
# 3. Authorization Bearer tokens: Bearer <token> (with or without quotes)
PATTERN_HEADER_AUTH = re.compile(
    r"((?:Authorization:\s*Bearer|Bearer)\s+['\"]?)[a-zA-Z0-9_\-\.]{12,}",
    re.IGNORECASE
)

def sanitize_secret_text(text: Any) -> str:
    """
    Redacts any configured or detected API keys and credentials from text.
    Handles strings, Exceptions, or arbitrary objects safely.
    """
    if text is None:
        return ""

    msg = str(text)
    if not msg:
        return ""

    # 1. Exact environment variable values replacement
    for env_name in SECRET_ENV_KEYS:
        val = os.environ.get(env_name)
        if val:
            val_clean = val.strip().strip("'\"")
            if len(val_clean) >= 4:
                msg = msg.replace(val_clean, REDACTED_REPLACEMENT)

    # 2. Defensive regex pattern redaction (URLs, headers, tokens)
    msg = PATTERN_URL_KEY.sub(r"\g<1>" + REDACTED_REPLACEMENT, msg)
    msg = PATTERN_HEADER_GOOG.sub(r"\g<1>" + REDACTED_REPLACEMENT, msg)
    msg = PATTERN_HEADER_AUTH.sub(r"\g<1>" + REDACTED_REPLACEMENT, msg)

    return msg
