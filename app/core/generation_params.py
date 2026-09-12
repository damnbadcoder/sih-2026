"""Canonical per-format generation parameter vocabularies.

These values mirror the frontend constants in
``frontend/src/lib/types.ts`` (``AUDIENCE_CATEGORIES``, ``TONES``,
``DETAIL_LEVELS``, ``OBJECTIVES``, ``LANGUAGES``). They are the allowed
values for per-output-format generation parameters.
"""

AUDIENCE_CATEGORY_IDS: frozenset[str] = frozenset(
    {"technical", "executive", "public", "regulatory", "internal"}
)

TONES: frozenset[str] = frozenset(
    {
        "Authoritative",
        "Urgent & Direct",
        "Executive & Concise",
        "Educational / Advisory",
        "Neutral & Factual",
    }
)

DETAIL_LEVELS: frozenset[str] = frozenset(
    {
        "Brief / TL;DR",
        "Standard Overview",
        "Comprehensive Analysis",
        "Deep Technical Breakdown",
    }
)

OBJECTIVES: frozenset[str] = frozenset(
    {
        "Threat Alert & Immediate Containment",
        "Executive Risk Assessment",
        "Incident Remediation & Recovery",
        "Public Safety & User Awareness",
        "Compliance & Regulatory Disclosure",
    }
)

LANGUAGES: frozenset[str] = frozenset(
    {"English", "Hindi", "Spanish", "French", "German", "Japanese"}
)
