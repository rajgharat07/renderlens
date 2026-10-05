SYSTEM_HINT = """You audit UI screenshots for accessibility problems that appear in the RENDERED pixels.
Focus on: low contrast text, text over busy images/gradients, truncated labels, broken visual hierarchy, color-only meaning.
Ignore pure DOM issues you cannot see (missing alt without an image visible, etc.).
Return ONLY valid JSON matching the schema. No markdown fences.
"""

AUDIT_SCHEMA_HINT = """
JSON schema:
{
  "findings": [
    {
      "id": "f1",
      "category": "contrast|text_over_image|truncation|hierarchy|color_only|tap_target|other",
      "severity": "critical|serious|moderate|minor",
      "description": "short human explanation",
      "bbox": {"x":0.0,"y":0.0,"w":0.2,"h":0.05,"coords_mode":"normalized"},
      "fg_hex": "#ffffff",
      "bg_hex": "#333333",
      "evidence": "what you see"
    }
  ],
  "request_crop": null,
  "notes": ""
}
bbox is normalized 0-1 relative to the full image (x,y = top-left).
If a region is too small to judge, set request_crop instead of guessing:
"request_crop": {"reason":"...", "bbox": {"x":..,"y":..,"w":..,"h":..,"coords_mode":"normalized"}}
Prefer at most one request_crop per turn.
"""


def first_pass_prompt() -> str:
    return (
        SYSTEM_HINT
        + AUDIT_SCHEMA_HINT
        + "\nAudit this screenshot. Propose findings with tight bboxes around the text/UI at risk.\n"
    )


def zoom_followup_prompt(prior_json: str) -> str:
    return (
        SYSTEM_HINT
        + AUDIT_SCHEMA_HINT
        + "\nThis is a ZOOMED crop of a region you asked for.\n"
        + "Prior turn JSON (for context):\n"
        + prior_json
        + "\nRe-judge only this crop. Update/confirm findings. Set request_crop to null unless still needed.\n"
    )


def second_pass_prompt(prior_json: str) -> str:
    return (
        SYSTEM_HINT
        + AUDIT_SCHEMA_HINT
        + "\nSecond look at the SAME full screenshot. Keep only findings you still believe.\n"
        + "Prior findings JSON:\n"
        + prior_json
        + "\nReturn a cleaned findings list. request_crop must be null.\n"
    )


def tile_flag_prompt(cols: int, rows: int) -> str:
    return (
        SYSTEM_HINT
        + f"\nThe image is divided into a {cols}x{rows} grid, tiles numbered row-major starting at 0.\n"
        + "Return JSON: {\"bad_tiles\": [0,3,5], \"notes\": \"...\"} listing tiles with a11y problems.\n"
        + "No markdown.\n"
    )
