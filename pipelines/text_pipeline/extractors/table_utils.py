"""
Utilities for parsing, normalizing, and structuring tables from Markdown and plain text.
"""

import re
from typing import List, Tuple
from pipelines.text_pipeline.schema import TableData


TABLE_ROW_PATTERN = re.compile(r"^\s*\|(.+)\|\s*$")
TABLE_SEPARATOR_PATTERN = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")


def extract_markdown_tables(markdown_text: str) -> List[TableData]:
    """
    Scans markdown text for table syntax and parses them into structured TableData objects.
    Preserves table structure, headers, rows, and dimensions.
    """
    tables: List[TableData] = []
    lines = markdown_text.splitlines()
    in_table = False
    current_table_lines: List[str] = []
    table_index = 1

    def clean_table_line(raw: str) -> str:
        s = raw.strip()
        # Remove bullet prefixes like '- |' or '* |'
        if re.match(r"^[-*+]\s*\|", s):
            s = re.sub(r"^[-*+]\s*", "", s)
        return s

    for line in lines:
        cleaned = clean_table_line(line)
        if cleaned.startswith("|") and cleaned.endswith("|"):
            in_table = True
            current_table_lines.append(cleaned)
        elif in_table and not cleaned:
            # Allow at most one blank line within table block
            continue
        else:
            if in_table:
                table_obj = _parse_table_block(current_table_lines, table_index)
                if table_obj:
                    tables.append(table_obj)
                    table_index += 1
                current_table_lines = []
                in_table = False

    if in_table and current_table_lines:
        table_obj = _parse_table_block(current_table_lines, table_index)
        if table_obj:
            tables.append(table_obj)

    return tables


def _parse_table_block(table_lines: List[str], table_index: int) -> TableData | None:
    """Helper to convert raw table lines into a TableData instance."""
    if len(table_lines) < 2:
        return None

    # Line 0 is header
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    
    start_idx = 1
    if len(table_lines) > 1 and TABLE_SEPARATOR_PATTERN.match(table_lines[1]):
        start_idx = 2

    rows: List[List[str]] = []
    for line in table_lines[start_idx:]:
        if TABLE_SEPARATOR_PATTERN.match(line):
            continue
        row_cells = [cell.strip() for cell in line.strip("|").split("|")]
        # Normalize cell count with headers
        if len(row_cells) < len(headers):
            row_cells.extend([""] * (len(headers) - len(row_cells)))
        elif len(row_cells) > len(headers):
            row_cells = row_cells[:len(headers)]
        rows.append(row_cells)

    raw_markdown = "\n".join(table_lines)
    return TableData(
        table_index=table_index,
        headers=headers,
        rows=rows,
        markdown_representation=raw_markdown,
        row_count=len(rows),
        column_count=len(headers)
    )


def format_matrix_to_markdown_table(headers: List[str], rows: List[List[str]]) -> str:
    """Convert raw headers and row arrays into clean markdown table syntax."""
    if not headers and not rows:
        return ""
    if not headers and rows:
        headers = [f"Col_{i+1}" for i in range(len(rows[0]))]

    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            if idx < len(col_widths):
                col_widths[idx] = max(col_widths[idx], len(str(cell)))

    header_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    sep_line = "| " + " | ".join("-" * max(col_widths[i], 3) for i in range(len(headers))) + " |"
    
    row_lines = []
    for row in rows:
        cells = [str(row[i]).ljust(col_widths[i]) if i < len(row) else "".ljust(col_widths[i]) for i in range(len(headers))]
        row_lines.append("| " + " | ".join(cells) + " |")

    return "\n".join([header_line, sep_line] + row_lines)
