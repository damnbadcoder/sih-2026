"""
Deterministic Threat Intelligence and Forensic Artifact Extractor.
Extracts CVEs, MITRE IDs, Hashes, IPs, Domains, URLs, Wallets, Credentials,
Registry Keys, File Paths, and Telemetry with structural boundary checks.
"""

import re
import ipaddress
from typing import List, Dict, Any, Tuple
from pipelines.text_pipeline.schema import ExtractedIOCs, ThreatIntelSummary

# --- Deterministic Regex Registry ---
CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
MITRE_ATTACK_PATTERN = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)

# Hashes
SHA256_PATTERN = re.compile(r"\b[a-fA-F0-9]{64}\b")
SHA1_PATTERN = re.compile(r"\b[a-fA-F0-9]{40}\b")
MD5_PATTERN = re.compile(r"\b[a-fA-F0-9]{32}\b")

# Network Artifacts
IPV4_CANDIDATE_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6_CANDIDATE_PATTERN = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|"
    r"\b(?:[0-9a-fA-F]{1,4}:)*:[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4})*\b"
)
URL_PATTERN = re.compile(r"(?:https?|hxxps?|ftp)://[^\s<>'\"`]+", re.IGNORECASE)
DOMAIN_PATTERN = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\[\.\]|\(\.\)|\.))+"
    r"(?:com|net|org|edu|gov|mil|io|xyz|ru|cn|info|biz|top|cc|me|tk|in|uk|de)\b",
    re.IGNORECASE
)
EMAIL_PATTERN = re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b")

# Forensic Artifacts & Threat Telemetry
CRYPTO_BTC_PATTERN = re.compile(r"\b(?:bc1|[13])[a-zA-HJ-NP-Z0-9]{25,39}\b")
CRYPTO_ETH_PATTERN = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
CRYPTO_XMR_PATTERN = re.compile(r"\b4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b")
REGISTRY_KEY_PATTERN = re.compile(r"\b(?:HKLM|HKCU|HKCR|HKU|HKCC)\\[A-Za-z0-9_\\]+\b", re.IGNORECASE)
WINDOWS_PATH_PATTERN = re.compile(r"\b[a-zA-Z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)*[^\\/:*?\"<>|\r\n]+\b")
AWS_KEY_PATTERN = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")

# Threat Actor Landscape
THREAT_ACTOR_PATTERN = re.compile(
    r"\b(?:APT\s*[-_]?\d+|FIN\s*[-_]?\d+|TA\s*[-_]?\d+|UNC\s*[-_]?\d+|"
    r"Lazarus(?:\s+Group)?|Volt\s+Typhoon|Salt\s+Typhoon|Sandworm|Cozy\s+Bear|Fancy\s+Bear|"
    r"LockBit(?:\s*\d+\.\d+)?|BlackCat|ALPHV|Cl0p|Scattered\s+Spider|Midnight\s+Blizzard|"
    r"DarkSide|REvil|Conti|Wizard\s+Spider|MuddyWater|Phobos|Hive|Makop|Ragnar\s*Locker|Djvu(?:\/Stop)?)\b",
    re.IGNORECASE
)

SEVERITY_PATTERN = re.compile(r"\b(CRITICAL|HIGH|MEDIUM|LOW|INFORMATIONAL)\b", re.IGNORECASE)
CVSS_SCORE_PATTERN = re.compile(
    r"(?:CVSS(?:\s*v?\d(?:\.\d)?)?(?:\s*Base\s*Score)?|Base\s*Score|CVSS\s*Score)"
    r"[*_]*[:\s=]+[*_]*\s*([0-9]\.[0-9]|10\.0)\b|"
    r"\b(?:cvss\s+(?:v\d\s+)?score\s+of\s+)([0-9]\.[0-9]|10\.0)\b",
    re.IGNORECASE
)
TIMELINE_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?\b|"
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
    re.IGNORECASE
)
AFFECTED_SYSTEMS_PATTERN = re.compile(
    r"\b(?:Windows\s+Server(?:\s+\d{4})?|Windows\s+\d{1,2}|Linux\s+Kernel|Ubuntu|RHEL|Debian|"
    r"CentOS|macOS|iOS|Android|VMware\s+ESXi|Apache\s+(?:HTTP\s+Server|Tomcat|Struts)|"
    r"Nginx|Microsoft\s+Exchange(?:\s+Server)?|Active\s+Directory|OpenSSL|FortiOS|Palo\s+Alto\s+PAN-OS|"
    r"Cisco\s+IOS(?:\s+XE)?|Ivanti\s+(?:Connect\s+Secure|EPMM)|Confluence|Jira|SolarWinds|"
    r"Citrix(?:\s+(?:Application\s+Delivery\s+Controller|ADC|Gateway|NetScaler))?|"
    r"Zoho(?:\s+ManageEngine(?:\s+ADSelfService\s+Plus)?)?)\b",
    re.IGNORECASE
)


