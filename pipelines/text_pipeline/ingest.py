"""
Master Ingestion & Pre-LLM Normalization Pipeline.
Ingests heterogeneous incoming documents (PDF, DOCX, MD, TXT, LOG, CSV, JSON),
parses structural tables, extracts deterministic threat IOCs without data loss,
and prepares dual-payload outputs (Clean Markdown + Structured Metadata JSON)
ready for downstream LangGraph agents.
"""

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union
from dotenv import load_dotenv

# Automatically load environment variables from .env file
load_dotenv()

from pipelines.base import BasePipeline
from pipelines.text_pipeline.schema import (
    DocumentMetadata,
    ExtractedSourceContext,
    ExtractedIOCs,
    ThreatIntelSummary,
    EnrichedGroundingContext,
)
from pipelines.text_pipeline.extractors.pdf_parser import PDFParser
from pipelines.text_pipeline.extractors.docx_parser import DocxParser
from pipelines.text_pipeline.extractors.text_parser import TextParser
from pipelines.text_pipeline.extractors.ioc_extractor import IOCExtractor
from pipelines.text_pipeline.chunking import build_llm_injection_bundle, estimate_tokens
from pipelines.text_pipeline.interpreters.interpreter import GroqInterpreter, Interpreter


def calculate_sha256(file_path: str) -> str:
    """Computes SHA-256 checksum of an input file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()


class TextIngestionPipeline(BasePipeline):
    """Unified multi-format text ingestion and pre-LLM context preparation pipeline."""

    SUPPORTED_EXTENSIONS = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".md": "markdown",
        ".markdown": "markdown",
        ".txt": "text",
        ".log": "log",
        ".csv": "csv",
        ".tsv": "tsv",
        ".json": "json",
    }

    def __init__(self, output_dir: str = "ingestion_outputs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize component parsers
        self.pdf_parser = PDFParser()
        self.docx_parser = DocxParser()
        self.text_parser = TextParser()
        self.ioc_extractor = IOCExtractor()
        self.interpreter = GroqInterpreter()

    def process(
        self,
        file_input: Union[str, Path, bytes],
        filename: Optional[str] = None,
        output_dir: Optional[str] = None,
        save_outputs: bool = True,
        enrich: bool = False,
    ) -> Union[ExtractedSourceContext, Tuple[ExtractedSourceContext, EnrichedGroundingContext]]:
        """
        Polymorphic execution entry point satisfying the BasePipeline contract.
        Accepts a file path string, Path object, or raw in-memory bytes.
        """
        if isinstance(file_input, bytes):
            import tempfile
            fname = filename or "document.txt"
            suffix = Path(fname).suffix or ".txt"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(file_input)
                tmp_path = tmp.name
            try:
                if enrich:
                    raw_ctx, enriched = self.process_and_enrich(tmp_path, output_dir=output_dir, save_outputs=save_outputs)
                    if filename:
                        raw_ctx.metadata.file_name = filename
                    return raw_ctx, enriched
                raw_ctx = self.process_file(tmp_path, output_dir=output_dir, save_outputs=save_outputs)
                if filename:
                    raw_ctx.metadata.file_name = filename
                return raw_ctx
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
        else:
            if enrich:
                return self.process_and_enrich(str(file_input), output_dir=output_dir, save_outputs=save_outputs)
            return self.process_file(str(file_input), output_dir=output_dir, save_outputs=save_outputs)

    def process_file(
        self,
        file_path: str,
        output_dir: Optional[str] = None,
        save_outputs: bool = True
    ) -> ExtractedSourceContext:
        """
        Ingests and transforms an input file into a validated ExtractedSourceContext.

        Args:
            file_path: Path to target file.
            output_dir: Custom output directory for the generated .md and .json files.
            save_outputs: Whether to write normalized .md and metadata .json to disk.

        Returns:
            ExtractedSourceContext: Complete Pydantic contract object.
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Input file does not exist: {file_path}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file format '{ext}'. Supported formats: {list(self.SUPPORTED_EXTENSIONS.keys())}"
            )

        file_type = self.SUPPORTED_EXTENSIONS[ext]
        file_size = path.stat().st_size
        checksum = calculate_sha256(str(path))

        # 1. Parse File Content based on MIME/Extension
        if file_type == "pdf":
            clean_markdown, tables = self.pdf_parser.parse(str(path))
        elif file_type == "docx":
            clean_markdown, tables = self.docx_parser.parse(str(path))
        else:
            clean_markdown, tables = self.text_parser.parse(str(path))

        # 2. Extract Document Statistics
        word_count = len(clean_markdown.split())
        char_count = len(clean_markdown)
        line_count = len(clean_markdown.splitlines())
        tokens = estimate_tokens(clean_markdown)

        metadata = DocumentMetadata(
            file_name=path.name,
            file_path=str(path),
            file_type=file_type,
            file_size_bytes=file_size,
            sha256_checksum=checksum,
            word_count=word_count,
            character_count=char_count,
            estimated_tokens=tokens,
            line_count=line_count
        )

        # 3. Deterministic IOC & Threat Intel Extraction (Pre-LLM)
        iocs = self.ioc_extractor.extract_iocs(clean_markdown)
        threat_intel = self.ioc_extractor.extract_threat_summary(clean_markdown, tables=tables)

        # 4. Prepare LLM Injection Bundle & Grounding Headers
        llm_bundle = build_llm_injection_bundle(
            metadata=metadata,
            clean_markdown=clean_markdown,
            iocs=iocs,
            tables=tables,
            threat_intel=threat_intel
        )

        # 5. Assemble the ExtractedSourceContext Contract
        context_bundle = ExtractedSourceContext(
            metadata=metadata,
            clean_markdown=clean_markdown,
            iocs=iocs,
            tables=tables,
            threat_intel=threat_intel,
            llm_bundle=llm_bundle
        )

        # 6. Save Dual-Payload Output (Clean Markdown + Metadata JSON)
        if save_outputs:
            target_dir = Path(output_dir) if output_dir else self.output_dir
            target_dir.mkdir(parents=True, exist_ok=True)

            stem = path.stem
            md_out_path = target_dir / f"{stem}_normalized.md"
            json_out_path = target_dir / f"{stem}_metadata.json"

            # Write clean normalized Markdown
            with open(md_out_path, "w", encoding="utf-8") as f:
                f.write(clean_markdown)

            # Write structured JSON metadata
            with open(json_out_path, "w", encoding="utf-8") as f:
                json.dump(context_bundle.to_dict(), f, indent=2, ensure_ascii=False)

        return context_bundle

    def process_and_enrich(
        self,
        file_path: str,
        output_dir: Optional[str] = None,
        save_outputs: bool = True
    ) -> Tuple[ExtractedSourceContext, EnrichedGroundingContext]:
        """
        Runs both Ingestion (Phase 1) and Semantic Interpretation (Phase 2).
        Produces enriched Markdown + enriched JSON, and automatically cleans up
        temporary intermediate Phase 1 files.
        """
        target_dir = Path(output_dir) if output_dir else self.output_dir
        source_context = self.process_file(file_path, output_dir=str(target_dir), save_outputs=save_outputs)
        enriched_context = self.interpreter.interpret(
            source_context=source_context,
            output_dir=str(target_dir),
            save_outputs=save_outputs
        )

        # Remove temporary intermediate Phase 1 files once enriched outputs are ready
        if save_outputs:
            stem = Path(file_path).stem
            for temp_file in [target_dir / f"{stem}_normalized.md", target_dir / f"{stem}_metadata.json"]:
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except OSError:
                        pass

        return source_context, enriched_context

    def process_batch(
        self,
        file_paths: List[str],
        output_dir: Optional[str] = None,
        enrich: bool = False
    ) -> List[Tuple[ExtractedSourceContext, Optional[EnrichedGroundingContext]]]:
        """Batch processes a list of files."""
        results = []
        for fp in file_paths:
            if enrich:
                src, enr = self.process_and_enrich(fp, output_dir=output_dir, save_outputs=True)
                results.append((src, enr))
            else:
                src = self.process_file(fp, output_dir=output_dir, save_outputs=True)
                results.append((src, None))
        return results


