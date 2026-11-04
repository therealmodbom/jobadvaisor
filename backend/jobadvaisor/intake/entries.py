"""Layout-free parser for an uploaded job list (`design.md` → The list import): every Markdown
table with a link column is a list of entries. The parser knows no column or status names; what
the columns and values mean comes from the user's confirmed `ImportMapping`."""

import re
from dataclasses import dataclass
from typing import Literal

from jobadvaisor.data.models import ImportMapping

DEFAULT_TABLE = "Tabelle"
MAX_VALUES = 30  # a column with more distinct values is no status or assessment column

MARKUP = re.compile(r"[*`]")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
SEPARATOR = re.compile(r"^[\s|:-]+$")
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
URL = re.compile(r"https?://[^\s<>)\]]+")


@dataclass(frozen=True)
class Table:
    """A table with a link column: `name` is the heading above it (`"Tabelle"` when none),
    `columns` the header names, `rows` the non-blank rows' raw cells, each padded or cut to
    the header's length, and `link` the index of the link column."""

    name: str
    columns: list[str]
    rows: list[list[str]]
    link: int


@dataclass(frozen=True)
class Entry:
    """One table row: `table` its table's name, `row` its cells except the link column (empty
    ones dropped, markup removed) joined with " · ", `url` the first http(s) URL of the link
    cell, `status` and `assessment` the mapped columns' cells (`None` when empty or unmapped)."""

    table: str
    row: str
    url: str | None
    status: str | None
    assessment: str | None


def _strip(text: str) -> str:
    return MARKUP.sub("", text).strip()


def _norm(text: str) -> str:
    # lower(), not casefold(): the mapping form compares with JavaScript's toLowerCase(), which
    # keeps "ß" apart from "ss" as lower() does; both sides must agree on which names are one
    return _strip(text).lower()


def _cells(line: str) -> list[str]:
    line = line.strip().removeprefix("|")
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [cell.strip().replace("\\|", "|") for cell in UNESCAPED_PIPE.split(line)]


def parse_tables(markdown: str) -> list[Table]:
    """Every table of `markdown` (header, separator line, rows) that has a link column, in
    file order. The link column is the one with the most cells holding an http(s) URL, the
    leftmost on a tie; a table without any such cell is left out. Never raises on malformed
    input: such tables simply yield nothing."""
    tables: list[Table] = []
    name = DEFAULT_TABLE
    block: list[str] = []
    for line in [*markdown.splitlines(), ""]:  # the sentinel closes a table at the end
        if line.lstrip().startswith("|"):
            block.append(line)
            continue
        if table := _table(block, name):
            tables.append(table)
        block = []
        if heading := HEADING.match(line):
            name = _strip(heading[1]) or DEFAULT_TABLE
    return tables


def _table(block: list[str], name: str) -> Table | None:
    """The table of one block of `|` lines, or `None` without a separator line or links."""
    if len(block) < 2 or not SEPARATOR.match(block[1]):
        return None
    columns = [_strip(cell) for cell in _cells(block[0])]
    rows = []
    for line in block[2:]:
        cells = _cells(line)
        if any(cells):
            rows.append((cells + [""] * len(columns))[:len(columns)])
    links = [sum(bool(URL.search(row[i])) for row in rows) for i in range(len(columns))]
    if max(links, default=0) == 0:
        return None
    return Table(name, columns, rows, links.index(max(links)))


def _index(columns: list[str], name: str | None) -> int | None:
    """The index of the first column named `name` (trimmed, without case), else `None`."""
    return next((i for i, column in enumerate(columns) if name and _norm(column) == _norm(name)),
                None)


def parse_entries(markdown: str, mapping: ImportMapping) -> list[Entry]:
    """The entries of every table of `markdown` in file order. With `mapping.status_column`
    only tables that have such a column count; a row's `status` and `assessment` are the cells
    of the mapped columns. Never raises."""
    entries = []
    for table in parse_tables(markdown):
        status = _index(table.columns, mapping.status_column)
        if mapping.status_column and status is None:
            continue
        assessment = _index(table.columns, mapping.assessment_column)
        for row in table.rows:
            url = URL.search(row[table.link])
            text = " · ".join(_strip(cell) for i, cell in enumerate(row)
                              if i != table.link and _strip(cell))
            entries.append(Entry(table.name, text, url[0] if url else None,
                                 _cell(row, status), _cell(row, assessment)))
    return entries


def tables_left_out(markdown: str, mapping: ImportMapping) -> list[dict]:
    """The tables `parse_entries` drops for lacking `mapping.status_column`, in file order, as
    `{"name", "entries"}` (their row count); empty without a status column. Never raises."""
    if not mapping.status_column:
        return []
    return [{"name": table.name, "entries": len(table.rows)} for table in parse_tables(markdown)
            if _index(table.columns, mapping.status_column) is None]


def _cell(row: list[str], index: int | None) -> str | None:
    return (_strip(row[index]) or None) if index is not None else None


def preview(markdown: str) -> dict:
    """What the mapping form needs to know of `markdown`: `tables` (`name`, `columns`,
    `entries` count of each table with a link column, in file order) and `values`, for each
    column name across those tables (link columns excluded, columns matched without case)
    its distinct non-empty values in first-seen order, only for columns with at most
    `MAX_VALUES` distinct values."""
    tables = parse_tables(markdown)
    columns: dict[str, tuple[str, dict[str, None]]] = {}
    for table in tables:
        for i, name in enumerate(table.columns):
            if i == table.link or not name:
                continue
            values = columns.setdefault(_norm(name), (name, {}))[1]
            values |= {value: None for row in table.rows if (value := _strip(row[i]))}
    return {"tables": [{"name": t.name, "columns": t.columns, "entries": len(t.rows)}
                       for t in tables],
            "values": {name: list(values) for name, values in columns.values()
                       if len(values) <= MAX_VALUES}}


def mapped_status(mapping: ImportMapping, value: str | None) -> Literal[
        "open", "applied", "done", "skip"]:
    """The status `mapping.values` gives the list's status `value` (trimmed, without case);
    open for an empty or unnamed value."""
    known = {_norm(key): status for key, status in mapping.values.items()}
    return known.get(_norm(value), "open") if value else "open"
