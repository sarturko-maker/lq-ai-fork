/**
 * Data-flow / lineage layout (PRIV-6c, ADR-F022).
 *
 * Pure mapping from the backend's `DataFlowGraph` (nodes + edges — the
 * System→Activity→Vendor/Transfer projection) to the positioned
 * `@xyflow/svelte` `Node`/`Edge` shapes the canvas renders. Kept in a standalone
 * module (not inline in the Svelte component) so the layout is deterministic and
 * unit-testable without mounting Svelte Flow — and so swapping the renderer later
 * (ADR-F022 keeps the projection lib-agnostic) touches only the view.
 *
 * Layout is a calm left→right lineage: systems (col 0) feed activities (col 1),
 * which disclose to recipients and transfer to destinations (col 2). Positions
 * are deterministic; the user can still drag/zoom/pan on the canvas. No graph
 * auto-layout dependency (dagre/elk) — this is the layout (ADR-F022).
 */
import type { Edge, Node } from '@xyflow/svelte';

import type { DataFlowEdge, DataFlowGraph, DataFlowNodeKind } from '$lib/lq-ai/api/ropa';
import { transferMechanismLabel } from './format';

/** Column index per node kind — the left→right lineage order. */
const COLUMN_OF: Record<DataFlowNodeKind, number> = {
	system: 0,
	activity: 1,
	recipient: 2,
	destination: 2
};

const X_GAP = 300;
const Y_GAP = 96;
const X_PAD = 24;
const Y_PAD = 24;

export interface DataFlowLayout {
	nodes: Node[];
	edges: Edge[];
	isEmpty: boolean;
}

/** Project the register graph into positioned Svelte Flow nodes + edges (pure). */
export function layoutDataFlow(graph: DataFlowGraph): DataFlowLayout {
	const rowInColumn: Record<number, number> = {};

	const nodes: Node[] = graph.nodes.map((node) => {
		const column = COLUMN_OF[node.kind];
		const row = rowInColumn[column] ?? 0;
		rowInColumn[column] = row + 1;
		return {
			id: node.id,
			type: 'flowNode',
			position: { x: X_PAD + column * X_GAP, y: Y_PAD + row * Y_GAP },
			data: { ...node }
		};
	});

	const edges: Edge[] = graph.edges.map((edge, index) => edgeFor(edge, index));

	return { nodes, edges, isEmpty: graph.nodes.length === 0 };
}

/**
 * One Svelte Flow edge. The id is index-based so it stays unique even if an
 * activity transfers to the same destination twice (a backend (source,target,
 * kind) tuple is not guaranteed unique for transfers). Restricted transfers are
 * flagged (animated + class + the mechanism as a label) so the Chapter V
 * safeguard reads at a glance.
 */
function edgeFor(edge: DataFlowEdge, index: number): Edge {
	const restricted = edge.kind === 'transferred_to' && edge.restricted === true;
	return {
		id: `e${index}:${edge.kind}`,
		source: edge.source,
		target: edge.target,
		type: 'smoothstep',
		animated: restricted,
		class: restricted ? 'lqf-edge-restricted' : `lqf-edge-${edge.kind}`,
		data: {
			kind: edge.kind,
			restricted: edge.restricted ?? null,
			mechanism: edge.mechanism ?? null,
			recipient: edge.recipient ?? null
		},
		label: restricted && edge.mechanism ? transferMechanismLabel(edge.mechanism) : undefined
	};
}
