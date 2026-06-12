<script lang="ts">
	/**
	 * Matters list for an entered practice area — activity rollups from
	 * settled rows (ADR-F004), pick-or-create in place (S8 plumbing),
	 * resume by clicking through to the matter view. The unit-of-work
	 * noun renders from area data, never code (ADR-F004).
	 */
	import PlusIcon from '@lucide/svelte/icons/plus';
	import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left';
	import ShieldIcon from '@lucide/svelte/icons/shield';

	import { Button } from '$lib/components/ui/button/index.js';
	import type { MatterActivity } from '$lib/lq-ai/api/agents';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { Project } from '$lib/lq-ai/types';
	import NewMatterDialog from './NewMatterDialog.svelte';
	import StatusPill from './StatusPill.svelte';
	import { timeAgo } from './helpers';

	let {
		area,
		matters,
		mattersError,
		nowMs,
		onBack,
		onOpenMatter,
		onCreated
	}: {
		area: PracticeArea;
		matters: MatterActivity[] | null;
		mattersError: string | null;
		nowMs: number;
		onBack: () => void;
		onOpenMatter: (matter: MatterActivity) => void;
		onCreated: (project: Project) => void;
	} = $props();

	const noun = $derived(area.unit_label.toLowerCase());

	let createOpen = $state(false);
</script>

<div class="mx-auto w-full max-w-4xl px-8 py-8" data-testid="lq-cockpit-matters">
	<button
		type="button"
		class="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors duration-150 hover:text-foreground"
		onclick={onBack}
	>
		<ChevronLeftIcon class="size-3.5" aria-hidden="true" />
		Practice areas
	</button>
	<div class="mt-2 flex items-center justify-between">
		<div>
			<h1 class="text-xl font-semibold tracking-tight text-foreground">{area.name}</h1>
			<p class="mt-0.5 text-sm text-muted-foreground">
				{area.unit_label}s in this area, most recent activity first.
			</p>
		</div>
		<Button size="sm" class="gap-1.5" onclick={() => (createOpen = true)}>
			<PlusIcon class="size-4" aria-hidden="true" />
			New {noun}
		</Button>
	</div>

	{#if mattersError}
		<p class="mt-6 text-sm text-destructive">Couldn't load {noun}s: {mattersError}</p>
	{:else if matters === null}
		<div class="mt-6 space-y-px" aria-hidden="true">
			{#each [0, 1, 2, 3] as i (i)}
				<div class="h-9 animate-pulse rounded-md bg-muted"></div>
			{/each}
		</div>
	{:else if matters.length === 0}
		<div class="mt-10 rounded-lg border border-border bg-card px-8 py-12 text-center">
			<h2 class="text-base font-semibold text-foreground">No {noun}s yet</h2>
			<p class="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
				Create your first {noun} — conversations, documents, and the agent's work all live inside it.
			</p>
			<Button class="mt-4" onclick={() => (createOpen = true)}>New {noun}</Button>
		</div>
	{:else}
		<ul class="mt-5 overflow-hidden rounded-lg border border-border bg-card">
			{#each matters as matter (matter.project_id)}
				<li class="border-b border-border last:border-b-0">
					<button
						type="button"
						class="flex h-12 w-full items-center gap-3 px-4 text-left transition-colors duration-150 hover:bg-muted/60"
						data-testid="lq-cockpit-matter-row"
						onclick={() => onOpenMatter(matter)}
					>
						<span class="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
							{matter.name}
							{#if matter.privileged}
								<ShieldIcon
									class="ml-1 inline size-3.5 align-[-2px] text-muted-foreground"
									aria-label="Privileged"
								/>
							{/if}
						</span>
						{#if matter.thread_count > 0}
							<span class="text-xs text-muted-foreground tabular-nums">
								{matter.thread_count} conversation{matter.thread_count === 1 ? '' : 's'}
							</span>
						{/if}
						<StatusPill status={matter.last_run_status} lastRunAt={matter.last_run_at} {nowMs} />
						<span class="w-20 text-right text-xs text-muted-foreground tabular-nums">
							{timeAgo(matter.last_run_at, nowMs)}
						</span>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<NewMatterDialog bind:open={createOpen} unitLabel={area.unit_label} {onCreated} />
