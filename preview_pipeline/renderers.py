"""Renderers: Convert structured content to markdown for UI preview."""

def render_linkedin(c: dict) -> str:
    lines = [
        c.get("hook", ""),
        "",
        c.get("threat_context", ""),
        "",
        "## Key Insights",
    ]
    for insight in c.get("key_insights", []):
        lines.append(f"- {insight}")
    lines.extend([
        "",
        "## Actionable Takeaways",
    ])
    for i, takeaway in enumerate(c.get("actionable_takeaways", []), 1):
        lines.append(f"{i}. {takeaway}")
    lines.extend([
        "",
        "---",
        "",
        c.get("discussion_prompt", ""),
        "",
        " ".join(c.get("hashtags", [])),
    ])
    return "\n".join(lines)


def render_social_thread(c: dict) -> str:
    tweets = c.get("all_tweets", [])
    if not tweets:
        tweets = [
            c.get("hook_tweet", ""),
            c.get("exploit_tweet", ""),
            c.get("ioc_tweet", ""),
            c.get("mitigation_tweet", ""),
            c.get("wrapup_tweet", ""),
        ]
    return "\n---\n".join(tweets)


def render_advisory(c: dict) -> str:
    lines = [
        f"# TECHNICAL SECURITY ADVISORY",
        f"**TRAFFIC LIGHT PROTOCOL:** {c.get('tl_protocol', 'TLP:AMBER+STRICT')} | **SEVERITY:** {c.get('severity', 'CRITICAL')}",
    ]
    if c.get("cvss_score"):
        lines.append(f"**CVSS v3.1:** {c['cvss_score']}")
    if c.get("cve_ids"):
        lines.append(f"**CVE(s):** {', '.join(c['cve_ids'])}")
    if c.get("threat_actor"):
        lines.append(f"**THREAT ACTOR:** {c['threat_actor']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append(c.get("executive_summary", ""))
    lines.append("")
    lines.append("## Technical Analysis & Exploit Chain")
    lines.append(c.get("technical_analysis", ""))
    lines.append("")
    lines.append("## Indicators of Compromise (IOCs)")
    lines.append("| Type | Indicator | Context | Recommended Action |")
    lines.append("|------|-----------|---------|-------------------|")
    for ioc in c.get("iocs", []):
        lines.append(f"| {ioc.get('type','')} | `{ioc.get('indicator','')}` | {ioc.get('context','')} | {ioc.get('action','')} |")
    lines.append("")
    lines.append("## Prioritized Mitigations")
    for i, m in enumerate(c.get("mitigations", []), 1):
        lines.append(f"{i}. {m}")
    if c.get("cert_reporting"):
        lines.append("")
        lines.append("## Official Reporting")
        lines.append(c["cert_reporting"])
    return "\n".join(lines)


def render_exec_summary(c: dict) -> str:
    lines = [
        "# EXECUTIVE BRIEF: CYBERSECURITY INCIDENT & RISK ASSESSMENT",
        "**CLASSIFICATION:** STRICTLY CONFIDENTIAL // BOARD MATERIAL",
        "",
        "---",
        "",
        "### BLUF (Bottom Line Up Front)",
        c.get("bluf", ""),
        "",
        "### Situation",
        c.get("situation", ""),
        "",
        "### Complication & Business Risk",
        c.get("complication", ""),
        "",
        "### Solution & Containment Actions",
        c.get("solution", ""),
        "",
        "### Strategic Recommendations & Decisions Required",
    ]
    for i, rec in enumerate(c.get("strategic_recommendations", []), 1):
        lines.append(f"{i}. {rec}")
    return "\n".join(lines)


def render_incident_report(c: dict) -> str:
    lines = [
        f"# INCIDENT TRIAGE & FORENSIC REPORT: {c.get('incident_id', 'INC-2026-XXXX')}",
        f"**Status:** {c.get('status', 'CONTAINED')} | **Severity:** {c.get('severity', 'Tier 1 High')}",
        "",
        "---",
        "",
        "## Incident Timeline (UTC)",
    ]
    for entry in c.get("timeline", []):
        lines.append(f"- **{entry.get('time', '')}** — {entry.get('event', '')}")
    lines.extend([
        "",
        "## Root Cause Analysis",
        c.get("root_cause", ""),
        "",
        "## Blast Radius & Affected Systems",
    ])
    for item in c.get("blast_radius", []):
        lines.append(f"- {item}")
    lines.extend([
        "",
        "## Corrective Actions",
    ])
    for action in c.get("corrective_actions", []):
        status = action.get("status", "pending").upper()
        lines.append(f"- [{status}] {action.get('action', '')} (Owner: {action.get('owner', 'TBD')})")
    return "\n".join(lines)


def render_press_release(c: dict) -> str:
    lines = [
        "# PUBLIC SECURITY ADVISORY & STATEMENT",
        f"**FOR IMMEDIATE RELEASE**",
        f"**Dateline:** {c.get('dateline', 'UNKNOWN — DATE')}",
        "",
        "---",
        "",
        f"## {c.get('headline', 'Security Advisory')}",
        "",
        "### Customer Impact Statement",
        c.get("customer_impact", ""),
        "",
        "### Proactive Protections Applied",
    ]
    for m in c.get("proactive_measures", []):
        lines.append(f"- {m}")
    lines.extend([
        "",
        "### Safe Practices for Users",
    ])
    for g in c.get("user_guidance", []):
        lines.append(f"- {g}")
    lines.extend([
        "",
        "### Media Contact",
        c.get("media_contact", ""),
    ])
    return "\n".join(lines)


def render_slide_deck(c: dict) -> str:
    lines = ["# PRESENTATION SLIDE DECK: THREAT RESPONSE & STRATEGY", ""]
    for i, slide in enumerate(c.get("slides", []), 1):
        lines.append(f"## Slide {i}: {slide.get('title', f'Slide {i}')}")
        lines.append(f"**Type:** {slide.get('type', 'CONTENT')}")
        lines.append("")
        for point in slide.get("key_points", []):
            lines.append(f"- {point}")
        if slide.get("speaker_notes"):
            lines.append("")
            lines.append(f"*Speaker Notes:* {slide['speaker_notes']}")
        lines.append("")
    return "\n".join(lines)


def render_video_script(c: dict) -> str:
    lines = [
        f"# VIDEO NARRATION SCRIPT: CYBER THREAT BRIEFING",
        f"**Runtime:** {c.get('runtime_seconds', 90)} seconds",
        "",
        "---",
        ""
    ]
    for scene in c.get("scenes", []):
        lines.append(f"## {scene.get('scene', 'Scene')}")
        lines.append(f"**Visual:** {scene.get('visual', '')}")
        lines.append(f"**Narrator (VO):** {scene.get('narrator', '')}")
        lines.append("")
    return "\n".join(lines)


def render_playbook(c: dict) -> str:
    lines = [
        f"# REMEDIATION PLAYBOOK: {c.get('playbook_code', 'PB-SEC-XX')}",
        f"**Category:** Emergency Containment & Recovery",
        "",
        "---",
        ""
    ]
    for stage in c.get("stages", []):
        lines.append(f"## Stage {stage.get('stage', '')}: {stage.get('title', '')}")
        lines.append("")
        for step in stage.get("steps", []):
            lines.append(f"- {step}")
        if stage.get("commands"):
            lines.append("")
            lines.append("**Commands:**")
            for cmd in stage["commands"]:
                lines.append(f"```bash\n{cmd}\n```")
        lines.append("")
    return "\n".join(lines)


RENDERERS = {
    "linkedin_post": render_linkedin,
    "social_thread": render_social_thread,
    "advisory": render_advisory,
    "exec_summary": render_exec_summary,
    "incident_report": render_incident_report,
    "press_release": render_press_release,
    "slide_deck": render_slide_deck,
    "video_script": render_video_script,
    "playbook": render_playbook,
}