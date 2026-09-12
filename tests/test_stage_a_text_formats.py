import uuid
from collections.abc import AsyncIterator

import pytest

from app.core.formats import MEDIA_CATEGORY_UNKNOWN, classify_format
from app.core.uploads import ALLOWED_UPLOAD_TYPES, validate_upload_type
from app.models.input_file import InputFile
from app.processing.inspection import (
    InspectionError,
    InspectionResult,
    MarkupInspector,
    RTFInspector,
    SigmaInspector,
    TextInspector,
    get_inspector,
)
from app.storage.local import LocalStorage

# Formats that gain an inspector within Stage A (the product-enumerated
# text/markup set plus the already-supported core/plain/media formats).
STAGE_A_COVERED = frozenset(
    {
        ".pdf",
        ".docx",
        ".xlsx",
        ".txt",
        ".md",
        ".log",
        ".markdown",
        ".csv",
        ".tsv",
        ".syslog",
        ".yara",
        ".sigma",
        ".py",
        ".sh",
        ".ps1",
        ".rtf",
        ".xml",
        ".rss",
        ".atom",
        ".json",
        ".jsonl",
        ".stix",
        ".taxii",
        ".png",
        ".jpg",
        ".jpeg",
        ".mp3",
        ".mp4",
    }
)

# Formats that gain an inspector within Stage B (legacy office, extended
# image/audio/video, SVG as data, and Windows Event Log).
STAGE_B_COVERED = frozenset(
    {
        ".pptx",
        ".xls",
        ".webp",
        ".svg",
        ".tiff",
        ".tif",
        ".bmp",
        ".wav",
        ".m4a",
        ".ogg",
        ".flac",
        ".mkv",
        ".mov",
        ".avi",
        ".webm",
        ".evtx",
    }
)

# The last two formats close out the 46-format allowlist via Stage C (legacy
# Office binary extraction through headless LibreOffice).
STAGE_C_COVERED = frozenset({".doc", ".ppt"})

ALL_STAGES_COVERED = STAGE_A_COVERED | STAGE_B_COVERED | STAGE_C_COVERED


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path / "uploads")


def make_input_file(
    storage: LocalStorage, filename: str, content_type: str, data: bytes
) -> InputFile:
    return InputFile(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        original_filename=filename,
        stored_filename=f"stored_{filename}",
        content_type=content_type,
        file_size=len(data),
        storage_path=f"{uuid.uuid4()}/job/{filename}",
    )


async def _bytes_chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def write_via_storage(storage: LocalStorage, input_file: InputFile, data: bytes) -> None:
    await storage.save(
        _bytes_chunks(data), input_file.storage_path, max_size=len(data) + 1
    )


async def _extract(
    storage: LocalStorage,
    filename: str,
    content_type: str,
    data: bytes,
    inspector=None,
) -> InspectionResult:
    inspector = inspector or get_inspector(classify_format(filename, content_type))
    assert inspector is not None, filename
    input_file = make_input_file(storage, filename, content_type, data)
    await write_via_storage(storage, input_file, data)
    result = await inspector.inspect(input_file, storage)
    assert isinstance(result, InspectionResult)
    assert result.supported_for_inspection is True
    return result


# --- the 46-format contract: allowlist, classification, inspector coverage ---


def test_every_allowed_extension_classifies_without_contradiction():
    for ext, content_type in ALLOWED_UPLOAD_TYPES.items():
        classification = classify_format(f"sample{ext}", content_type)
        assert classification.media_category != MEDIA_CATEGORY_UNKNOWN, (ext, content_type)


def test_every_allowed_extension_resolves_an_inspector():
    for ext, content_type in ALLOWED_UPLOAD_TYPES.items():
        validate_upload_type(f"sample{ext}", content_type)
        inspector = get_inspector(classify_format(f"sample{ext}", content_type))
        assert inspector is not None, f"{ext} must be inspectable"
    assert set(ALLOWED_UPLOAD_TYPES) == ALL_STAGES_COVERED


# --- plain text family (extends existing .txt/.md coverage) -----------------


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        (
            "app.log",
            "text/plain",
            b"2026-01-01T10:00:00Z boot completed\n2026-01-01T10:01:00Z error full\n",
        ),
        ("notes.markdown", "text/markdown", b"# Title\n\nbody text\n"),
        (
            "syslog.txt",
            "text/plain",
            b"Jan  1 12:00:00 host sshd[1]: Accepted publickey for admin\n",
        ),
        ("rule.yara", "text/plain", b'rule Evil { strings: $a = "MZ" condition: $a }\n'),
        ("sample.py", "text/x-python", b"print('hello')\n"),
        ("deploy.sh", "text/x-sh", b"echo deploying\n"),
        ("script.ps1", "text/plain", b"Write-Host 'hello'\n"),
    ],
)
async def test_plain_text_family_extracts_raw_content(
    storage: LocalStorage, filename, content_type, content
):
    result = await _extract(storage, filename, content_type, content)
    assert result.extracted_text == content.decode("utf-8-sig")
    assert result.metadata["char_count"] == len(content)
    assert result.media_category == "text"


