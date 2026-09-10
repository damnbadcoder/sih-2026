"""
Deterministic IOC and Threat Intelligence Extractor.
Extracts CVEs, IPs, Hashes, Domains, URLs, MITRE ATT&CK IDs, and Threat Telemetry
with zero loss pre-LLM injection.
"""

import re
import ipaddress
from typing import List, Dict, Any, Tuple
from pipelines.schema import ExtractedIOCs, ThreatIntelSummary


# --- Deterministic Regex Patterns ---
CVE_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
MITRE_ATTACK_PATTERN = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)

# Hashes: Strict boundary hex patterns
SHA256_PATTERN = re.compile(r"\b[a-fA-F0-9]{64}\b")
SHA1_PATTERN = re.compile(r"\b[a-fA-F0-9]{40}\b")
MD5_PATTERN = re.compile(r"\b[a-fA-F0-9]{32}\b")

# IPv4 with boundary check
IPV4_CANDIDATE_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# IPv6 candidate
IPV6_CANDIDATE_PATTERN = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|"
    r"\b(?:[0-9a-fA-F]{1,4}:)*:[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4})*\b"
)

# Defanged and standard URLs
URL_PATTERN = re.compile(
    r"(?:https?|hxxps?|ftp)://[^\s<>'\"`]+",
    re.IGNORECASE
)

# Defanged and standard Domains
DOMAIN_PATTERN = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\[\.\]|\(\.\)|\.))+"
    r"(?:com|net|org|edu|gov|mil|io|xyz|ru|cn|info|biz|top|cc|me|tk|in|uk|de)\b",
    re.IGNORECASE
)

# Common Threat Actor naming styles
THREAT_ACTOR_PATTERN = re.compile(
    r"\b(?:APT\s*[-_]?\d+|FIN\s*[-_]?\d+|TA\s*[-_]?\d+|UNC\s*[-_]?\d+|"
    r"Lazarus(?:\s+Group)?|Volt\s+Typhoon|Salt\s+Typhoon|Sandworm|Cozy\s+Bear|Fancy\s+Bear|"
    r"LockBit(?:\s*\d+\.\d+)?|BlackCat|ALPHV|Cl0p|Scattered\s+Spider|Midnight\s+Blizzard|"
    r"DarkSide|REvil|Conti|Wizard\s+Spider|MuddyWater)\b",
    re.IGNORECASE
)

# Severity rating patterns
SEVERITY_PATTERN = re.compile(
    r"\b(CRITICAL|HIGH|MEDIUM|LOW|INFORMATIONAL)\b",
    re.IGNORECASE
)

# CVSS Score pattern (e.g. CVSS:3.1/AV:N/... or **CVSS Base Score:** 9.8 or Base Score: 9.8)
CVSS_SCORE_PATTERN = re.compile(
    r"(?:CVSS(?:\s*v?\d(?:\.\d)?)?(?:\s*Base\s*Score)?|Base\s*Score|CVSS\s*Score)"
    r"[*_]*[:\s=]+[*_]*\s*([0-9]\.[0-9]|10\.0)\b|"
    r"\b(?:cvss\s+(?:v\d\s+)?score\s+of\s+)([0-9]\.[0-9]|10\.0)\b",
    re.IGNORECASE
)

# Timeline and Date patterns
TIMELINE_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?\b|"
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
    re.IGNORECASE
)

# Common systems / software indicators
AFFECTED_SYSTEMS_PATTERN = re.compile(
    r"\b(?:Windows\s+Server(?:\s+\d{4})?|Windows\s+\d{1,2}|Linux\s+Kernel|Ubuntu|RHEL|Debian|"
    r"CentOS|macOS|iOS|Android|VMware\s+ESXi|Apache\s+(?:HTTP\s+Server|Tomcat|Struts)|"
    r"Nginx|Microsoft\s+Exchange(?:\s+Server)?|Active\s+Directory|OpenSSL|FortiOS|Palo\s+Alto\s+PAN-OS|"
    r"Cisco\s+IOS(?:\s+XE)?|Ivanti\s+(?:Connect\s+Secure|EPMM)|Confluence|Jira|SolarWinds|Citrix\s+NetScaler)\b",
    re.IGNORECASE
)


def refang(indicator: str) -> str:
    """Normalize defanged indicators (e.g. hxxp -> http, [.] -> .)."""
    clean = indicator.replace("[.]", ".").replace("(.)", ".")
    clean = clean.replace("hxxp://", "http://").replace("hxxps://", "https://")
    clean = clean.replace("[at]", "@").replace("(@)", "@")
    return clean


def is_valid_ipv4(ip_str: str) -> bool:
    """Validate IPv4 address and exclude common false positives like version numbers."""
    try:
        ip = ipaddress.IPv4Address(ip_str)
        # Avoid treating 0.0.0.0 or broadcast as meaningful threat IOC
        if ip_str in {"0.0.0.0", "255.255.255.255"}:
            return False
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def is_valid_ipv6(ip_str: str) -> bool:
    """Validate IPv6 address."""
    try:
        ipaddress.IPv6Address(ip_str)
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def clean_url_or_domain(text: str) -> str:
    """Remove trailing punctuation often mistakenly captured from surrounding prose."""
    return text.rstrip(".,;:)'\"`]")


