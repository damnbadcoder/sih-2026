"""
Text and Unstructured Data Parser.
Parses Markdown, Plain Text, Telemetry Logs, CSV/TSV, and JSON feeds.
"""

import os
import csv
import json
from io import StringIO
from typing import Tuple, List
from pipelines.schema import TableData
from pipelines.extractors.table_utils import extract_markdown_tables, format_matrix_to_markdown_table


class TextParser:
    """Parses text-based formats (MD, TXT, LOG, CSV, JSON) into clean Markdown and structured tables."""

    def parse(self, file_path: str) -> Tuple[str, List[TableData]]:
        """
        Parses a text-based file into clean Markdown and structured TableData objects.

        Args:
            file_path: Path to text/md/csv/json/log file.

        Returns:
            Tuple of (clean_markdown_string, list_of_TableData)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        raw_text, encoding = self._read_file_with_fallback(file_path)

        if ext in {".md", ".markdown"}:
            tables = extract_markdown_tables(raw_text)
            return raw_text.strip(), tables

        elif ext in {".csv", ".tsv"}:
            return self._parse_delimited(raw_text, delimiter="," if ext == ".csv" else "\t")

        elif ext == ".json":
            return self._parse_json(raw_text)

        elif ext in {".log", ".txt"}:
            return self._parse_plain_or_log(raw_text, ext)

        else:
            # General fallback for any other text format
            tables = extract_markdown_tables(raw_text)
            return raw_text.strip(), tables

    def _read_file_with_fallback(self, file_path: str) -> Tuple[str, str]:
        """Attempt to read file with utf-8, falling back to latin-1 or utf-16."""
        for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "utf-16"]:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read(), enc
            except UnicodeDecodeError:
                continue
        # Fallback ignoring errors
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(), "utf-8-lossy"

    def _parse_delimited(self, content: str, delimiter: str = ",") -> Tuple[str, List[TableData]]:
        """Converts CSV/TSV table directly into Markdown table and TableData."""
        reader = csv.reader(StringIO(content), delimiter=delimiter)
        all_rows = [row for row in reader if any(cell.strip() for cell in row)]
        
        if not all_rows:
            return "", []

        headers = all_rows[0]
        data_rows = all_rows[1:] if len(all_rows) > 1 else []
        table_md = format_matrix_to_markdown_table(headers, data_rows)

        table_data = TableData(
            table_index=1,
            headers=headers,
            rows=data_rows,
            markdown_representation=table_md,
            row_count=len(data_rows),
            column_count=len(headers)
        )
        return table_md, [table_data]

    def _parse_json(self, content: str) -> Tuple[str, List[TableData]]:
        """Parses JSON content into clean readable Markdown."""
        try:
            data = json.loads(content)
            pretty_json = json.dumps(data, indent=2)
            markdown = f"```json\n{pretty_json}\n```"

            tables: List[TableData] = []
            # If JSON is a list of flat dicts, also convert into TableData
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                headers = list(data[0].keys())
                rows = []
                for item in data:
                    if isinstance(item, dict):
                        rows.append([str(item.get(h, "")) for h in headers])
                if headers and rows:
                    table_md = format_matrix_to_markdown_table(headers, rows)
                    tables.append(TableData(
                        table_index=1,
                        headers=headers,
                        rows=rows,
                        markdown_representation=table_md,
                        row_count=len(rows),
                        column_count=len(headers)
                    ))
                    markdown = f"{table_md}\n\n{markdown}"

            return markdown, tables
        except json.JSONDecodeError:
            return f"```\n{content.strip()}\n```", []

    def _parse_plain_or_log(self, content: str, ext: str) -> Tuple[str, List[TableData]]:
        """Parses plain text or log entries, extracting markdown tables if present."""
        clean_text = content.strip()
        tables = extract_markdown_tables(clean_text)

        # If it's a raw log file, wrap log lines or format with a clear header
        if ext == ".log":
            markdown = f"### Ingested Log Telemetry\n\n```text\n{clean_text}\n```"
        else:
            markdown = clean_text

        return markdown, tables
