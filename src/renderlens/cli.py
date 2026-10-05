from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from renderlens.backends import GeminiGemmaBackend, OllamaGemma3Backend
from renderlens.pipeline import run_audit
from renderlens.report import emit_artifacts

app = typer.Typer(add_completion=False, no_args_is_help=True, help="RenderLens — Gemma sees the render.")


def _backend(name: str, model: Optional[str]):
    if name == "ollama":
        return OllamaGemma3Backend(model=model or "gemma3:4b")
    return GeminiGemmaBackend(model=model or "gemma-4-26b-a4b-it")


@app.command()
def audit(
    image: Path = typer.Argument(..., exists=True, readable=True, help="UI screenshot"),
    out: Path = typer.Option(Path("out"), "--out", "-o", help="Output directory"),
    backend: str = typer.Option("gemini", "--backend", help="gemini | ollama"),
    model: Optional[str] = typer.Option(None, "--model"),
    localization: str = typer.Option("bbox", "--localization", help="bbox | tile_grid"),
    bg_mode: str = typer.Option("worst", "--bg-mode", help="solid | worst | p5"),
    max_zoom: int = typer.Option(2, "--max-zoom"),
    no_second_pass: bool = typer.Option(False, "--no-second-pass"),
    raw_dump: Optional[Path] = typer.Option(None, "--raw-dump", help="Save raw model turns"),
):
    """Audit a screenshot and write annotated + HTML + markdown reports."""
    load_dotenv()
    if backend == "gemini" and not os.environ.get("GEMINI_API_KEY"):
        typer.echo("GEMINI_API_KEY missing — set it in .env or the environment.", err=True)
        raise typer.Exit(2)

    b = _backend(backend, model)
    report = run_audit(
        image,
        b,
        temperature=0.0,
        max_zoom_rounds=max_zoom,
        use_second_pass=not no_second_pass,
        localization_mode="tile_grid" if localization == "tile_grid" else "bbox",  # type: ignore[arg-type]
        bg_mode=bg_mode if bg_mode in ("solid", "worst", "p5") else "worst",  # type: ignore[arg-type]
        raw_dump_dir=raw_dump,
    )
    paths = emit_artifacts(report, out)
    typer.echo(f"verified={len(report.verified)} observed={len(report.model_observed)} dropped={len(report.dropped)}")
    typer.echo(f"html={paths['html']}")
    # CI-friendly: fail on verified critical/serious
    bad = [f for f in report.verified if f.severity.value in ("critical", "serious")]
    raise typer.Exit(1 if bad else 0)


@app.command("version")
def version_cmd():
    from renderlens import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
