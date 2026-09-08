#!/usr/bin/env python3
"""Render human-readable delivery.md / delivery.html from candidates.jsonl.

Reads leads.yaml for product meta, contact preference, and output.format.
Optionally embeds lead-research/brief.md. Does not invent leads — only formats
records already in the jsonl.

Usage:
  python3 scripts/render_delivery.py lead-research/candidates.jsonl \\
    --config leads.yaml --brief lead-research/brief.md --out-dir lead-research
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTACT_CHANNELS = ("email", "phone", "linkedin", "website_form")
EXCLUSION = ("competitor", "unreachable", "excluded")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"error: {path}:{line_no}: invalid JSON ({exc})") from exc
            if not isinstance(obj, dict):
                raise SystemExit(f"error: {path}:{line_no}: record must be an object")
            rows.append(obj)
    return rows


def load_yaml_lite(path: Path | None) -> dict[str, Any]:
    if not path or not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except ImportError:
        return _scrape_leads_yaml(text)
    except Exception as exc:  # noqa: BLE001
        print(f"warning: failed to parse {path}: {exc}", file=sys.stderr)
        return _scrape_leads_yaml(text)


def _scrape_leads_yaml(text: str) -> dict[str, Any]:
    """Best-effort scrape when PyYAML is unavailable (company + output only)."""
    company: dict[str, Any] = {}
    output: dict[str, Any] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.endswith(":") and not line.startswith(" ") and not line.startswith("\t"):
            section = line[:-1].strip()
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if section == "company" and key in (
            "name_zh",
            "name_en",
            "product_or_service",
            "website",
            "contact_email",
        ):
            company[key] = val
        elif section == "output":
            if key == "format":
                output["format"] = val
            elif key == "outreach_language":
                output["outreach_language"] = val
            elif key == "contact_preference" and val.startswith("["):
                inner = val.strip("[]")
                output["contact_preference"] = [
                    p.strip().strip('"').strip("'") for p in inner.split(",") if p.strip()
                ]
    result: dict[str, Any] = {}
    if company:
        result["company"] = company
    if output:
        result["output"] = output
    return result

def sort_leads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(r: dict[str, Any]) -> tuple[Any, ...]:
        pri = r.get("priority")
        score = r.get("score")
        pri_key = pri if isinstance(pri, int) else 10**9
        score_key = -float(score) if isinstance(score, (int, float)) else 0.0
        return (pri_key, score_key, str(r.get("company", "")))

    return sorted(rows, key=key)


def pick_contact(row: dict[str, Any], preference: list[str]) -> str:
    contacts = row.get("contacts")
    if not isinstance(contacts, list) or not contacts:
        return "—"
    by_channel = {
        c.get("channel"): c
        for c in contacts
        if isinstance(c, dict) and c.get("channel") in CONTACT_CHANNELS
    }
    order = [c for c in preference if c in CONTACT_CHANNELS] or list(CONTACT_CHANNELS)
    for ch in order:
        c = by_channel.get(ch)
        if c and c.get("value"):
            conf = c.get("confidence", "?")
            return f"{ch}: {c['value']} ({conf})"
    # fallback first contact
    c = contacts[0]
    if isinstance(c, dict) and c.get("value"):
        return f"{c.get('channel', '?')}: {c['value']} ({c.get('confidence', '?')})"
    return "—"


def fmt_score(row: dict[str, Any]) -> str:
    score = row.get("score")
    if isinstance(score, (int, float)):
        return f"{float(score):.2f}"
    return "—"


def product_title(cfg: dict[str, Any]) -> str:
    company = cfg.get("company") if isinstance(cfg.get("company"), dict) else {}
    name = company.get("name_zh") or company.get("name_en") or "B2B Lead Research"
    product = company.get("product_or_service") or ""
    if product:
        return f"{name} — {product}"
    return str(name)


def resolve_format(cli: str, cfg: dict[str, Any]) -> str:
    if cli:
        return cli
    out = cfg.get("output") if isinstance(cfg.get("output"), dict) else {}
    fmt = out.get("format") or "both"
    if fmt == "markdown_table":  # legacy alias
        return "markdown"
    if fmt not in ("markdown", "html", "both"):
        print(f"warning: unknown output.format {fmt!r}, using both", file=sys.stderr)
        return "both"
    return fmt


def contact_preference(cfg: dict[str, Any]) -> list[str]:
    out = cfg.get("output") if isinstance(cfg.get("output"), dict) else {}
    pref = out.get("contact_preference")
    if isinstance(pref, list) and pref:
        return [str(x) for x in pref]
    return ["email", "phone", "linkedin"]


def md_escape(text: Any) -> str:
    s = str(text).replace("|", "\\|").replace("\n", " ")
    return s


def html_esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def render_markdown(
    rows: list[dict[str, Any]],
    cfg: dict[str, Any],
    brief: str | None,
    generated_at: str,
) -> str:
    pref = contact_preference(cfg)
    main = sort_leads([r for r in rows if r.get("disposition") == "main"])
    backup = sort_leads([r for r in rows if r.get("disposition") == "backup"])
    excluded = sort_leads([r for r in rows if r.get("disposition") in EXCLUSION])

    lines: list[str] = []
    lines.append(f"# {product_title(cfg)}")
    lines.append("")
    lines.append(f"_Generated: {generated_at}_")
    lines.append("")
    if brief:
        lines.append("## Brief")
        lines.append("")
        lines.append(brief.rstrip())
        lines.append("")

    def table(section: str, items: list[dict[str, Any]]) -> None:
        lines.append(f"## {section}")
        lines.append("")
        if not items:
            lines.append("_None._")
            lines.append("")
            return
        lines.append("| # | Company | Country | Segment | Score | Risk | Contact | Match reason | Website |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for i, r in enumerate(items, start=1):
            website = r.get("website") or "—"
            if website != "—" and isinstance(website, str) and website.startswith("http"):
                website_cell = f"[link]({website})"
            else:
                website_cell = md_escape(website)
            lines.append(
                "| {n} | {co} | {cy} | {seg} | {sc} | {rk} | {ct} | {mr} | {ws} |".format(
                    n=i,
                    co=md_escape(r.get("company", "")),
                    cy=md_escape(r.get("country", "")),
                    seg=md_escape(r.get("segment", "—")),
                    sc=fmt_score(r),
                    rk=md_escape(r.get("risk_level", "—")),
                    ct=md_escape(pick_contact(r, pref)),
                    mr=md_escape(r.get("match_reason", "—")),
                    ws=website_cell,
                )
            )
        lines.append("")

    table("Main list", main)
    table("Backup pool", backup)

    lines.append("## Exclusion list")
    lines.append("")
    if not excluded:
        lines.append("_None._")
        lines.append("")
    else:
        lines.append("| # | Company | Country | Disposition | Reason | Sources |")
        lines.append("|---|---|---|---|---|---|")
        for i, r in enumerate(excluded, start=1):
            sources = r.get("sources") if isinstance(r.get("sources"), list) else []
            src = "; ".join(str(s) for s in sources[:3]) or "—"
            lines.append(
                "| {n} | {co} | {cy} | {disp} | {reason} | {src} |".format(
                    n=i,
                    co=md_escape(r.get("company", "")),
                    cy=md_escape(r.get("country", "")),
                    disp=md_escape(r.get("disposition", "")),
                    reason=md_escape(r.get("exclusion_reason", "—")),
                    src=md_escape(src),
                )
            )
        lines.append("")

    lines.append("## Evidence appendix (main list)")
    lines.append("")
    if not main:
        lines.append("_No main-list leads._")
        lines.append("")
    for r in main:
        lines.append(f"### {r.get('company', 'Unknown')}")
        lines.append("")
        lines.append(f"- Country: {r.get('country', '—')}")
        lines.append(f"- Segment: {r.get('segment', '—')}")
        lines.append(f"- Score: {fmt_score(r)} · Risk: {r.get('risk_level', '—')}")
        lines.append("")
        lines.append("#### Demand/supply evidence")
        for ev in r.get("segment_evidence") or []:
            if not isinstance(ev, dict):
                continue
            lines.append(
                f"- `{ev.get('signal')}`: {ev.get('observation')} — {ev.get('source')}"
            )
        lines.append("")
        lines.append("#### Due diligence")
        lines.append("")
        lines.append(str(r.get("due_diligence_summary") or "—"))
        lines.append("")
        for chk in r.get("due_diligence_checks") or []:
            if not isinstance(chk, dict):
                continue
            lines.append(
                f"- `{chk.get('check')}` ({chk.get('status')}): {chk.get('finding')} — {chk.get('source')}"
            )
        lines.append("")
        lines.append("#### Score breakdown")
        lines.append("")
        bd = r.get("score_breakdown") if isinstance(r.get("score_breakdown"), dict) else {}
        for part in ("fit", "volume", "activity", "accessibility", "region_weight"):
            block = bd.get(part) if isinstance(bd.get(part), dict) else {}
            lines.append(
                f"- `{part}` = {block.get('value', '—')} — {block.get('basis', '—')}"
            )
        lines.append("")
        lines.append("#### Contacts")
        lines.append("")
        contacts = r.get("contacts") if isinstance(r.get("contacts"), list) else []
        if not contacts:
            lines.append("- No public contacts recorded.")
        for c in contacts:
            if not isinstance(c, dict):
                continue
            lines.append(
                f"- {c.get('channel')}: {c.get('value')} ({c.get('confidence')}) — {c.get('source')}"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Machine source: `lead-research/candidates.jsonl`. Do not treat this file as authoritative over the jsonl._")
    lines.append("")
    return "\n".join(lines)


CSS = """
:root {
  --ink: #1a1a1a;
  --muted: #5c5c5c;
  --line: #d8d8d8;
  --bg: #f7f5f1;
  --card: #ffffff;
  --accent: #0b3d2e;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  color: var(--ink);
  background: var(--bg);
  line-height: 1.45;
}
header, main { max-width: 1080px; margin: 0 auto; padding: 1.5rem; }
header h1 { font-size: 1.75rem; margin: 0 0 0.35rem; color: var(--accent); }
header .meta { color: var(--muted); font-size: 0.95rem; }
section { background: var(--card); border: 1px solid var(--line); padding: 1.25rem 1.4rem; margin: 1.25rem 0; }
section h2 { margin-top: 0; font-size: 1.25rem; border-bottom: 1px solid var(--line); padding-bottom: 0.4rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
th, td { border-bottom: 1px solid var(--line); padding: 0.45rem 0.4rem; text-align: left; vertical-align: top; }
th { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted); }
a { color: var(--accent); }
.brief { white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.85rem; background: #f0eee8; padding: 0.9rem; border: 1px solid var(--line); }
details { border-top: 1px solid var(--line); padding: 0.7rem 0; }
details:first-of-type { border-top: none; }
summary { cursor: pointer; font-weight: 600; }
.muted { color: var(--muted); }
footer { max-width: 1080px; margin: 0 auto 2rem; padding: 0 1.5rem; color: var(--muted); font-size: 0.85rem; }
@media print {
  body { background: #fff; }
  section { break-inside: avoid; border: none; padding: 0; margin: 1rem 0; }
  details[open] summary { margin-bottom: 0.4rem; }
}
"""


def render_html(
    rows: list[dict[str, Any]],
    cfg: dict[str, Any],
    brief: str | None,
    generated_at: str,
) -> str:
    pref = contact_preference(cfg)
    main = sort_leads([r for r in rows if r.get("disposition") == "main"])
    backup = sort_leads([r for r in rows if r.get("disposition") == "backup"])
    excluded = sort_leads([r for r in rows if r.get("disposition") in EXCLUSION])
    title = product_title(cfg)

    def lead_table(items: list[dict[str, Any]]) -> str:
        if not items:
            return "<p class='muted'>None.</p>"
        parts = [
            "<table><thead><tr>"
            "<th>#</th><th>Company</th><th>Country</th><th>Segment</th>"
            "<th>Score</th><th>Risk</th><th>Contact</th><th>Match reason</th><th>Website</th>"
            "</tr></thead><tbody>"
        ]
        for i, r in enumerate(items, start=1):
            website = r.get("website") or ""
            if isinstance(website, str) and website.startswith("http"):
                web_cell = f'<a href="{html_esc(website)}">link</a>'
            else:
                web_cell = "—"
            parts.append(
                "<tr>"
                f"<td>{i}</td>"
                f"<td>{html_esc(r.get('company', ''))}</td>"
                f"<td>{html_esc(r.get('country', ''))}</td>"
                f"<td>{html_esc(r.get('segment', '—'))}</td>"
                f"<td>{html_esc(fmt_score(r))}</td>"
                f"<td>{html_esc(r.get('risk_level', '—'))}</td>"
                f"<td>{html_esc(pick_contact(r, pref))}</td>"
                f"<td>{html_esc(r.get('match_reason', '—'))}</td>"
                f"<td>{web_cell}</td>"
                "</tr>"
            )
        parts.append("</tbody></table>")
        return "".join(parts)

    def exclusion_table(items: list[dict[str, Any]]) -> str:
        if not items:
            return "<p class='muted'>None.</p>"
        parts = [
            "<table><thead><tr>"
            "<th>#</th><th>Company</th><th>Country</th><th>Disposition</th>"
            "<th>Reason</th><th>Sources</th>"
            "</tr></thead><tbody>"
        ]
        for i, r in enumerate(items, start=1):
            sources = r.get("sources") if isinstance(r.get("sources"), list) else []
            src_bits = []
            for s in sources[:3]:
                if isinstance(s, str) and s.startswith("http"):
                    src_bits.append(f'<a href="{html_esc(s)}">{html_esc(s)}</a>')
                else:
                    src_bits.append(html_esc(s))
            parts.append(
                "<tr>"
                f"<td>{i}</td>"
                f"<td>{html_esc(r.get('company', ''))}</td>"
                f"<td>{html_esc(r.get('country', ''))}</td>"
                f"<td>{html_esc(r.get('disposition', ''))}</td>"
                f"<td>{html_esc(r.get('exclusion_reason', '—'))}</td>"
                f"<td>{'<br>'.join(src_bits) if src_bits else '—'}</td>"
                "</tr>"
            )
        parts.append("</tbody></table>")
        return "".join(parts)

    def evidence_block(r: dict[str, Any]) -> str:
        bits: list[str] = [f"<details open><summary>{html_esc(r.get('company', 'Unknown'))}</summary>"]
        bits.append(
            f"<p>Country: {html_esc(r.get('country', '—'))} · "
            f"Segment: {html_esc(r.get('segment', '—'))} · "
            f"Score: {html_esc(fmt_score(r))} · Risk: {html_esc(r.get('risk_level', '—'))}</p>"
        )
        bits.append("<h3>Demand/supply evidence</h3><ul>")
        for ev in r.get("segment_evidence") or []:
            if not isinstance(ev, dict):
                continue
            src = ev.get("source", "")
            src_html = (
                f'<a href="{html_esc(src)}">{html_esc(src)}</a>'
                if isinstance(src, str) and src.startswith("http")
                else html_esc(src)
            )
            bits.append(
                f"<li><code>{html_esc(ev.get('signal'))}</code>: "
                f"{html_esc(ev.get('observation'))} — {src_html}</li>"
            )
        bits.append("</ul>")
        bits.append("<h3>Due diligence</h3>")
        bits.append(f"<p>{html_esc(r.get('due_diligence_summary') or '—')}</p><ul>")
        for chk in r.get("due_diligence_checks") or []:
            if not isinstance(chk, dict):
                continue
            src = chk.get("source", "")
            src_html = (
                f'<a href="{html_esc(src)}">{html_esc(src)}</a>'
                if isinstance(src, str) and src.startswith("http")
                else html_esc(src)
            )
            bits.append(
                f"<li><code>{html_esc(chk.get('check'))}</code> "
                f"({html_esc(chk.get('status'))}): {html_esc(chk.get('finding'))} — {src_html}</li>"
            )
        bits.append("</ul>")
        bits.append("<h3>Score breakdown</h3><ul>")
        bd = r.get("score_breakdown") if isinstance(r.get("score_breakdown"), dict) else {}
        for part in ("fit", "volume", "activity", "accessibility", "region_weight"):
            block = bd.get(part) if isinstance(bd.get(part), dict) else {}
            bits.append(
                f"<li><code>{part}</code> = {html_esc(block.get('value', '—'))} — "
                f"{html_esc(block.get('basis', '—'))}</li>"
            )
        bits.append("</ul><h3>Contacts</h3><ul>")
        contacts = r.get("contacts") if isinstance(r.get("contacts"), list) else []
        if not contacts:
            bits.append("<li>No public contacts recorded.</li>")
        for c in contacts:
            if not isinstance(c, dict):
                continue
            src = c.get("source", "")
            src_html = (
                f'<a href="{html_esc(src)}">{html_esc(src)}</a>'
                if isinstance(src, str) and src.startswith("http")
                else html_esc(src)
            )
            bits.append(
                f"<li>{html_esc(c.get('channel'))}: {html_esc(c.get('value'))} "
                f"({html_esc(c.get('confidence'))}) — {src_html}</li>"
            )
        bits.append("</ul></details>")
        return "".join(bits)

    brief_html = (
        f"<section><h2>Brief</h2><div class='brief'>{html_esc(brief)}</div></section>"
        if brief
        else ""
    )
    evidence_html = (
        "".join(evidence_block(r) for r in main)
        if main
        else "<p class='muted'>No main-list leads.</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html_esc(title)}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>{html_esc(title)}</h1>
  <div class="meta">Generated: {html_esc(generated_at)}</div>
</header>
<main>
  {brief_html}
  <section><h2>Main list</h2>{lead_table(main)}</section>
  <section><h2>Backup pool</h2>{lead_table(backup)}</section>
  <section><h2>Exclusion list</h2>{exclusion_table(excluded)}</section>
  <section><h2>Evidence appendix (main list)</h2>{evidence_html}</section>
</main>
<footer>Machine source: lead-research/candidates.jsonl. This HTML is a rendering only.</footer>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path, help="Path to candidates.jsonl")
    parser.add_argument("--config", type=Path, default=Path("leads.yaml"))
    parser.add_argument("--brief", type=Path, default=Path("lead-research/brief.md"))
    parser.add_argument("--out-dir", type=Path, default=Path("lead-research"))
    parser.add_argument(
        "--format",
        choices=["markdown", "html", "both", ""],
        default="",
        help="Override output.format from leads.yaml",
    )
    args = parser.parse_args()

    if not args.candidates.is_file():
        print(f"error: file not found: {args.candidates}", file=sys.stderr)
        return 2

    rows = load_jsonl(args.candidates)
    cfg = load_yaml_lite(args.config)
    brief = None
    if args.brief.is_file():
        brief = args.brief.read_text(encoding="utf-8")

    fmt = resolve_format(args.format, cfg)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    if fmt in ("markdown", "both"):
        md_path = args.out_dir / "delivery.md"
        md_path.write_text(render_markdown(rows, cfg, brief, generated_at), encoding="utf-8")
        written.append(str(md_path))
    if fmt in ("html", "both"):
        html_path = args.out_dir / "delivery.html"
        html_path.write_text(render_html(rows, cfg, brief, generated_at), encoding="utf-8")
        written.append(str(html_path))

    print("Wrote: " + ", ".join(written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
