"""Diff two revisions of a robot bundle, link by link.

A twin is a file that gets regenerated, and a regenerated file is only trustworthy if you can see
what moved. This module answers that in the only units that matter: how many instances a link has,
how much volume it occupies, and how much it weighs -- each as a count, a difference and a percent,
with added and removed links named rather than silently absent.

Two rules:

* **A change of zero is a result.** A link that came out identical across a revision is printed as
  ``unchanged``. Filtering those rows out of the report would hide the fact that the compile is
  reproducible.
* **A percent with no denominator is not printed.** When the previous revision has no value for a
  link (a newly added link, or a volume that was never measured), the difference is ``None`` and the
  report shows a dash. A percent change against zero is not a percent change.

One refusal. Two documents can describe the same robot with different link identities: a proposal
carries one row per part, a compiled bundle one row per merged body. Diffed by name, every row on
each side is absent from the other, and the result reads as "19 links removed, 7 added" for a robot
whose parts never moved. When the two sides share no link id at all, this module refuses to produce
that table: it returns ``comparable=False`` with the reason, and the renderers print the refusal. A
diff that reports deletions that never happened is worse than no diff.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

# How much of the smaller side must appear on both before a link-by-link table means anything. Half
# is deliberately lenient: a revision may rename a link or two, but when the overlap collapses to a
# single name out of seven the documents are describing different things, not different revisions.
_MIN_SHARED_FRACTION = 0.5


class LinkRow(BaseModel):
    """One link as a single revision describes it."""

    link_id: str
    name: str = ""
    quantity: int = 0
    parts: int = 0
    volume_m3: float | None = None
    mass_kg: float | None = None


class LinkTable(dict):
    """A ``{link_id: LinkRow}`` map that remembers which identity scheme produced it.

    The scheme is what makes a diff honest. A proposal names one link per part family; a compiled
    bundle names one per merged body. Both are dictionaries keyed by short strings, and several of
    those strings are the same word on both sides while meaning different sets of parts -- so
    looking at the names alone cannot tell you whether a removal is real.
    """

    #: one link per part family, from a ``links:`` document
    FAMILIES = "part family"
    #: one link per merged body, from a ``bodies:`` document or a compiled bundle
    BODIES = "body"

    def __init__(self, *args, scheme: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.scheme = scheme


class LinkDelta(BaseModel):
    link_id: str
    name: str = ""
    status: str  # added | removed | changed | unchanged
    quantity_before: int | None = None
    quantity_after: int | None = None
    quantity_delta: int | None = None
    volume_before_m3: float | None = None
    volume_after_m3: float | None = None
    volume_delta_percent: tuple[float | None, float | None] | None = None
    mass_before_kg: float | None = None
    mass_after_kg: float | None = None
    mass_delta_kg: float | None = None
    mass_delta_percent: float | None = None


class Revision(BaseModel):
    schema_version: str = "robocad.twin.revision/1"
    before: str
    after: str
    links: list[LinkDelta] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # False when the two sides do not use the same link identity. ``links`` is then empty on
    # purpose: there is no link-by-link statement to make, and an empty table says that better than
    # a table of phantom removals.
    comparable: bool = True
    incomparable_reason: str | None = None

    @property
    def changed(self) -> list[LinkDelta]:
        return [link for link in self.links if link.status != "unchanged"]

    @property
    def worst_volume_change_percent(self) -> float | None:
        """Largest absolute volume change, so a caller can set a threshold against one number."""
        values = [
            abs(link.volume_delta_percent[1])
            for link in self.links
            if link.volume_delta_percent and link.volume_delta_percent[1] is not None
        ]
        return max(values) if values else None


def _percent(before: float | None, after: float | None) -> tuple[float | None, float | None] | None:
    """``(absolute percent, signed percent)`` for a volume, or None when there is no denominator."""
    if before is None or after is None or before <= 0.0:
        return None
    change = 100.0 * (after - before) / before
    return (abs(change), change)


def diff_links(
    before: dict[str, LinkRow],
    after: dict[str, LinkRow],
    before_label: str = "before",
    after_label: str = "after",
) -> Revision:
    """Compare two link tables by name. A link absent from one side is named, not dropped.

    Refuses, with ``comparable=False``, when the two sides mostly do not share link ids: that is two
    identity schemes, not a revision.
    """
    shared = set(before) & set(after)
    smaller = min(len(before), len(after))
    scheme_before = getattr(before, "scheme", None)
    scheme_after = getattr(after, "scheme", None)
    if scheme_before and scheme_after and scheme_before != scheme_after:
        reason = (
            f"`{before_label}` names one link per {scheme_before}, "
            f"`{after_label}` names one per {scheme_after}, so a row on one side is not the same "
            f"thing as a row of the same name on the other: {len(shared)} of "
            f"{len(after)} name(s) coincide and mean different sets of parts. The diff is refused "
            f"rather than written, because a table built from it reports links as removed that "
            f"never moved. To compare revisions of this robot, diff two documents that name their "
            f"links the same way."
        )
        return Revision(
            before=before_label,
            after=after_label,
            links=[],
            notes=[reason],
            comparable=False,
            incomparable_reason=reason,
        )
    mostly_unshared = bool(before) and bool(after) and len(shared) < _MIN_SHARED_FRACTION * smaller
    if mostly_unshared:
        reason = (
            f"The two sides barely share a link id: `{before_label}` names {len(before)} link(s), "
            f"`{after_label}` names {len(after)}, and only {len(shared)} name(s) appear on both. "
            f"A diff at that overlap is two identity schemes read as a revision: it reports links "
            f"as removed and added that never moved. The compiled bundle groups parts into bodies, "
            f"a proposal names one link per part, and the two rows are not the same thing. Compare "
            f"two documents that name their links the same way, or a document against itself "
            f"recompiled."
        )
        return Revision(
            before=before_label,
            after=after_label,
            links=[],
            notes=[reason],
            comparable=False,
            incomparable_reason=reason,
        )
    deltas: list[LinkDelta] = []
    for link_id in sorted(set(before) | set(after)):
        old = before.get(link_id)
        new = after.get(link_id)
        if old is None:
            deltas.append(
                LinkDelta(
                    link_id=link_id,
                    name=new.name if new else "",
                    status="added",
                    quantity_after=new.quantity if new else None,
                    volume_after_m3=new.volume_m3 if new else None,
                    mass_after_kg=new.mass_kg if new else None,
                )
            )
            continue
        if new is None:
            deltas.append(
                LinkDelta(
                    link_id=link_id,
                    name=old.name,
                    status="removed",
                    quantity_before=old.quantity,
                    volume_before_m3=old.volume_m3,
                    mass_before_kg=old.mass_kg,
                )
            )
            continue
        volume_change = _percent(old.volume_m3, new.volume_m3)
        mass_delta = (
            None
            if old.mass_kg is None or new.mass_kg is None
            else new.mass_kg - old.mass_kg
        )
        mass_percent = (
            None
            if mass_delta is None or not old.mass_kg
            else 100.0 * mass_delta / old.mass_kg
        )
        changed = bool(old.quantity != new.quantity) or bool(
            volume_change is not None and volume_change[0] > 1e-9
        )
        deltas.append(
            LinkDelta(
                link_id=link_id,
                name=new.name or old.name,
                status="changed" if changed else "unchanged",
                quantity_before=old.quantity,
                quantity_after=new.quantity,
                quantity_delta=new.quantity - old.quantity,
                volume_before_m3=old.volume_m3,
                volume_after_m3=new.volume_m3,
                volume_delta_percent=volume_change,
                mass_before_kg=old.mass_kg,
                mass_after_kg=new.mass_kg,
                mass_delta_kg=mass_delta,
                mass_delta_percent=mass_percent,
            )
        )
    notes = [
        "A link that came out identical is printed as unchanged: a revision that reproduces the "
        "previous one is a result, not an empty diff.",
        "A percent is shown only when the previous revision has a value to divide by; a new link or "
        "an unmeasured volume shows a dash instead.",
    ]
    return Revision(before=before_label, after=after_label, links=deltas, notes=notes)


def from_joints_yaml(path: str | Path) -> dict[str, LinkRow]:
    """Link rows from a ``robot.joints.yaml`` (a proposal or a compiled skeleton).

    Both shapes are read: the proposal names the list ``links`` and each row ``link_id``, the compiled
    skeleton names them ``bodies`` and ``body_id``. A diff tool that only understood one of them would
    quietly compare nothing.
    """
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    # A proposal carries ``links`` (one row per part family); a compiled skeleton carries
    # ``bodies`` (one row per merged link). The distinction is returned with the rows, because it is
    # the one fact that decides whether a diff of the two is a statement about the robot.
    is_families = document.get("links") is not None
    rows = LinkTable(scheme=LinkTable.FAMILIES if is_families else LinkTable.BODIES)
    for link in (document.get("links") or document.get("bodies") or []):
        link_id = link.get("link_id") or link.get("body_id")
        if not link_id:
            continue
        volume = link.get("volume_m3")
        mass = link.get("mass_kg")
        rows[link_id] = LinkRow(
            link_id=link_id,
            name=link.get("name", "") or "",
            quantity=len(link.get("instance_ids", []) or []),
            parts=len(link.get("part_ids", []) or []),
            volume_m3=float(volume) if volume is not None else None,
            mass_kg=float(mass) if mass is not None else None,
        )
    return rows


def from_bundle(bundle: dict) -> dict[str, LinkRow]:
    """Link rows from a compiled ``bundle.json``."""
    rows = LinkTable(scheme=LinkTable.BODIES)
    for body in bundle.get("bodies", []) or []:
        body_id = body.get("body_id")
        if not body_id:
            continue
        volume = body.get("solid_volume_m3")
        mass = body.get("mass_kg")
        rows[body_id] = LinkRow(
            link_id=body_id,
            name=body.get("name", "") or "",
            # bundle.json names them instance_count/part_count; a caller may hand over the report's
            # body rows, which name them instances/parts. Reading one spelling only reported a
            # quantity of zero for every link, and a diff of zeros says nothing changed.
            quantity=int(body.get("instances", body.get("instance_count", 0)) or 0),
            parts=int(body.get("parts", body.get("part_count", 0)) or 0),
            volume_m3=float(volume) if volume is not None else None,
            mass_kg=float(mass) if mass is not None else None,
        )
    return rows


def render_markdown(revision: Revision) -> str:
    lines = [
        f"## Revision diff: {revision.before} -> {revision.after}",
        "",
    ]
    if not revision.comparable:
        lines.append(f"**Not comparable.** {revision.incomparable_reason}")
        lines.append("")
        return "\n".join(lines) + "\n"
    lines.extend([
        "| link | status | instances before | after | delta | solid volume before (cm3) | after (cm3) | volume change | mass change (g) |",
        "|---|---|---|---|---|---|---|---|---|",
    ])
    for link in revision.links:
        volume_change = "—"
        if link.volume_delta_percent and link.volume_delta_percent[1] is not None:
            volume_change = f"{link.volume_delta_percent[1]:+.2f}%"
        before = "—" if link.volume_before_m3 is None else f"{link.volume_before_m3 * 1e6:.3f}"
        after = "—" if link.volume_after_m3 is None else f"{link.volume_after_m3 * 1e6:.3f}"
        mass = "—" if link.mass_delta_kg is None else f"{link.mass_delta_kg * 1e3:+.2f}"
        lines.append(
            f"| `{link.link_id}` | {link.status} | "
            f"{'—' if link.quantity_before is None else link.quantity_before} | "
            f"{'—' if link.quantity_after is None else link.quantity_after} | "
            f"{'—' if link.quantity_delta is None else f'{link.quantity_delta:+d}'} | "
            f"{before} | {after} | {volume_change} | {mass} |"
        )
    lines.append("")
    lines.extend(f"- {note}" for note in revision.notes)
    return "\n".join(lines) + "\n"


def render_html(revision: Revision) -> str:
    import html as _html

    rows = []
    for link in revision.links:
        volume_change = "—"
        if link.volume_delta_percent and link.volume_delta_percent[1] is not None:
            volume_change = f"{link.volume_delta_percent[1]:+.2f}%"
        before = "—" if link.volume_before_m3 is None else f"{link.volume_before_m3 * 1e6:.3f}"
        after = "—" if link.volume_after_m3 is None else f"{link.volume_after_m3 * 1e6:.3f}"
        mass = "—" if link.mass_delta_kg is None else f"{link.mass_delta_kg * 1e3:+.2f}"
        rows.append(
            f"<tr class='{link.status}'><td><code>{_html.escape(link.link_id)}</code></td>"
            f"<td>{link.status}</td>"
            f"<td>{'—' if link.quantity_before is None else link.quantity_before}</td>"
            f"<td>{'—' if link.quantity_after is None else link.quantity_after}</td>"
            f"<td>{'—' if link.quantity_delta is None else f'{link.quantity_delta:+d}'}</td>"
            f"<td>{before}</td><td>{after}</td><td>{volume_change}</td><td>{mass}</td></tr>"
        )
    notes = "".join(f"<li>{_html.escape(n)}</li>" for n in revision.notes)
    heading = (
        f"<h2>Revision diff</h2><p>{_html.escape(revision.before)} -> "
        f"{_html.escape(revision.after)}</p>"
    )
    if not revision.comparable:
        return (
            heading
            + f"<div class='banner'><strong>Not comparable.</strong> "
            + _html.escape(revision.incomparable_reason or "")
            + "</div>"
        )
    return (
        heading
        + "<table><tr><th>link</th><th>status</th><th>instances before</th><th>after</th>"
        "<th>delta</th><th>volume before (cm3)</th><th>after (cm3)</th><th>volume change</th>"
        "<th>mass change (g)</th></tr>" + "".join(rows) + "</table>"
        f"<ul>{notes}</ul>"
    )


__all__ = [
    "LinkDelta",
    "LinkRow",
    "LinkTable",
    "Revision",
    "diff_links",
    "from_bundle",
    "from_joints_yaml",
    "render_html",
    "render_markdown",
]
