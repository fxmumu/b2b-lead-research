#!/usr/bin/env python3
"""Validate the rendered lead-research/delivery.html.

`validate_candidates.py` guards the *data* (candidates.jsonl). This script guards the
*rendering* — the defects that are invisible in the source and only show up as a broken
deliverable: crushed table columns, raw markdown left in the page, a Chinese document
declared as English, an external stylesheet that breaks the single-file contract.

Checks (errors fail the run):
  - well-formed markup: no unclosed / stray / mismatched tags
  - no bare "&" (unescaped ampersand) outside <style>/<script>/comments
  - exactly one inline <style>, zero external stylesheet/script (single-file contract)
  - <meta charset> and viewport present
  - <html lang> matches the script of the body content (zh-CN when CJK is present)
  - every <table> sits inside .table-wrap, so wide tables scroll instead of crushing
  - no `overflow-wrap: anywhere` on a blanket th/td/* selector — `anywhere` takes part in
    min-content sizing and collapses a cell to one character wide (vertical headers)
  - @media print zeroes out table min-width, otherwise right-hand columns get clipped
  - the embedded brief carries no raw markdown markers (##, **, |---|)
  - exactly one <h1>, and no <h2> nested inside the brief block
  - with --candidates: the Contact column of every main/backup row carries that record's
    own first email (catches a contact picker that reorders or dedupes contacts)

Warnings (do not fail the run):
  - no CJK font in the font stack while the document contains CJK text
  - `overflow-wrap: break-word` absent from the stylesheet
  - heading levels that skip (h2 -> h4)
  - host preview instrumentation (`data-page-node-id`) written back into the file

Usage:
  python3 scripts/validate_delivery.py lead-research/delivery.html
  python3 scripts/validate_delivery.py lead-research/delivery.html \
    --candidates lead-research/candidates.jsonl --verbose
  # Windows without python3: python scripts/validate_delivery.py ...
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

VOID_ELEMENTS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    }
)

# Elements whose text content is not markup; excluded from the bare-& scan.
RAW_TEXT_ELEMENTS = ("style", "script")

# Entity forms that legitimately start with "&".
BARE_AMP = re.compile(r"&(?!#[0-9]+;|#x[0-9A-Fa-f]+;|[A-Za-z][A-Za-z0-9]*;)")

CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

CJK_FONT_HINTS = (
    "songti", "heiti", "pingfang", "hiragino", "microsoft yahei",
    "noto sans cjk", "noto serif cjk", "source han", "simsun", "simhei",
)

# Selectors that, when carrying `overflow-wrap: anywhere`, break table layout.
BLANKET_SELECTORS = frozenset({"*", "th", "td"})

DELIVERY_DISPOSITIONS = ("main", "backup")

EXPECTED_SECTIONS = ("Brief", "Main list", "Backup pool", "Exclusion list")


class MarkupChecker(HTMLParser):
    """Track tag balance and collect structure facts in a single pass."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[tuple[str, int]] = []
        self.errors: list[str] = []
        self.tag_counts: dict[str, int] = {}
        self.headings: list[tuple[int, str]] = []
        self._open_heading: tuple[int, str, int] | None = None
        self._open_heading_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1
        line, _ = self.getpos()
        if tag not in VOID_ELEMENTS:
            self.stack.append((tag, line))
        if re.fullmatch(r"h[1-6]", tag):
            self._open_heading = (int(tag[1]), "", line)
            self._open_heading_text = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_ELEMENTS:
            return
        line, _ = self.getpos()
        if not self.stack:
            self.errors.append(f"L{line}: stray </{tag}> with nothing open")
            return
        if self.stack[-1][0] == tag:
            self.stack.pop()
        elif any(t == tag for t, _ in self.stack):
            while self.stack and self.stack[-1][0] != tag:
                orphan, orphan_line = self.stack.pop()
                self.errors.append(
                    f"L{orphan_line}: <{orphan}> never closed (closed implicitly by </{tag}> at L{line})"
                )
            self.stack.pop()
        else:
            self.errors.append(f"L{line}: unmatched </{tag}>")

        if re.fullmatch(r"h[1-6]", tag) and self._open_heading:
            self.headings.append((self._open_heading[0], "".join(self._open_heading_text).strip()))
            self._open_heading = None

    def handle_data(self, data: str) -> None:
        if self._open_heading:
            self._open_heading_text.append(data)

    def close(self) -> None:  # type: ignore[override]
        super().close()
        for tag, line in self.stack:
            self.errors.append(f"L{line}: <{tag}> never closed")


