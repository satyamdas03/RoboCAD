import pytest

from ai_cad.assembly import transpile_assembly
from ai_cad.composer import compose_feature_tree
from ai_cad.decomposition import decompose
from ai_cad.executor import execute_code


def test_compose_quadcopter_feature_tree():
    result = decompose("450 mm quadcopter with four motor arms", use_llm=False)
    tree = compose_feature_tree(result)

    assert tree.schema_version == "2.0.0"
    assert len(tree.parts) == 3
    assert tree.domain == "mechanical"
    assert len(tree.assemblies) == 1

    assembly = tree.assemblies[0]
    assert len(assembly.instances) == 9  # hub + 4 arms + 4 mounts
    # Layout mates are preserved; inferred hub-mount mates add 4 more.
    assert len(assembly.mates) >= 8
    assert all(len(m.entities) == 2 for m in assembly.mates)


def test_compose_quadcopter_transpiles_and_executes(tmp_path):
    result = decompose("450 mm quadcopter with four motor arms", use_llm=False)
    tree = compose_feature_tree(result)
    code = transpile_assembly(tree)

    assert "from build123d import *" in code
    assert "part_0" in code
    assert "Compound(children=[" in code

    exec_result = execute_code(code, output_dir=tmp_path, timeout=120)
    assert exec_result["success"] is True
    assert exec_result["stl_path"] is not None


def test_compose_robot_arm_executes(tmp_path):
    result = decompose("robot arm with gripper", use_llm=False)
    tree = compose_feature_tree(result)
    code = transpile_assembly(tree)
    exec_result = execute_code(code, output_dir=tmp_path, timeout=120)
    assert exec_result["success"] is True


def test_compose_robot_arm_has_prismatic_gripper():
    """The default robot arm layout now produces a parallel-jaw prismatic gripper."""
    result = decompose("robot arm with gripper", use_llm=False)
    tree = compose_feature_tree(result)
    assembly = tree.assemblies[0]

    gripper_mates = [m for m in assembly.mates if m.id.startswith("m_gripper_")]
    assert len(gripper_mates) == 2
    assert all(m.type == "prismatic" for m in gripper_mates)

    gripper_joints = [j for j in assembly.joints if j.parent_link == "i_forearm_link" or j.child_link.startswith("i_gripper")]
    assert len(gripper_joints) == 2
    assert all(j.type == "prismatic" for j in gripper_joints)
    assert all(j.limits == pytest.approx((0.0, 15.0)) for j in gripper_joints)


def test_compose_quadcopter_with_aero_shell_executes(tmp_path):
    """Regression: duct-family shell feature used an undefined 'part' variable in assemblies."""
    result = decompose("450 mm quadcopter with four motor arms and an aerodynamic shell", use_llm=False)
    assert result.multi_domain is True
    assert any(p.family == "duct" for p in result.parts)

    tree = compose_feature_tree(result)
    code = transpile_assembly(tree)
    # Duct is now a hollow tube via outer + inner subtract, not Shell.
    assert "extrude(duct_outer.sketch" in code
    assert "extrude(duct_inner.sketch" in code
    assert "Mode.SUBTRACT" in code
    assert "part_3.part" in code

    exec_result = execute_code(code, output_dir=tmp_path, timeout=120)
    assert exec_result["success"] is True
    assert exec_result["stl_path"] is not None


def test_compose_global_parameters_include_defaults():
    result = decompose("450 mm quadcopter with four motor arms", use_llm=False)
    tree = compose_feature_tree(result)
    names = {p.name for p in tree.parameters}
    # Defaults from all three part families are present.
    assert "hub_diameter" in names
    assert "link_length" in names
    assert "mount_width" in names


def test_compose_validates_tree():
    result = decompose("robot arm with gripper", use_llm=False)
    tree = compose_feature_tree(result)
    errors = tree.validate_tree()
    assert errors == []
