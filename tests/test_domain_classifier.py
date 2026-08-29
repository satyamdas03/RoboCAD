from ai_cad.domain import classify_domain


def test_mechanical_prompt():
    result = classify_domain("A 120 mm bracket with four M3 holes")
    assert result.primary == "mechanical"
    assert result.scores["mechanical"] > 0.7
    assert not result.multi_domain


def test_aero_prompt():
    result = classify_domain("NACA 2412 airfoil with 200 mm chord")
    assert result.primary == "aero"
    assert result.scores["aero"] > 0.7


def test_multi_domain_prompt():
    result = classify_domain("450 mm quadcopter frame with motor arms and aerodynamic shell")
    assert result.multi_domain
    assert "mechanical" in result.scores
    assert "aero" in result.scores
