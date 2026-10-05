from renderlens.parse import extract_json_object, parse_model_turn


def test_extract_fenced_json():
    text = """```json
{"findings": [], "request_crop": null, "notes": "ok"}
```"""
    data = extract_json_object(text)
    assert data is not None
    assert data["notes"] == "ok"


def test_parse_model_turn_findings():
    raw = '{"findings":[{"id":"f1","category":"contrast","severity":"serious","description":"low","bbox":{"x":0.1,"y":0.2,"w":0.3,"h":0.1}}],"request_crop":null}'
    turn = parse_model_turn(raw)
    assert len(turn.findings) == 1
    assert turn.findings[0].id == "f1"
