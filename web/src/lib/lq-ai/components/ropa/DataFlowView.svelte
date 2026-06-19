<script lang="ts">
	/**
	 * Data-flow / lineage view (PRIV-6c, ADR-F022) — an interactive node-link map
	 * of the deployment-global ROPA register: systems feed the activities that
	 * process their data, which disclose to recipients and transfer to third
	 * countries (restricted transfers flagged with their Chapter V safeguard).
	 * Read-only — the Privacy agent maintains the register, the user explores it
	 * (system proposes, user owns); the graph informs, it never edits.
	 *
	 * Rendered with @xyflow/svelte (ADR-F022) but in LQ.AI's own F013 style — our
	 * custom node card, our charcoal + scarce-accent palette — NOT the library's
	 * or OneTrust's/Oscar's chrome. Svelte Flow is client-only, so the canvas is
	 * browser-guarded with a text fallback.
	 */
	import { browser } from '$app/environment';
	import {
		Background,
		Controls,
		SvelteFlow,
		type Edge,
		type Node,
		type NodeTypes
	} from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';

	import type { DataFlowGraph } from '$lib/lq-ai/api/ropa';
	import DataFlowNodeCard from './DataFlowNodeCard.svelte';
	import { layoutDataFlow } from './dataFlow';

	let { graph }: { graph: DataFlowGraph } = $props();

	const nodeTypes: NodeTypes = { flowNode: DataFlowNodeCard };

	const isEmpty = $derived(graph.nodes.length === 0);

	// Svelte Flow binds (and mutates on drag) the node/edge arrays; (re)build them
	// from the pure layout whenever the register graph changes.
	let nodes = $state.raw<Node[]>([]);
	let edges = $state.raw<Edge[]>([]);
	$effect(() => {
		const layout = layoutDataFlow(graph);
		nodes = layout.nodes;
		edges = layout.edges;
	});

	const LEGEND: { kind: string; label: string }[] = [
		{ kind: 'system', label: 'System' },
		{ kind: 'activity', label: 'Activity' },
		{ kind: 'recipient', label: 'Recipient' },
		{ kind: 'destination', label: 'Third country' }
	];
</script>

<div data-testid="lq-ropa-dataflow">
	{#if isEmpty}
		<p class="max-w-prose text-sm text-muted-foreground">
			No data flows yet — the Privacy agent maps systems, activities, recipients and transfers as it
			builds the register, and this lineage view fills in as those links are recorded.
		</p>
	{:else if browser}
		<div class="space-y-3">
			<!-- Legend: kind accents + the restricted-transfer cue. -->
			<div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
				{#each LEGEND as l (l.kind)}
					<span class="flex items-center gap-1.5">
						<span class="size-2.5 rounded-sm lqf-dot lqf-dot-{l.kind}"></span>{l.label}
					</span>
				{/each}
				<span class="flex items-center gap-1.5">
					<span class="lqf-restricted-cue"></span>Restricted transfer
				</span>
			</div>

			<div class="lqf-canvas rounded-lg border border-border">
				<SvelteFlow
					bind:nodes
					bind:edges
					{nodeTypes}
					fitView
					nodesConnectable={false}
					proOptions={{ hideAttribution: true }}
				>
					<Background />
					<Controls showLock={false} />
				</SvelteFlow>
			</div>
		</div>
	{:else}
		<p class="max-w-prose text-sm text-muted-foreground">Loading the data-flow map…</p>
	{/if}
</div>

<style>
	.lqf-canvas {
		height: 560px;
		overflow: hidden;
	}
	/* F013 styling of the Svelte Flow canvas — calm charcoal + scarce accent. */
	.lqf-canvas :global(.svelte-flow) {
		background: var(--background);
	}
	.lqf-canvas :global(.svelte-flow__edge-path) {
		stroke: var(--border);
	}
	.lqf-canvas :global(.lqf-edge-disclosed_to .svelte-flow__edge-path),
	.lqf-canvas :global(.lqf-edge-transferred_to .svelte-flow__edge-path) {
		stroke: var(--muted-foreground);
	}
	.lqf-canvas :global(.lqf-edge-restricted .svelte-flow__edge-path) {
		stroke: var(--destructive);
	}
	.lqf-canvas :global(.svelte-flow__edge-text) {
		fill: var(--muted-foreground);
		font-size: 0.625rem;
	}

	/* Legend cues — match the node-card left-accent colours. */
	.lqf-dot-system {
		background: var(--brand);
	}
	.lqf-dot-activity {
		background: var(--foreground);
	}
	.lqf-dot-recipient {
		background: var(--muted-foreground);
	}
	.lqf-dot-destination {
		background: var(--destructive);
	}
	.lqf-restricted-cue {
		display: inline-block;
		height: 2px;
		width: 1rem;
		background: var(--destructive);
	}
</style>
