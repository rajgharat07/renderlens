# Evaluation

## What we measure

RenderLens ships a small synthetic dataset (`eval/generate_dataset.py`, 40 images) with known injected defects:

- low-contrast text on solid backgrounds
- white text over bright gradients
- truncation
- weak hierarchy
- color-only status indicators
- clean controls with no injected defect

## Pipeline comparison

The eval harness compares:

1. **Pixel baseline** — deterministic WCAG sampling on a fixed tile grid (no text localization)
2. **Gemma proposals** — model findings before / without full tier filtering in the per-row fields
3. **Full RenderLens pipeline** — verified / model-observed / dropped tiers

Gemma calls use temperature `0`. Raw responses are stored under `eval/raw_responses/`.

Verified contrast findings use the same WCAG math as the ground-truth check, so that tier’s contrast calls match the math by design.

## Latest results

Source: `eval/results.json` (12-image subset, `gemma-4-26b-a4b-it`, max zoom 0, no second pass).

| Slice | Result |
| --- | --- |
| `solid_*` low contrast | verified contrast 2/2 |
| `sky_*` text over gradient | verified contrast 2/2 |
| truncation / hierarchy / color-only | model-observed 6/6 |
| `ok_*` clean controls | verified 0, observed 0 |
| Visual-only recall (as reported in JSON) | 0.75 |

Demo screenshot `examples/screenshots/demo_hero.png` was also run live: 2 verified critical contrast findings, with annotated and auto-fix outputs under `docs/assets/`.

## Reproduce

```bash
python eval/generate_dataset.py
python eval/run_eval.py --ids "solid_00;sky_00;trunc_00;hier_00;color_00;ok_00;solid_01;sky_01;trunc_01;hier_01;color_01;ok_01"
```

Inspect `eval/results.json` and `eval/raw_responses/`.

## Limitations

- The tile-grid baseline does not know where text is, so it is a weak baseline on purpose.
- Bounding boxes from the model can be imperfect; sampling follows those boxes.
- Model-observed findings are not independently verified.
- API rate limits / failures can force partial runs; the JSON notes when that happens.
