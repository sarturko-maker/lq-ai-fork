<script lang="ts">
	/**
	 * Matters list for an entered practice area — activity rollups from
	 * settled rows (ADR-F004), pick-or-create in place (S8 plumbing),
	 * resume by clicking through to the matter view. The unit-of-work
	 * noun renders from area data, never code (ADR-F004).
	 */
	import { fade } from 'svelte/transition';
	import PlusIcon from '@lucide/svelte/icons/plus';
	import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left';
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right';
	import FolderOpenIcon from '@lucide/svelte/icons/folder-open';
	import ShieldIcon from '@lucide/svelte/icons/shield';

	import { Button } from '$lib/components/ui/button/index.js';
	import type { MatterActivity } from '$lib/lq-ai/api/agents';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { Project } from '$lib/lq-ai/types';
	import NewMatterDialog from './NewMatterDialog.svelte';
	import StatusPill from './StatusPill.svelte';
	import { mattersForArea, motionMs, timeAgo } from './helpers';

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

	// F1-S3: only THIS area's matters (they file via projects.practice_area_id,
	// surfaced as practice_area_key). null while loading.
	const areaMatters = $derived(matters === null ? null : mattersForArea(matters, area.key));

	let createOpen = $state(false);
</script>

<div
	class="mx-auto w-full max-w-4xl px-6 py-8 sm:px-8"
	data-testid="lq-cockpit-matters"
	in:fade|global={{ duration: motionMs(120) }}
>
	<button
		type="button"
		class="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors duration-150 hover:text-foreground"
		onclick={onBack}
	>
		<ChevronLeftIcon class="size-3.5" aria-hidden="true" />
		Practice areas
	</button>
	<div class="mt-2 flex items-center justify-between gap-3">
		<div class="min-w-0">
			<h1 class="truncate text-2xl font-semibold tracking-tight text-foreground">{area.name}</h1>
			<p class="mt-0.5 text-sm text-muted-foreground">
				{area.unit_label}s in this area, most recent activity first.
			</p>
		</div>
		<Button size="sm" class="shrink-0 gap-1.5" onclick={() => (createOpen = true)}>
			<PlusIcon class="size-4" aria-hidden="true" />
			New {noun}
		</Button>
	</div>

	{#if mattersError}
		<p class="mt-6 text-sm text-destructive">Couldn't load {noun}s: {mattersError}</p>
	{:else if areaMatters === null}
		<!-- Skeleton mirrors the loaded shape: a floating card of h-12 rows. -->
		<div
			class="mt-6 overflow-hidden rounded-xl border border-border bg-card shadow-xs"
			aria-hidden="true"
		>
			{#each [0, 1, 2, 3] as i (i)}
				<div class="flex h-12 items-center border-b border-border px-4 last:border-b-0">
					<div class="h-3.5 w-2/5 animate-pulse rounded bg-muted"></div>
				</div>
			{/each}
		</div>
	{:else if areaMatters.length === 0}
		<div class="mt-10 rounded-xl border border-border bg-card px-8 py-12 text-center shadow-xs">
			<div class="mx-auto flex size-10 items-center justify-center rounded-full bg-muted">
				<FolderOpenIcon class="size-5 text-muted-foreground" aria-hidden="true" />
			</div>
			<h2 class="mt-3 text-base font-semibold text-foreground">No {noun}s yet</h2>
			<p class="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
				Create your first {noun} — conversations, documents, and the agent's work all live inside it.
			</p>
			<Button class="mt-4" onclick={() => (createOpen = true)}>New {noun}</Button>
		</div>
	{:else}
		<ul class="mt-6 overflow-hidden rounded-xl border border-border bg-card shadow-xs">
			{#each areaMatters as matter (matter.project_id)}
				<li class="border-b border-border last:border-b-0">
					<button
						type="button"
						class="group flex h-12 w-full items-center gap-3 px-4 text-left transition-colors duration-150 ease-out hover:bg-muted/60"
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
						<ChevronRightIcon
							class="size-4 shrink-0 text-transparent transition-colors duration-150 group-hover:text-muted-foreground/70"
							aria-hidden="true"
						/>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<NewMatterDialog
	bind:open={createOpen}
	unitLabel={area.unit_label}
	practiceAreaId={area.id}
	{onCreated}
/>
