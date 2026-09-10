"""
PDF Parser using PyMuPDF4LLM.
Converts incoming PDF files into structured, hierarchical Markdown with table relationships preserved.
"""

import os
from typing import Tuple, List
import pymupdf
import pymupdf4llm
from pipelines.schema import TableData
from pipelines.extractors.table_utils import extract_markdown_tables


class PDFParser:
    """Extracts high-fidelity Markdown and structured tables from PDF files."""

    def parse(self, file_path: str) -> Tuple[str, List[TableData]]:
        """
        Parses a PDF file into clean Markdown and structured TableData objects.

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
        except Exception as e:
            # Fallback to standard PyMuPDF text extraction if pymupdf4llm runs into layout edge cases
            doc = pymupdf.open(file_path)
            pages_text = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                pages_text.append(f"<!-- Page {page_num + 1} -->\n" + page.get_text())
            doc.close()
            markdown_content = "\n\n".join(pages_text)

        # Clean any trailing excessive blank lines
        cleaned_markdown = "\n".join(
            line for line in markdown_content.splitlines() if line.strip() or line == ""
        ).strip()

        # Extract structured tables from the generated markdown
        tables = extract_markdown_tables(cleaned_markdown)

        return cleaned_markdown, tables
