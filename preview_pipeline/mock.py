from typing import List, Dict, Any
from .types import (
    MultiPreviewResult, 
    PlatformPreview, 
    SensitiveDataFlag,
    OutputType,
    LinkedInPreviewContent,
    SocialThreadPreviewContent,
    AdvisoryPreviewContent,
    ExecSummaryPreviewContent,
    IncidentReportPreviewContent,
    PressReleasePreviewContent,
    SlideDeckPreviewContent,
    VideoScriptPreviewContent,
    PlaybookPreviewContent,
)

from .renderers import RENDERERS
from .proofchecker import scan_and_redact

MOCK_STRUCTURED = {
    OutputType.LINKEDIN_POST: LinkedInPreviewContent(
        hook="🚨 If your org runs BankShield middleware, you need to read this immediately.",
        threat_context="The ShadowGate Collective is actively exploiting CVE-2026-41822 (CVSS 9.1) in BankShield v8.x controllers, compromising 3,200+ nodes across 14 regional networks. Initial ingress via 10.14.2.1.",
        key_insights=[
            "Legacy rule-based detection misses multi-stage payloads — behavioral monitoring is now non-negotiable.",
            "Credential harvesting occurred within 6 minutes of initial access — zero-trust segmentation limited blast radius.",
            "Vendor patch available but 67% of regional nodes remain unpatched due to change-control bottlenecks.",
        ],
        actionable_takeaways=[
            "Immediately isolate all external BankShield management interfaces and block inbound on port 4433.",
            "Force global credential revocation and enforce phishing-resistant MFA on all controller consoles.",
            "Ingest ShadowGate IOCs into SIEM/EDR and deploy emergency vendor hotfix within 4 hours.",
        ],
        discussion_prompt="What's your current protocol for third-party middleware patch verification across remote assets?",
        hashtags=["#CyberSecurity", "#ThreatIntel", "#CISO", "#SecOps", "#InfoSec", "#DevSecOps"],
        citations_used=["[^src-1]", "[^src-2]"]
    ),
    OutputType.SOCIAL_THREAD: SocialThreadPreviewContent(
        hook_tweet="1/5 🚨 BREAKING: ShadowGate Collective exploiting CVE-2026-41822 (CVSS 9.1) in BankShield middleware. 3,200+ controllers compromised across 14 regions. Thread 🧵👇",
        exploit_tweet="2/5 ⚡ EXPLOIT CHAIN: Unauthenticated RCE via deserialization flaw → credential dump (T1003) → lateral movement via Remote Services (T1021). Ingress IP: 10.14.2.1 staging creds on internal switches.",
        ioc_tweet="3/5 🔍 KEY IOCs: CVE-2026-41822 | IP 10.14.2.1 (ingress/lateral) | Actor: ShadowGate Collective | Target: BankShield v8.x controllers. Check SIEM for anomalous egress from controller subnets NOW.",
        mitigation_tweet="4/5 🛡️ MITIGATE NOW: 1️⃣ Isolate controller mgmt ports 2️⃣ Rotate ALL admin creds + enforce FIDO2 MFA 3️⃣ Deploy vendor hotfix + monitor for anomalous process exec on endpoints.",
        wrapup_tweet="5/5 🔗 Full advisory + IOCs + SIEM rules submitted to CERT. Retweet to warn peers 🔁 Bookmark for SecOps runbook 🔖 #CyberSecurity #ThreatIntel #ZeroDay",
        all_tweets=[
            "1/5 🚨 BREAKING: ShadowGate Collective exploiting CVE-2026-41822 (CVSS 9.1) in BankShield middleware. 3,200+ controllers compromised across 14 regions. Thread 🧵👇",
            "2/5 ⚡ EXPLOIT CHAIN: Unauthenticated RCE via deserialization flaw → credential dump (T1003) → lateral movement via Remote Services (T1021). Ingress IP: 10.14.2.1 staging creds on internal switches.",
            "3/5 🔍 KEY IOCs: CVE-2026-41822 | IP 10.14.2.1 (ingress/lateral) | Actor: ShadowGate Collective | Target: BankShield v8.x controllers. Check SIEM for anomalous egress from controller subnets NOW.",
            "4/5 🛡️ MITIGATE NOW: 1️⃣ Isolate controller mgmt ports 2️⃣ Rotate ALL admin creds + enforce FIDO2 MFA 3️⃣ Deploy vendor hotfix + monitor for anomalous process exec on endpoints.",
            "5/5 🔗 Full advisory + IOCs + SIEM rules submitted to CERT. Retweet to warn peers 🔁 Bookmark for SecOps runbook 🔖 #CyberSecurity #ThreatIntel #ZeroDay",
        ],
        citations_used=["[^src-1]", "[^src-2]"]
    ),
    OutputType.ADVISORY: AdvisoryPreviewContent(
        tl_protocol="TLP:AMBER+STRICT",
        severity="CRITICAL",
        cvss_score=9.1,
        cve_ids=["CVE-2026-41822"],
        threat_actor="ShadowGate Collective",
        affected_systems=["BankShield middleware v8.x", "BankShield Controller OS v8.0-8.4"],
        executive_summary="Active exploitation of CVE-2026-41822 by ShadowGate Collective has compromised 3,200+ BankShield controllers across 14 regional networks. Credential harvesting and lateral movement confirmed. Immediate isolation and patching required.",
        technical_analysis="Attackers exploited unauthenticated deserialization (CVE-2026-41822) in BankShield ingestion endpoint for initial access (T1190). Post-exploitation: OS credential dumping via LSASS (T1003.001), lateral movement through SMB/WinRM (T1021.002/T1021.006), and C2 beaconing over HTTPS. No persistence on database layer detected.",
        iocs=[
            {"type": "CVE", "indicator": "CVE-2026-41822", "context": "Root exploit vector - unauthenticated RCE", "action": "patch"},
            {"type": "IPv4", "indicator": "10.14.2.1", "context": "Ingress & lateral staging node", "action": "block"},
            {"type": "Domain", "indicator": "telemetry-sync-auth.net", "context": "C2 exfiltration endpoint", "action": "block"},
            {"type": "SHA-256", "indicator": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "context": "Stager binary hash", "action": "monitor"},
            {"type": "Actor", "indicator": "ShadowGate Collective", "context": "Primary campaign attribution", "action": "hunt"},
        ],
        mitigations=[
            "IMMEDIATE: Network isolation of all BankShield controller nodes; block inbound 10.14.2.1 at perimeter.",
            "IMMEDIATE: Global credential revocation + session termination for all admin accounts; enforce FIDO2 MFA.",
            "URGENT: Deploy vendor hotfix for CVE-2026-41822 across all regional clusters within 4 hours.",
            "SHORT-TERM: Update SIEM correlation rules for anomalous egress from controller subnets; enable 14-day forensic logging.",
            "STRATEGIC: Implement zero-trust segmentation for all third-party middleware; mandate patch SLAs in vendor contracts.",
        ],
        cert_reporting="Report confirmed indicators to National CERT: incident-response@cert-in.org.in",
        citations_used=["[^src-1]", "[^src-2]", "[^src-3]"]
    ),
    OutputType.EXEC_SUMMARY: ExecSummaryPreviewContent(
        bluf="ShadowGate Collective exploited CVE-2026-41822 in BankShield middleware, compromising 3,200+ controllers across 14 regions; SOC contained perimeter ingress, zero lateral expansion to core transaction pipelines.",
        situation="BankShield middleware v8.x controllers across regional networks exposed via unpatched deserialization vulnerability (CVE-2026-41822, CVSS 9.1). Threat actor ShadowGate Collective achieved initial access via 10.14.2.1.",
        complication="Operational exposure: perimeter switches quarantined to prevent systemic outage; core pipelines online under heightened monitoring. Regulatory: 6-hour mandatory disclosure initiated per central banking/CERT guidelines. Brand/legal: no customer deposit tampering detected.",
        solution="Network isolation applied to affected endpoints; global admin credentials rotated + MFA enforced; digital forensics team deployed for host telemetry preservation; vendor hotfix deployment in progress.",
        strategic_recommendations=[
            "Approve emergency vendor remediation budget for expedited patching + independent code audit.",
            "Authorize coordinated public disclosure holding statement with legal/cyber counsel.",
            "Mandate zero-trust segmentation for all third-party middleware in procurement policy.",
            "Invest in autonomous EDR rollout to reduce dwell time by 60% across controller fleet.",
        ],
        citations_used=["[^src-1]", "[^src-2]"]
    ),
    OutputType.INCIDENT_REPORT: IncidentReportPreviewContent(
        incident_id="INC-2026-9812",
        status="CONTAINED",
        severity="Tier 1 High",
        timeline=[
            {"time": "08:14:22", "event": "Initial anomalous ingress traffic flagged from foreign subnet 10.14.2.1"},
            {"time": "08:21:05", "event": "Privilege escalation alert triggered exploiting CVE-2026-41822 on core switches"},
            {"time": "08:35:00", "event": "SOC initiated perimeter containment and IP blocklist push"},
            {"time": "09:10:14", "event": "Host isolation completed; zero persistence mechanisms found on database layer"},
        ],
        root_cause="CVE-2026-41822 deserialization flaw in BankShield v8.x ingestion endpoint allowed unauthenticated RCE. Attackers dumped admin credentials via LSASS and moved laterally via SMB.",
        blast_radius=[
            "3,200+ BankShield controllers across 14 regional networks",
            "Administrative credentials for controller management consoles",
            "Internal switch management interfaces (no database layer persistence)",
        ],
        corrective_actions=[
            {"action": "Ingress point isolated and firewall blocklists enforced", "status": "complete", "owner": "NetSec"},
            {"action": "Administrative credentials revoked and rotated", "status": "complete", "owner": "IAM"},
            {"action": "14-day continuous telemetry logging activated", "status": "complete", "owner": "SOC"},
            {"action": "Vendor hotfix deployment across regional clusters", "status": "in-progress", "owner": "Infra"},
        ],
        citations_used=["[^src-1]", "[^src-2]"]
    ),
    OutputType.PRESS_RELEASE: PressReleasePreviewContent(
        dateline="NEW DELHI — October 12, 2026",
        headline="National Cyber Agency Confirms Proactive Containment of Banking Infrastructure Security Event",
        customer_impact="Consumer accounts and customer data repositories remain secure and uncompromised. No evidence of deposit tampering or balance alteration.",
        proactive_measures=[
            "Security patches and firewall blocklists deployed across all affected regional nodes within 2 hours of detection.",
            "Automated defensive protocols neutralized unauthorized ingress from external endpoints.",
            "Continuous telemetry monitoring maintained in coordination with national cyber defense agencies.",
            "Full IOC set and SIEM detection rules shared with CERT coordination bodies.",
        ],
        user_guidance=[
            "Ensure multi-factor authentication remains active on all banking portals.",
            "Report suspicious account activity to your bank's official fraud helpline.",
            "Keep banking apps updated to latest versions.",
        ],
        media_contact="press-office@cert-in.org.in | +91-11-XXXX-XXXX",
        citations_used=["[^src-1]"]
    ),
    OutputType.SLIDE_DECK: SlideDeckPreviewContent(
        slides=[
            {"title": "Executive Overview", "type": "TITLE_SLIDE", "key_points": ["Incident Briefing & Threat Defense Strategy", "ShadowGate Collective | CVE-2026-41822 | BankShield Middleware", "Rapid containment confirmed — zero core pipeline impact"], "speaker_notes": "Welcome stakeholders; set reassuring tone highlighting rapid containment."},
            {"title": "Anatomy of the Exploit", "type": "TWO_COLUMN", "key_points": ["LEFT: Technical payload & CVE-2026-41822 deserialization chain", "RIGHT: MITRE ATT&CK — T1190, T1003, T1021, T1071", "Perimeter bypass telemetry & credential staging evidence"], "speaker_notes": "Walk through attack progression left-to-right; emphasize MITRE mapping."},
            {"title": "Remediation Timeline & Hardening", "type": "TIMELINE", "key_points": ["Phase 1 (0-4hrs): Isolation, credential rotation, blocklists", "Phase 2 (4-24hrs): Vendor hotfix deployment, forensic imaging", "Phase 3 (24-72hrs): Zero-trust segmentation, detection rule updates", "Phase 4 (7d): Post-incident review, vendor SLA renegotiation"], "speaker_notes": "Present budget/timeline estimates; highlight Phase 1 complete."},
            {"title": "Strategic Recommendations", "type": "CONCLUSION", "key_points": ["Autonomous EDR rollout — reduce dwell time 60%", "Zero-trust middleware segmentation — procurement mandate", "Vendor patch SLAs in contracts — legal enforcement", "Board-level cyber risk quantification — quarterly review"], "speaker_notes": "Request executive sign-off on 3 budget items."},
        ],
        citations_used=["[^src-1]", "[^src-2]"]
    ),
    OutputType.VIDEO_SCRIPT: VideoScriptPreviewContent(
        runtime_seconds=90,
        scenes=[
            {"scene": "Scene 1 (0:00 - 0:15): Threat Alert Hook", "visual": "Global threat map animation with flashing alert nodes over 14 regional networks", "narrator": "Security telemetry has detected an active campaign targeting enterprise banking infrastructure. ShadowGate Collective is exploiting a critical vulnerability right now. Here is your situational briefing."},
            {"scene": "Scene 2 (0:15 - 0:45): Technical Breakdown", "visual": "Exploit sequence animation: deserialization RCE → credential dump → lateral movement via SMB", "narrator": "Attackers weaponized CVE-2026-41822, an unauthenticated deserialization flaw in BankShield middleware. They achieved remote code execution, dumped administrative credentials, and moved laterally across 3,200 controllers in 14 regions."},
            {"scene": "Scene 3 (0:45 - 1:15): Defense Directives", "visual": "Three bold checkmarks: Isolate Controllers | Rotate Credentials + MFA | Deploy Hotfix & Monitor", "narrator": "Your immediate priorities: First, isolate all BankShield management interfaces and block the ingress IP. Second, revoke every administrative credential and enforce phishing-resistant MFA. Third, deploy the emergency vendor patch and ingest IOCs into your SIEM."},
            {"scene": "Scene 4 (1:15 - 1:30): Conclusion & Resources", "visual": "Transmute Intelligence logo, security portal URL, CERT contact, QR code", "narrator": "Full indicators of compromise, SIEM rules, and remediation scripts are available at the link below. Report confirmed activity to your national CERT. Stay vigilant."},
        ],
        citations_used=["[^src-1]", "[^src-2]"]
    ),
    OutputType.PLAYBOOK: PlaybookPreviewContent(
        playbook_code="PB-SEC-09",
        stages=[
            {"stage": 1, "title": "Identification & Verification", "steps": ["Query SIEM/EDR for CVE-2026-41822 exploitation signatures", "Cross-reference source IP 10.14.2.1 against threat intel feeds", "Identify all hosts with outbound sessions to telemetry-sync-auth.net in past 48h", "Validate BankShield controller version inventory across regions"], "commands": ["grep -r 'CVE-2026-41822' /var/log/siem/", "ioc-check --ip 10.14.2.1 --feed all", "netflow-query --dst-ip 10.14.2.1 --since 48h"]},
            {"stage": 2, "title": "Immediate Containment", "steps": ["Apply VLAN quarantine rule QUARANTINE_TIER_1 to affected controller VMs", "Inject perimeter firewall block for 10.14.2.1 and telemetry-sync-auth.net", "Terminate all active OAuth/JWT sessions for BankShield management consoles", "Disable external access to controller management ports (4433, 8443)"], "commands": ["iptables -A INPUT -s 10.14.2.1 -j DROP", "iptables -A OUTPUT -d 10.14.2.1 -j DROP", "firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=10.14.2.1 drop'", "kubectl label nodes bankshield-controller quarantine=true"]},
            {"stage": 3, "title": "Eradication & Recovery", "steps": ["Re-image compromised nodes using golden baseline templates v8.4.1+", "Rotate all API keys, service principals, and database credentials", "Validate integrity using hash baseline: sha256sum -c /etc/security/baseline_hashes.sha256", "Deploy vendor hotfix for CVE-2026-41822 across all regional clusters"], "commands": ["ansible-playbook reimage-controllers.yml --extra-vars 'version=8.4.1'", "vault rotate --path secret/bankshield/*", "sha256sum -c /etc/security/baseline_hashes.sha256", "yum update -y bankshield-middleware-8.4.1"]},
            {"stage": 4, "title": "Post-Incident Auditing", "steps": ["Compile timeline report within 48 hours for CERT submission", "Update internal detection signatures for ShadowGate TTPs", "Review dwell time metrics and logging gaps across controller fleet", "Renegotiate vendor patch SLA contracts with mandatory 24hr critical patch window"], "commands": ["dfir-timeline --incident INC-2026-9812 --output report.pdf", "sigma-rule-gen --actor ShadowGate --output rules/", "log-audit --fleet bankshield --since 30d"]},
        ],
        citations_used=["[^src-1]", "[^src-2]", "[^src-3]"]
    ),
}