def main():
    """Command-line interface for the ingestion and Qwen interpretation pipeline."""
    parser = argparse.ArgumentParser(
        description="Deterministic Text Ingestion & Semantic Interpretation Pipeline"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to an input file (.pdf, .docx, .md, .txt, .log, .csv, .json) or directory"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="ingestion_outputs",
        help="Directory to save the generated Markdown and JSON files (default: ingestion_outputs)"
    )
    parser.add_argument(
        "--enrich", "-e",
        action="store_true",
        help="Run Groq LLM interpreter to extract rich semantic grounding context (.md and .json)"
    )
    parser.add_argument(
        "--print-summary", "-s",
        action="store_true",
        help="Print summary of extracted IOCs, metadata, and grounding analysis to stdout"
    )

    args = parser.parse_args()
    pipeline = TextIngestionPipeline(output_dir=args.output_dir)

    target = Path(args.input)
    if not target.exists():
        print(f"Error: Path '{args.input}' does not exist.", file=sys.stderr)
        sys.exit(1)

    files_to_process = []
    if target.is_dir():
        for item in target.iterdir():
            if item.suffix.lower() in pipeline.SUPPORTED_EXTENSIONS:
                files_to_process.append(str(item))
        if not files_to_process:
            print(f"No supported files found in directory '{args.input}'.")
            sys.exit(0)
    else:
        files_to_process.append(str(target))

    print(f"[*] Processing {len(files_to_process)} file(s) (Enrichment: {'ENABLED' if args.enrich else 'DISABLED'})...")
    for fp in files_to_process:
        print(f" -> Processing: {fp}")
        stem = Path(fp).stem

        if args.enrich:
            context, enriched = pipeline.process_and_enrich(fp, output_dir=args.output_dir, save_outputs=True)
            print(f"    [+] Saved enriched Markdown:   {args.output_dir}/{stem}_enriched_context.md")
            print(f"    [+] Saved enriched JSON:       {args.output_dir}/{stem}_enriched_context.json")
            print(f"    [i] Cleaned up temporary Phase 1 intermediate files.")
        else:
            context = pipeline.process_file(fp, output_dir=args.output_dir, save_outputs=True)
            enriched = None
            print(f"    [+] Saved normalized Markdown: {args.output_dir}/{stem}_normalized.md")
            print(f"    [+] Saved metadata JSON:       {args.output_dir}/{stem}_metadata.json")

        if args.print_summary:
            print("\n" + "=" * 65)
            print(f"INGESTION SUMMARY: {context.metadata.file_name}")
            print("=" * 65)
            print(f"Tokens: ~{context.metadata.estimated_tokens} | Words: {context.metadata.word_count} | Tables: {len(context.tables)}")
            print(f"Severity: {context.threat_intel.severity_keywords}")
            print(f"CVEs: {context.iocs.cves}")
            print(f"MITRE ATT&CK: {context.iocs.mitre_attack_ids}")
            print(f"Threat Actors: {context.threat_intel.threat_actors}")
            print(f"Affected Systems: {context.threat_intel.affected_systems}")
            print(f"IPv4 Addresses: {context.iocs.ipv4_addresses}")
            print(f"SHA256 Hashes: {context.iocs.sha256_hashes}")
            print(f"Domains / URLs: {context.iocs.domains + context.iocs.urls}")

            if enriched:
                print("\n--- ENRICHED GROUNDING ANCHOR ---")
                print(f"Title: {enriched.title}")
                print(f"Minto Situation:   {enriched.minto_pyramid.situation}")
                print(f"Minto Complication:{enriched.minto_pyramid.complication}")
                print(f"Minto Solution:    {enriched.minto_pyramid.solution}")
                print(f"Locked Facts:      {enriched.locked_numerical_facts}")
                print(f"Mitigations Count: {len(enriched.actionable_mitigations)}")
            print("=" * 65 + "\n")


TextPipeline = TextIngestionPipeline
ingest_text = lambda file_input, filename=None, output_dir=None, save_outputs=True, enrich=False: TextIngestionPipeline(output_dir=output_dir or "ingestion_outputs").process(file_input, filename=filename, output_dir=output_dir, save_outputs=save_outputs, enrich=enrich)


if __name__ == "__main__":
    main()
