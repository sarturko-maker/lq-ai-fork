"""Privacy data-flow / lineage projection — PRIV-6c (fork, ADR-F018/F019/F022).

Pure projection over the deployment-global ROPA register: turns the loaded
``*Read`` DTOs into a :class:`~app.schemas.ropa.DataFlowGraph` — the relational
graph ADR-F019 stores (System → Processing Activity → Vendor / Transfer) as a
node-link data map. No I/O: the read handler loads the rows and hands them here,
mirroring ``app.ropa_summary.build_summary`` / ``app.ropa_export.build_export``,
so the projection is unit-tested in isolation and there is one load path
(``app.api.ropa._load_register``) for the export, the summary and the graph.

Direction = data flow: a **system** feeds the **activity** that processes its
data (``processed_by``); the activity **discloses** to a **recipient** vendor
(``disclosed_to``) and **transfers** to a third-country **destination**
(``transferred_to``, carrying the Chapter V safeguard). A system or vendor with
no activity link surfaces as an unconnected node — the graph is honest about
orphan inventory.

Labels + categorical badges only (no free-text): a node label is the entity name
(already exposed by every register read; a ``destination`` label is the
transfer's free-text country string), and the badges are categorical. No
``purpose`` / ``retention`` / ``description`` / transfer ``details`` crosses the
wire, so neither the shared-read posture (ADR-F019) nor the private→shared
confused-deputy concern (Backlog / ADR-F021) is heightened.
"""

from __future__ import annotations

from app.schemas.ropa import (
    DataFlowEdge,
    DataFlowGraph,
    DataFlowNode,
    ProcessingActivityRead,
    SystemRead,
    VendorRead,
)


def build_graph(
    activities: list[ProcessingActivityRead],
    systems: list[SystemRead],
    vendors: list[VendorRead],
) -> DataFlowGraph:
    """Project the loaded register into the data-flow / lineage graph (PRIV-6c).

    Node order is deterministic — systems, then activities, then recipients, then
    destinations — each group in the register's canonical ``created_at, name``
    order (the order the rows arrive in); destinations follow in first-seen order.
    Edges follow the activities in that same order.
    """
    nodes: list[DataFlowNode] = []
    edges: list[DataFlowEdge] = []

    for system in systems:
        nodes.append(
            DataFlowNode(
                id=f"system:{system.id}",
                kind="system",
                label=system.name,
                system_type=system.system_type,
                ai_usage=system.ai_usage,
            )
        )

    # Destination nodes are discovered from the activities' transfers; collected
    # here (deduped by the exact destination string — no silent normalisation)
    # and appended after the recipients so the node order stays grouped by kind.
    seen_destinations: set[str] = set()
    destination_nodes: list[DataFlowNode] = []

    for activity in activities:
        activity_id = f"activity:{activity.id}"
        nodes.append(
            DataFlowNode(
                id=activity_id,
                kind="activity",
                label=activity.name,
                lawful_basis=activity.lawful_basis,
                controller_role=activity.controller_role,
                special_category=activity.special_category,
            )
        )
        # System → Activity: the activity processes data living in this system.
        for linked_system in activity.systems:
            edges.append(
                DataFlowEdge(
                    source=f"system:{linked_system.id}",
                    target=activity_id,
                    kind="processed_by",
                )
            )
        # Activity → Recipient: the activity discloses data to this vendor.
        for linked_vendor in activity.vendors:
            edges.append(
                DataFlowEdge(
                    source=activity_id,
                    target=f"recipient:{linked_vendor.id}",
                    kind="disclosed_to",
                )
            )
        # Activity → Destination: a third-country transfer; the Chapter V
        # safeguard (restricted ⇒ mechanism) and the optional recipient vendor
        # ride the edge, not the destination node (the same country can be a
        # destination from several activities under different safeguards).
        for transfer in activity.transfers:
            destination_id = f"destination:{transfer.destination}"
            if transfer.destination not in seen_destinations:
                seen_destinations.add(transfer.destination)
                destination_nodes.append(
                    DataFlowNode(
                        id=destination_id,
                        kind="destination",
                        label=transfer.destination,
                    )
                )
            edges.append(
                DataFlowEdge(
                    source=activity_id,
                    target=destination_id,
                    kind="transferred_to",
                    restricted=transfer.restricted,
                    mechanism=transfer.mechanism,
                    recipient=transfer.vendor.name if transfer.vendor else None,
                )
            )

    for vendor in vendors:
        nodes.append(
            DataFlowNode(
                id=f"recipient:{vendor.id}",
                kind="recipient",
                label=vendor.name,
                vendor_role=vendor.vendor_role,
                dpa_status=vendor.dpa_status,
            )
        )

    nodes.extend(destination_nodes)
    return DataFlowGraph(nodes=nodes, edges=edges)