def get_mock_previews(content_md: str, selected_outputs: List[str], is_organization: bool) -> MultiPreviewResult:
    previews = {}
    
    for platform in selected_outputs:
        if platform not in MOCK_STRUCTURED:
            continue
            
        structured = MOCK_STRUCTURED[platform]
        renderer = RENDERERS.get(platform)
        draft_content = renderer(structured.model_dump()) if renderer else str(structured)
        citations = structured.citations_used
        
        flags = []
        if is_organization:
            draft_content, flags = scan_and_redact(draft_content)
        
        previews[platform] = PlatformPreview(
            platform_key=platform,
            display_name=platform.replace("_", " ").title(),
            draft_title=f"{platform.replace('_', ' ').title()} Preview",
            draft_content=draft_content,
            structured_content=structured,
            citations_used=citations,
            sensitive_flags=flags
        )
        
    return MultiPreviewResult(
        is_organization=is_organization,
        previews=previews,
        source_summary="Mock threat intelligence: ShadowGate Collective exploiting CVE-2026-41822 in BankShield middleware across 14 regional networks.",
        extracted_facts=[
            "ShadowGate Collective exploiting CVE-2026-41822 (CVSS 9.1)",
            "3,200+ BankShield controllers compromised across 14 regions",
            "Ingress IP 10.14.2.1 used for credential staging",
            "Admin credentials harvested via LSASS dump",
            "Lateral movement via SMB/WinRM",
            "Zero persistence on database layer",
            "Vendor hotfix available for CVE-2026-41822",
        ],
        metadata_anchors={
            "threat_actor": "ShadowGate Collective",
            "cve": "CVE-2026-41822",
            "cvss": 9.1,
            "target": "BankShield middleware v8.x",
            "ingress_ip": "10.14.2.1",
            "c2_domain": "telemetry-sync-auth.net",
        }
    )