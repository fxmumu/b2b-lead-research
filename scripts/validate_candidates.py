#!/usr/bin/env python3
"""Validate lead-research/candidates.jsonl against assets/lead-schema.json.

Checks:
  - each line is JSON and matches the schema (Draft 2020-12 subset via jsonschema if
    installed; otherwise a built-in structural check covering required fields,
    enums, and disposition/stage gates)
  - stage-gated field presence for in-pipeline (pending) records
  - exclusion_reason when disposition is an exclusion class
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
        "risk_level",
        "due_diligence_summary",
        "contacts",
    ),
    "scored": (
        "segment",
        "risk_level",
        "score",
        "score_breakdown",
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

    segment = record.get("segment")
    if segment is not None and segment not in SEGMENTS:
        errs.append(f"{prefix}: invalid segment {segment!r} (use taxonomy keys)")

    if disposition in EXCLUSION_DISPOSITIONS and not record.get("exclusion_reason"):
        errs.append(f"{prefix}: disposition={disposition} requires exclusion_reason")

    if disposition in ("main", "backup"):
        if stage != "scored":
            errs.append(f"{prefix}: disposition={disposition} requires stage=scored")
        for key in ("score", "score_breakdown", "risk_level", "segment"):
            if key not in record:
                errs.append(f"{prefix}: disposition={disposition} requires '{key}'")

    if disposition == "pending" and stage in STAGE_FIELDS:
        for key in STAGE_FIELDS[stage]:
            if key not in record:
                errs.append(f"{prefix}: stage={stage} pending record missing '{key}'")
        # Competitors may stop at screened without segment; pending screened needs demand-side evidence.
        if stage != "discovered" and stage in ("screened", "diligenced", "verified", "scored"):
            evidence = record.get("segment_evidence")
            if stage in ("screened", "diligenced") and not evidence:
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
            if weights:
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
