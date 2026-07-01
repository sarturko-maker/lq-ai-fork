<script lang="ts">
	/**
	 * F2 Tabular T7 — the matter's Grids tab (ADR-F055).
	 *
	 * A full-width read panel listing this matter's agentic grids (the derived
	 * artifacts of the tabular-review tool), sibling to Documents (source files).
	 * Each row opens the reused full grid at /tabular/[id] and can be soft-deleted
	 * (the lawyer owns the artifact — ADR-F042). Owner-scoped server-side
	 * (cross-matter → 404). A grid has no stored title, so the row title is derived
	 * from its column names.
	 */
	import { onDestroy, onMount, untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import TableIcon from '@lucide/svelte/icons/table';
	import Trash2Icon from '@lucide/svelte/icons/trash-2';

	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';
	import { timeAgo } from '$lib/lq-ai/cockpit/helpers';
	import { listMatterGrids, deleteTabularExecution } from '$lib/lq-ai/api/tabular';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import type { TabularExecutionSummary } from '$lib/lq-ai/types';
	import { gridStatusLabel, gridStatusTone, gridSubtitle, gridTitle } from './grids-panel-helpers';

	let {
		projectId,
		reloadKey = 0,
		nowMs,
		onOpenGrid
	}: {
		projectId: string;
		reloadKey?: number;
		nowMs: number;
		/**
		 * F2 Tabular T6: open a grid as an in-cockpit stage-takeover (keeps the
		 * conversation mounted → live SSE survives). When absent (e.g. a future
		 * standalone mount) the row falls back to navigating to `/tabular/[id]`.
		 */
		onOpenGrid?: (gridId: string) => void;
	} = $props();

	let grids = $state<TabularExecutionSummary[] | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let deletingId = $state<string | null>(null);
	let actionError = $state<string | null>(null);

	// Out-of-order guard: a slow fetch must not clobber a fresher one (mirrors
	// DocumentsPanel / MemoryPanel — the settle reconcile can overlap a load).
	let loadGeneration = 0;
	let destroyed = false;

	async function load(quiet = false) {
		const gen = ++loadGeneration;
		if (!quiet) {
			loading = true;
			error = null;
		}
		try {
			const data = await listMatterGrids(projectId);
			if (gen !== loadGeneration || destroyed) return;
			grids = data;
			if (!quiet) error = null;
		} catch (e) {
			if (gen !== loadGeneration || destroyed) return;
			if (!quiet) {
				error = e instanceof LQAIApiError ? e.message : 'Failed to load this matter’s grids.';
			}
		} finally {
			if (!quiet && gen === loadGeneration) loading = false;
		}
	}

	onMount(() => {
		void load();
	});
	onDestroy(() => {
		destroyed = true;
	});

	// Settle reconcile: when the host bumps reloadKey (a run just settled), pull
	// once so a newly-finalized grid appears without a manual refresh.
	let lastReloadKey = untrack(() => reloadKey);
	$effect(() => {
		if (reloadKey === lastReloadKey) return;
		lastReloadKey = reloadKey;
		void load(true);
	});

	function open(grid: TabularExecutionSummary) {
		if (onOpenGrid) {
			onOpenGrid(grid.id);
			return;
		}
		void goto(`/lq-ai/tabular/${grid.id}`);
	}

	async function remove(grid: TabularExecutionSummary) {
		actionError = null;
		deletingId = grid.id;
		try {
			await deleteTabularExecution(grid.id);
			if (destroyed) return;
			// Supersede any in-flight (settle-triggered) load whose snapshot predates
			// this DELETE — otherwise it could re-insert the just-deleted row.
			loadGeneration++;
			grids = (grids ?? []).filter((g) => g.id !== grid.id);
		} catch (e) {
			if (destroyed) return;
			actionError = e instanceof LQAIApiError ? e.message : 'Could not delete this grid.';
		} finally {
			if (!destroyed) deletingId = null;
		}
	}
</script>

<PageShell>
	<SectionHeader title="Grids" subtitle="Comparison grids this matter's agent has built." />

	{#if loading}
		<div class="space-y-2" data-testid="lq-grids-loading">
			{#each [0, 1, 2] as i (i)}
				<Skeleton class="h-16 w-full rounded-lg" />
			{/each}
		</div>
	{:else if error}
		<p class="text-sm text-destructive" data-testid="lq-grids-error">
			{error}
			<button type="button" class="ml-2 underline" onclick={() => load()}>Retry</button>
		</p>
	{:else if !grids || grids.length === 0}
		<div
			class="rounded-lg border border-dashed border-border p-6 text-center"
			data-testid="lq-grids-empty"
		>
			<TableIcon class="mx-auto size-6 text-muted-foreground" aria-hidden="true" />
			<p class="mt-2 text-sm font-medium text-foreground">No grids yet</p>
			<p class="mt-1 text-xs text-muted-foreground">
				Ask the agent to compare a field across several of this matter's documents — the grid it
				builds will appear here.
			</p>
		</div>
	{:else}
		{#if actionError}
			<p class="text-sm text-destructive" data-testid="lq-grids-action-error">{actionError}</p>
		{/if}
		<ul class="space-y-2" data-testid="lq-grids-list">
			{#each grids as grid (grid.id)}
				<li
					class="flex items-center gap-3 rounded-lg border border-border bg-card p-3 transition-colors hover:bg-muted/40"
					data-testid="lq-grids-row"
					data-grid-id={grid.id}
				>
					<TableIcon class="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
					<button
						type="button"
						class="min-w-0 flex-1 text-left"
						onclick={() => open(grid)}
						data-testid="lq-grids-open"
					>
						<span class="block truncate text-sm font-medium text-foreground">{gridTitle(grid)}</span
						>
						<span class="block truncate text-xs text-muted-foreground">
							{gridSubtitle(grid)} · {timeAgo(grid.created_at, nowMs)}
						</span>
					</button>
					<Badge variant="secondary" class="shrink-0 ag-grid-status--{gridStatusTone(grid.status)}">
						{gridStatusLabel(grid.status)}
					</Badge>
					<Button
						variant="ghost"
						size="icon"
						class="shrink-0 text-muted-foreground hover:text-destructive"
						disabled={deletingId === grid.id}
						onclick={() => remove(grid)}
						aria-label="Delete grid"
						data-testid="lq-grids-delete"
					>
						<Trash2Icon class="size-4" aria-hidden="true" />
					</Button>
				</li>
			{/each}
		</ul>
	{/if}
</PageShell>
