"""Markdown + self-contained HTML reports."""

from __future__ import annotations

import base64
import html
import io
from pathlib import Path
from typing import Optional

from PIL import Image

from renderlens.schema import AuditReport, Finding, Tier
from renderlens.visuals import annotate_image, auto_fix_preview, save_image


def _b64_png(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def findings_md(title: str, items: list[Finding]) -> str:
    lines = [f"### {title} ({len(items)})", ""]
    if not items:
        lines.append("_None._")
        lines.append("")
        return "\n".join(lines)
    for f in items:
        ratio = f"{f.contrast_ratio:.2f}:1" if f.contrast_ratio is not None else "n/a"
        lines.append(
            f"- **[{f.severity.value}] {f.category}** — {f.description} "
            f"(contrast {ratio}; {f.fix_detail or f.drop_reason or f.fix_kind or ''})"
        )
    lines.append("")
    return "\n".join(lines)


def write_markdown(report: AuditReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        f"# RenderLens audit — `{Path(report.image_path).name}`",
        "",
        f"- Model: `{report.model}`",
        f"- Backend: `{report.meta.get('backend')}`",
        f"- Latency: {report.latency_ms:.0f} ms",
        f"- Zoom rounds: {report.zoom_rounds}",
        f"- Localization: `{report.localization_mode}`",
        "",
        findings_md("Verified (math-confirmed)", report.verified),
        findings_md(
            "Model-observed (unverified visual findings)", report.model_observed
        ),
        findings_md("Dropped (contradicted by math)", report.dropped),
        "## Honesty note",
        "",
        "Verified-tier contrast precision is correct *by construction* "
        "(same WCAG math as ground truth). Model-observed findings are labeled "
        "unverified — two-pass agreement is the same model agreeing with itself.",
        "",
    ]
    path.write_text("\n".join(body), encoding="utf-8")
    return path


def write_html(
    report: AuditReport,
    path: Path,
    *,
    annotated: Optional[Image.Image] = None,
    fixed: Optional[Image.Image] = None,
    fix_detail: str = "",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    src = Image.open(report.image_path).convert("RGB")
    if annotated is None:
        annotated = annotate_image(
            src, [f for f in report.findings if f.tier != Tier.DROPPED]
        )

    def section(title: str, items: list[Finding]) -> str:
        rows = []
        for f in items:
            ratio = f"{f.contrast_ratio:.2f}:1" if f.contrast_ratio is not None else "—"
            rows.append(
                "<tr>"
                f"<td>{html.escape(f.severity.value)}</td>"
                f"<td>{html.escape(f.category)}</td>"
                f"<td>{html.escape(f.description)}</td>"
                f"<td>{ratio}</td>"
                f"<td>{html.escape(f.fix_detail or f.drop_reason or '')}</td>"
                "</tr>"
            )
        body = "".join(rows) or "<tr><td colspan=5><em>None</em></td></tr>"
        return (
            f"<h2>{html.escape(title)} ({len(items)})</h2>"
            "<table><thead><tr>"
            "<th>Severity</th><th>Category</th><th>Description</th>"
            "<th>Contrast</th><th>Notes</th></tr></thead>"
            f"<tbody>{body}</tbody></table>"
        )

    fix_block = ""
    if fixed is not None:
        fix_block = (
            "<h2>Auto-fix preview</h2>"
            f"<p>{html.escape(fix_detail)}</p>"
            f'<img alt="auto-fix" src="data:image/png;base64,{_b64_png(fixed)}"/>'
        )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>RenderLens — {html.escape(Path(report.image_path).name)}</title>
<style>
  body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background:#0b0f14; color:#e8eef7; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }}
  th, td {{ border: 1px solid #2a3544; padding: 0.5rem; text-align: left; }}
  th {{ background: #151b24; }}
  img {{ max-width: 100%; border-radius: 8px; margin: 0.5rem 0 1.5rem; }}
  code {{ color: #9ad; }}
  .muted {{ color: #9aa7b8; }}
</style>
</head>
<body>
<h1>RenderLens audit</h1>
<p class="muted">Model <code>{html.escape(report.model)}</code> ·
{report.latency_ms:.0f} ms · zoom rounds {report.zoom_rounds}</p>
<h2>Annotated screenshot</h2>
<img alt="annotated" src="data:image/png;base64,{_b64_png(annotated)}"/>
{fix_block}
{section("Verified (math-confirmed)", report.verified)}
{section("Model-observed (unverified)", report.model_observed)}
{section("Dropped", report.dropped)}
<p class="muted">Verified contrast precision is correct by construction (same WCAG math).
Model-observed findings stay labeled unverified.</p>
</body></html>
"""
    path.write_text(doc, encoding="utf-8")
    return path


def emit_artifacts(
    report: AuditReport,
    out_dir: Path,
) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src = Image.open(report.image_path).convert("RGB")
    keep = [f for f in report.findings if f.tier != Tier.DROPPED]
    annotated = annotate_image(src, keep)
    ann_path = save_image(annotated, out_dir / "annotated.png")

    fixed = None
    fix_detail = ""
    # prefer first verified text_over_image / contrast for auto-fix demo
    target = next(
        (f for f in report.verified if f.category in ("text_over_image", "contrast")),
        None,
    )
    if target:
        fixed, fix_detail = auto_fix_preview(src, target)
        save_image(fixed, out_dir / "autofix.png")

    md = write_markdown(report, out_dir / "report.md")
    html_path = write_html(
        report, out_dir / "report.html", annotated=annotated, fixed=fixed, fix_detail=fix_detail
    )
    (out_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return {
        "annotated": ann_path,
        "markdown": md,
        "html": html_path,
        "json": out_dir / "report.json",
    }
