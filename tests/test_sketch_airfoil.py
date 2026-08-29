from ai_cad.feature_tree import SketchEntity
from ai_cad.sketch_solver import solve_sketch


def test_airfoil_entity():
    entities = [SketchEntity(type="airfoil", id="af1", naca="2412", chord=200.0)]
    result = solve_sketch(entities, [])
    assert "af1" in result.points
    assert len(result.points["af1"]) > 10
