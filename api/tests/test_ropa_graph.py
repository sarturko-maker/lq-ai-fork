"""Pure data-flow / lineage projection — PRIV-6c.

Unit tests for :func:`app.ropa_graph.build_graph` over Read DTOs (no DB): the
endpoint test in ``test_ropa_read.py`` covers the live HTTP/auth path; here we
pin the projection in isolation — node kinds + badges, the three edge kinds,
destination dedup, orphan (unconnected) nodes, deterministic kind-grouped order,
and that no free-text crosses into the graph.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app import ropa_graph
from app.schemas.ropa import (
    DataFlowGraph,
    DataFlowNode,
    ProcessingActivityRead,
    SystemRead,
    SystemSummary,
    TransferSummary,
    VendorRead,
    VendorSummary,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _system_read(
    sid: uuid.UUID,
    *,
    name: str = "CRM DB",
    system_type: str = "database",
    ai_usage: bool = False,
    description: str | None = None,
) -> SystemRead:
    return SystemRead(
        id=sid,
        name=name,
        system_type=system_type,
        description=description,
        owner=None,
        hosting_location=None,
        retention=None,
        security_measures=None,
        ai_usage=ai_usage,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _vendor_read(
    vid: uuid.UUID,
    *,
    name: str = "Mailchimp",
    vendor_role: str = "processor",
    dpa_status: str = "in_place",
) -> VendorRead:
    return VendorRead(
        id=vid,
        name=name,
        vendor_role=vendor_role,
        description=None,
        country=None,
        dpa_status=dpa_status,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _activity_read(
    aid: uuid.UUID,
    *,
    name: str = "Marketing CRM",
    lawful_basis: str = "consent",
    controller_role: str = "controller",
    special_category: bool = False,
    art9_condition: str | None = None,
    purpose: str = "p",
    retention: str = "1 year",
    systems: tuple[SystemSummary, ...] = (),
    vendors: tuple[VendorSummary, ...] = (),
    transfers: tuple[TransferSummary, ...] = (),
) -> ProcessingActivityRead:
    return ProcessingActivityRead(
        id=aid,
        name=name,
        purpose=purpose,
        lawful_basis=lawful_basis,
        controller_role=controller_role,
        retention=retention,
        special_category=special_category,
        art9_condition=art9_condition,
        created_at=_NOW,
        updated_at=_NOW,
        systems=list(systems),
        vendors=list(vendors),
        transfers=list(transfers),
        data_subject_categories=[],
        data_categories=[],
    )


def _transfer(
    destination: str,
    *,
    restricted: bool = False,
    mechanism: str | None = None,
    details: str | None = None,
    vendor: VendorSummary | None = None,
) -> TransferSummary:
    return TransferSummary(
        id=uuid.uuid4(),
        destination=destination,
        restricted=restricted,
        mechanism=mechanism,
        details=details,
        vendor=vendor,
    )


def _by_kind(graph: DataFlowGraph) -> dict[str, list[DataFlowNode]]:
    out: dict[str, list[DataFlowNode]] = {}
    for node in graph.nodes:
        out.setdefault(node.kind, []).append(node)
    return out


def test_empty_register_is_empty_graph() -> None:
    graph = ropa_graph.build_graph([], [], [])
    assert graph.nodes == []
    assert graph.edges == []


def test_nodes_carry_kind_label_and_only_their_own_badges() -> None:
    sid, vid, aid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    graph = ropa_graph.build_graph(
        activities=[
            _activity_read(
                aid,
                name="Marketing CRM",
                lawful_basis="legitimate_interests",
                controller_role="controller",
                special_category=True,
                art9_condition="explicit_consent",
                systems=(SystemSummary(id=sid, name="CRM DB", system_type="crm"),),
                vendors=(VendorSummary(id=vid, name="Mailchimp", vendor_role="processor"),),
            )
        ],
        systems=[_system_read(sid, name="CRM DB", system_type="crm", ai_usage=True)],
        vendors=[
            _vendor_read(vid, name="Mailchimp", vendor_role="processor", dpa_status="pending")
        ],
    )
    by_kind = _by_kind(graph)

    sys_node = by_kind["system"][0]
    assert sys_node.id == f"system:{sid}"
    assert sys_node.label == "CRM DB"
    assert sys_node.system_type == "crm"
    assert sys_node.ai_usage is True
    # A system node carries no activity/recipient badges.
    assert sys_node.lawful_basis is None
    assert sys_node.vendor_role is None

    act_node = by_kind["activity"][0]
    assert act_node.id == f"activity:{aid}"
    assert act_node.label == "Marketing CRM"
    assert act_node.lawful_basis == "legitimate_interests"
    assert act_node.controller_role == "controller"
    assert act_node.special_category is True
    assert act_node.system_type is None
    assert act_node.vendor_role is None

    rec_node = by_kind["recipient"][0]
    assert rec_node.id == f"recipient:{vid}"
    assert rec_node.label == "Mailchimp"
    assert rec_node.vendor_role == "processor"
    assert rec_node.dpa_status == "pending"
    assert rec_node.lawful_basis is None


def test_edges_follow_the_relationships() -> None:
    sid, vid, aid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    graph = ropa_graph.build_graph(
        activities=[
            _activity_read(
                aid,
                systems=(SystemSummary(id=sid, name="CRM DB", system_type="crm"),),
                vendors=(VendorSummary(id=vid, name="Mailchimp", vendor_role="processor"),),
                transfers=(
                    _transfer(
                        "United States",
                        restricted=True,
                        mechanism="standard_contractual_clauses",
                        vendor=VendorSummary(id=vid, name="Mailchimp", vendor_role="processor"),
                    ),
                ),
            )
        ],
        systems=[_system_read(sid)],
        vendors=[_vendor_read(vid)],
    )
    edges = {(e.source, e.target, e.kind): e for e in graph.edges}

    assert (f"system:{sid}", f"activity:{aid}", "processed_by") in edges
    assert (f"activity:{aid}", f"recipient:{vid}", "disclosed_to") in edges

    transfer_edge = edges[(f"activity:{aid}", "destination:United States", "transferred_to")]
    assert transfer_edge.restricted is True
    assert transfer_edge.mechanism == "standard_contractual_clauses"
    assert transfer_edge.recipient == "Mailchimp"

    dest = _by_kind(graph)["destination"][0]
    assert dest.id == "destination:United States"
    assert dest.label == "United States"


def test_non_restricted_transfer_without_recipient_has_none() -> None:
    aid = uuid.uuid4()
    graph = ropa_graph.build_graph(
        [_activity_read(aid, transfers=(_transfer("Germany"),))],
        [],
        [],
    )
    transfer_edges = [e for e in graph.edges if e.kind == "transferred_to"]
    assert len(transfer_edges) == 1
    edge = transfer_edges[0]
    assert edge.restricted is False
    assert edge.mechanism is None
    assert edge.recipient is None


def test_orphan_system_and_vendor_are_unconnected_nodes() -> None:
    sid, vid = uuid.uuid4(), uuid.uuid4()
    graph = ropa_graph.build_graph(
        activities=[], systems=[_system_read(sid)], vendors=[_vendor_read(vid)]
    )
    by_kind = _by_kind(graph)
    assert len(by_kind["system"]) == 1
    assert len(by_kind["recipient"]) == 1
    # No activity → no edges; the inventory nodes are present but unconnected.
    assert graph.edges == []


def test_destination_dedup_across_activities() -> None:
    a1, a2 = uuid.uuid4(), uuid.uuid4()
    graph = ropa_graph.build_graph(
        [
            _activity_read(a1, transfers=(_transfer("United States"),)),
            _activity_read(a2, transfers=(_transfer("United States"),)),
        ],
        [],
        [],
    )
    destinations = _by_kind(graph)["destination"]
    assert len(destinations) == 1
    assert destinations[0].id == "destination:United States"

    transferred = [e for e in graph.edges if e.kind == "transferred_to"]
    assert len(transferred) == 2
    assert all(e.target == "destination:United States" for e in transferred)


def test_node_order_is_grouped_by_kind() -> None:
    sid, vid, aid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    graph = ropa_graph.build_graph(
        activities=[_activity_read(aid, transfers=(_transfer("United States"),))],
        systems=[_system_read(sid)],
        vendors=[_vendor_read(vid)],
    )
    assert [n.kind for n in graph.nodes] == ["system", "activity", "recipient", "destination"]


def test_no_free_text_crosses_into_the_graph() -> None:
    # Confused-deputy guard (ADR-F019 / Backlog): a node label is the entity name,
    # but free-text (purpose / retention / system description / transfer details)
    # must never reach the wire. Names DO appear (they are labels); the secret does not.
    secret = "PRIVILEGED-NARRATIVE-DO-NOT-LEAK"
    sid, vid, aid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    graph = ropa_graph.build_graph(
        activities=[
            _activity_read(
                aid,
                purpose=secret,
                retention=secret,
                systems=(SystemSummary(id=sid, name="CRM DB", system_type="crm"),),
                transfers=(_transfer("Germany", details=secret),),
            )
        ],
        systems=[_system_read(sid, description=secret)],
        vendors=[_vendor_read(vid)],
    )
    dumped = graph.model_dump_json()
    assert secret not in dumped
    # The benign labels are present (they are already exposed by the register reads).
    assert "CRM DB" in dumped
    assert "Germany" in dumped
