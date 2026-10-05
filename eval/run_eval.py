"""Three-way eval with temperature 0 + raw response dumps.

Baseline = deterministic engine on fixed tile grid (no Gemma).
Gemma-unverified = model proposals before math tiers.
Full = tiered pipeline.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

from renderlens.backends import GeminiGemmaBackend
from renderlens.contrast import passes_aa, sample_region, tile_boxes
from renderlens.pipeline import run_audit


ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "dataset"
RAW = ROOT / "raw_responses"
OUT = ROOT / "results.json"


def pixel_only_baseline(image_path: Path) -> list[dict]:
    """Deterministic tile-grid contrast scan — no model.

    This is intentionally limited (no text localization). Documented as such.
    """
    img = Image.open(image_path).convert("RGB")
    hits = []
    for i, box in enumerate(tile_boxes(*img.size, 4, 4)):
        sampled = sample_region(img, box, bg_mode="worst")
        if not passes_aa(sampled.ratio):
            hits.append({"tile": i, "ratio": round(sampled.ratio, 2)})
    return hits


def main() -> None:
    import argparse
    import time as _time

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="max images (0=all)")
    parser.add_argument(
        "--ids",
        default="",
        help="comma-separated ids or prefixes, e.g. solid_00,sky_00 or solid,sky",
    )
    args = parser.parse_args()

    load_dotenv()
    index = json.loads((DATASET / "index.json").read_text(encoding="utf-8"))
    if args.ids:
        prefixes = [p.strip() for p in args.ids.replace(";", ",").split(",") if p.strip()]
        index = [
            it
            for it in index
            if any(it["id"] == p or it["id"].startswith(p + "_") or it["id"].startswith(p)
                   for p in prefixes)
        ]
        # de-dupe while preserving order when both exact and prefix match
        seen = set()
        deduped = []
        for it in index:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            deduped.append(it)
        index = deduped
    if args.limit and args.limit > 0:
        index = index[: args.limit]
    print(f"eval_n={len(index)} ids={[it['id'] for it in index]}")
    backend = GeminiGemmaBackend()
    RAW.mkdir(parents=True, exist_ok=True)

    rows = []
    for item in index:
        path = DATASET / item["file"]
        t0 = time.perf_counter()
        baseline = pixel_only_baseline(path)
        baseline_ms = (time.perf_counter() - t0) * 1000

        report = None
        last_err = None
        for attempt in range(3):
            try:
                report = run_audit(
                    path,
                    backend,
                    temperature=0.0,
                    max_zoom_rounds=0,
                    use_second_pass=False,
                    raw_dump_dir=RAW,
                )
                break
            except Exception as exc:  # noqa: BLE001 — eval must survive flaky API
                last_err = exc
                print(f"retry {item['id']} attempt={attempt+1} err={exc}")
                _time.sleep(2 + attempt * 3)
        if report is None:
            rows.append(
                {
                    "id": item["id"],
                    "kind": item["kind"],
                    "expected_defects": sorted(item.get("defects") or []),
                    "error": str(last_err),
                }
            )
            continue

        expected = set(item.get("defects") or [])
        verified_cats = {f.category for f in report.verified}
        observed_cats = {f.category for f in report.model_observed}
        found = verified_cats | observed_cats
        visual_expected = expected & {
            "truncation",
            "hierarchy",
            "color_only",
            "text_over_image",
        }
        visual_hit = len(visual_expected & found)
        visual_total = len(visual_expected)

        rows.append(
            {
                "id": item["id"],
                "kind": item["kind"],
                "expected_defects": sorted(expected),
                "baseline_low_contrast_tiles": len(baseline),
                "baseline_ms": round(baseline_ms, 1),
                "verified": [f.category for f in report.verified],
                "model_observed": [f.category for f in report.model_observed],
                "dropped": [f.category for f in report.dropped],
                "latency_ms": round(report.latency_ms, 1),
                "visual_recall_num": visual_hit,
                "visual_recall_den": visual_total,
                "zoom_rounds": report.zoom_rounds,
            }
        )
        print(item["id"], "verified", len(report.verified), "obs", len(report.model_observed))

    vis_n = sum(r.get("visual_recall_num", 0) for r in rows)
    vis_d = sum(r.get("visual_recall_den", 0) for r in rows)
    summary = {
        "note": (
            "Verified contrast precision is correct by construction (same WCAG math). "
            "Baseline = tile-grid deterministic scan without text localization. "
            "Visual recall uses synthetic injected defects. "
            "This run used max_zoom=0 and no second-pass for speed/rate-limits."
        ),
        "n_images": len(rows),
        "visual_recall": (vis_n / vis_d) if vis_d else None,
        "rows": rows,
    }
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