async def test_script_sources_are_never_executed(storage: LocalStorage):
    payload = b'__import__("os").system("echo pwned > /tmp/pwned_stage_a")\n'
    result = await _extract(storage, "evil.py", "text/x-python", payload)
    assert result.extracted_text == payload.decode("utf-8")
    # The payload reaches grounding strictly as inert text — extraction never
    # imports or executes the file's code.
    for name in ("__import__", "system"):
        assert name in result.extracted_text


# --- delimited text ----------------------------------------------------------


async def test_csv_rows_rendered_as_tab_separated_lines(storage: LocalStorage):
    result = await _extract(
        storage,
        "report.csv",
        "text/csv",
        b"id,name\n1,alice\n2,\nbob,charlie\n",
    )
    assert result.extracted_text == "id\tname\n1\talice\n2\nbob\tcharlie"
    assert result.metadata["format"] == "csv"
    assert result.metadata["row_count"] == 4


async def test_tsv_rows_rendered_without_blank_columns(storage: LocalStorage):
    result = await _extract(
        storage, "data.tsv", "text/tab-separated-values", b"a\tb\t\n\tc\n"
    )
    assert result.extracted_text == "a\tb\nc"
    assert result.metadata["format"] == "tsv"


async def test_empty_csv_yields_no_text(storage: LocalStorage):
    result = await _extract(storage, "empty.csv", "text/csv", b"")
    assert result.extracted_text is None
    assert result.metadata["format"] == "csv"


# --- JSON / JSONL ------------------------------------------------------------


async def test_json_flattened_deterministically(storage: LocalStorage):
    result = await _extract(
        storage,
        "bundle.json",
        "application/json",
        b'{"a":{"b":[1,true,null,"x"]},"c":"y"}',
    )
    assert result.extracted_text == "a.b[0]: 1\na.b[1]: true\na.b[2]: null\na.b[3]: x\nc: y"
    assert result.metadata["format"] == "json"


async def test_jsonlines_multiple_records(storage: LocalStorage):
    result = await _extract(
        storage,
        "events.jsonl",
        "application/json",
        b'{"ts":1,"ip":"10.0.0.1"}\n{"ts":2,"ip":"10.0.0.2"}\n',
    )
    assert result.metadata["format"] == "jsonl"
    assert result.metadata["line_count"] == 2
    assert "ip: 10.0.0.1" in result.extracted_text
    assert "ip: 10.0.0.2" in result.extracted_text


async def test_malformed_json_raises_controlled_inspection_error(storage: LocalStorage):
    with pytest.raises(InspectionError):
        await _extract(storage, "bad.json", "application/json", b"{not json")


async def test_malformed_jsonl_raises_controlled_inspection_error(storage: LocalStorage):
    with pytest.raises(InspectionError):
        await _extract(
            storage, "bad.jsonl", "application/json", b'{"ok":1}\n{broken\n'
        )


# --- XML family (XML / RSS / Atom / STIX / TAXII) ----------------------------


async def test_xml_extracts_element_text_without_entity_expansion(storage: LocalStorage):
    result = await _extract(
        storage,
        "doc.xml",
        "application/xml",
        b"<root><item>Alpha &amp; Beta</item><item>&lt;tag&gt;</item></root>",
    )
    assert "Alpha & Beta" in result.extracted_text
    assert "<tag>" in result.extracted_text
    assert result.metadata["root"] == "root"
    assert result.metadata["format"] == "xml"


async def test_rss_feed_extraction(storage: LocalStorage):
    result = await _extract(
        storage,
        "feed.rss",
        "application/rss+xml",
        b'<rss version="2.0"><channel><title>News wire</title>'
        b"<item><title>Breach reported</title></item></channel></rss>",
    )
    assert "News wire" in result.extracted_text
    assert "Breach reported" in result.extracted_text
    assert result.metadata["format"] == "rss"


async def test_atom_feed_extraction(storage: LocalStorage):
    result = await _extract(
        storage,
        "feed.atom",
        "application/atom+xml",
        b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Incident feed</title>'
        b"<entry><title>Malware detected</title></entry></feed>",
    )
    assert "Incident feed" in result.extracted_text
    assert "Malware detected" in result.extracted_text
    assert result.metadata["root"] == "feed"


async def test_stix_xml_variant(storage: LocalStorage):
    result = await _extract(
        storage,
        "bundle.stix",
        "text/xml",
        b'<stix:STIX_Package xmlns:stix="http://stix.mitre.org/stix-1">'
        b"<stix:Title>APT campaign</stix:Title>"
        b"</stix:STIX_Package>",
    )
    assert "APT campaign" in result.extracted_text
    assert result.metadata["root"] == "STIX_Package"
    assert result.metadata["format"] == "stix"


async def test_stix_json_variant_flatens(storage: LocalStorage):
    result = await _extract(
        storage,
        "bundle.stix",
        "application/json",
        b'{"type":"indicator","name":"badgateway","pattern":"[file:name = \'x\']"}',
    )
    assert "type: indicator" in result.extracted_text
    assert "pattern: [file:name = 'x']" in result.extracted_text
    assert result.metadata["encoding"] == "json"


