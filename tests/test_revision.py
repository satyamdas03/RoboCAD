"""Tests for the revision diff.

Two behaviours matter more than the formatting: a link that did not change is still printed, and a
percent is never computed against a missing or zero denominator.
"""
from __future__ import annotations

import pytest

from ai_cad.compiler import revision
from ai_cad.compiler.revision import LinkRow, diff_links


def row(link_id, quantity=1, volume=1.0e-4, mass=0.1, parts=1):
    return LinkRow(link_id=link_id, name=link_id, quantity=quantity, parts=parts, volume_m3=volume,
                   mass_kg=mass)


class TestDiffLinks:
    def test_a_quantity_change_shows_as_a_count_and_a_delta(self):
        result = diff_links({"a": row("a", quantity=3)}, {"a": row("a", quantity=5)})
        link = result.links[0]
        assert link.status == "changed"
        assert (link.quantity_before, link.quantity_after, link.quantity_delta) == (3, 5, 2)

    def test_a_volume_change_shows_as_a_percent(self):
        result = diff_links({"a": row("a", volume=1.0e-4)}, {"a": row("a", volume=1.2e-4)})
        assert result.links[0].volume_delta_percent == pytest.approx((20.0, 20.0))
        assert result.worst_volume_change_percent == pytest.approx(20.0)

    def test_an_identical_link_is_printed_as_unchanged(self):
        result = diff_links({"a": row("a")}, {"a": row("a")})
        assert result.links[0].status == "unchanged"
        assert result.changed == []

    def test_an_added_link_is_named_not_dropped(self):
        result = diff_links({}, {"a": row("a", quantity=4)})
        link = result.links[0]
        assert link.status == "added"
        assert link.quantity_before is None
        assert link.quantity_after == 4

    def test_a_removed_link_is_named_with_what_it_used_to_be(self):
        result = diff_links({"a": row("a", quantity=2)}, {})
        link = result.links[0]
        assert link.status == "removed"
        assert link.quantity_before == 2
        assert link.quantity_after is None

    def test_no_percent_without_a_denominator(self):
        result = diff_links({"a": row("a", volume=0.0)}, {"a": row("a", volume=1.0e-4)})
        assert result.links[0].volume_delta_percent is None
        assert result.worst_volume_change_percent is None

    def test_a_missing_mass_stays_missing_on_both_sides(self):
        before = {"a": LinkRow(link_id="a", quantity=1, volume_m3=1.0e-4, mass_kg=None)}
        after = {"a": LinkRow(link_id="a", quantity=1, volume_m3=1.0e-4, mass_kg=0.2)}
        result = diff_links(before, after)
        assert result.links[0].mass_delta_kg is None
        assert result.links[0].mass_delta_percent is None

    def test_links_are_ordered_so_two_runs_diff_cleanly(self):
        result = diff_links({"b": row("b"), "a": row("a")}, {"a": row("a"), "b": row("b")})
        assert [link.link_id for link in result.links] == ["a", "b"]


class TestReaders:
    def test_a_joints_yaml_yields_quantity_parts_and_volume(self, tmp_path):
        path = tmp_path / "robot.joints.yaml"
        path.write_text(
            "schema: robocad.joints/1\n"
            "links:\n"
            "- link_id: base\n"
            "  name: Base\n"
            "  instance_ids: [i1, i2]\n"
            "  part_ids: [p1]\n"
            "  volume_m3: 0.0002\n",
            encoding="utf-8",
        )
        rows = revision.from_joints_yaml(path)
        assert rows["base"].quantity == 2
        assert rows["base"].parts == 1
        assert rows["base"].volume_m3 == pytest.approx(2.0e-4)
        assert rows["base"].mass_kg is None

    def test_a_bundle_yields_the_same_shape(self):
        bundle = {
            "bodies": [
                {
                    "body_id": "base",
                    "name": "Base",
                    "instances": 2,
                    "parts": 1,
                    "solid_volume_m3": 2.0e-4,
                    "mass_kg": 0.25,
                }
            ]
        }
        rows = revision.from_bundle(bundle)
        assert rows["base"].quantity == 2
        assert rows["base"].mass_kg == pytest.approx(0.25)

    def test_a_real_bundle_counts_instances_under_the_field_it_actually_uses(self):
        # bundle.json writes instance_count/part_count. A reader that only knew instances/parts
        # reported a quantity of zero for every body, and a diff of zeros says nothing changed.
        bundle = {
            "bodies": [
                {
                    "body_id": "base",
                    "name": "Base",
                    "instance_count": 7,
                    "part_count": 3,
                    "solid_volume_m3": 2.0e-4,
                    "mass_kg": 0.25,
                }
            ]
        }
        rows = revision.from_bundle(bundle)
        assert rows["base"].quantity == 7
        assert rows["base"].parts == 3

    def test_markdown_and_html_carry_the_dash_for_missing_values(self):
        result = diff_links({"a": row("a", mass=None)}, {"a": row("a", mass=None)})
        assert "| — |" in revision.render_markdown(result)
        assert "<td>—</td>" in revision.render_html(result)


