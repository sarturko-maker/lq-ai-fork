<script lang="ts">
	/**
	 * LEFT rail — practice areas from seeded `practice_areas` rows
	 * (ADR-F002: backend entities; frontend-only grouping was rejected)
	 * plus the pinned "Unfiled conversations" bucket. Unconfigured areas
	 * are INERT: visibly listed, honestly disabled — no composer, no
	 * matter creation under them (MILESTONES § F1 demo-tool rule).
	 */
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { UnfiledThreadsSummary } from '$lib/lq-ai/api/agents';
	import InboxIcon from '@lucide/svelte/icons/inbox';

	let {
		areas,
		areasError,
		unfiled,
		selectedAreaKey,
		unfiledOpen,
		onSelectArea,
		onSelectUnfiled
	}: {
		areas: PracticeArea[] | null;
		areasError: string | null;
		unfiled: UnfiledThreadsSummary | null;
		selectedAreaKey: string | null;
		unfiledOpen: boolean;
		onSelectArea: (area: PracticeArea) => void;
		onSelectUnfiled: () => void;
	} = $props();
</script>

<!-- The rail sits ON the canvas (F1-S2.1: content floats as cards, nav
     recedes — the bg comes from the shell: canvas in the pane, raised
     bg-background in the narrow drawer). -->
<nav
	class="flex h-full min-h-0 flex-col text-sidebar-foreground"
	aria-label="Practice areas"
	data-testid="lq-cockpit-rail"
>
	<div class="flex-1 overflow-y-auto px-2 py-3">
		<p
			class="px-2.5 pb-1.5 text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase"
		>
			Practice areas
		</p>
		{#if areas === null && !areasError}
			<!-- Skeletons match the real row height (h-9). -->
			<div class="space-y-0.5" aria-hidden="true">
				{#each [0, 1, 2] as i (i)}
					<div class="h-9 animate-pulse rounded-md bg-sidebar-accent/70"></div>
				{/each}
			</div>
		{:else if areasError}
			<p class="px-2.5 py-1 text-sm text-destructive">Couldn't load practice areas: {areasError}</p>
		{:else if areas}
			<ul class="space-y-0.5">
				{#each areas as area (area.id)}
					<li>
						{#if area.configured}
							<button
								type="button"
								class="flex h-9 w-full items-center justify-between gap-2 rounded-md px-2.5 text-sm font-medium transition-colors duration-150 ease-out hover:bg-sidebar-accent {selectedAreaKey ===
									area.key && !unfiledOpen
									? 'bg-accent text-accent-foreground'
									: ''}"
								data-testid="lq-cockpit-area-{area.key}"
								onclick={() => onSelectArea(area)}
							>
								<span class="min-w-0 truncate">{area.name}</span>
							</button>
						{:else}
							<div
								class="flex h-9 w-full cursor-default items-center justify-between gap-2 rounded-md px-2.5 text-sm text-muted-foreground"
								aria-disabled="true"
								data-testid="lq-cockpit-area-{area.key}"
							>
								<span class="min-w-0 truncate">{area.name}</span>
								<span class="shrink-0 text-[11px] whitespace-nowrap text-muted-foreground/80">
									Not configured
								</span>
							</div>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</div>
	<div class="shrink-0 border-t border-sidebar-border px-2 py-2">
		<button
			type="button"
			class="flex h-9 w-full items-center justify-between rounded-md px-2.5 text-sm font-medium transition-colors duration-150 hover:bg-sidebar-accent {unfiledOpen
				? 'bg-accent text-accent-foreground'
				: ''}"
			data-testid="lq-cockpit-unfiled"
			onclick={onSelectUnfiled}
		>
			<span class="flex min-w-0 items-center gap-2">
				<InboxIcon class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
				<span class="truncate">Unfiled conversations</span>
			</span>
			{#if unfiled && unfiled.thread_count > 0}
				<span
					class="rounded-full bg-sidebar-accent px-1.5 py-0.5 text-[11px] font-semibold tabular-nums"
				>
					{unfiled.thread_count}
				</span>
			{/if}
		</button>
		<p class="truncate px-2.5 pt-2 text-[11px] text-muted-foreground">
			<strong>LQ.AI</strong> — Open-Source Legal AI · Apache-2.0
		</p>
	</div>
</nav>
