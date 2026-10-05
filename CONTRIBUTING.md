# Contributing to RenderLens

Thanks for helping. Keep changes small and honest.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env   # add GEMINI_API_KEY
pytest
```

## Guidelines

- Multimodal path must stay essential: if removing the screenshot still "works", rethink the change.
- Don't claim Agent Skill compliance or local Gemma 4 support without tests.
- Prefer deterministic checks for contrast; keep model-observed findings labeled unverified.
- Human comments only where the "why" isn't obvious.

## Pull requests

1. Fork + branch from `main`
2. Add/adjust tests when you touch contrast math or parsing
3. Update README if behavior changes
4. Open a PR with a short before/after note

## Good first issues

See the issue tracker labels (`good first issue`).
