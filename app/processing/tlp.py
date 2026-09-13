import re
from enum import Enum


class TLPLevel(str, Enum):
    RED = "TLP:RED"
    AMBER = "TLP:AMBER"
    GREEN = "TLP:GREEN"
    CLEAR = "TLP:CLEAR"


PATTERNS_RED = [
    re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|secret[_-]?key|password|passwd|auth[_-]?token)\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b"),
]

PATTERNS_AMBER = [
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
]


def classify_tlp(text: str | None) -> str:
    if not text:
        return TLPLevel.CLEAR.value

    for pattern in PATTERNS_RED:
        if pattern.search(text):
            return TLPLevel.RED.value

    for pattern in PATTERNS_AMBER:
        if pattern.search(text):
            return TLPLevel.AMBER.value

    return TLPLevel.CLEAR.value