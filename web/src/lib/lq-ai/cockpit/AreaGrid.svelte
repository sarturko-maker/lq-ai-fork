<script lang="ts">
	/**
	 * Landing view — the AREA LIST (MILESTONES § F1: the cockpit lands here,
	 * never auto-landed in an area), re-skinned to the F013 Vercel language in
	 * F2-VL2. Configured areas are enterable `Card`s with live rollups + a
	 * `StatusDot` (the area's latest matter status); unconfigured areas are INERT
	 * dashed cards with an honest "Not configured" state. Below, a calm
	 * "Recent matters" dot-status list keeps every matter — incl. unfiled/legacy
	 * ones (null area key) — one click away.
	 *
	 * Area cards use gap'd bordered `Card`s (not the hairline `CardGrid` plane):
	 * with a variable area count the single-plane technique leaves a trailing
	 * empty cell on non-full rows (the VL1 carry-over), so the gap'd variant —
	 * clean at every count + breakpoint — is the resolution here. All rollups
	 * derive from settled rows (ADR-F004); no invented copy.
	 */
	import { fade } from 'svelte/transition';
	import BriefcaseIcon from '@lucide/svelte/icons/briefcase';
	import FolderIcon from '@lucide/svelte/icons/folder';
	import GavelIcon from '@lucide/svelte/icons/gavel';
	import ScaleIcon from '@lucide/svelte/icons/scale';
	import ShieldIcon from '@lucide/svelte/icons/shield';
	import UsersIcon from '@lucide/svelte/icons/users';

	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { MatterActivity } from '$lib/lq-ai/api/agents';
	import Card from '$lib/lq-ai/components/primitives/Card.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import Stack from '$lib/lq-ai/components/primitives/Stack.svelte';
	import StatusDot from '$lib/lq-ai/components/primitives/StatusDot.svelte';
	import { areaActivityCounts, MOTION, motionMs, runDot, timeAgo } from './helpers';

	let {
		areas,
		areasError,
		matters,
		nowMs,
		onEnterArea,
		onOpenMatter
	}: {
		areas: PracticeArea[] | null;
		areasError: string | null;
		matters: MatterActivity[] | null;
		nowMs: number;
		onEnterArea: (area: PracticeArea) => void;
		onOpenMatter: (matter: MatterActivity) => void;
	} = $props();

	// F1-S3: matters file under their area via projects.practice_area_id
	// (surfaced as practice_area_key) — each card counts only ITS matters.
	// null while loading (see areaActivityCounts).
	const byArea = $derived(matters === null ? null : areaActivityCounts(matters));

	// key → display name, for the recent-matters list (null key = unfiled).
	const areaNameByKey = $derived(new Map((areas ?? []).map((a) => [a.key, a.name])));

	// Decorative per-area glyph (presentation only; unknown keys fall back).
	const AREA_ICON: Record<string, typeof FolderIcon> = {
		commercial: ScaleIcon,
		disputes: GavelIcon,
		'm-and-a': BriefcaseIcon,
		privacy: ShieldIcon,
		employment: UsersIcon
	};
	function areaIcon(key: string): typeof FolderIcon {
		return AREA_ICON[key] ?? FolderIcon;
	}

	function unitPlural(area: PracticeArea, count: number): string {
		const unit = area.unit_label.toLowerCase();
		return `${unit}${count === 1 ? '' : 's'}`;
	}

	function matterSub(matter: MatterActivity): string {
		const area = matter.practice_area_key
			? (areaNameByKey.get(matter.practice_area_key) ?? matter.practice_area_key)
			: 'Unfiled';
		const convs = `${matter.thread_count} conversation${matter.thread_count === 1 ? '' : 's'}`;
		return `${area} · ${convs}`;
	}
</script>

