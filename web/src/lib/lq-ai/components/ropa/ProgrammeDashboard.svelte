<script lang="ts">
	/**
	 * Privacy programme dashboard (PRIV-6b) — the read-only "SEE the programme"
	 * overview over the deployment-global ROPA register: headline totals, the
	 * register's shape (lawful-basis / controller-role / DPA-status breakdowns,
	 * special-category & restricted-transfer counts) and honest "needs attention"
	 * gaps. Pure presentation over the server-computed `ProgrammeSummary` (counts
	 * only — no free-text). LQ.AI F013 style (charcoal + scarce accent), NOT
	 * Oscar's/OneTrust's chrome. The dashboard informs; it never remediates
	 * (system proposes, user owns).
	 */
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert';
	import CheckIcon from '@lucide/svelte/icons/check';
	import type { CountByValue, ProgrammeSummary } from '$lib/lq-ai/api/ropa';
	import { controllerRoleLabel, dpaStatusLabel, lawfulBasisLabel } from './format';

	let { summary }: { summary: ProgrammeSummary } = $props();

	const isEmpty = $derived(
		summary.activities_total === 0 &&
			summary.systems_total === 0 &&
			summary.vendors_total === 0
	);

	const tiles = $derived([
		{ label: 'Processing activities', value: summary.activities_total },
		{ label: 'Systems', value: summary.systems_total },
		{ label: 'Vendors', value: summary.vendors_total },
		{ label: 'Third-country transfers', value: summary.transfers_total }
	]);

	type Group = { title: string; buckets: CountByValue[]; labelOf: (v: string) => string };
	const groups = $derived<Group[]>([
		{ title: 'Lawful basis', buckets: summary.lawful_basis, labelOf: lawfulBasisLabel },
		{ title: 'Controller role', buckets: summary.controller_role, labelOf: controllerRoleLabel },
		{ title: 'DPA status', buckets: summary.dpa_status, labelOf: dpaStatusLabel }
	]);

	// Calm: hide zero buckets; bar width is relative to the busiest bucket in the group.
	function shown(buckets: CountByValue[]): CountByValue[] {
		return buckets.filter((b) => b.count > 0);
	}
	function pct(count: number, buckets: CountByValue[]): number {
		const max = Math.max(1, ...buckets.map((b) => b.count));
		return Math.round((count / max) * 100);
	}

	const gaps = $derived(
		[
			{ label: 'activities with no system mapped', count: summary.gaps.activities_without_systems },
			{
				label: 'activities with no recipient recorded',
				count: summary.gaps.activities_without_recipients
			},
			{
				label: 'activities with no personal-data categories',
				count: summary.gaps.activities_without_data_categories
			},
			{
				label: 'activities with no data-subject categories',
				count: summary.gaps.activities_without_data_subjects
			},
			{ label: 'vendors with an outstanding DPA', count: summary.gaps.vendors_without_dpa }
		].filter((g) => g.count > 0)
	);
</script>

<div data-testid="lq-ropa-dashboard">
{#if isEmpty}
	<p class="max-w-prose text-sm text-muted-foreground">
		No programme data yet — the Privacy agent builds the ROPA register as it works, and this overview
		fills in as activities, systems and vendors are recorded.
	</p>
{:else}
	<div class="space-y-6">
		<!-- Headline totals -->
		<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
			{#each tiles as t (t.label)}
				<div class="rounded-lg border border-border p-4">
					<div class="text-2xl font-semibold tracking-tight text-foreground">{t.value}</div>
					<div class="mt-0.5 text-xs text-muted-foreground">{t.label}</div>
					{#if t.label === 'Third-country transfers' && summary.transfers_total > 0}
						<div class="mt-1 text-xs text-muted-foreground">
							{summary.transfers_restricted} restricted
						</div>
					{/if}
				</div>
			{/each}
		</div>

		<!-- Secondary signals -->
		<div class="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
			<span><span class="font-medium text-foreground">{summary.special_category_activities}</span>
				special-category {summary.special_category_activities === 1 ? 'activity' : 'activities'}</span>
			<span><span class="font-medium text-foreground">{summary.systems_using_ai}</span>
				{summary.systems_using_ai === 1 ? 'system' : 'systems'} using AI</span>
		</div>

		<!-- Breakdowns -->
		<div class="grid grid-cols-1 gap-5 md:grid-cols-3">
			{#each groups as g (g.title)}
				<div class="space-y-2">
					<h3 class="text-sm font-semibold tracking-tight text-foreground">{g.title}</h3>
					{#if shown(g.buckets).length === 0}
						<p class="text-sm text-muted-foreground">—</p>
					{:else}
						<ul class="space-y-1.5">
							{#each shown(g.buckets) as b (b.value)}
								<li class="space-y-1">
									<div class="flex items-baseline justify-between gap-2 text-sm">
										<span class="text-foreground">{g.labelOf(b.value)}</span>
										<span class="tabular-nums text-muted-foreground">{b.count}</span>
									</div>
									<div class="h-1.5 overflow-hidden rounded-full bg-muted">
										<div
											class="h-full rounded-full bg-foreground/70"
											style="width: {pct(b.count, g.buckets)}%"
										></div>
									</div>
								</li>
							{/each}
						</ul>
					{/if}
				</div>
			{/each}
		</div>

		<!-- Needs attention -->
		<div class="space-y-2">
			<h3 class="text-sm font-semibold tracking-tight text-foreground">Needs attention</h3>
			{#if gaps.length === 0}
				<p class="flex items-center gap-2 text-sm text-muted-foreground">
					<CheckIcon class="size-4 text-brand" aria-hidden="true" />
					Nothing outstanding — every activity is mapped and every DPA is settled.
				</p>
			{:else}
				<ul class="space-y-1.5">
					{#each gaps as gap (gap.label)}
						<li
							class="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-foreground"
						>
							<TriangleAlertIcon class="size-4 shrink-0 text-destructive" aria-hidden="true" />
							<span class="font-medium tabular-nums">{gap.count}</span>
							<span class="text-muted-foreground">{gap.label}</span>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	</div>
{/if}
</div>
