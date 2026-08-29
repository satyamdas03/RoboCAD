from ai_cad.intent_parser import parse_domain_intent


def test_mechanical_intent(monkeypatch):
    monkeypatch.setattr(
        "ai_cad.intent_parser._llm_extract",
        lambda p, d: {
            "parameters": [{"name": "length", "value": 120.0, "unit": "mm"}],
            "features": [{"type": "extrude", "id": "f1"}],
            "constraints": [],
            "notes": [],
            "confidence": 0.9,
        },
    )
    intent = parse_domain_intent("A 120 mm bracket", domain="mechanical")
    assert intent.domain == "mechanical"
    assert intent.parameters[0].name == "length"


def test_fallback_to_mechanical(monkeypatch):
    from ai_cad.domain import DomainPrediction

    monkeypatch.setattr(
        "ai_cad.intent_parser.classify_domain",
        lambda p: DomainPrediction(
            primary="aero",
            scores={"mechanical": 0.0, "aero": 1.0},
            reasoning="mock",
            multi_domain=False,
        ),
    )
    intent = parse_domain_intent("some random text")
    assert intent.domain == "mechanical"
    assert intent.confidence == 0.0
