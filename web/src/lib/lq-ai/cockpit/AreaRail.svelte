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
	 *
	 * UX-A-2 (ADR-F014): an expandable "Tools" group lists the tool surfaces
	 * (Lucide glyphs via the shared `tabIcon()` map; active highlight from the
	 * caller's `activeTab`; the legacy executor group rests one step quieter,
	 * the M3 treatment). Selecting one renders it in the cockpit canvas (for
	 * migrated surfaces) — the way "back to the cockpit" is now always the rail.
	 */
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import InboxIcon from '@lucide/svelte/icons/inbox';
	import PlusIcon from '@lucide/svelte/icons/plus';

	import { Button } from '$lib/components/ui/button/index.js';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { MatterActivity, UnfiledThreadsSummary } from '$lib/lq-ai/api/agents';
	import { tabGroupOf, type TabDef, type TabId, type User } from '$lib/lq-ai/tabs';
	import { tabIcon } from '$lib/lq-ai/tab-icons';
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
		toolTabs,
		activeTab,
		onSelectArea,
		onSelectUnfiled,
		onNewMatter,
		onSelectTool
	}: {
		areas: PracticeArea[] | null;
		areasError: string | null;
		unfiled: UnfiledThreadsSummary | null;
		matters: MatterActivity[] | null;
		nowMs: number;
		user: User | null;
		selectedAreaKey: string | null;
		unfiledOpen: boolean;
		/** The tool surfaces to list under "Tools" (already role/pref-filtered). */
		toolTabs: TabDef[];
		/** The tab id the canvas is currently showing, for the active highlight. */
		activeTab: TabId | null;
		onSelectArea: (area: PracticeArea) => void;
		onSelectUnfiled: () => void;
		/** Start something new — routes to the landing launcher (ADR-F002). */
		onNewMatter: () => void;
		/** Open a tool surface (renders in the canvas for migrated surfaces). */
		onSelectTool: (tab: TabDef) => void;
	} = $props();

	const byArea = $derived(matters === null ? null : areaActivityCounts(matters));
	const accountInitial = $derived((user?.email ?? '?').trim().charAt(0).toUpperCase() || '?');

	// Expandable Tools group — open by default so the surfaces are discoverable
	// (the dead-end this slice fixes). Component-local; the pane + drawer each
	// hold their own toggle, which is fine since only one is visible at a time.
	let toolsOpen = $state(true);
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

		<!-- Tools — the expandable surface group (UX-A-2, ADR-F014). Reaches the
		     tool surfaces from the cockpit rail; migrated surfaces render in the
		     canvas alongside this rail (no more dead-end). -->
		<div class="border-sidebar-border mt-3 border-t pt-3">
			<button
				type="button"
				class="text-label text-muted-foreground hover:text-foreground flex w-full items-center justify-between px-2.5 pb-1.5 uppercase transition-colors duration-150"
				aria-expanded={toolsOpen}
				aria-controls="lq-cockpit-tools"
				data-testid="lq-cockpit-tools-toggle"
				onclick={() => (toolsOpen = !toolsOpen)}
			>
				<span>Tools</span>
				<ChevronDownIcon
					class="size-3.5 transition-transform duration-150 ease-out {toolsOpen
						? ''
						: '-rotate-90'}"
					aria-hidden="true"
				/>
			</button>
			{#if toolsOpen}
				<ul class="space-y-0.5" id="lq-cockpit-tools" data-testid="lq-cockpit-tools">
					{#each toolTabs as tab (tab.id)}
						{@const Icon = tabIcon(tab.id)}
						{@const isActive = activeTab === tab.id}
						<li>
							<button
								type="button"
								class="flex h-9 w-full items-center gap-2 rounded-md px-2.5 text-sm font-medium transition-colors duration-150 ease-out {isActive
									? 'bg-card text-foreground shadow-xs'
									: tabGroupOf(tab) === 'legacy'
										? 'text-muted-foreground/80 hover:bg-sidebar-accent hover:text-foreground'
										: 'hover:bg-sidebar-accent'}"
								aria-current={isActive ? 'page' : undefined}
								data-testid="lq-cockpit-tool-{tab.id}"
								onclick={() => onSelectTool(tab)}
							>
								<Icon class="text-muted-foreground size-4 shrink-0" aria-hidden="true" />
								<span class="min-w-0 truncate">{tab.label}</span>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
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
