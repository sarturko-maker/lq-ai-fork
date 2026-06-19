/**
 * Data-flow / lineage layout (PRIV-6c).
 *
 * The codebase covers the register at the pure-helper layer (no
 * @testing-library/svelte). `layoutDataFlow` is the pure mapping from the backend
 * graph to positioned Svelte Flow nodes/edges; here we pin the deterministic
 * column layout, the restricted-transfer edge styling, and unique edge ids.
 */
import { describe, expect, it } from 'vitest';

import type { DataFlowGraph, DataFlowNode } from '$lib/lq-ai/api/ropa';
import { layoutDataFlow } from './dataFlow';
import { transferMechanismLabel } from './format';

const node = (id: string, kind: DataFlowNode['kind'], label = id): DataFlowNode => ({
	id,
	kind,
	label
});

describe('layoutDataFlow', () => {
	it('reports an empty graph', () => {
		const r = layoutDataFlow({ nodes: [], edges: [] });
		expect(r.isEmpty).toBe(true);
		expect(r.nodes).toEqual([]);
		expect(r.edges).toEqual([]);
	});

	it('lays kinds out left→right in lineage columns', () => {
		const g: DataFlowGraph = {
			nodes: [
				node('system:a', 'system'),
				node('activity:b', 'activity'),
				node('recipient:c', 'recipient'),
				node('destination:D', 'destination')
			],
			edges: []
		};
		const byId = Object.fromEntries(layoutDataFlow(g).nodes.map((n) => [n.id, n]));
		expect(byId['system:a'].position.x).toBeLessThan(byId['activity:b'].position.x);
		expect(byId['activity:b'].position.x).toBeLessThan(byId['recipient:c'].position.x);
		// Recipients and destinations share the rightmost column.
		expect(byId['recipient:c'].position.x).toBe(byId['destination:D'].position.x);
	});

	it('stacks nodes within a column', () => {
		const { nodes } = layoutDataFlow({
			nodes: [node('s1', 'system'), node('s2', 'system')],
			edges: []
		});
		expect(nodes[0].position.x).toBe(nodes[1].position.x);
		expect(nodes[0].position.y).not.toBe(nodes[1].position.y);
	});

	it('carries the node kind/label through as data on a flowNode', () => {
		const { nodes } = layoutDataFlow({
			nodes: [node('activity:x', 'activity', 'Marketing')],
			edges: []
		});
		expect(nodes[0].type).toBe('flowNode');
		expect(nodes[0].data.kind).toBe('activity');
		expect(nodes[0].data.label).toBe('Marketing');
	});

	it('flags a restricted transfer edge with the mechanism label', () => {
		const { edges } = layoutDataFlow({
			nodes: [],
			edges: [
				{
					source: 'activity:a',
					target: 'destination:US',
					kind: 'transferred_to',
					restricted: true,
					mechanism: 'standard_contractual_clauses',
					recipient: 'Mailchimp'
				}
			]
		});
		expect(edges[0].animated).toBe(true);
		expect(edges[0].class).toBe('lqf-edge-restricted');
		expect(edges[0].label).toBe(transferMechanismLabel('standard_contractual_clauses'));
	});

	it('leaves non-restricted and structural edges calm (no animation/label)', () => {
		const { edges } = layoutDataFlow({
			nodes: [],
			edges: [
				{ source: 'system:a', target: 'activity:b', kind: 'processed_by' },
				{
					source: 'activity:b',
					target: 'destination:DE',
					kind: 'transferred_to',
					restricted: false
				}
			]
		});
		expect(edges[0].class).toBe('lqf-edge-processed_by');
		expect(edges[0].animated).toBe(false);
		expect(edges[0].label).toBeUndefined();
		expect(edges[1].class).toBe('lqf-edge-transferred_to');
		expect(edges[1].animated).toBe(false);
	});

	it('gives every edge a unique id even when (source,target,kind) repeats', () => {
		const dup = {
			source: 'activity:a',
			target: 'destination:US',
			kind: 'transferred_to' as const,
			restricted: false
		};
		const { edges } = layoutDataFlow({ nodes: [], edges: [dup, dup] });
		expect(edges[0].id).not.toBe(edges[1].id);
		expect(new Set(edges.map((e) => e.id)).size).toBe(2);
	});
});
