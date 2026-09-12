"""
Universal PDF Parser using PyMuPDF and OCR.
Extracts document metadata, attachments, visual hierarchy blocks, vector text,
hyperlink annotations, AcroForms, and full-page fallback OCR renderings.
"""

import os
from typing import Tuple, List, Dict, Any
import pymupdf
import pymupdf4llm
from pipelines.text_pipeline.schema import TableData
from pipelines.text_pipeline.extractors.table_utils import extract_markdown_tables
from pipelines.text_pipeline.extractors.ocr_utils import extract_text_from_image_bytes, is_ocr_available


class PDFParser:
    """Extracts high-fidelity Markdown, structured tables, and telemetry from all PDF layouts."""

    MIN_TEXT_CHARS = 120

    def parse(self, file_path: str) -> Tuple[str, List[TableData]]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        doc = pymupdf.open(file_path)
        page_outputs: List[str] = []
        ocr_enabled = is_ocr_available()

        # Extract structured markdown with table preservation across all pages
        try:
            page_chunks = pymupdf4llm.to_markdown(file_path, page_chunks=True)
        except Exception:
            page_chunks = []

        # 1. Document Metadata Header
        meta_items = [
            f"- **{k.capitalize()}:** {v}"
            for k, v in doc.metadata.items()
            if v and str(v).strip()
        ]
        if meta_items:
            page_outputs.append("### 📋 Document Metadata\n" + "\n".join(meta_items))

        # 2. Embedded Document Attachments (Malware droppers, embedded spreadsheets)
        if doc.embfile_count() > 0:
            emb_entries = []
            for i in range(doc.embfile_count()):
                emb_info = doc.embfile_info(i)
                emb_name = emb_info.get("filename", f"attachment_{i}")
                emb_size = emb_info.get("size", 0)
                emb_entries.append(f"- `{emb_name}` ({emb_size} bytes)")
            page_outputs.append("### 📎 Embedded File Attachments\n" + "\n".join(emb_entries))

        # 3. Iterative Page-Level Processing
        for page_num in range(len(doc)):
            page = doc[page_num]
            raw_text = page.get_text("text").strip()

            chunk_text = ""
            if page_num < len(page_chunks):
                chunk_text = page_chunks[page_num].get("text", "").strip()

            # Identify if page is graphic-heavy, vector-rendered, or scanned
            if ocr_enabled and len(raw_text) < self.MIN_TEXT_CHARS:
                page_ocr = self._ocr_entire_page(page, dpi=220)
                if page_ocr:
                    page_content = f"{chunk_text}\n\n**Visual / Scanned Content (OCR):**\n\n{page_ocr}".strip() if chunk_text else page_ocr
                else:
                    page_content = chunk_text or raw_text
            else:
                page_content = chunk_text or self._extract_structured_page(doc, page)

            # Extract interactive AcroForm entries if present on the page
            form_fields = self._extract_form_fields(page)
            if form_fields:
                page_content += "\n\n**Interactive Form Inputs:**\n" + "\n".join(
                    f"- **{field['name']}:** {field['value']}" for field in form_fields
                )

            # Explicitly separate link annotations from security threat telemetry
            ref_links = self._extract_annotated_links(page)
            if ref_links:
                page_content += "\n\n**Explicit Reference Links & Resources (Not Threat IOCs):**\n" + "\n".join(
                    f"- [{item['title']}]({item['uri']})" if item['title'] != item['uri'] else f"- <{item['uri']}>"
                    for item in ref_links
                )

            page_header = f"<!-- Page {page_num + 1} -->"
            page_outputs.append(f"{page_header}\n{page_content}".strip())

        doc.close()

        combined_markdown = "\n\n---\n\n".join(page_outputs).strip()
        cleaned_markdown = "\n".join(
            line for line in combined_markdown.splitlines() if line.strip() or line == ""
        ).strip()

        tables = extract_markdown_tables(cleaned_markdown)
        return cleaned_markdown, tables

    def _extract_structured_page(self, doc: pymupdf.Document, page: pymupdf.Page) -> str:
        """Preserves visual boundaries and font hierarchy to avoid cross-block pollution."""
        try:
            page_dict: Dict[str, Any] = page.get_text("dict")
            blocks = page_dict.get("blocks", [])
            lines_out: List[str] = []

            for block in blocks:
                if block.get("type") == 0:  # Text block
                    block_lines: List[str] = []
                    for line in block.get("lines", []):
                        line_text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                        if line_text:
                            first_span = line.get("spans", [{}])[0]
                            font_size = first_span.get("size", 10)
                            flags = first_span.get("flags", 0)
                            is_bold = bool(flags & (1 << 4))

                            if (is_bold or font_size > 12.5) and len(line_text) < 90:
                                block_lines.append(f"\n**{line_text}**")
                            else:
                                block_lines.append(line_text)

                    if block_lines:
                        lines_out.append("\n".join(block_lines))

            extracted = "\n\n".join(lines_out).strip()
            return extracted if extracted else pymupdf4llm.to_markdown(doc, pages=[page.number]).strip()
        except Exception:
            return pymupdf4llm.to_markdown(doc, pages=[page.number]).strip()

    def _extract_annotated_links(self, page: pymupdf.Page) -> List[Dict[str, str]]:
        """Extracts native hyperlink references embedded in PDF coordinates."""
        links: List[Dict[str, str]] = []
        for link in page.get_links():
            uri = link.get("uri")
            if uri:
                rect = link.get("from")
                label = page.get_text("text", clip=rect).strip() if rect else ""
                links.append({
                    "title": label if label else uri,
                    "uri": uri
                })
        return links

    def _extract_form_fields(self, page: pymupdf.Page) -> List[Dict[str, str]]:
        """Extracts interactive form names and active values."""
        fields: List[Dict[str, str]] = []
        for widget in page.widgets():
            name = widget.field_name or "UnknownField"
            val = widget.field_value
            if val is not None and str(val).strip():
                fields.append({"name": name, "value": str(val).strip()})
        return fields

    def _ocr_entire_page(self, page: pymupdf.Page, dpi: int = 220) -> str:
        """Rasterizes the full vector page canvas and runs OCR."""
        try:
            pix = page.get_pixmap(dpi=dpi)
            ocr_result = extract_text_from_image_bytes(pix.tobytes("png"), min_length=15, psm_mode=6)
            return ocr_result.strip() if ocr_result else ""
        except Exception:
            return ""