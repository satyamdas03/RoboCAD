from ai_cad.feature_tree import (
    Assembly,
    Feature,
    FeatureTree,
    KinematicJoint,
    PCBOutline,
    Part,
    SurfaceFeature,
)


def test_default_domain_is_mechanical():
    tree = FeatureTree(
        design_id="d1",
        prompt="bracket",
        parameters=[{"name": "thickness", "value": 3.0}],
        features=[{"type": "extrude", "id": "f1", "sketch_id": "s1", "depth": 10.0}],
    )
    assert tree.features[0].domain == "mechanical"


def test_aero_surface_feature():
    tree = FeatureTree(
        design_id="d2",
        prompt="airfoil",
        parameters=[{"name": "chord", "value": 200.0}],
        features=[
            SurfaceFeature(
                id="af1",
                type="airfoil",
                profile={"naca": "2412", "chord_param": "chord"},
            ).model_dump()
        ],
    )
    assert tree.features[0].domain == "aero"


def test_kinematic_joint_in_assembly():
    asm = Assembly(
        id="a1",
        name="arm",
        parts=[],
        mates=[],
        joints=[
            KinematicJoint(
                id="j1",
                type="revolute",
                parent_link="base",
                child_link="link1",
                origin=(0, 0, 0),
                axis=(0, 0, 1),
            )
        ],
    )
    assert asm.joints[0].type == "revolute"


def test_pcb_outline():
    pcb = PCBOutline(
        id="pcb1",
        board_shape=[(0, 0), (85, 0), (85, 56), (0, 56)],
        mounting_holes=[(3.5, 3.5, 3.0)],
    )
    assert pcb.domain == "electronics"


def test_part_carries_domain():
    part = Part(id="p1", domain="aero")
    assert part.domain == "aero"


def test_feature_tree_schema_version_bumped():
    tree = FeatureTree(design_id="d3", prompt="test")
    assert tree.schema_version == "2.0.0"
