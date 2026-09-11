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
import re
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
    # 同一渠道可能有多条（如多个邮箱）：保留记录中先出现的那条，
    # 不要用 dict 推导让后出现的覆盖先出现的。
    by_channel: dict[str, dict[str, Any]] = {}
    for c in contacts:
        if isinstance(c, dict) and c.get("channel") in CONTACT_CHANNELS:
            by_channel.setdefault(c["channel"], c)
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


def brief_md_to_html(md: str) -> str:
    """把 brief.md 转成 HTML 片段，供交付物内嵌展示。

    只覆盖 brief 里实际会出现的语法：`#` 标题、`-` 无序列表、`1.` 有序列表、
    段落、管道表格、`**粗体**`、`` `行内代码` ``。刻意不引入 markdown 依赖——
    本脚本要求零第三方包也能直接跑。先做 HTML 转义再套内联标签，因此不会引入注入面。
    """
    out: list[str] = []
    para: list[str] = []
    stack: list[str] = []  # 当前打开的列表标签（ul / ol）

    def inline(s: str) -> str:
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        return s

    def flush_para() -> None:
        if para:
            out.append("<p>" + inline(" ".join(para).strip()) + "</p>")
            para.clear()

    def close_lists() -> None:
        while stack:
            out.append(f"</{stack.pop()}>")

    def is_row(s: str) -> bool:
        t = s.strip()
        return t.startswith("|") and t.endswith("|") and t.count("|") >= 2

    def split_row(s: str) -> list[str]:
        t = s.strip()
        if t.startswith("|"):
            t = t[1:]
        if t.endswith("|"):
            t = t[:-1]
        return [c.strip() for c in t.split("|")]

    def is_sep(s: str) -> bool:
        # |---|---| 形式的表头分隔行
        if not is_row(s):
            return False
        cells = split_row(s)
        return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells)

    lines = md.replace("\r\n", "\n").split("\n")
    i, total = 0, len(lines)
    while i < total:
        line = lines[i].rstrip()
        if not line.strip():
            flush_para()
            close_lists()
            i += 1
            continue

        # 管道表格：本行是 | ... |，且下一行是分隔行
        if is_row(line) and i + 1 < total and is_sep(lines[i + 1]):
            flush_para()
            close_lists()
            header = split_row(line)
            i += 2
            body: list[list[str]] = []
            while i < total and is_row(lines[i]):
                body.append(split_row(lines[i]))
                i += 1
            width = len(header)
            out.append('<div class="table-wrap"><table class="brief-table"><thead><tr>')
            out.extend(f"<th>{inline(c)}</th>" for c in header)
            out.append("</tr></thead><tbody>")
            for r in body:
                cells = (r + [""] * width)[:width]
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            out.append("</tbody></table></div>")
            continue

        m_head = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m_head:
            flush_para()
            close_lists()
            # brief 的 # / ## 整体下移两级（→ h3 / h4），
            # 让 section 自带的 <h2>Brief</h2> 保持唯一的区块级标题，文档大纲不出现两个 h2。
            lvl = min(len(m_head.group(1)) + 2, 6)
            out.append(f"<h{lvl}>{inline(m_head.group(2))}</h{lvl}>")
            i += 1
            continue

        m_ul = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        m_ol = re.match(r"^(\s*)\d+[.)]\s+(.*)$", line)
        if m_ul or m_ol:
            flush_para()
            want = "ul" if m_ul else "ol"
            if not stack or stack[-1] != want:
                close_lists()
                out.append(f"<{want}>")
                stack.append(want)
            out.append(f"<li>{inline((m_ul or m_ol).group(2))}</li>")
            i += 1
            continue

        para.append(line.strip())
        i += 1

    flush_para()
    close_lists()
    return "\n".join(out)


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
  font-family: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, "Songti SC", "Noto Serif CJK SC", "Source Han Serif SC", "PingFang SC", serif;
  color: var(--ink);
  background: var(--bg);
  line-height: 1.45;
}
header, main { max-width: 1080px; margin: 0 auto; padding: 1.5rem; }
header h1 { font-size: 1.55rem; margin: 0 0 0.35rem; color: var(--accent); text-wrap: balance; }
header .meta { color: var(--muted); font-size: 0.95rem; }
section { background: var(--card); border: 1px solid var(--line); padding: 1.25rem 1.4rem; margin: 1.25rem 0; }
section h2 { margin-top: 0; font-size: 1.25rem; border-bottom: 1px solid var(--line); padding-bottom: 0.4rem; }
/* 宽表在窄屏下改为横向滚动，而不是把列挤成一团 */
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
/* 用 break-word 而非 anywhere：anywhere 会把单元格的 min-content 宽度压到 1 个字符，
   导致列被挤成竖排表头。break-word 只在必要时断词，不参与最小宽度计算。 */
