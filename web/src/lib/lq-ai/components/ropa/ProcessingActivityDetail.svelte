<script lang="ts">
	/**
	 * One processing activity (Article 30 record) + the systems it uses (PRIV-3).
	 * Read-only detail in LQ.AI's F013 style; cross-links to the systems it
	 * composes (click a system → the parent opens that system's detail).
	 */
	import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';
	import type { ProcessingActivityRead } from '$lib/lq-ai/api/ropa';
	import {
		art9ConditionLabel,
		controllerRoleLabel,
		lawfulBasisLabel,
		systemTypeLabel,
		vendorRoleLabel
	} from './format';

	let {
		activity,
		onBack,
		onOpenSystem,
		onOpenVendor
	}: {
		activity: ProcessingActivityRead;
		onBack: () => void;
		onOpenSystem: (id: string) => void;
		onOpenVendor: (id: string) => void;
	} = $props();
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
		<SectionHeader size="page" title={activity.name} subtitle="Processing activity" />
		<div class="flex flex-wrap gap-1.5">
			<Badge variant="secondary">{lawfulBasisLabel(activity.lawful_basis)}</Badge>
			<Badge variant="outline">{controllerRoleLabel(activity.controller_role)}</Badge>
			{#if activity.special_category}
				<Badge variant="destructive">Special category</Badge>
			{/if}
		</div>
	</div>

	<dl class="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-[10rem_1fr]">
		<dt class="text-muted-foreground">Purpose</dt>
		<dd class="text-foreground">{activity.purpose}</dd>

		<dt class="text-muted-foreground">Lawful basis</dt>
		<dd class="text-foreground">{lawfulBasisLabel(activity.lawful_basis)}</dd>

		<dt class="text-muted-foreground">Controller role</dt>
		<dd class="text-foreground">{controllerRoleLabel(activity.controller_role)}</dd>

		<dt class="text-muted-foreground">Retention</dt>
		<dd class="text-foreground">{activity.retention}</dd>

		{#if activity.special_category}
			<dt class="text-muted-foreground">Article 9 condition</dt>
			<dd class="text-foreground">{art9ConditionLabel(activity.art9_condition)}</dd>
		{/if}
	</dl>

	<div class="space-y-2">
		<h3 class="text-sm font-semibold tracking-tight text-foreground">
			Systems used
			<span class="text-muted-foreground">({activity.systems.length})</span>
		</h3>
		{#if activity.systems.length === 0}
			<p class="text-sm text-muted-foreground">No systems linked to this activity yet.</p>
		{:else}
			<ul class="flex flex-wrap gap-1.5">
				{#each activity.systems as sys (sys.id)}
					<li>
						<button
							type="button"
							class="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs text-foreground transition-colors duration-150 hover:bg-muted"
							onclick={() => onOpenSystem(sys.id)}
						>
							{sys.name}
							<span class="text-muted-foreground">{systemTypeLabel(sys.system_type)}</span>
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>

	<div class="space-y-2">
		<h3 class="text-sm font-semibold tracking-tight text-foreground">
			Recipients
			<span class="text-muted-foreground">({activity.vendors.length})</span>
		</h3>
		{#if activity.vendors.length === 0}
			<p class="text-sm text-muted-foreground">No recipients linked to this activity yet.</p>
		{:else}
			<ul class="flex flex-wrap gap-1.5">
				{#each activity.vendors as vendor (vendor.id)}
					<li>
						<button
							type="button"
							class="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs text-foreground transition-colors duration-150 hover:bg-muted"
							onclick={() => onOpenVendor(vendor.id)}
						>
							{vendor.name}
							<span class="text-muted-foreground">{vendorRoleLabel(vendor.vendor_role)}</span>
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
