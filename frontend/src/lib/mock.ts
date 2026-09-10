import type {
  Citation,
  GenerationParams,
  OutputTypeId,
} from "./types";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function generatePlan(
  sourceText: string,
  fileNames: string[],
  links: string[],
  outputs: { id: OutputTypeId; params: GenerationParams }[]
): Promise<{ plan: string; citations: Citation[] }> {
  await sleep(600);

  const citations: Citation[] = [];
  let citIdx = 1;

  if (sourceText.trim()) {
    citations.push({
      id: `cit-${citIdx++}`,
      label: "Raw Telemetry & Advisory Input",
      kind: "text",
    });
  }

  for (const f of fileNames) {
    citations.push({
      id: `cit-${citIdx++}`,
      label: f,
      kind: "file",
    });
  }

  for (const l of links) {
    try {
      const url = new URL(l);
      citations.push({
        id: `cit-${citIdx++}`,
        label: url.hostname + url.pathname,
        kind: "link",
      });
    } catch {
      citations.push({
        id: `cit-${citIdx++}`,
        label: l,
        kind: "link",
      });
    }
  }

  const plan = `### Grounding Transformation Plan

**Context Analysis:**
- **Source Modalities:** ${fileNames.length ? `${fileNames.length} attached file(s), ` : ""}${links.length ? `${links.length} external intelligence link(s), ` : ""}direct narrative text (${sourceText.trim().length} chars).
- **Target Deliverables:** ${outputs.map((o) => o.id).join(", ")}

**Execution Directives:**
1. **Fact Locking:** Canonical anchor extracted for threat actors, CVEs, IOCs, and timelines to prevent multi-agent hallucination.
2. **Audience Alignment:** Enforcing tone (${outputs[0]?.params.tone || "Authoritative"}) and detail level (${outputs[0]?.params.detail || "Standard"}).
3. **Citation Tagging:** Every technical claim will reference verified source entities.

*Feel free to edit this blueprint before proceeding with generation.*`;

  return { plan, citations };
}

