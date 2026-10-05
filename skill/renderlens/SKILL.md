---
name: renderlens
description: Audit UI screenshots for rendered accessibility issues using Gemma 4 multimodal reasoning plus deterministic WCAG contrast math. Use when the user shares a screenshot or asks about visual contrast, text-over-image, truncation, hierarchy, or color-only meaning that DOM linters miss.
license: MIT
compatibility: Requires Python 3.10+, renderlens CLI installed, and GEMINI_API_KEY for the default Gemma 4 (Gemini API) backend. Optional Ollama + gemma3:4b for local Gemma 3 (not Gemma 4).
metadata:
  author: rajgharat0772
  open_standard: https://agentskills.io/specification
---

# RenderLens

## When to use

- User provides a UI screenshot and wants accessibility findings grounded in pixels.
- DOM-only tools (axe) are incomplete for text over images/gradients.
- User asks to measure contrast, propose a scrim/recolor fix, or produce an HTML a11y report.

## How to run

```bash
# from the renderlens repo root, with GEMINI_API_KEY set
pip install -e .
renderlens audit path/to/screenshot.png --out out/run
```

Then read `out/run/report.md` and open `out/run/report.html`.

## Output rules

- Separate **verified** (math-confirmed contrast) from **model-observed** (unverified) findings.
- Never claim axe "passed" without evidence; axe often marks text-over-image as incomplete/needs-review.
- Never call the Ollama backend Gemma 4 — it is Gemma 3 if configured.
- Prefer the annotated PNG + auto-fix preview in demos.

## Compliance

This folder follows the Agent Skills Open Standard (`name` + `description` frontmatter, directory name matches `name`). See https://agentskills.io/specification.