def strip_raw_text(source: str) -> str:
    """Blank out <style>/<script>/comments, preserving offsets so line numbers hold."""
    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    out = source
    for tag in RAW_TEXT_ELEMENTS:
        out = re.sub(rf"<{tag}\b[^>]*>.*?</{tag}>", blank, out, flags=re.S | re.I)
    out = re.sub(r"<!--.*?-->", blank, out, flags=re.S)
    return out


def iter_css_rules(css: str, prefix: str = ""):
    """Yield (selector, declarations) for every rule, recursing into at-rules.

    Nested at-rules (@media, @supports) get folded into the selector as a prefix so a
    caller can tell "th, td {...}" from "@media print th, td {...}".
    """
    i, n = 0, len(css)
    while i < n:
        if css.startswith("/*", i):
            end = css.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        brace = css.find("{", i)
        if brace < 0:
            return
        selector = css[i:brace].strip()
        depth, k = 0, brace
        while k < n:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        body = css[brace + 1 : k]
        if selector.startswith("@"):
            yield from iter_css_rules(body, f"{prefix}{selector} ")
        elif selector:
            yield f"{prefix}{selector}", body
        i = k + 1


def _line_of(source: str, needle: str) -> int:
    idx = source.find(needle)
    return source.count("\n", 0, idx) + 1 if idx >= 0 else 0


_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.S | re.I)
_BREAK = re.compile(r"<br\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")


def cell_text(fragment: str) -> str:
    """Flatten a table cell to plain text: drop tags, keep <br> as a space, unescape."""
    text = _BREAK.sub(" ", fragment)
    text = _TAG.sub("", text)
    return normalize(html.unescape(text))


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_lead_rows(source: str) -> list[dict[str, str]]:
    """Pull (company, contact) out of every main/backup table body row.

    Identifies the tables by their header row rather than by `class="leads"`, so the
    check still works against output from older versions (which emitted a bare <table>).

    Column order is fixed by references/delivery.md:
    # | Company | Country | Segment | Score | Risk | Contact | Match reason | Website
    """
    rows: list[dict[str, str]] = []
    for table in re.finditer(r"<table\b[^>]*>(.*?)</table>", source, re.S | re.I):
        body = table.group(1)
        header = re.search(r"<tr\b[^>]*>(.*?)</tr>", body, re.S | re.I)
        if not header:
            continue
        labels = [cell_text(c) for c in _CELL.findall(header.group(1))]
        if "Company" not in labels or "Contact" not in labels:
            continue
        company_at, contact_at = labels.index("Company"), labels.index("Contact")
        for row in _ROW.finditer(body):
            cells = [cell_text(c) for c in _CELL.findall(row.group(1))]
            if len(cells) <= max(company_at, contact_at) or cells[0] == "#":
                continue
            rows.append({"company": cells[company_at], "contact": cells[contact_at]})
    return rows


def check_markup(source: str, errors: list[str]) -> tuple[MarkupChecker, str]:
    checker = MarkupChecker()
    checker.feed(source)
    checker.close()
    errors.extend(checker.errors)
    return checker, strip_raw_text(source)


def check_bare_ampersand(stripped: str, errors: list[str]) -> None:
    for match in BARE_AMP.finditer(stripped):
        line = stripped.count("\n", 0, match.start()) + 1
        errors.append(f"L{line}: bare '&' must be escaped as &amp;")


def check_head_and_lang(source: str, stripped: str, errors: list[str], warnings: list[str]) -> None:
    if not re.search(r"<meta[^>]+charset=[\"']?utf-8", source, re.I):
        errors.append("<meta charset='utf-8'> missing")

    if not re.search(r"<meta[^>]+name=[\"']viewport[\"']", source, re.I):
        errors.append("<meta name='viewport'> missing")

    lang_match = re.search(r"<html[^>]+lang=[\"']([^\"']*)[\"']", source, re.I)
    if not lang_match:
        errors.append("<html lang='...'> missing")
    else:
        lang = lang_match.group(1).strip().lower()
        has_cjk = bool(CJK.search(stripped))
        if has_cjk and not lang.startswith("zh"):
            errors.append(
                f"<html lang='{lang}'> but the body contains CJK text — "
                "CJK shaping and line-breaking follow the wrong rules (expected zh-*)"
            )
        if not has_cjk and lang.startswith("zh"):
            warnings.append(f"<html lang='{lang}'> but no CJK text found in the body")


