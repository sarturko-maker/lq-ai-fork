<script lang="ts">
	/**
	 * One vendor / recipient + the processing activities that disclose to it
	 * (PRIV-5a). Read-only detail in LQ.AI's F013 style; cross-links to the
	 * activities that disclose to it (click one → the parent opens its detail).
	 */
	import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';
	import type { VendorRead } from '$lib/lq-ai/api/ropa';
	import { dpaStatusLabel, lawfulBasisLabel, vendorRoleLabel } from './format';

	let {
		vendor,
		onBack,
		onOpenActivity
	}: {
		vendor: VendorRead;
		onBack: () => void;
		onOpenActivity: (id: string) => void;
	} = $props();

	// Optional descriptive rows — only render what the agent has filled in.
	const rows = $derived(
		[
			{ label: 'Description', value: vendor.description },
			{ label: 'Country', value: vendor.country }
		].filter((r) => r.value)
	);
</script>

<div class="space-y-5">
	<button
		type="button"
		class="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors duration-150 hover:text-foreground"
		onclick={onBack}
	>
		<ChevronLeftIcon class="size-3.5" aria-hidden="true" />
		Register
	</button>

	<div class="flex flex-wrap items-start justify-between gap-3">
		<SectionHeader size="page" title={vendor.name} subtitle="Vendor / recipient" />
		<div class="flex flex-wrap gap-1.5">
			<Badge variant="secondary">{vendorRoleLabel(vendor.vendor_role)}</Badge>
			<Badge variant="outline">DPA: {dpaStatusLabel(vendor.dpa_status)}</Badge>
		</div>
	</div>

	{#if rows.length > 0}
		<dl class="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-[10rem_1fr]">
			{#each rows as row (row.label)}
				<dt class="text-muted-foreground">{row.label}</dt>
				<dd class="text-foreground">{row.value}</dd>
			{/each}
		</dl>
	{:else}
		<p class="text-sm text-muted-foreground">
			No further detail recorded yet — the Privacy agent fills these in as it learns the vendor.
		</p>
	{/if}

	<div class="space-y-2">
		<h3 class="text-sm font-semibold tracking-tight text-foreground">
			Receives data from
			<span class="text-muted-foreground">({vendor.processing_activities.length})</span>
		</h3>
		{#if vendor.processing_activities.length === 0}
			<p class="text-sm text-muted-foreground">
				No processing activities disclose to this vendor yet.
			</p>
		{:else}
			<ul class="flex flex-wrap gap-1.5">
				{#each vendor.processing_activities as pa (pa.id)}
					<li>
						<button
							type="button"
							class="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs text-foreground transition-colors duration-150 hover:bg-muted"
							onclick={() => onOpenActivity(pa.id)}
						>
							{pa.name}
							<span class="text-muted-foreground">{lawfulBasisLabel(pa.lawful_basis)}</span>
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
