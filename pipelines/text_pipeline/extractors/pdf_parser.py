"""
PDF Parser using PyMuPDF4LLM and Tesseract OCR.
Converts incoming PDF files into structured, hierarchical Markdown with table
relationships preserved and embedded images/scanned pages OCR-processed into context.
"""

import os
from typing import Tuple, List
import pymupdf
import pymupdf4llm
from pipelines.text_pipeline.schema import TableData
from pipelines.text_pipeline.extractors.table_utils import extract_markdown_tables
from pipelines.text_pipeline.extractors.ocr_utils import extract_text_from_image_bytes, is_ocr_available


class PDFParser:
    """Extracts high-fidelity Markdown, structured tables, and OCR text from PDF files."""

    def parse(self, file_path: str) -> Tuple[str, List[TableData]]:
        """
        Parses a PDF file into clean Markdown and structured TableData objects.
        Also extracts and OCRs embedded figures, diagrams, and scanned pages.

        Args:
            file_path: Absolute or relative path to PDF file.

        Returns:
            Tuple of (clean_markdown_string, list_of_TableData)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        try:
            # Primary high-fidelity parser via pymupdf4llm
            markdown_content = pymupdf4llm.to_markdown(
                doc=file_path,
                page_chunks=False,
                write_images=False,
                extract_words=False
            )
            if not isinstance(markdown_content, str):
                markdown_content = str(markdown_content)
        except Exception:
            # Fallback to standard PyMuPDF text extraction if pymupdf4llm encounters layout edge cases
            doc_fallback = pymupdf.open(file_path)
            pages_text = []
            for page_num in range(len(doc_fallback)):
                page = doc_fallback[page_num]
                pages_text.append(f"<!-- Page {page_num + 1} -->\n" + page.get_text())
            doc_fallback.close()
            markdown_content = "\n\n".join(pages_text)

        # Extract embedded image and scanned page text via OCR if available
        ocr_blocks = self._extract_image_ocr_blocks(file_path)
        if ocr_blocks:
            markdown_content += "\n\n## 🖼️ Extracted Embedded Image & Diagram Telemetry (OCR)\n\n" + "\n\n".join(ocr_blocks)

        # Clean any trailing excessive blank lines
        cleaned_markdown = "\n".join(
            line for line in markdown_content.splitlines() if line.strip() or line == ""
        ).strip()

        # Extract structured tables from the generated markdown
        tables = extract_markdown_tables(cleaned_markdown)

        return cleaned_markdown, tables

    def _extract_image_ocr_blocks(self, file_path: str) -> List[str]:
        """Extracts text from embedded images, diagrams, or scanned pages via OCR."""
        if not is_ocr_available():
            return []

        ocr_blocks: List[str] = []
        try:
            doc = pymupdf.open(file_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text().strip()
                image_list = page.get_images(full=True)

                # Check for scanned page: very little selectable text but images/visuals present
                if len(page_text) < 60 and len(image_list) > 0:
                    try:
                        pix = page.get_pixmap(dpi=150)
                        page_ocr = extract_text_from_image_bytes(pix.tobytes("png"))
                        if page_ocr and len(page_ocr) > len(page_text):
                            ocr_blocks.append(
                                f"### 📄 Page {page_num + 1} Scanned Content (OCR)\n\n"
                                f"```text\n{page_ocr}\n```"
                            )
                            continue
                    except Exception:
                        pass

                # Inspect embedded images on this page
                for img_idx, img_info in enumerate(image_list, start=1):
                    xref = img_info[0]
                    try:
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image.get("image")
                        if not image_bytes:
                            continue
                        img_ocr = extract_text_from_image_bytes(image_bytes)
                        # Avoid duplicating text that is already in page text
                        if img_ocr and img_ocr not in page_text:
                            ocr_blocks.append(
                                f"### 🖼️ Figure {img_idx} on Page {page_num + 1} (OCR)\n\n"
                                f"```text\n{img_ocr}\n```"
                            )
                    except Exception:
                        continue
            doc.close()
        except Exception:
            pass

        return ocr_blocks