async def test_taxii_xml_variant(storage: LocalStorage):
    result = await _extract(
        storage,
        "exchange.taxii",
        "application/xml",
        b'<taxii_11:TAXII_Messages '
        b'xmlns:taxii_11="http://taxii.mitre.org/message/taxii_xml_binding-1.1" '
        b'xmlns:stix="http://stix.mitre.org/stix-1">'
        b"<stix:Title>Alert Intel</stix:Title></taxii_11:TAXII_Messages>",
    )
    assert "Alert Intel" in result.extracted_text
    assert result.metadata["format"] == "taxii"


async def test_xxe_never_resolves_external_entities(storage: LocalStorage):
    payload = (
        b'<?xml version="1.0"?>'
        b"<!DOCTYPE r [<!ENTITY e SYSTEM \"file:///etc/passwd\">]>"
        b"<r>&e;</r>"
    )
    result = await _extract(storage, "evil.xml", "application/xml", payload)
    assert result.supported_for_inspection is True
    assert "&e;" in result.extracted_text
    assert "root:" not in result.extracted_text


async def test_billion_laughs_bomb_is_not_expanded(storage: LocalStorage):
    payload = (
        b'<?xml version="1.0"?>'
        b"<!DOCTYPE bomb [<!ENTITY a \"1234567890\">"
        b"<!ENTITY b \"&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;\">]>"
        b"<bomb>&b;&b;&b;&b;&b;</bomb>"
    )
    result = await _extract(storage, "bomb.xml", "application/xml", payload)
    assert result.supported_for_inspection is True
    assert len(result.extracted_text) < 200


async def test_malformed_xml_raises_controlled_inspection_error(storage: LocalStorage):
    with pytest.raises(InspectionError):
        await _extract(storage, "bad.xml", "application/xml", b"<root><unclosed>")


async def test_xml_declared_as_text_plain_still_routes_to_markup_inspector(
    storage: LocalStorage,
):
    result = await _extract(
        storage, "feed.xml", "text/plain", b"<r><e>routed by extension</e></r>"
    )
    assert result.extracted_text == "routed by extension"


# --- Sigma -------------------------------------------------------------------


async def test_sigma_rules_are_flattened_yaml_detection_data(storage: LocalStorage):
    result = await _extract(
        storage,
        "detect.sigma",
        "text/yaml",
        b"title: Suspicious Process\nlogsource:\n  category: process_creation\n"
        b"detection:\n  selection:\n    Image: '*cmd.exe'\n",
    )
    assert "title: Suspicious Process" in result.extracted_text
    assert "category: process_creation" in result.extracted_text
    assert result.metadata["format"] == "sigma"


async def test_sigma_safe_load_never_executes_tags(storage: LocalStorage):
    # safe_load rejects untrusted python tags with a controlled InspectionError
    # instead of ever constructing/executing the referenced callable.
    with pytest.raises(InspectionError):
        await _extract(
            storage,
            "evil.sigma",
            "text/yaml",
            b"title: T\nvalue: !!python/object/apply:os.system [echo pwned]\n",
        )


async def test_malformed_sigma_raises_controlled_inspection_error(storage: LocalStorage):
    with pytest.raises(InspectionError):
        await _extract(storage, "bad.sigma", "text/yaml", b"title: [unclosed")


# --- RTF ---------------------------------------------------------------------


async def test_rtf_control_words_stripped_to_plain_text(storage: LocalStorage):
    result = await _extract(
        storage,
        "letter.rtf",
        "application/rtf",
        b"{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Arial;}}\\f0 "
        b"Firewall alert on \\u104?ost: \\'e9vasion\\par end}",
    )
    assert result.extracted_text == "Firewall alert on host: évasion\nend"
    assert result.metadata["format"] == "rtf"


async def test_rtf_destinations_like_headers_are_skipped(storage: LocalStorage):
    result = await _extract(
        storage,
        "memo.rtf",
        "application/rtf",
        b"{\\rtf1\\ansi Body\\par{\\header Confidential header}tail}",
    )
    assert "Body" in result.extracted_text
    assert "tail" in result.extracted_text
    assert "Confidential header" not in result.extracted_text


async def test_rtf_missing_magic_is_rejected(storage: LocalStorage):
    inspector = RTFInspector()
    with pytest.raises(InspectionError):
        await _extract(
            storage,
            "fake.rtf",
            "application/rtf",
            b"{\\winword not rtf",
            inspector=inspector,
        )


# --- cross-format guarantees -------------------------------------------------


async def test_text_json_and_markup_inspectors_share_deterministic_contracts(
    storage: LocalStorage,
):
    for filename, content_type, data, inspector in [
        ("a.json", "application/json", b'{"x":1,"y":[1,2]}', TextInspector()),
        ("b.xml", "application/xml", b"<r><e>t</e></r>", MarkupInspector()),
        ("c.sigma", "text/yaml", b"title: T\ndetection:\n  x: y\n", SigmaInspector()),
    ]:
        result = await _extract(storage, filename, content_type, data, inspector=inspector)
        assert result.media_category == "text"