<script lang="ts">
	/**
	 * One system/asset + the processing activities that use it (PRIV-3).
	 * Read-only detail in LQ.AI's F013 style; cross-links to the activities that
	 * compose it (click an activity → the parent opens that activity's detail).
	 */
	import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';
	import type { SystemRead } from '$lib/lq-ai/api/ropa';
	import { lawfulBasisLabel, systemTypeLabel } from './format';

	let {
		system,
		onBack,
		onOpenActivity
	}: {
		system: SystemRead;
		onBack: () => void;
		onOpenActivity: (id: string) => void;
	} = $props();

	// Optional descriptive rows — only render what the agent has filled in.
	const rows = $derived(
		[
			{ label: 'Description', value: system.description },
			{ label: 'Owner', value: system.owner },
			{ label: 'Hosting location', value: system.hosting_location },
			{ label: 'Retention', value: system.retention },
			{ label: 'Security measures', value: system.security_measures }
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
		<SectionHeader size="page" title={system.name} subtitle="System" />
		<div class="flex flex-wrap gap-1.5">
			<Badge variant="secondary">{systemTypeLabel(system.system_type)}</Badge>
			{#if system.ai_usage}
				<Badge variant="outline">Uses AI</Badge>
			{/if}
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
			No further detail recorded yet — the Privacy agent fills these in as it learns the system.
		</p>
	{/if}

	<div class="space-y-2">
		<h3 class="text-sm font-semibold tracking-tight text-foreground">
			Used by
			<span class="text-muted-foreground">({system.processing_activities.length})</span>
		</h3>
		{#if system.processing_activities.length === 0}
			<p class="text-sm text-muted-foreground">No processing activities use this system yet.</p>
		{:else}
			<ul class="flex flex-wrap gap-1.5">
				{#each system.processing_activities as pa (pa.id)}
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
