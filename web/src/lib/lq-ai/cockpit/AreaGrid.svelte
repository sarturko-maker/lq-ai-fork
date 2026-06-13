<script lang="ts">
	/**
	 * Landing view — the AREA LIST (MILESTONES § F1: the cockpit lands
	 * here, never auto-landed in an area). Configured areas are enterable
	 * cards with live rollups; unconfigured areas are INERT cards with an
	 * honest "Not configured" state.
	 */
	import { fade } from 'svelte/transition';
	import ArrowRightIcon from '@lucide/svelte/icons/arrow-right';

	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { MatterActivity } from '$lib/lq-ai/api/agents';
	import { areaActivityCounts, motionMs, timeAgo } from './helpers';

	let {
		areas,
		areasError,
		matters,
		nowMs,
		onEnterArea
	}: {
		areas: PracticeArea[] | null;
		areasError: string | null;
		matters: MatterActivity[] | null;
		nowMs: number;
		onEnterArea: (area: PracticeArea) => void;
	} = $props();

	// F1-S3: matters file under their area via projects.practice_area_id
	// (surfaced as practice_area_key) — each card counts only ITS matters.
	// null while loading (see areaActivityCounts).
	const byArea = $derived(matters === null ? null : areaActivityCounts(matters));
</script>

<div
	class="mx-auto w-full max-w-4xl px-6 py-10 sm:px-8"
	data-testid="lq-cockpit-area-grid"
	in:fade|global={{ duration: motionMs(120) }}
>
	<h1 class="text-2xl font-semibold tracking-tight text-foreground">Your practice</h1>
	<p class="mt-1.5 text-sm text-muted-foreground">
		Pick a practice area to work in — each area runs its matters with its own agent.
	</p>

	{#if areasError}
		<p class="mt-6 text-sm text-destructive">Couldn't load practice areas: {areasError}</p>
	{:else if areas === null}
		<div class="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-hidden="true">
			{#each [0, 1, 2] as i (i)}
				<div class="h-32 animate-pulse rounded-xl border border-border bg-card shadow-xs"></div>
			{/each}
		</div>
	{:else}
		<div class="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
			{#each areas as area (area.id)}
				{#if area.configured}
					{@const stats = byArea?.get(area.key)}
					<!-- Floating card: resting shadow-xs, hover lifts to shadow-sm
					     (tokenized elevation scale, F1-S2.1). -->
					<button
						type="button"
						class="group flex flex-col items-start rounded-xl border border-border bg-card p-5 text-left shadow-xs transition-[box-shadow,transform,border-color] duration-150 ease-out hover:-translate-y-px hover:shadow-sm"
						data-testid="lq-cockpit-area-card-{area.key}"
						onclick={() => onEnterArea(area)}
					>
						<span
							class="text-sm font-semibold text-foreground transition-colors duration-150 group-hover:text-primary"
						>
							{area.name}
						</span>
						<span class="mt-1 text-xs text-muted-foreground">
							{#if byArea === null}
								Loading {area.unit_label.toLowerCase()}s…
							{:else if !stats}
								No {area.unit_label.toLowerCase()}s yet
							{:else}
								<span class="tabular-nums">{stats.count}</span>
								{area.unit_label.toLowerCase()}{stats.count === 1 ? '' : 's'}
								{#if stats.lastActivity}
									· active {timeAgo(stats.lastActivity, nowMs)}
								{/if}
							{/if}
						</span>
						<span class="mt-4 flex items-center gap-1 text-xs font-medium text-primary">
							Enter
							<ArrowRightIcon
								class="size-3.5 transition-transform duration-150 ease-out group-hover:translate-x-0.5"
								aria-hidden="true"
							/>
						</span>
					</button>
				{:else}
					<div
						class="flex flex-col items-start rounded-xl border border-dashed border-border bg-card/40 p-5"
						aria-disabled="true"
						data-testid="lq-cockpit-area-card-{area.key}"
					>
						<span
							class="flex w-full items-center justify-between gap-2 text-sm font-semibold text-muted-foreground"
						>
							<span class="min-w-0 truncate">{area.name}</span>
							<span
								class="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium whitespace-nowrap text-muted-foreground"
							>
								Not configured
							</span>
						</span>
						<span class="mt-1 text-xs text-muted-foreground">
							This area's agent hasn't been configured yet.
						</span>
					</div>
				{/if}
			{/each}
		</div>
	{/if}
</div>