def check_self_contained(source: str, errors: list[str]) -> None:
    external = re.findall(r"<link\b[^>]*rel=[\"']?stylesheet", source, re.I)
    if external:
        errors.append(f"{len(external)} external stylesheet <link> — the deliverable must be self-contained")
    external_js = re.findall(r"<script\b[^>]*\bsrc=", source, re.I)
    if external_js:
        errors.append(f"{len(external_js)} external <script src=...> — the deliverable must be self-contained")
    inline = len(re.findall(r"<style\b", source, re.I))
    if inline == 0:
        errors.append("no inline <style> found — the deliverable must carry its own CSS")
    elif inline > 1:
        errors.append(f"{inline} inline <style> blocks (expected 1)")


def check_host_instrumentation(source: str, warnings: list[str]) -> None:
    """Flag attributes the host's HTML preview panel writes back into the file.

    Opening the deliverable in a live preview can persist element-tracking attributes
    (e.g. `data-page-node-id`) into the file on disk. Harmless to render, but it triples
    the file size and means the file is no longer byte-identical to a fresh render.
    """
    injected = len(re.findall(r"\bdata-page-node-id=", source))
    if injected:
        warnings.append(
            f"{injected} 'data-page-node-id' attribute(s) present — the host's preview "
            "panel wrote its element tracking back into this file. Re-run the render to "
            "get a clean copy before sending the deliverable out."
        )


def check_cjk_fonts(source: str, stripped: str, warnings: list[str]) -> None:
    if not CJK.search(stripped):
        return
    lowered = source.lower()
    if not any(hint in lowered for hint in CJK_FONT_HINTS):
        warnings.append(
            "document contains CJK text but the font stack lists no CJK font "
            "(e.g. 'Songti SC', 'Noto Serif CJK SC', 'PingFang SC') — "
            "CJK glyphs fall back to whatever the OS picks"
        )


def check_tables(source: str, errors: list[str]) -> int:
    count = 0
    for match in re.finditer(r"<table\b", source, re.I):
        count += 1
        before = source[: match.start()]
        div_at = before.rfind("<div")
        if div_at < 0 or "table-wrap" not in before[div_at : match.start()]:
            line = source.count("\n", 0, match.start()) + 1
            errors.append(
                f"L{line}: <table> is not wrapped in <div class='table-wrap'> — "
                "a wide table will crush its columns on narrow screens instead of scrolling"
            )
    return count


def check_css_strategy(source: str, errors: list[str], warnings: list[str]) -> None:
    style_match = re.search(r"<style\b[^>]*>(.*?)</style>", source, re.S | re.I)
    if not style_match:
        return
    css = style_match.group(1)
    rules = list(iter_css_rules(css))

    for selector, body in rules:
        if "overflow-wrap" not in body and "word-wrap" not in body:
            continue
        value = re.search(r"overflow-wrap\s*:\s*([^;]+)", body)
        if not value or "anywhere" not in value.group(1):
            continue
        for part in selector.split(","):
            if part.strip() in BLANKET_SELECTORS:
                errors.append(
                    f"selector '{selector.strip()}' uses 'overflow-wrap: anywhere' — "
                    "'anywhere' takes part in min-content sizing and collapses a cell to "
                    "one character wide (vertical table headers). Use 'break-word' and "
                    "scope 'anywhere' to a single long-URL column."
                )
                break

    if "overflow-wrap: break-word" not in css:
        warnings.append("'overflow-wrap: break-word' not found — table cell wrapping strategy may have regressed")

    print_rules = [(sel, body) for sel, body in rules if sel.startswith("@media print")]
    if not print_rules:
        errors.append("@media print block missing — the table min-width overrides would be lost")
        return
    combined = " ".join(body for _, body in print_rules)
    if not re.search(r"min-width\s*:\s*0", combined):
        errors.append(
            "@media print does not zero out table min-width — fixed min-widths overflow "
            "the paper and clip the right-hand columns"
        )


def check_brief(source: str, checker: MarkupChecker, errors: list[str]) -> None:
    brief = re.search(r"<div class=['\"]brief['\"]>(.*?)</div>\s*</section>", source, re.S)
    if not brief:
        return
    body = brief.group(1)
    line = _line_of(source, "<div class='brief'>") or _line_of(source, '<div class="brief">')

    for pattern, label in (
        (r"^#{1,6}\s", "a markdown heading ('## …')"),
        (r"\*\*[^*]+\*\*", "markdown bold ('**…**')"),
        (r"^\s*\|.*\|\s*$", "a markdown table row ('| a | b |')"),
        (r"^\s*\|?[\s:-]*-{3,}[\s:|-]*$", "a markdown table separator ('|---|')"),
    ):
        if re.search(pattern, body, re.M):
            errors.append(
                f"L{line}: the embedded brief still contains {label} — the raw markdown was "
                "dumped into the page instead of being converted to markup"
            )
            break

    if re.search(r"<h2\b", body, re.I):
        errors.append(
            f"L{line}: an <h2> is nested inside the brief block — the section's own "
            "<h2> must stay the only section-level heading (shift brief headings down)"
        )