class IOCExtractor:
    """Deterministic cybersecurity indicator extraction engine."""

    def __init__(self, ignored_domains: List[str] = None):
        self.ignored_domains = set(ignored_domains or [
            "github.com", "schemas.openxmlformats.org", "w3.org",
            "microsoft.com", "google.com", "python.org", "pypi.org"
        ])

    def extract_iocs(self, text: str) -> ExtractedIOCs:
        """Extract all deterministic IOCs from input text with validation and deduplication."""
        # 1. CVEs
        cves = sorted(list(set(cve.upper() for cve in CVE_PATTERN.findall(text))))

        # 2. MITRE ATT&CK IDs
        mitre_ids = sorted(list(set(m.upper() for m in MITRE_ATTACK_PATTERN.findall(text))))

        # 3. Hashes
        sha256_candidates = SHA256_PATTERN.findall(text)
        sha1_candidates = SHA1_PATTERN.findall(text)
        md5_candidates = MD5_PATTERN.findall(text)

        sha256_set = set(h.lower() for h in sha256_candidates)
        # Filter out hashes from shorter lists if they are substrings of a longer hash
        sha1_set = set(
            h.lower() for h in sha1_candidates
            if not any(h.lower() in s256 for s256 in sha256_set)
        )
        md5_set = set(
            h.lower() for h in md5_candidates
            if not any(h.lower() in s256 for s256 in sha256_set)
            and not any(h.lower() in s1 for s1 in sha1_set)
        )

        # 4. IP Addresses
        raw_ips = IPV4_CANDIDATE_PATTERN.findall(text)
        valid_ipv4 = sorted(list(set(ip for ip in raw_ips if is_valid_ipv4(ip))))

        raw_ipv6 = IPV6_CANDIDATE_PATTERN.findall(text)
        valid_ipv6 = sorted(list(set(ip for ip in raw_ipv6 if is_valid_ipv6(ip))))

        # 5. URLs
        raw_urls = [clean_url_or_domain(refang(u)) for u in URL_PATTERN.findall(text)]
        urls = sorted(list(set(u for u in raw_urls if len(u) > 10)))

        # 6. Domains
        raw_domains = [clean_url_or_domain(refang(d)).lower() for d in DOMAIN_PATTERN.findall(text)]
        domains = sorted(list(set(
            d for d in raw_domains
            if d not in self.ignored_domains and not d.endswith(".local") and not d.startswith("127.")
        )))

        total = (
            len(cves) + len(mitre_ids) + len(sha256_set) + len(sha1_set) +
            len(md5_set) + len(valid_ipv4) + len(valid_ipv6) + len(urls) + len(domains)
        )

        return ExtractedIOCs(
            cves=cves,
            ipv4_addresses=valid_ipv4,
            ipv6_addresses=valid_ipv6,
            sha256_hashes=sorted(list(sha256_set)),
            sha1_hashes=sorted(list(sha1_set)),
            md5_hashes=sorted(list(md5_set)),
            domains=domains,
            urls=urls,
            mitre_attack_ids=mitre_ids,
            total_iocs_found=total
        )

    def extract_threat_summary(self, text: str, tables: List[Any] = None) -> ThreatIntelSummary:
        """Extract threat context: actors, affected systems, severity, CVSS scores, and timelines."""
        actors = sorted(list(set(
            re.sub(r"\s+", " ", m.strip()) for m in THREAT_ACTOR_PATTERN.findall(text)
        )))

        systems = sorted(list(set(
            re.sub(r"\s+", " ", m.strip()) for m in AFFECTED_SYSTEMS_PATTERN.findall(text)
        )))

        severities = list(set(s.upper() for s in SEVERITY_PATTERN.findall(text)))
        # Order by standard priority
        severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"]
        ordered_severities = [s for s in severity_order if s in severities]

        raw_cvss = CVSS_SCORE_PATTERN.findall(text)
        cvss_scores: List[float] = []
        for match in raw_cvss:
            score_str = match[0] if match[0] else match[1]
            try:
                cvss_scores.append(float(score_str))
            except (ValueError, IndexError):
                continue

        # Extract CVSS from structured tables if present
        if tables:
            for tbl in tables:
                cvss_col_idx = None
                for idx, h in enumerate(getattr(tbl, "headers", [])):
                    if "cvss" in h.lower():
                        cvss_col_idx = idx
                        break
                if cvss_col_idx is not None:
                    for row in getattr(tbl, "rows", []):
                        if cvss_col_idx < len(row):
                            val = row[cvss_col_idx].strip()
                            try:
                                cvss_scores.append(float(val))
                            except ValueError:
                                pass

        cvss_scores = sorted(list(set(cvss_scores)), reverse=True)

        timelines = sorted(list(set(
            re.sub(r"\s+", " ", t.strip()) for t in TIMELINE_PATTERN.findall(text)
        )))

        return ThreatIntelSummary(
            threat_actors=actors,
            affected_systems=systems,
            severity_keywords=ordered_severities,
            cvss_scores=cvss_scores,
            timelines=timelines
        )
