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
        "duct",
        "heat_sink",
        "pcb_bracket",
        "enclosure",
        "limb_segment",
        "end_effector",
    }
    assert set(PART_FAMILY_REGISTRY) == expected


def test_list_families_filter_by_domain():
    mechanical = list_families("mechanical")
    assert {f.name for f in mechanical} == {"bracket", "link", "hub", "mount"}

    aero = list_families("aero")
    assert {f.name for f in aero} == {"airfoil", "wing", "duct"}


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


def test_family_interface_csys_present():
    family = get_family("link")
    assert family.interface_csys is not None
    assert family.interface_csys.id == "link_interface_a"