def check_headings(checker: MarkupChecker, errors: list[str], warnings: list[str]) -> None:
    h1s = checker.tag_counts.get("h1", 0)
    if h1s != 1:
        errors.append(f"{h1s} <h1> element(s) (expected exactly 1)")

    levels = [lvl for lvl, _ in checker.headings]
    for prev, curr in zip(levels, levels[1:]):
        if curr - prev > 1:
            warnings.append(f"heading level jumps from h{prev} to h{curr} (a level is skipped)")

    labels = [text for lvl, text in checker.headings if lvl == 2]
    for expected in EXPECTED_SECTIONS:
        if not any(expected.lower() in label.lower() for label in labels):
            warnings.append(f"section heading {expected!r} not found among <h2>: {labels}")


def check_candidates_cross_ref(path: Path, source: str, errors: list[str]) -> int:
    """Check the Contact column of the main/backup tables against the source records.

    Comparing against the table cell (rather than "does the address appear anywhere in the
    page") is what catches the real defect: `pick_contact` silently returning a different
    contact than the record's first one. A page-wide search would miss it whenever the
    evidence appendix happens to print the address anyway.
    """
    rows = extract_lead_rows(source)
    by_company: dict[str, dict[str, str]] = {}
    for row in rows:
        by_company.setdefault(normalize(row["company"]), row)

    checked = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"could not read {path}: {exc}")
        return 0

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{line_no}: invalid JSON ({exc})")
            continue
        if not isinstance(record, dict):
            continue
        if record.get("disposition") not in DELIVERY_DISPOSITIONS:
            continue

        contacts = record.get("contacts")
        if not isinstance(contacts, list):
            continue
        emails = [
            c.get("value")
            for c in contacts
            if isinstance(c, dict) and c.get("channel") == "email" and c.get("value")
        ]
        if not emails:
            continue

        company = str(record.get("company", ""))
        row = by_company.get(normalize(company))
        if row is None:
            errors.append(
                f"{path}:{line_no}: {company!r} has no row in the main/backup tables"
            )
            continue

        checked += 1
        if emails[0] not in row["contact"]:
            errors.append(
                f"{path}:{line_no}: {company!r} Contact column reads {row['contact']!r} "
                f"but the record's first email is {emails[0]!r} — the contact picker "
                "did not preserve the record's own ordering"
            )
    return checked


def validate_file(
    html_path: Path,
    candidates: Path | None,
    verbose: bool,
) -> int:
    if not html_path.is_file():
        print(f"error: file not found: {html_path}", file=sys.stderr)
        return 2

    source = html_path.read_text(encoding="utf-8")
    if not source.strip():
        print(f"FAIL: {html_path} (empty file)")
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    checker, stripped = check_markup(source, errors)
    check_bare_ampersand(stripped, errors)
    check_head_and_lang(source, stripped, errors, warnings)
    check_self_contained(source, errors)
    check_host_instrumentation(source, warnings)
    check_cjk_fonts(source, stripped, warnings)
    table_count = check_tables(source, errors)
    check_css_strategy(source, errors, warnings)
    check_brief(source, checker, errors)
    check_headings(checker, errors, warnings)

    cross_checked = 0
    if candidates:
        cross_checked = check_candidates_cross_ref(candidates, source, errors)

    if verbose:
        print(f"  tags: {sum(checker.tag_counts.values())}")
        print(f"  tables wrapped: {table_count}")
        print(f"  headings: {[(f'h{l}', t[:28]) for l, t in checker.headings]}")
        if candidates:
            print(f"  contacts cross-checked: {cross_checked}")

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if errors:
        print(f"FAIL: {html_path} ({len(errors)} issue(s))")
        for err in errors:
            print(f"  - {err}")
        return 1

    detail = f"{table_count} table(s), {len(checker.headings)} heading(s)"
    if candidates:
        detail += f", {cross_checked} contact(s) cross-checked"
    suffix = f" — {len(warnings)} warning(s)" if warnings else ""
    print(f"OK: {html_path} ({detail}){suffix}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "html",
        type=Path,
        nargs="?",
        default=Path("lead-research/delivery.html"),
        help="Path to the rendered delivery.html (default: lead-research/delivery.html)",
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=None,
        help="Optional candidates.jsonl to cross-check that each delivery record's "
             "first email actually made it into the page",
    )
    parser.add_argument("--verbose", action="store_true", help="Print structural counts")
    args = parser.parse_args()
    return validate_file(args.html, args.candidates, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
