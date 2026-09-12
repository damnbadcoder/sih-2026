import re
from typing import Tuple, List
from .types import SensitiveDataFlag

# Comprehensive regex patterns for sensitive data
PATTERNS = [
    # 1. RFC 1918 Private IPs & local hostnames
    {
        "type": "Internal IP",
        "regex": r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|127\.\d{1,3}\.\d{1,3}\.\d{1,3})\b",
        "context": "RFC 1918 private address space"
    },
    # 2. Credentials, secrets & tokens
    {
        "type": "Credential/Secret",
        "regex": r"\b((?:password|passwd|pwd|secret|api[_-]?key|auth[_-]?token|bearer[_-]?token|rootkit[_-]?key)\s*[:=]\s*[\"']?[^\s\"',;]{4,}[\"']?)\b",
        "context": "Hardcoded credential or secret"
    },
    # 3. Classified Operational Markings
    {
        "type": "Classified Entity",
        "regex": r"\b(TOP\s+SECRET(?:\s*\/\/\s*[A-Z]+)?|SECRET\s*\/\/\s*NOFORN|RESTRICTED\s+OPERATION|INTERNAL\s+ONLY(?:\s*-\s*NOT\s+FOR\s+PUBLIC)?|OPERATION\s+SHADOWGATE\s+INTERNAL)\b",
        "context": "Classified handling caveat"
    },
    # 4. Internal Hostnames & database nodes
    {
        "type": "Internal Host",
        "regex": r"\b([a-zA-Z0-9_\-\.]+\.(?:internal|local|corp|intranet|lan)|core-db-prod-\d+|bank-hsm-\d+|dc-internal-auth)\b",
        "context": "Internal infrastructure hostname"
    },
    # 5. Internal PII & Employee IDs
    {
        "type": "Unredacted PII",
        "regex": r"\b([a-zA-Z0-9_.+-]+@(?:[a-zA-Z0-9-]+\.)?(?:internal|local|corp|ntro\.internal))\b|\b(EMP-[0-9]{4,8}|UID-[0-9]{4,8})\b",
        "context": "Internal email or employee identifier"
    },
    # 6. Offensive Exploit Payloads
    {
        "type": "Exploit Payload",
        "regex": r"(?:\\x[0-9a-fA-F]{2}){4,}|\b(?:curl|wget)\s+[^|\n]+(?:\|\s*(?:bash|sh))\b",
        "context": "Potential exploit payload or shell command"
    },
    # 7. Database connection strings
    {
        "type": "DB Connection String",
        "regex": r"(?:postgresql|mysql|mongodb|redis)://[^:\s]+:[^@\s]+@[^/\s]+",
        "context": "Database connection string with credentials"
    },
    # 8. AWS/GCP/Azure keys
    {
        "type": "Cloud API Key",
        "regex": r"\b(AKIA[0-9A-Z]{16}|ya29\.[0-9A-Za-z\-_]+|AIza[0-9A-Za-z\-_]{35})\b",
        "context": "Cloud provider API key"
    },
]

def scan_and_redact(text: str) -> Tuple[str, List[SensitiveDataFlag]]:
    """
    Scan text for sensitive data patterns and wrap matches in red HTML spans.
    Returns (redacted_text, list_of_flags).
    Avoids double-wrapping already-redacted content.
    Deduplicates flags by matched value.
    """
    if not text:
        return text, []
    
    flags: List[SensitiveDataFlag] = []
    seen_matches = set()  # Track unique matched values
    
    # Collect all matches first with their positions
    all_matches = []
    for pattern_info in PATTERNS:
        data_type = pattern_info["type"]
        pattern = pattern_info["regex"]
        context = pattern_info.get("context", "")
        
        for match in re.finditer(pattern, text, re.IGNORECASE):
            matched_text = match.group(0)
            start, end = match.span()
            # Skip if already wrapped in our sensitive marker
            if "[SENSITIVE:" in matched_text:
                continue
            # Check surrounding context in original text for existing wrapper
            surrounding = text[max(0, start-50):end+50]
            if 'style="color: red"' in surrounding or "[SENSITIVE:" in surrounding:
                continue
            # Deduplicate by matched text
            if matched_text in seen_matches:
                continue
            seen_matches.add(matched_text)
            all_matches.append((start, end, matched_text, data_type, context))
    
    # Sort by start position descending so we can replace from end to start
    # without messing up positions
    all_matches.sort(key=lambda x: x[0], reverse=True)
    
    redacted_text = text
    for start, end, matched_text, data_type, context in all_matches:
        flags.append(SensitiveDataFlag(
            match=matched_text, 
            type=data_type,
            location=context
        ))
        wrapper = f'<span style="color: red; font-weight: bold;">[SENSITIVE: {matched_text} ({data_type})]</span>'
        redacted_text = redacted_text[:start] + wrapper + redacted_text[end:]
    
    return redacted_text, flags