def refang(indicator: str) -> str:
    """Standardizes defanged strings into actionable network indicators."""
    clean = indicator.replace("[.]", ".").replace("(.)", ".")
    clean = clean.replace("hxxp://", "http://").replace("hxxps://", "https://")
    clean = clean.replace("[at]", "@").replace("(@)", "@")
    return clean


def is_valid_ipv4(ip_str: str) -> bool:
    """Validates IPv4 structure and removes non-routable false positives."""
    try:
        ip = ipaddress.IPv4Address(ip_str)
        if ip_str in {"0.0.0.0", "255.255.255.255"} or ip_str.startswith("127."):
            return False
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def is_valid_ipv6(ip_str: str) -> bool:
    try:
        ipaddress.IPv6Address(ip_str)
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def clean_url_or_domain(text: str) -> str:
    return text.rstrip(".,;:)'\"`]")


class IOCExtractor:
    """Comprehensive IOC and Forensic Telemetry Extraction Engine."""

    def __init__(self, ignored_domains: List[str] = None):
        # Known non-malicious vendor documentation and advisory repositories
        self.ignored_domains = set(ignored_domains or [
            "github.com", "schemas.openxmlformats.org", "w3.org",
            "microsoft.com", "google.com", "python.org", "pypi.org",
            "cert-in.org.in", "csk.gov.in", "nomoreransom.org", "docs.microsoft.com"
        ])

    def extract_iocs(self, text: str) -> ExtractedIOCs:
        """Extracts and sanitizes security indicators, dropping benign reference links."""
        cves = sorted(list(set(cve.upper() for cve in CVE_PATTERN.findall(text))))
        mitre_ids = sorted(list(set(m.upper() for m in MITRE_ATTACK_PATTERN.findall(text))))

        sha256_candidates = SHA256_PATTERN.findall(text)
        sha1_candidates = SHA1_PATTERN.findall(text)
        md5_candidates = MD5_PATTERN.findall(text)

        sha256_set = set(h.lower() for h in sha256_candidates)
        sha1_set = set(
            h.lower() for h in sha1_candidates
            if not any(h.lower() in s256 for s256 in sha256_set)
        )
        md5_set = set(
            h.lower() for h in md5_candidates
            if not any(h.lower() in s256 for s256 in sha256_set)
            and not any(h.lower() in s1 for s1 in sha1_set)
        )

        valid_ipv4 = sorted(list(set(ip for ip in IPV4_CANDIDATE_PATTERN.findall(text) if is_valid_ipv4(ip))))
        valid_ipv6 = sorted(list(set(ip for ip in IPV6_CANDIDATE_PATTERN.findall(text) if is_valid_ipv6(ip))))

        raw_urls = [clean_url_or_domain(refang(u)) for u in URL_PATTERN.findall(text)]
        urls = sorted(list(set(
            u for u in raw_urls
            if len(u) > 10 and not any(ign in u.lower() for ign in self.ignored_domains)
        )))

        raw_domains = [clean_url_or_domain(refang(d)).lower() for d in DOMAIN_PATTERN.findall(text)]
        domains = sorted(list(set(
            d for d in raw_domains
            if d not in self.ignored_domains
            and not any(d.endswith("." + ign) for ign in self.ignored_domains)
            and not d.endswith(".local")
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

    def extract_forensic_artifacts(self, text: str) -> Dict[str, List[str]]:
        """Extracts host forensic indicators, secrets, and financial extortion artifacts."""
        return {
            "emails": sorted(list(set(EMAIL_PATTERN.findall(text)))),
            "btc_wallets": sorted(list(set(CRYPTO_BTC_PATTERN.findall(text)))),
            "eth_wallets": sorted(list(set(CRYPTO_ETH_PATTERN.findall(text)))),
            "xmr_wallets": sorted(list(set(CRYPTO_XMR_PATTERN.findall(text)))),
            "registry_keys": sorted(list(set(REGISTRY_KEY_PATTERN.findall(text)))),
            "windows_paths": sorted(list(set(WINDOWS_PATH_PATTERN.findall(text)))),
            "aws_keys": sorted(list(set(AWS_KEY_PATTERN.findall(text))))
        }

    def extract_threat_summary(self, text: str, tables: List[Any] = None) -> ThreatIntelSummary:
        """Extracts actors, affected platforms, CVSS scores, and timelines."""
        actors = sorted(list(set(
            re.sub(r"\s+", " ", m.strip()) for m in THREAT_ACTOR_PATTERN.findall(text)
        )))

        systems = sorted(list(set(
            re.sub(r"\s+", " ", m.strip()) for m in AFFECTED_SYSTEMS_PATTERN.findall(text)
        )))

        severities = list(set(s.upper() for s in SEVERITY_PATTERN.findall(text)))
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