class TestComparability:
    """Two documents that name their links differently are not a revision.

    The failure this guards against really happened: a per-part proposal was diffed against a
    seven-body compiled bundle and the report said 19 links were removed, none of which had gone.
    """

    def test_no_shared_link_id_is_refused_rather_than_reported_as_removals(self):
        proposal = {name: row(name) for name in ("base_08p", "050375033", "jaw_02")}
        compiled = {name: row(name) for name in ("base_so101", "upper_arm_so101")}
        result = diff_links(proposal, compiled, "robot.joints.proposed.yaml", "so101_demo")
        assert result.comparable is False
        assert result.links == []
        assert result.changed == []
        assert result.worst_volume_change_percent is None
        assert "barely share a link id" in (result.incomparable_reason or "")

    def test_a_proposal_diffed_against_a_bundle_is_refused_even_where_names_coincide(self, tmp_path):
        """The real failure: seven family names are also seven body names, and mean different things.

        ``base_so101`` is a family of four parts in the proposal and a body of 150 instances in the
        bundle. A name-only diff reported the other nineteen families as removed links.
        """
        from ai_cad.compiler import revision as revision_module

        path = tmp_path / "robot.joints.proposed.yaml"
        path.write_text(
            "schema: robocad.joints/1\n"
            "links:\n"
            "- link_id: base_so101\n"
            "  name: Base_SO101\n"
            "  instance_ids: [a, b, c, d]\n"
            "  part_ids: [p1, p2, p3, p4]\n"
            "- link_id: base_08p\n"
            "  name: Base_08p\n"
            "  instance_ids: [e]\n"
            "  part_ids: [p5]\n"
            "- link_id: moving_jaw_so101\n"
            "  name: Moving_Jaw_SO101\n"
            "  instance_ids: [f]\n"
            "  part_ids: [p6]\n",
            encoding="utf-8",
        )
        bundle = {
            "bodies": [
                {"body_id": "base_so101", "name": "Base_SO101", "instance_count": 150,
                 "part_count": 69},
                {"body_id": "moving_jaw_so101", "name": "Moving_Jaw_SO101", "instance_count": 1,
                 "part_count": 1},
            ]
        }
        before = revision_module.from_joints_yaml(path)
        after = revision_module.from_bundle(bundle)
        assert before.scheme == revision_module.LinkTable.FAMILIES
        assert after.scheme == revision_module.LinkTable.BODIES
        result = revision_module.diff_links(before, after, path.name, "so101_demo")
        assert result.comparable is False
        assert result.links == []
        assert "part family" in (result.incomparable_reason or "")
        assert "removed" in (result.incomparable_reason or "")

    def test_a_compiled_skeleton_diffed_against_a_bundle_is_compared(self, tmp_path):
        """Both name bodies, so the same names mean the same links and the table is a revision."""
        from ai_cad.compiler import revision as revision_module

        path = tmp_path / "robot.joints.yaml"
        path.write_text(
            "schema: robocad.joints/1\n"
            "bodies:\n"
            "- body_id: base\n"
            "  name: Base\n"
            "  instance_ids: [i1]\n"
            "  volume_m3: 0.0001\n"
            "  mass_kg: 0.1\n",
            encoding="utf-8",
        )
        before = revision_module.from_joints_yaml(path)
        after = revision_module.from_bundle(
            {"bodies": [{"body_id": "base", "instance_count": 2, "part_count": 1,
                         "solid_volume_m3": 2.0e-4, "mass_kg": 0.2}]}
        )
        result = revision_module.diff_links(before, after)
        assert result.comparable is True
        assert result.links[0].status == "changed"
        assert result.links[0].quantity_delta == 1

    def test_the_refusal_says_which_side_has_which_links(self):
        result = diff_links({"a": row("a")}, {"b": row("b")}, "before.yaml", "after.json")
        reason = result.incomparable_reason or ""
        assert "before.yaml" in reason and "after.json" in reason
        assert "1 link(s)" in reason

    def test_an_empty_previous_document_still_reports_every_link_as_added(self):
        # Deliberate: an empty baseline is a real state (a first compile), and "added" is true
        # against it. Only two populated documents that share no name are refused.
        result = diff_links({}, {"base": row("base")}, "robot.joints.yaml", "so101_demo")
        assert result.comparable is True
        assert result.links[0].status == "added"

    def test_one_shared_link_is_enough_to_compare(self):
        # A real revision can rename most of the robot. Once any identity survives, additions and
        # removals are genuine statements and the table is written.
        result = diff_links(
            {"base": row("base"), "old": row("old")},
            {"base": row("base", quantity=2), "new": row("new")},
        )
        assert result.comparable is True
        assert {link.link_id: link.status for link in result.links} == {
            "base": "changed",
            "new": "added",
            "old": "removed",
        }

    def test_the_markdown_prints_the_refusal_and_no_table(self):
        result = diff_links({"a": row("a")}, {"b": row("b")}, "proposal.yaml", "bundle.json")
        text = revision.render_markdown(result)
        assert "Not comparable." in text
        assert "| link | status |" not in text
        assert "| `" not in text  # no link rows: the refusal is the whole content

    def test_the_html_prints_the_refusal_in_a_banner(self):
        from ai_cad.compiler.revision import Revision

        result = diff_links({"a": row("a")}, {"b": row("b")})
        page = revision.render_html(Revision(**result.model_dump()))
        assert "<div class='banner'><strong>Not comparable.</strong>" in page
        assert "<table>" not in page

    def test_a_comparison_survives_a_json_round_trip(self):
        # The refusal reaches report.html through report.json, which is a serialised Revision.
        from ai_cad.compiler.revision import Revision

        result = diff_links({"a": row("a")}, {"b": row("b")})
        restored = Revision(**result.model_dump())
        assert restored.comparable is False
        assert restored.incomparable_reason == result.incomparable_reason


class TestHtmlEscaping:
    def test_a_status_is_escaped_before_it_reaches_markup(self):
        # A revision can be rebuilt from a report.json this process did not write, and ``status`` is
        # a plain string on the model. It is four words when this module writes it; it is escaped
        # when anything else does.
        from ai_cad.compiler.revision import LinkDelta, Revision

        result = Revision(
            before="a.yaml",
            after="b.yaml",
            links=[LinkDelta(link_id="a", status="<script>alert(1)</script>")],
        )
        page = revision.render_html(result)
        assert "<script>" not in page
        assert "&lt;script&gt;" in page
