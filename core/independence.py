"""Source independence and shared upstream dependency analysis."""

from __future__ import annotations

from collections.abc import Sequence

from core.models import Evidence, IndependenceSummary


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def _norm_set(values: Sequence[str]) -> set[str]:
    result: set[str] = set()
    for val in values:
        cleaned = _norm(val)
        if cleaned:
            result.add(cleaned)
    return result


def analyze_source_independence(
    evidence_items: Sequence[Evidence],
) -> IndependenceSummary:
    """Analyze relationships and shared upstream dependencies across evidence items.

    Rules:
    - Products sharing an original observation source, upstream dataset, derived_from
      lineage link, or declared shared dependency are grouped as correlated and
      NEVER counted as independent corroboration.
    - When provenance metadata is missing for any source in a multi-source set,
      independence cannot be established and remains explicitly 'unknown'.
    """
    n = len(evidence_items)
    if n == 0:
        return IndependenceSummary(
            status="unknown",
            assessed_source_count=0,
            independent_group_count=0,
            correlated_groups=[],
            shared_dependencies=[],
            notes=["No evidence sources were provided for independence analysis."],
        )

    if n == 1:
        ev = evidence_items[0]
        note = (
            "Single evidence source assessed; corroboration independence does not apply."
            if ev.provenance is not None
            else "Single evidence source assessed; upstream provenance metadata is not declared."
        )
        return IndependenceSummary(
            status="single_source",
            assessed_source_count=1,
            independent_group_count=1,
            correlated_groups=[[ev.id]],
            shared_dependencies=[],
            notes=[note],
        )

    # Disjoint-set union to group correlated evidence items
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            if ra < rb:
                parent[rb] = ra
            else:
                parent[ra] = rb

    shared_links: list[str] = []
    missing_provenance_ids: list[str] = []

    for idx, ev in enumerate(evidence_items):
        prov = ev.provenance
        if prov is None or (
            _norm(prov.original_source) is None
            and not _norm_set(prov.upstream_datasets)
            and not _norm_set(prov.derived_from)
        ):
            missing_provenance_ids.append(ev.id)

    for i in range(n):
        ev_a = evidence_items[i]
        prov_a = ev_a.provenance
        ids_a = _norm_set([x for x in (ev_a.id, ev_a.product_id) if x])
        orig_a = _norm(prov_a.original_source) if prov_a else None
        up_a = _norm_set(prov_a.upstream_datasets) if prov_a else set()
        der_a = _norm_set(prov_a.derived_from) if prov_a else set()
        dep_a = _norm_set(prov_a.shared_dependencies) if prov_a else set()

        for j in range(i + 1, n):
            ev_b = evidence_items[j]
            prov_b = ev_b.provenance
            ids_b = _norm_set([x for x in (ev_b.id, ev_b.product_id) if x])
            orig_b = _norm(prov_b.original_source) if prov_b else None
            up_b = _norm_set(prov_b.upstream_datasets) if prov_b else set()
            der_b = _norm_set(prov_b.derived_from) if prov_b else set()
            dep_b = _norm_set(prov_b.shared_dependencies) if prov_b else set()

            reasons: list[str] = []
            if orig_a and orig_b and orig_a == orig_b:
                reasons.append(f"original_source:{orig_a}")
            for ds in sorted(up_a & up_b):
                reasons.append(f"upstream_dataset:{ds}")
            if (der_a & ids_b) or (der_b & ids_a) or (der_a & der_b):
                reasons.append(f"derived_lineage:{ev_a.id}<->{ev_b.id}")
            for dep in sorted(dep_a & dep_b):
                reasons.append(f"shared_dependency:{dep}")
            if (
                ev_a.product_id
                and ev_b.product_id
                and _norm(ev_a.product_id) == _norm(ev_b.product_id)
            ):
                reasons.append(f"product_id:{_norm(ev_a.product_id)}")

            if reasons:
                union(i, j)
                for r in reasons:
                    if r not in shared_links:
                        shared_links.append(r)

    groups_map: dict[int, list[str]] = {}
    for idx, ev in enumerate(evidence_items):
        root = find(idx)
        groups_map.setdefault(root, []).append(ev.id)
    groups = list(groups_map.values())

    if shared_links:
        notes = [
            (
                "Shared upstream sources or dependencies were detected across evidence items; "
                "derived or correlated products are not counted as independent corroboration."
            )
        ]
        if missing_provenance_ids:
            notes.append(
                "Some evidence items lack declared provenance metadata; additional undeclared correlations may exist."
            )
        return IndependenceSummary(
            status="shared_dependencies_detected",
            assessed_source_count=n,
            independent_group_count=len(groups) if not missing_provenance_ids else None,
            correlated_groups=groups,
            shared_dependencies=shared_links,
            notes=notes,
        )

    if missing_provenance_ids:
        return IndependenceSummary(
            status="unknown",
            assessed_source_count=n,
            independent_group_count=None,
            correlated_groups=groups,
            shared_dependencies=[],
            notes=[
                "Source independence is unknown because one or more evidence items lack declared upstream provenance; multiple evidence records may derive from correlated observations and are not treated as independent."
            ],
        )

    return IndependenceSummary(
        status="distinct_declared_sources",
        assessed_source_count=n,
        independent_group_count=len(groups),
        correlated_groups=groups,
        shared_dependencies=[],
        notes=[
            "Declared provenance shows distinct original sources and no known shared upstream dependencies; undeclared operational correlations cannot be ruled out."
        ],
    )
