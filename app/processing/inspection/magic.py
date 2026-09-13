SIGNATURES = {
    "pdf": [(0, b"%PDF")],
    "zip_docx": [(0, b"PK\x03\x04")],
    "ole": [(0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")],
    "png": [(0, b"\x89PNG\r\n\x1a\n")],
    "jpeg": [(0, b"\xff\xd8\xff")],
    "gif": [(0, b"GIF8")],
    "rtf": [(0, b"{\\rtf")],
    "evtx": [(0, b"ElfFile\x00")],
    "mp4": [(4, b"ftyp")],
    "wav": [(0, b"RIFF"), (8, b"WAVE")],
}

def detect_magic(header: bytes) -> str | None:
    if not header:
        return None
    for fmt, matches in SIGNATURES.items():
        if all(len(header) >= offset + len(sig) and header[offset:offset+len(sig)] == sig for offset, sig in matches):
            return fmt
    return None