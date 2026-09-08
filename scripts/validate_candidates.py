#!/usr/bin/env python3
"""Validate lead-research/candidates.jsonl against assets/lead-schema.json.

Checks:
  - each line is JSON and matches the schema (Draft 2020-12 subset via jsonschema if
    installed; otherwise a built-in structural check covering required fields,
    enums, and disposition/stage gates)
  - stage-gated field presence for in-pipeline (pending) records
  - exclusion_reason when disposition is an exclusion class
  - delivery-state (main/backup) hard evidence trail: segment_evidence,
    due_diligence_checks (all 5), score_breakdown bases, contacts provenance
  - score ≈ weighted sum of breakdown when --config leads.yaml is given

Usage:
  python3 scripts/validate_candidates.py lead-research/candidates.jsonl
  python3 scripts/validate_candidates.py lead-research/candidates.jsonl --config leads.yaml
  # Windows without python3: python scripts/validate_candidates.py ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = SKILL_DIR / "assets" / "lead-schema.json"

STAGES = ("discovered", "screened", "diligenced", "verified", "scored")
DISPOSITIONS = ("pending", "main", "backup", "competitor", "unreachable", "excluded")
EXCLUSION_DISPOSITIONS = ("competitor", "unreachable", "excluded")
DELIVERY_DISPOSITIONS = ("main", "backup")
DD_CHECKS = (
    "authenticity",
    "operating_status",
    "business_relevance",
    "risk_signals",
    "reachability",
)
SEGMENTS = (
    "end_user",
    "epc",
    "installer",
    "distributor",
    "importer",
    "trading_company",
    "oem_buyer",
    "developer_owner",
)

# Minimum fields expected once a pending record has reached a given stage.
STAGE_FIELDS: dict[str, tuple[str, ...]] = {
    "discovered": (),
    "screened": ("segment", "segment_evidence", "match_reason"),
    "diligenced": (
        "segment",
        "segment_evidence",
        "risk_level",
        "due_diligence_summary",
        "due_diligence_checks",
    ),
    "verified": (
        "segment",
        "segment_evidence",
        "risk_level",
        "due_diligence_summary",
        "due_diligence_checks",
        "contacts",
    ),
    "scored": (
        "segment",
        "segment_evidence",
        "risk_level",
        "due_diligence_summary",
        "due_diligence_checks",
        "contacts",
        "score",
        "score_breakdown",
        "match_reason",
    ),
}


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def try_jsonschema(record: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return []
    validator_cls = jsonschema.Draft202012Validator
    errors = sorted(validator_cls(schema).iter_errors(record), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _looks_like_uri(value: Any) -> bool:
    return isinstance(value, str) and (value.startswith("http://") or value.startswith("https://"))


def check_evidence_item(item: Any, prefix: str, path: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(item, dict):
        return [f"{prefix}: {path} must be an object"]
    if item.get("signal") not in ("demand_side", "supply_side"):
        errs.append(f"{prefix}: {path}.signal must be demand_side or supply_side")
    if not _nonempty_str(item.get("observation")):
        errs.append(f"{prefix}: {path}.observation must be a non-empty string")
    if not _looks_like_uri(item.get("source")):
        errs.append(f"{prefix}: {path}.source must be an http(s) URL")
    return errs


def check_dd_item(item: Any, prefix: str, path: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(item, dict):
        return [f"{prefix}: {path} must be an object"]
    if item.get("check") not in DD_CHECKS:
        errs.append(f"{prefix}: {path}.check must be one of {DD_CHECKS}")
    if not _nonempty_str(item.get("finding")):
        errs.append(f"{prefix}: {path}.finding must be a non-empty string")
    if not _looks_like_uri(item.get("source")):
        errs.append(f"{prefix}: {path}.source must be an http(s) URL")
    if item.get("status") not in ("confirmed", "inconclusive", "negative"):
        errs.append(f"{prefix}: {path}.status must be confirmed|inconclusive|negative")
    return errs


def check_delivery_evidence(record: dict[str, Any], line_no: int) -> list[str]:
    """Hard-require the four evidence trails for main/backup delivery records."""
    errs: list[str] = []
    prefix = f"L{line_no}"
    disposition = record.get("disposition")

    evidence = record.get("segment_evidence")
    if not isinstance(evidence, list) or len(evidence) < 1:
        errs.append(f"{prefix}: disposition={disposition} requires non-empty segment_evidence")
    else:
        for i, item in enumerate(evidence):
            errs.extend(check_evidence_item(item, prefix, f"segment_evidence[{i}]"))
        if not any(
            isinstance(item, dict) and item.get("signal") == "demand_side" for item in evidence
        ):
            errs.append(
                f"{prefix}: disposition={disposition} requires ≥1 demand_side "
                "entry in segment_evidence"
            )

    if not _nonempty_str(record.get("match_reason")):
        errs.append(f"{prefix}: disposition={disposition} requires non-empty match_reason")

    if not _nonempty_str(record.get("due_diligence_summary")):
        errs.append(
            f"{prefix}: disposition={disposition} requires non-empty due_diligence_summary"
        )

    checks = record.get("due_diligence_checks")
    if not isinstance(checks, list) or len(checks) != 5:
        errs.append(
            f"{prefix}: disposition={disposition} requires due_diligence_checks "
            "with exactly 5 items"
        )
    else:
        seen: set[str] = set()
        for i, item in enumerate(checks):
            errs.extend(check_dd_item(item, prefix, f"due_diligence_checks[{i}]"))
            if isinstance(item, dict) and item.get("check") in DD_CHECKS:
                check_name = item["check"]
                if check_name in seen:
                    errs.append(f"{prefix}: duplicate due_diligence_checks.check={check_name}")
                seen.add(check_name)
        missing = [c for c in DD_CHECKS if c not in seen]
        if missing:
            errs.append(f"{prefix}: due_diligence_checks missing {missing}")

    breakdown = record.get("score_breakdown")
    if not isinstance(breakdown, dict):
        errs.append(f"{prefix}: disposition={disposition} requires score_breakdown object")
    else:
        for part in ("fit", "volume", "activity", "accessibility", "region_weight"):
            block = breakdown.get(part)
            if not isinstance(block, dict):
                errs.append(f"{prefix}: score_breakdown.{part} missing")
                continue
            if not isinstance(block.get("value"), (int, float)):
                errs.append(f"{prefix}: score_breakdown.{part}.value must be a number")
            if not _nonempty_str(block.get("basis")):
                errs.append(f"{prefix}: score_breakdown.{part}.basis must be non-empty")

    if "score" not in record or not isinstance(record.get("score"), (int, float)):
        errs.append(f"{prefix}: disposition={disposition} requires numeric score")

    contacts = record.get("contacts")
    if not isinstance(contacts, list):
        errs.append(f"{prefix}: disposition={disposition} requires contacts array (may be [])")
    elif len(contacts) == 0:
        # Empty contacts allowed only if reachability check documents the gap.
        reach = None
        for item in checks if isinstance(checks, list) else []:
            if isinstance(item, dict) and item.get("check") == "reachability":
                reach = item
                break
        finding = (reach or {}).get("finding", "")
        if not _nonempty_str(finding):
            errs.append(
                f"{prefix}: empty contacts requires reachability.finding explaining "
                "no public contact channel"
            )
    else:
        for i, item in enumerate(contacts):
            if not isinstance(item, dict):
                errs.append(f"{prefix}: contacts[{i}] must be an object")
                continue
            if item.get("channel") not in ("email", "phone", "linkedin", "website_form"):
                errs.append(f"{prefix}: contacts[{i}].channel invalid")
            if not _nonempty_str(item.get("value")):
                errs.append(f"{prefix}: contacts[{i}].value must be non-empty")
            if not _looks_like_uri(item.get("source")):
                errs.append(f"{prefix}: contacts[{i}].source must be an http(s) URL")
            if item.get("confidence") not in ("high", "medium", "low"):
                errs.append(f"{prefix}: contacts[{i}].confidence must be high|medium|low")

    if disposition == "main" and record.get("risk_level") == "high":
        errs.append(f"{prefix}: disposition=main cannot have risk_level=high (use excluded)")

    return errs


def check_competitor_evidence(record: dict[str, Any], line_no: int) -> list[str]:
    errs: list[str] = []
    prefix = f"L{line_no}"
    evidence = record.get("segment_evidence")
    if not isinstance(evidence, list) or len(evidence) < 1:
        errs.append(f"{prefix}: disposition=competitor requires non-empty segment_evidence")
        return errs
    for i, item in enumerate(evidence):
        errs.extend(check_evidence_item(item, prefix, f"segment_evidence[{i}]"))
    if not any(isinstance(item, dict) and item.get("signal") == "supply_side" for item in evidence):
        errs.append(f"{prefix}: disposition=competitor requires ≥1 supply_side segment_evidence")
    return errs


def builtin_check(record: dict[str, Any], line_no: int) -> list[str]:
    errs: list[str] = []
    prefix = f"L{line_no}"

    for key in ("company", "country", "sources", "stage", "disposition"):
        if key not in record:
            errs.append(f"{prefix}: missing required field '{key}'")

    stage = record.get("stage")
    disposition = record.get("disposition")

    if stage is not None and stage not in STAGES:
        errs.append(f"{prefix}: invalid stage {stage!r}")
    if disposition is not None and disposition not in DISPOSITIONS:
        errs.append(f"{prefix}: invalid disposition {disposition!r}")

    sources = record.get("sources")
    if sources is not None and (not isinstance(sources, list) or len(sources) < 1):
        errs.append(f"{prefix}: sources must be a non-empty array")
    elif isinstance(sources, list):
        for i, src in enumerate(sources):
            if not _looks_like_uri(src):
                errs.append(f"{prefix}: sources[{i}] must be an http(s) URL")

    segment = record.get("segment")
    if segment is not None and segment not in SEGMENTS:
        errs.append(f"{prefix}: invalid segment {segment!r} (use taxonomy keys)")

    if disposition in EXCLUSION_DISPOSITIONS and not _nonempty_str(record.get("exclusion_reason")):
        errs.append(f"{prefix}: disposition={disposition} requires exclusion_reason")

    if disposition in DELIVERY_DISPOSITIONS:
        if stage != "scored":
            errs.append(f"{prefix}: disposition={disposition} requires stage=scored")
        errs.extend(check_delivery_evidence(record, line_no))

    if disposition == "competitor":
        errs.extend(check_competitor_evidence(record, line_no))

    if disposition == "pending" and stage in STAGE_FIELDS:
        for key in STAGE_FIELDS[stage]:
            if key not in record:
                errs.append(f"{prefix}: stage={stage} pending record missing '{key}'")
        if stage in ("screened", "diligenced", "verified", "scored"):
            evidence = record.get("segment_evidence")
            if not evidence:
                errs.append(f"{prefix}: stage={stage} requires segment_evidence")

    breakdown = record.get("score_breakdown")
    if isinstance(breakdown, dict) and "score" in record:
        for part in ("fit", "volume", "activity", "accessibility", "region_weight"):
            block = breakdown.get(part)
            if not isinstance(block, dict) or "value" not in block or "basis" not in block:
                errs.append(f"{prefix}: score_breakdown.{part} needs value + basis")

    return errs


def check_score_math(record: dict[str, Any], weights: dict[str, float], line_no: int) -> list[str]:
    breakdown = record.get("score_breakdown")
    score = record.get("score")
    if not isinstance(breakdown, dict) or not isinstance(score, (int, float)):
        return []
    try:
        fit = float(breakdown["fit"]["value"])
        volume = float(breakdown["volume"]["value"])
        activity = float(breakdown["activity"]["value"])
        accessibility = float(breakdown["accessibility"]["value"])
        region_weight = float(breakdown["region_weight"]["value"])
    except (KeyError, TypeError, ValueError):
        return [f"L{line_no}: score_breakdown values not numeric"]

    total_w = sum(weights.get(k, 0) for k in ("fit", "volume", "activity", "accessibility"))
    if total_w <= 0:
        return [f"L{line_no}: scoring.weights sum to 0"]
    # Match segmentation.md: normalize when sum != 1 (±0.01).
    scale = 1.0 if abs(total_w - 1.0) <= 0.01 else 1.0 / total_w
    expected = (
        weights.get("fit", 0) * scale * fit
        + weights.get("volume", 0) * scale * volume
        + weights.get("activity", 0) * scale * activity
        + weights.get("accessibility", 0) * scale * accessibility
    ) * region_weight
    if abs(expected - float(score)) > 0.01:
        return [f"L{line_no}: score {score} != recomputed {expected:.4f} from breakdown × weights"]
    return []


def load_weights(config_path: Path) -> dict[str, float] | None:
    text = config_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        weights = (data or {}).get("scoring", {}).get("weights", {})
        if isinstance(weights, dict) and weights:
            return {k: float(v) for k, v in weights.items()}
    except ImportError:
        # Minimal YAML scrape for scoring.weights.* floats
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"warning: failed to parse {config_path}: {exc}", file=sys.stderr)
        return None

    weights: dict[str, float] = {}
    in_weights = False
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].rstrip()
        if stripped.strip() == "weights:":
            in_weights = True
            continue
        if in_weights:
            if stripped and not stripped.startswith(" ") and not stripped.startswith("\t"):
                break
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if key and val:
                    try:
                        weights[key] = float(val)
                    except ValueError:
                        pass
    return weights or None


def validate_file(path: Path, config: Path | None) -> int:
    schema = load_schema()
    weights = load_weights(config) if config and config.is_file() else None
    if config and weights is None:
        print(f"warning: could not load scoring.weights from {config}", file=sys.stderr)

    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2

    errors: list[str] = []
    companies: dict[str, int] = {}
    with path.open(encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"L{line_no}: invalid JSON ({exc})")
                continue
            if not isinstance(record, dict):
                errors.append(f"L{line_no}: record must be a JSON object")
                continue

            js_errs = try_jsonschema(record, schema)
            errors.extend(f"L{line_no}: {e}" for e in js_errs)
            errors.extend(builtin_check(record, line_no))
            if weights and record.get("disposition") in DELIVERY_DISPOSITIONS:
                errors.extend(check_score_math(record, weights, line_no))

            company = str(record.get("company", "")).strip().lower()
            if company:
                if company in companies:
                    errors.append(
                        f"L{line_no}: duplicate company {record.get('company')!r} "
                        f"(also L{companies[company]})"
                    )
                else:
                    companies[company] = line_no

    if errors:
        print(f"FAIL: {path} ({len(errors)} issue(s))")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"OK: {path} ({len(companies)} candidate(s))")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path, help="Path to candidates.jsonl")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional leads.yaml to recompute score from weights",
    )
    args = parser.parse_args()
    return validate_file(args.candidates, args.config)


if __name__ == "__main__":
    sys.exit(main())
