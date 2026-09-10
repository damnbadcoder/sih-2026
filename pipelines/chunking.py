"""
Semantic Chunking and LLM Context Injection Formatter.
Prepares normalized markdown and metadata into high-fidelity LLM prompts and chunked representations.
"""

import re
from typing import List, Optional
from pipelines.schema import (
    ExtractedIOCs,
    ThreatIntelSummary,
    TableData,
    DocumentMetadata,
    SemanticChunk,
    LLMInjectionBundle,
)


def estimate_tokens(text: str) -> int:
    """Rough heuristic estimate of token count (~4 characters per token in English)."""
    return max(1, len(text) // 4)


class SemanticChunker:
    """Chunks Markdown text by headings and logical blocks without breaking tables or code blocks."""

    def __init__(self, max_chunk_tokens: int = 1200, overlap_tokens: int = 150):
        self.max_chunk_tokens = max_chunk_tokens
        self.overlap_tokens = overlap_tokens

    def chunk_markdown(self, markdown_text: str) -> List[SemanticChunk]:
        """
        Splits markdown into semantic sections respecting headers (#, ##, ###)
        and preserves integrity of code blocks and tables.
        """
        sections: List[Tuple[str, str]] = []  # (heading, content)
        lines = markdown_text.splitlines()
        
        current_heading = "Document Root"
        current_lines: List[str] = []

        for line in lines:
            # Check if heading line
            match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if match and not line.strip().startswith("```"):
                if current_lines:
                    sections.append((current_heading, "\n".join(current_lines).strip()))
                    current_lines = []
                current_heading = match.group(2).strip()
            current_lines.append(line)

        if current_lines:
            sections.append((current_heading, "\n".join(current_lines).strip()))

        chunks: List[SemanticChunk] = []
        chunk_counter = 1

        for heading, content in sections:
            if not content:
                continue

            est_tokens = estimate_tokens(content)
            if est_tokens <= self.max_chunk_tokens:
                chunks.append(SemanticChunk(
                    chunk_id=chunk_counter,
                    parent_section=heading,
                    text=content,
                    token_estimate=est_tokens,
                    char_length=len(content)
                ))
                chunk_counter += 1
            else:
                # Sub-chunk by paragraphs
                paragraphs = re.split(r"\n\s*\n", content)
                curr_sub: List[str] = []
                curr_tok = 0

                for p in paragraphs:
                    p_tok = estimate_tokens(p)
                    if curr_tok + p_tok > self.max_chunk_tokens and curr_sub:
                        block_text = "\n\n".join(curr_sub)
                        chunks.append(SemanticChunk(
                            chunk_id=chunk_counter,
                            parent_section=heading,
                            text=block_text,
                            token_estimate=estimate_tokens(block_text),
                            char_length=len(block_text)
                        ))
                        chunk_counter += 1
                        curr_sub = [p]
                        curr_tok = p_tok
                    else:
                        curr_sub.append(p)
                        curr_tok += p_tok

                if curr_sub:
                    block_text = "\n\n".join(curr_sub)
                    chunks.append(SemanticChunk(
                        chunk_id=chunk_counter,
                        parent_section=heading,
                        text=block_text,
                        token_estimate=estimate_tokens(block_text),
                        char_length=len(block_text)
                    ))
                    chunk_counter += 1

        return chunks


def build_llm_injection_bundle(
    metadata: DocumentMetadata,
    clean_markdown: str,
    iocs: ExtractedIOCs,
    tables: List[TableData],
    threat_intel: ThreatIntelSummary,
    chunker: Optional[SemanticChunker] = None
) -> LLMInjectionBundle:
    """
    Constructs an optimized injection bundle for the LLM Grounding and Agentic Pipeline.
    Injects pre-extracted deterministic anchors so LLM cannot drift on core facts.
    """
    if chunker is None:
        chunker = SemanticChunker()

    chunks = chunker.chunk_markdown(clean_markdown)

    # Build Grounding Anchor Header
    header_lines = [
        "================================================================================",
        "IMMUTABLE SOURCE TELEMETRY & GROUNDING ANCHOR (PRE-EXTRACTED ZERO-LOSS CONTEXT)",
        "================================================================================",
        f"SOURCE_DOCUMENT: {metadata.file_name} ({metadata.file_type.upper()})",
        f"DOCUMENT_SHA256: {metadata.sha256_checksum}",
        f"WORD_COUNT: {metadata.word_count} | ESTIMATED_TOKENS: {metadata.estimated_tokens}",
        ""
    ]

    if threat_intel.severity_keywords:
        header_lines.append(f"DETECTED_SEVERITY: {', '.join(threat_intel.severity_keywords)}")
    if threat_intel.cvss_scores:
        header_lines.append(f"CVSS_SCORES: {', '.join(str(s) for s in threat_intel.cvss_scores)}")
    if threat_intel.threat_actors:
        header_lines.append(f"IDENTIFIED_THREAT_ACTORS: {', '.join(threat_intel.threat_actors)}")
    if threat_intel.affected_systems:
        header_lines.append(f"AFFECTED_SYSTEMS: {', '.join(threat_intel.affected_systems)}")
    if threat_intel.timelines:
        header_lines.append(f"DETECTED_TIMELINES: {', '.join(threat_intel.timelines)}")

    header_lines.append("\n--- EXTRACTED DETERMINISTIC INDICATORS (IOCs) ---")
    header_lines.append(f"CVE_IDS: {', '.join(iocs.cves) if iocs.cves else 'None identified'}")
    header_lines.append(f"MITRE_ATTACK_TECHNIQUES: {', '.join(iocs.mitre_attack_ids) if iocs.mitre_attack_ids else 'None identified'}")
    header_lines.append(f"IPV4_INDICATORS: {', '.join(iocs.ipv4_addresses) if iocs.ipv4_addresses else 'None identified'}")
    header_lines.append(f"IPV6_INDICATORS: {', '.join(iocs.ipv6_addresses) if iocs.ipv6_addresses else 'None identified'}")
    header_lines.append(f"SHA256_HASHES: {', '.join(iocs.sha256_hashes) if iocs.sha256_hashes else 'None identified'}")
    header_lines.append(f"SHA1_HASHES: {', '.join(iocs.sha1_hashes) if iocs.sha1_hashes else 'None identified'}")
    header_lines.append(f"MD5_HASHES: {', '.join(iocs.md5_hashes) if iocs.md5_hashes else 'None identified'}")
    header_lines.append(f"DOMAINS: {', '.join(iocs.domains) if iocs.domains else 'None identified'}")
    header_lines.append(f"URLS: {', '.join(iocs.urls) if iocs.urls else 'None identified'}")

    if tables:
        header_lines.append(f"\n--- EXTRACTED TABLES ({len(tables)} table(s) parsed) ---")
        for tbl in tables:
            header_lines.append(f"[Table {tbl.table_index}] Headers: {', '.join(tbl.headers)} ({tbl.row_count} rows)")

    header_lines.append("================================================================================")
    grounding_header = "\n".join(header_lines)

    # Full prompt context with delimiters
    prompt_context = (
        f"{grounding_header}\n\n"
        f"### FULL NORMALIZED DOCUMENT BODY\n\n"
        f"```markdown\n{clean_markdown}\n```\n"
    )

    return LLMInjectionBundle(
        system_grounding_header=grounding_header,
        formatted_context_for_prompt=prompt_context,
        semantic_chunks=chunks
    )