th, td { border-bottom: 1px solid var(--line); padding: 0.45rem 0.4rem; text-align: left; vertical-align: top; overflow-wrap: break-word; }
th { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted); }
table.leads { min-width: 62rem; }
table.leads th:nth-child(2), table.leads td:nth-child(2) { min-width: 8rem; }
table.leads th:nth-child(7), table.leads td:nth-child(7) { min-width: 10rem; }
table.leads th:nth-child(8), table.leads td:nth-child(8) { min-width: 20rem; }
table.exclusions { min-width: 46rem; }
table.exclusions th:nth-child(5), table.exclusions td:nth-child(5) { min-width: 18rem; }
/* Sources 列是整段无空格的 URL：只有 anywhere 才能把它纳入最小宽度计算，
   否则单个长 URL 会把整张表撑出容器（break-word 不参与 min-content）。 */
table.exclusions td:last-child { overflow-wrap: anywhere; }
a { color: var(--accent); }
/* brief.md 已转成 HTML（见 brief_md_to_html），这里按正文排版，不再用等宽 pre-wrap
   把 Markdown 标记裸露出来。 */
.brief { background: #faf8f5; padding: 0.35rem 1.1rem 0.9rem; border: 1px solid var(--line); overflow-wrap: anywhere; }
.brief > :first-child { margin-top: 0.6rem; }
.brief > :last-child { margin-bottom: 0; }
.brief h3 { font-size: 1rem; margin: 1.05rem 0 0.4rem; color: var(--accent); }
.brief h4 { font-size: 0.94rem; margin: 0.85rem 0 0.35rem; color: var(--ink); }
.brief p { margin: 0.45rem 0; line-height: 1.62; }
.brief ul, .brief ol { margin: 0.4rem 0 0.6rem; padding-left: 1.4rem; }
.brief li { margin: 0.24rem 0; line-height: 1.6; }
.brief code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.86em; background: #ece8e1; padding: 0.08em 0.32em; border-radius: 3px; }
.brief strong { color: #2f2a24; }
/* brief 里的管道表格：不要继承 leads/exclusions 的 min-width，也不要把表头大写化 */
.brief .table-wrap { margin: 0.55rem 0 0.75rem; }
.brief table.brief-table { min-width: 0; font-size: 0.88rem; }
.brief table.brief-table th { text-transform: none; letter-spacing: 0; font-size: 0.85rem; }
.brief table.brief-table th, .brief table.brief-table td { overflow-wrap: break-word; }
details { border-top: 1px solid var(--line); padding: 0.7rem 0; }
details:first-of-type { border-top: none; }
summary { cursor: pointer; font-weight: 600; }
.muted { color: var(--muted); }
footer { max-width: 1080px; margin: 0 auto 2rem; padding: 0 1.5rem; color: var(--muted); font-size: 0.85rem; }
@media (max-width: 700px) {
  header, main { padding: 1rem 0.85rem; }
  section { padding: 1rem 0.9rem; }
  header h1 { font-size: 1.3rem; }
  table { font-size: 0.86rem; }
}
@media print {
  body { background: #fff; }
  .table-wrap { overflow: visible; }
  /* 打印时取消最小宽度，让表格收缩到纸张宽度，避免被裁掉右侧列 */
  table.leads, table.exclusions { min-width: 0; }
  table.leads th:nth-child(n), table.leads td:nth-child(n),
  table.exclusions th:nth-child(n), table.exclusions td:nth-child(n) { min-width: 0; }
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
            '<div class="table-wrap"><table class="leads"><thead><tr>'
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
        parts.append("</tbody></table></div>")
        return "".join(parts)

    def exclusion_table(items: list[dict[str, Any]]) -> str:
        if not items:
            return "<p class='muted'>None.</p>"
        parts = [
            '<div class="table-wrap"><table class="exclusions"><thead><tr>'
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
        parts.append("</tbody></table></div>")
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
        f"<section><h2>Brief</h2><div class='brief'>{brief_md_to_html(brief)}</div></section>"
        if brief
        else ""
    )
    evidence_html = (
        "".join(evidence_block(r) for r in main)
        if main
        else "<p class='muted'>No main-list leads.</p>"
    )

    # 正文以中文为主（match_reason / brief / 论据均为中文），
    # 按标题是否含中日韩字符决定 lang，避免中文字形与断行按英文规则处理。
    doc_lang = "zh-CN" if any("\u4e00" <= ch <= "\u9fff" for ch in title) else "en"

    return f"""<!DOCTYPE html>
<html lang="{doc_lang}">
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
