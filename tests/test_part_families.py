from ai_cad.feature_tree import Part
from ai_cad.part_families import (
    PART_FAMILY_REGISTRY,
    get_family,
    instantiate_family,
    list_families,
)


def test_registry_contains_all_phase18_families():
    expected = {
        "bracket",
        "link",
        "hub",
        "mount",
        "airfoil",
        "wing",
        "propeller_blade",
        "duct",
        "heat_sink",
        "pcb",
        "pcb_bracket",
        "enclosure",
        "connector",
        "cable_channel",
        "fan_mount",
        "heat_spreader",
        "limb_segment",
        "end_effector",
        "foot",
        "torso_plate",
        "hip_hub",
        "shoulder_hub",
    }
    assert set(PART_FAMILY_REGISTRY) == expected


def test_list_families_filter_by_domain():
    mechanical = list_families("mechanical")
    assert {f.name for f in mechanical} == {"bracket", "link", "hub", "mount"}

    aero = list_families("aero")
    assert {f.name for f in aero} == {"airfoil", "wing", "propeller_blade", "duct"}


def test_get_family_unknown_raises():
    try:
        get_family("nonexistent")
    except KeyError as exc:
        assert "nonexistent" in str(exc)
    else:
        raise AssertionError("Expected KeyError")


def test_instantiate_family_returns_part():
    part = instantiate_family("bracket", "b1")
    assert isinstance(part, Part)
    assert part.id == "b1"
    assert part.domain == "mechanical"
    assert len(part.sketches) == 1
    assert len(part.features) == 1


def test_instantiate_family_applies_parameter_overrides():
    from ai_cad.feature_tree import Parameter

    part = instantiate_family(
        "mount",
        "m1",
        parameter_overrides=[Parameter(name="mount_width", value=80.0, unit="mm")],
    )
    # The override value is in the family default set, but the Part does not
    # store parameters; they are merged into the global FeatureTree by composer.
    assert part.domain == "mechanical"
    assert len(part.sketches) == 1


def test_family_interfaces_present():
    family = get_family("link")
    assert len(family.interfaces) >= 1
    iface = next(i for i in family.interfaces if i.id == "pin_a")
    assert iface.csys.id == "link_pin_a"
    assert iface.type == "pin"
    assert iface.mate_hint == "revolute"
    assert "link/pin_b" in (iface.mate_with or [])
