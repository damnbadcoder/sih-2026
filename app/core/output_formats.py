"""Canonical output-format vocabulary for the transformation domain.

The nine format IDs and labels are copied verbatim from the frontend's
``OUTPUT_TYPES`` array in ``frontend/src/lib/types.ts``. This is the single
backend representation of that vocabulary; frontend and backend must not
diverge.
"""

from enum import StrEnum


class OutputFormat(StrEnum):
    ADVISORY = "advisory"
    EXEC_SUMMARY = "exec_summary"
    INCIDENT_REPORT = "incident_report"
    SOCIAL_THREAD = "social_thread"
    LINKEDIN_POST = "linkedin_post"
    PRESS_RELEASE = "press_release"
    SLIDE_DECK = "slide_deck"
    VIDEO_SCRIPT = "video_script"
    PLAYBOOK = "playbook"


OUTPUT_FORMAT_LABELS: dict[OutputFormat, str] = {
    OutputFormat.ADVISORY: "Technical Advisory",
    OutputFormat.EXEC_SUMMARY: "Executive Brief",
    OutputFormat.INCIDENT_REPORT: "Incident Report",
    OutputFormat.SOCIAL_THREAD: "Social / X Thread",
    OutputFormat.LINKEDIN_POST: "LinkedIn Post",
    OutputFormat.PRESS_RELEASE: "Public Advisory",
    OutputFormat.SLIDE_DECK: "Slide Deck Outline",
    OutputFormat.VIDEO_SCRIPT: "Video Script",
    OutputFormat.PLAYBOOK: "Remediation Playbook",
}

OUTPUT_FORMAT_HINTS: dict[OutputFormat, str] = {
    OutputFormat.ADVISORY: (
        "Detailed technical bulletin with IOCs, CVEs, and MITRE ATT&CK mappings"
    ),
    OutputFormat.EXEC_SUMMARY: (
        "Minto Pyramid summary tailored for C-suite risk & decision-makers"
    ),
    OutputFormat.INCIDENT_REPORT: (
        "Timeline, root cause analysis, and impacted systems triage"
    ),
    OutputFormat.SOCIAL_THREAD: (
        "Thread breakdown optimized for character limits and high engagement"
    ),
    OutputFormat.LINKEDIN_POST: (
        "Structured post with key takeaways, insights, and hashtags"
    ),
    OutputFormat.PRESS_RELEASE: (
        "Clear, non-technical public statement and safety guidelines"
    ),
    OutputFormat.SLIDE_DECK: (
        "Structured presentation slides with bullet points and speaker notes"
    ),
    OutputFormat.VIDEO_SCRIPT: (
        "Scene-by-scene script with visual cues, narrator script, and timings"
    ),
    OutputFormat.PLAYBOOK: (
        "Step-by-step technical containment and recovery action plan"
    ),
}

OUTPUT_FORMAT_IDS: frozenset[str] = frozenset(fmt.value for fmt in OutputFormat)


def is_output_format(value: str) -> bool:
    return value in OUTPUT_FORMAT_IDS
