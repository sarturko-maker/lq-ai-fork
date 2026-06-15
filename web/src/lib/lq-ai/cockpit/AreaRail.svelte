<script lang="ts">
	/**
	 * LEFT rail — practice areas from seeded `practice_areas` rows
	 * (ADR-F002: backend entities; frontend-only grouping was rejected)
	 * plus the pinned "Unfiled conversations" bucket. Unconfigured areas
	 * are INERT: visibly listed, honestly disabled — no composer, no
	 * matter creation under them (MILESTONES § F1 demo-tool rule).
	 *
	 * F2-VL2: re-skinned to the F013 Vercel sidebar — a `--sidebar` surface
	 * with a "New matter" ink button (routes to the launcher), the area list
	 * carrying a per-area activity `StatusDot` (the area's latest matter
	 * status, ADR-F004 settled rows), the unfiled bucket, and an account
	 * footer. Account ACTIONS stay in the header (CockpitHeader); the footer
	 * is identity only. Keeps the practice-area-first IA (no IA change — F2).
	 */
	import InboxIcon from '@lucide/svelte/icons/inbox';
	import PlusIcon from '@lucide/svelte/icons/plus';

	import { Button } from '$lib/components/ui/button/index.js';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { MatterActivity, UnfiledThreadsSummary } from '$lib/lq-ai/api/agents';
	import type { User } from '$lib/lq-ai/tabs';
	import StatusDot from '$lib/lq-ai/components/primitives/StatusDot.svelte';
	import { areaActivityCounts, runDot } from './helpers';

	let {
		areas,
		areasError,
		unfiled,
		matters,
		nowMs,
		user,
		selectedAreaKey,
		unfiledOpen,
		onSelectArea,
		onSelectUnfiled,
		onNewMatter
	}: {
		areas: PracticeArea[] | null;
		areasError: string | null;
		unfiled: UnfiledThreadsSummary | null;
		matters: MatterActivity[] | null;
		nowMs: number;
		user: User | null;
		selectedAreaKey: string | null;
		unfiledOpen: boolean;
		onSelectArea: (area: PracticeArea) => void;
		onSelectUnfiled: () => void;
		/** Start something new — routes to the landing launcher (ADR-F002). */
		onNewMatter: () => void;
	} = $props();

	const byArea = $derived(matters === null ? null : areaActivityCounts(matters));
	const accountInitial = $derived((user?.email ?? '?').trim().charAt(0).toUpperCase() || '?');
</script>

<!-- The rail is the Vercel `--sidebar` surface (#fafafa / #0c0c0c) — a step off
     the white canvas the main pane sits on; the resizer hairline divides them. -->
<nav
	class="bg-sidebar text-sidebar-foreground flex h-full min-h-0 flex-col"
	aria-label="Practice areas"
	data-testid="lq-cockpit-rail"
>
	<div class="px-3 pt-3 pb-1">
		<Button
			class="w-full justify-center gap-1.5"
			data-testid="lq-cockpit-new-matter"
			onclick={onNewMatter}
		>
			<PlusIcon class="size-4" aria-hidden="true" /> New matter
		</Button>
	</div>

	<div class="flex-1 overflow-y-auto px-2 py-3">
		<p class="text-label text-muted-foreground px-2.5 pb-1.5 uppercase">Practice areas</p>
		{#if areas === null && !areasError}
			<!-- Skeletons match the real row height (h-9). -->
			<div class="space-y-0.5" aria-hidden="true">
				{#each [0, 1, 2] as i (i)}
					<div class="bg-sidebar-accent/70 h-9 animate-pulse rounded-md"></div>
				{/each}
			</div>
		{:else if areasError}
			<p class="px-2.5 py-1 text-sm text-destructive">Couldn't load practice areas: {areasError}</p>
		{:else if areas}
			<ul class="space-y-0.5">
				{#each areas as area (area.id)}
					<li>
						{#if area.configured}
							{@const stats = byArea?.get(area.key)}
							{@const rd =
								stats && stats.lastStatus !== null
									? runDot(stats.lastStatus, stats.lastActivity, nowMs)
									: null}
							<button
								type="button"
								class="flex h-9 w-full items-center justify-between gap-2 rounded-md px-2.5 text-sm font-medium transition-colors duration-150 ease-out {selectedAreaKey ===
									area.key && !unfiledOpen
									? 'bg-card text-foreground shadow-xs'
									: 'hover:bg-sidebar-accent'}"
								data-testid="lq-cockpit-area-{area.key}"
								onclick={() => onSelectArea(area)}
							>
								<span class="min-w-0 truncate">{area.name}</span>
								{#if rd}
									<!-- bare activity dot (no label) — the area's latest status. -->
									<StatusDot status={rd.dot} label="" title={rd.label} class="shrink-0" />
								{/if}
							</button>
						{:else}
							<div
								class="text-muted-foreground flex h-9 w-full cursor-default items-center justify-between gap-2 rounded-md px-2.5 text-sm"
								aria-disabled="true"
								data-testid="lq-cockpit-area-{area.key}"
							>
								<span class="min-w-0 truncate">{area.name}</span>
								<span class="shrink-0 text-[11px] whitespace-nowrap">Not configured</span>
							</div>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</div>

	<div class="border-sidebar-border shrink-0 border-t px-2 py-2">
		<button
			type="button"
			class="flex h-9 w-full items-center justify-between rounded-md px-2.5 text-sm font-medium transition-colors duration-150 {unfiledOpen
				? 'bg-card text-foreground shadow-xs'
				: 'hover:bg-sidebar-accent'}"
			data-testid="lq-cockpit-unfiled"
			onclick={onSelectUnfiled}
		>
			<span class="flex min-w-0 items-center gap-2">
				<InboxIcon class="text-muted-foreground size-4 shrink-0" aria-hidden="true" />
				<span class="truncate">Unfiled conversations</span>
			</span>
			{#if unfiled && unfiled.thread_count > 0}
				<span
					class="bg-sidebar-accent rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums"
				>
					{unfiled.thread_count}
				</span>
			{/if}
		</button>
	</div>

	{#if user}
		<!-- Account footer — identity only; sign-out/settings live in the header. -->
		<div class="border-sidebar-border flex shrink-0 items-center gap-2.5 border-t px-4 py-3">
			<span
				class="bg-muted border-border grid size-7 shrink-0 place-items-center rounded-full border text-[11px] font-semibold"
				aria-hidden="true">{accountInitial}</span
			>
			<span class="min-w-0 leading-tight">
				<span class="text-foreground block truncate text-xs font-medium">{user.email}</span>
				<span class="text-muted-foreground block text-[11px] capitalize"
					>{user.role ?? 'member'}</span
				>
			</span>
		</div>
	{/if}
</nav>
