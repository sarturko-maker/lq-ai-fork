<script lang="ts">
	/**
	 * Landing view — the AREA LIST (MILESTONES § F1: the cockpit lands
	 * here, never auto-landed in an area). Configured areas are enterable
	 * cards with live rollups; unconfigured areas are INERT cards with an
	 * honest "Not configured" state.
	 */
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { MatterActivity } from '$lib/lq-ai/api/agents';
	import { timeAgo } from './helpers';

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

	// v0: every matter renders under the single configured area —
	// presentation only, nothing stored (S3's projects.practice_area_id
	// makes filing real; MILESTONES pre-F1 guard).
	const matterCount = $derived(matters?.length ?? null);
	const lastActivity = $derived(matters && matters.length > 0 ? matters[0].last_run_at : null);
</script>

<div class="mx-auto w-full max-w-4xl px-8 py-10" data-testid="lq-cockpit-area-grid">
	<h1 class="text-xl font-semibold tracking-tight text-foreground">Your practice</h1>
	<p class="mt-1 text-sm text-muted-foreground">
		Pick a practice area to work in — each area runs its matters with its own agent.
	</p>

	{#if areasError}
		<p class="mt-6 text-sm text-destructive">Couldn't load practice areas: {areasError}</p>
	{:else if areas === null}
		<div class="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-hidden="true">
			{#each [0, 1, 2] as i (i)}
				<div class="h-28 animate-pulse rounded-lg border border-border bg-card"></div>
			{/each}
		</div>
	{:else}
		<div class="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{#each areas as area (area.id)}
				{#if area.configured}
					<button
						type="button"
						class="group flex flex-col items-start rounded-lg border border-border bg-card p-4 text-left transition-shadow duration-150 hover:shadow-[0_1px_2px_rgb(0_0_0/0.05),0_2px_8px_rgb(0_0_0/0.04)]"
						data-testid="lq-cockpit-area-card-{area.key}"
						onclick={() => onEnterArea(area)}
					>
						<span class="text-sm font-semibold text-foreground group-hover:text-primary">
							{area.name}
						</span>
						<span class="mt-1 text-xs text-muted-foreground">
							{#if matterCount === null}
								Loading {area.unit_label.toLowerCase()}s…
							{:else if matterCount === 0}
								No {area.unit_label.toLowerCase()}s yet
							{:else}
								<span class="tabular-nums">{matterCount}</span>
								{area.unit_label.toLowerCase()}{matterCount === 1 ? '' : 's'}
								{#if lastActivity}
									· active {timeAgo(lastActivity, nowMs)}
								{/if}
							{/if}
						</span>
						<span class="mt-3 text-xs font-medium text-primary">Enter →</span>
					</button>
				{:else}
					<div
						class="flex flex-col items-start rounded-lg border border-dashed border-border bg-transparent p-4"
						aria-disabled="true"
						data-testid="lq-cockpit-area-card-{area.key}"
					>
						<span
							class="flex w-full items-center justify-between text-sm font-semibold text-muted-foreground"
						>
							{area.name}
							<span
								class="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
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