export async function generateDeliverable(
  id: OutputTypeId,
  sourceText: string,
  params: GenerationParams
): Promise<string> {
  await sleep(700);

  const previewSnippet = sourceText.trim()
    ? sourceText.trim().slice(0, 150) + "..."
    : "Critical system event analysis";
  const dateStr = new Date().toISOString().split("T")[0];

  switch (id) {
    case "advisory":
      return `# TECHNICAL THREAT ADVISORY: TA-2026-${Math.floor(1000 + Math.random() * 9000)}
**Published Date:** ${dateStr}  
**Severity:** CRITICAL (CVSS 9.8)  
**Target Audience:** ${params.targetAudience || "SOC Analysts, CERT Teams, CISO Staff"}  
**Language:** ${params.language}

---

## 1. Executive Summary
An ongoing cyber campaign has been detected exploiting vulnerabilities in perimeter infrastructure. Initial telemetry suggests zero-day vector chaining resulting in unauthorized privilege escalation.

> **Source Summary:**  
> ${previewSnippet}

## 2. Technical Analysis & Attack Vector
- **Initial Access:** Weaponized payloads bypassing web application firewalls.
- **Execution & Persistence:** Process hollowing and scheduled cron modification.
- **Lateral Movement:** Pass-the-hash techniques across internal subnets.

## 3. Indicators of Compromise (IOCs)
| Type | Indicator | Context / Notes |
| :--- | :--- | :--- |
| **SHA-256** | \`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\` | Stager binary |
| **IPv4** | \`198.51.100.42\` | C2 Infrastructure |
| **Domain** | \`telemetry-sync-auth[.]net\` | Exfiltration Endpoint |

## 4. Recommended Mitigations
1. **Immediate Quarantine:** Block inbound traffic from listed C2 IPs at firewall boundaries.
2. **Patching:** Apply vendor security updates immediately.
3. **Credential Invalidation:** Force global password resets for compromised administrator accounts.`;

    case "exec_summary":
      return `# Executive Brief: Cybersecurity Incident & Risk Assessment
**Date:** ${dateStr}  
**Classification:** STRICTLY CONFIDENTIAL  
**Prepared For:** Executive Board & C-Suite  

---

### Situation
A sophisticated attack campaign has targeted key digital infrastructure components. Our detection systems have quarantined the threat, preventing enterprise data compromise.

### Complication & Business Risk
- **Operational Exposure:** 3 critical internal services required temporary isolation for forensics.
- **Regulatory Impact:** Mandatory 72-hour notification threshold actively monitored.
- **Estimated Remediation Downtime:** Under 2 hours.

### Strategic Recommendations & ROI
1. **Approve Enhanced EDR Rollout:** Expedite autonomous endpoint detection to lower dwell time by 60%.
2. **Resource Allocation:** Empower the incident response team to perform deep forensic sweeps across secondary clusters.
3. **Customer Assurance:** Maintain transparent communication with key enterprise partners.`;

    case "incident_report":
      return `# Incident Triage & Forensic Report
**Incident ID:** INC-2026-9812  
**Status:** CONTAINED / UNDER TRIAGE  
**Severity Level:** Tier 1 High  

---

## Timeline of Events (UTC)
- **08:14:22** - Initial anomalous ingress traffic flagged from foreign subnet.
- **08:21:05** - Privilege escalation alert triggered on core API gateway.
- **08:35:00** - SOC initiated perimeter containment and IP blocklist push.
- **09:10:14** - Host isolation completed; zero persistence mechanisms found on database layer.

## Root Cause Analysis
The attack exploited an unpatched deserialization vulnerability in public-facing ingestion endpoints.

## Corrective Actions
- [x] Ingress point patched and recompiled
- [x] Network segmentation policy re-enforced
- [ ] 14-day continuous forensic logging activated`;

    case "social_thread":
      return `🧵 **1/5 THREAT ALERT: Critical Advisory Breakdown**

A high-severity exploitation campaign is targeting enterprise systems. Here is everything your security team needs to know in 60 seconds 👇

---

**2/5 🔍 The Attack Vector**
Threat actors are leveraging deserialization zero-days to achieve unauthenticated remote code execution. Perimeter logging shows active scanning in the wild.

---

**3/5 🛡️ Key Indicators (IOCs)**
- Block C2 IP: \`198.51.100.42\`
- Search for hashes matching stager binaries
- Review suspicious API gateway parent processes

---

**4/5 ⚡ Immediate Action Items**
1️⃣ Segment management interfaces  
2️⃣ Review external access audit logs  
3️⃣ Patch immediately upon vendor advisory availability  

---

**5/5 🔗 Stay Safe**
Full technical advisory and IOC hashes available via official channels. Retweet to inform the community. #CyberSecurity #ThreatIntel #InfoSec`;

    case "linkedin_post":
      return `🚨 **Critical Threat Intelligence Advisory: What Engineering & Security Leaders Need to Know**

Cybersecurity threat actors are actively exploiting unpatched gateway endpoints. Here is an actionable breakdown from our intelligence team:

**Key Takeaways:**
🔹 **Vulnerability Profile:** Remote Code Execution leading to privilege escalation.
🔹 **Threat Level:** Critical (Active scanning observed globally).
🔹 **Immediate Action Required:** Patch perimeter interfaces and verify authentication logs.

💡 **Why this matters for CISOs and IT Directors:**
Legacy rule-based detection often misses multi-stage payloads. Ensuring real-time behavioral monitoring and strict zero-trust segmentation is critical to minimize blast radius.

What proactive measures is your team taking today? Let’s discuss in the comments below.

#CyberSecurity #CISO #ThreatIntelligence #DevSecOps #RiskManagement`;

    case "press_release":
      return `# PUBLIC SECURITY ADVISORY & STATEMENT
**FOR IMMEDIATE RELEASE**  
**Date:** ${dateStr}  
**Contact:** media-security@transmute.intel  

---

### Statement on Recent Threat Landscape Findings

Transmute Security Labs has identified a sophisticated cybersecurity campaign impacting public internet infrastructure. Our team has collaborated with CERT authorities to provide defensive countermeasures.

**Summary for Customers and Partners:**
- **Customer Data Protection:** No direct compromise of customer data stores has occurred.
- **Defensive Measures:** Automated mitigations and security rules have been pushed to all protected networks.
- **Recommended User Steps:** Users and administrators should ensure multi-factor authentication (MFA) remains active across all company portals.

We remain committed to maintaining the highest security standards and open communication with the community.`;

    case "slide_deck":
      return `# Presentation Slide Outline: Threat Response & Strategy

---
### Slide 1: Executive Overview
- **Title:** Incident Briefing & Threat Defense Strategy
- **Key Points:**
  - Brief summary of detected threat vectors
  - Immediate defensive response posture
  - Business impact assessment: Minimal operational interruption
- *Speaker Note:* Welcome stakeholders; set reassuring tone highlighting rapid containment.

---
### Slide 2: Threat Landscape & Vector Analysis
- **Title:** Anatomy of the Exploit
- **Key Points:**
  - Initial entry point via public endpoints
  - Multi-stage payload evasion techniques
  - MITRE ATT&CK Matrix mapping (T1190, T1059)
- *Speaker Note:* Walk through attack progression diagram from left to right.

---
### Slide 3: Roadmap to Zero-Trust Hardening
- **Title:** Corrective Action & Next Steps
- **Key Points:**
  - Enhanced network micro-segmentation
  - Autonomous SOC monitoring upgrade
  - Comprehensive staff awareness refresh
- *Speaker Note:* Present budget and timeline estimates for recommended security tooling.`;

    case "video_script":
      return `# Video Narration Script: Cyber Threat Briefing

**Runtime:** 01:30  
**Tone:** ${params.tone}  
**Language:** ${params.language}  

---

**[SCENE 1: 00:00 - 00:15]**  
- **Visual Cue:** Dramatic dark cyber map visual with flashing alerts over global server nodes.  
- **Narrator (VO):** "Within the last 24 hours, security telemetry detected an active exploitation wave targeting enterprise infrastructure. Here is your situational briefing."

---

**[SCENE 2: 00:15 - 00:45]**  
- **Visual Cue:** Animated breakdown of the exploit payload bypassing firewalls and isolating endpoints.  
- **Narrator (VO):** "Attackers utilized chained vulnerabilities to attempt administrative takeover. However, automated detection mechanisms quarantined the affected subnets before lateral movement could occur."

---

**[SCENE 3: 00:45 - 01:15]**  
- **Visual Cue:** 3 bold checkmarks on screen with clear actionable mitigation steps.  
- **Narrator (VO):** "Your immediate priorities: block known malicious C2 IP addresses, inspect gateway authorization logs, and apply the latest emergency vendor patch."

---

**[SCENE 4: 01:15 - 01:30]**  
- **Visual Cue:** Transmute Intelligence logo, link to security portal, and support QR code.  
- **Narrator (VO):** "For full indicators of compromise and detailed remediation scripts, visit the link below. Stay vigilant."`;

    case "playbook":
      return `# Incident Response Remediation Playbook
**Playbook Code:** PB-SEC-09  
**Category:** Emergency Containment & Recovery  

---

## Stage 1: Identification & Verification
1. Verify alert telemetry from SIEM/EDR consoles.
2. Cross-reference source IP against threat intelligence feed (\`198.51.100.42\`).
3. Identify all hosts that initiated outbound sessions to the flagged domain within the past 48 hours.

## Stage 2: Immediate Containment
- **Network Isolation:** Apply VLAN quarantine rule \`QUARANTINE_TIER_1\` to affected virtual machines.
- **Firewall Rule Injection:**
  \`\`\`bash
  iptables -A INPUT -s 198.51.100.42 -j DROP
  iptables -A OUTPUT -d 198.51.100.42 -j DROP
  \`\`\`
- **Session Revocation:** Terminate all active OAuth and JWT sessions for impacted services.

## Stage 3: Eradication & Recovery
1. Re-image compromised nodes using golden baseline templates.
2. Rotate API keys and service principal credentials.
3. Validate integrity checks using hash baseline:
   \`\`\`bash
   sha256sum -c /etc/security/baseline_hashes.sha256
   \`\`\`

## Stage 4: Post-Incident Review
- Compile timeline report within 48 hours.
- Update internal detection signatures and firewall baseline.`;

    default:
      return `# Transmute Deliverable
**Type:** ${id}  
**Audience:** ${params.audienceCategory}  
**Tone:** ${params.tone}  

Generated analysis based on provided intelligence sources.`;
  }
}

export async function regenerateDeliverable(
  id: OutputTypeId,
  sourceText: string,
  params: GenerationParams,
  refinement: string
): Promise<string> {
  const base = await generateDeliverable(id, sourceText, params);
  return `${base}\n\n---\n*Updated with refinement directive: "${refinement}"*`;
}