<PageShell size="narrow" data-testid="lq-cockpit-area-grid">
	<div in:fade|global={{ duration: motionMs(MOTION.base) }}>
		{#if areasError}
			<p class="text-sm text-destructive">Couldn't load practice areas: {areasError}</p>
		{:else}
			<!-- F2-M4/VL2: an eyebrow, not a heading — the landing's single h1 is
			     the launcher hero above; the grid reads as the "or pick an area"
			     path. -->
			<p class="text-label text-muted-foreground uppercase">Your practice</p>

			{#if areas === null}
				<div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-hidden="true">
					{#each [0, 1, 2] as i (i)}
						<div class="border-border bg-card h-36 animate-pulse rounded-lg border"></div>
					{/each}
				</div>
			{:else}
				<div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
					{#each areas as area (area.id)}
						{@const Icon = areaIcon(area.key)}
						{#if area.configured}
							{@const stats = byArea?.get(area.key)}
							<Card
								bordered
								interactive
								data-testid="lq-cockpit-area-card-{area.key}"
								onclick={() => onEnterArea(area)}
							>
								<Stack gap="sm">
									<Icon class="text-foreground size-[22px]" strokeWidth={1.7} aria-hidden="true" />
									<span class="text-subheading text-foreground">{area.name}</span>
									{#if byArea === null}
										<span class="text-caption text-muted-foreground">Loading…</span>
									{:else if stats}
										{@const rd = runDot(stats.lastStatus, stats.lastActivity, nowMs)}
										<StatusDot
											status={rd.dot}
											title={rd.label}
											label="{stats.count} {unitPlural(area, stats.count)}{stats.lastActivity
												? ` · ${timeAgo(stats.lastActivity, nowMs)}`
												: ''}"
										/>
									{:else}
										<StatusDot status="idle" label="No {unitPlural(area, 0)} yet" />
									{/if}
								</Stack>
							</Card>
						{:else}
							<Card bordered class="border-dashed" data-testid="lq-cockpit-area-card-{area.key}">
								<Stack gap="sm">
									<Icon
										class="text-muted-foreground/60 size-[22px]"
										strokeWidth={1.7}
										aria-hidden="true"
									/>
									<span class="text-subheading text-muted-foreground flex items-center gap-2">
										<span class="min-w-0 truncate">{area.name}</span>
										<span
											class="bg-muted text-muted-foreground shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap"
										>
											Not configured
										</span>
									</span>
									<span class="text-caption text-muted-foreground">
										This area's agent hasn't been configured yet.
									</span>
								</Stack>
							</Card>
						{/if}
					{/each}
				</div>

				{#if matters && matters.length > 0}
					<!-- Recent matters — every matter, newest first (ADR-F004 settled
					     rows). Includes unfiled/legacy matters (null area key) so they
					     stay reachable; opening one binds by id (the matter view needs
					     no area). -->
					<section class="mt-12" data-testid="lq-cockpit-recent-matters">
						<p class="text-label text-muted-foreground uppercase">Recent matters</p>
						<div class="border-border mt-4 border-t">
							{#each matters as matter (matter.project_id)}
								{@const rd = runDot(matter.last_run_status, matter.last_run_at, nowMs)}
								<button
									type="button"
									class="border-border hover:bg-muted/50 -mx-2 flex w-full items-center justify-between gap-3 rounded-md border-b px-2 py-3.5 text-left transition-colors"
									data-testid="lq-cockpit-recent-matter-row"
									onclick={() => onOpenMatter(matter)}
								>
									<span class="min-w-0 flex-1">
										<span class="text-foreground block truncate text-sm font-medium">
											{matter.name}
										</span>
										<span class="text-caption text-muted-foreground block truncate">
											{matterSub(matter)}
										</span>
									</span>
									<span class="flex shrink-0 items-center gap-3">
										{#if matter.last_run_at}
											<span class="text-caption text-muted-foreground tabular-nums">
												{timeAgo(matter.last_run_at, nowMs)}
											</span>
										{/if}
										<StatusDot status={rd.dot} label={rd.label} />
									</span>
								</button>
							{/each}
						</div>
					</section>
				{/if}
			{/if}
		{/if}
	</div>
</PageShell>
