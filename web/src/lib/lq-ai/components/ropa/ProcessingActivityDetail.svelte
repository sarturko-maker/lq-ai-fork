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
		assessmentStatusLabel,
		assessmentTypeLabel,
		controllerRoleLabel,
		dpiaOnFile,
		lawfulBasisLabel,
		systemTypeLabel,
		transferMechanismLabel,
		vendorRoleLabel
	} from './format';

	let {
		activity,
		onBack,
		onOpenSystem,
		onOpenVendor,
		onOpenAssessment
	}: {
		activity: ProcessingActivityRead;
		onBack: () => void;
		onOpenSystem: (id: string) => void;
		onOpenVendor: (id: string) => void;
		onOpenAssessment: (id: string) => void;
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
			{#if dpiaOnFile(activity.assessments)}
				<!-- PRIV-A3 write-back marker: a completed DPIA covers this activity. -->
				<Badge variant="outline">DPIA on file</Badge>
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

	<div class="space-y-2">
		<h3 class="text-sm font-semibold tracking-tight text-foreground">
			Third-country transfers
			<span class="text-muted-foreground">({activity.transfers.length})</span>
		</h3>
		{#if activity.transfers.length === 0}
			<p class="text-sm text-muted-foreground">
				No third-country transfers recorded for this activity.
			</p>
		{:else}
			<ul class="space-y-2">
				{#each activity.transfers as transfer (transfer.id)}
					<li class="rounded-md border border-border p-3 text-sm">
						<div class="flex flex-wrap items-center gap-2">
							<span class="font-medium text-foreground">{transfer.destination}</span>
							{#if transfer.restricted}
								<Badge variant="destructive">Restricted</Badge>
								<Badge variant="outline">{transferMechanismLabel(transfer.mechanism)}</Badge>
							{:else}
								<Badge variant="secondary">Not restricted</Badge>
							{/if}
						</div>
						{#if transfer.vendor}
							{@const recipient = transfer.vendor}
							<p class="mt-1.5 text-xs text-muted-foreground">
								Recipient:
								<button
									type="button"
									class="text-foreground underline-offset-2 transition-colors duration-150 hover:text-brand hover:underline"
									onclick={() => onOpenVendor(recipient.id)}
								>
									{recipient.name}
								</button>
							</p>
						{/if}
						{#if transfer.details}
							<p class="mt-1.5 text-xs text-muted-foreground">{transfer.details}</p>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</div>

	<div class="space-y-2">
		<h3 class="text-sm font-semibold tracking-tight text-foreground">
			Categories of data subjects
			<span class="text-muted-foreground">({activity.data_subject_categories.length})</span>
		</h3>
		{#if activity.data_subject_categories.length === 0}
			<p class="text-sm text-muted-foreground">No categories of data subjects recorded yet.</p>
		{:else}
			<ul class="flex flex-wrap gap-1.5">
				{#each activity.data_subject_categories as category (category.id)}
					<li><Badge variant="secondary">{category.name}</Badge></li>
				{/each}
			</ul>
		{/if}
	</div>

	<div class="space-y-2">
		<h3 class="text-sm font-semibold tracking-tight text-foreground">
			Categories of personal data
			<span class="text-muted-foreground">({activity.data_categories.length})</span>
		</h3>
		{#if activity.data_categories.length === 0}
			<p class="text-sm text-muted-foreground">No categories of personal data recorded yet.</p>
		{:else}
			<ul class="flex flex-wrap gap-1.5">
				{#each activity.data_categories as category (category.id)}
					<li><Badge variant="secondary">{category.name}</Badge></li>
				{/each}
			</ul>
		{/if}
	</div>

	<!-- PRIV-A3 write-back: the assessments covering this activity, deep-linking to
	     the assessment detail. This is how a completed DPIA "writes back" onto the
	     ROPA register (read-only projection; the agent stays the sole writer). -->
	<div class="space-y-2">
		<h3 class="text-sm font-semibold tracking-tight text-foreground">
			Assessments
			<span class="text-muted-foreground">({activity.assessments.length})</span>
		</h3>
		{#if activity.assessments.length === 0}
			<p class="text-sm text-muted-foreground">No assessments cover this activity yet.</p>
		{:else}
			<ul class="flex flex-wrap gap-1.5">
				{#each activity.assessments as assessment (assessment.id)}
					<li>
						<button
							type="button"
							class="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs text-foreground transition-colors duration-150 hover:bg-muted"
							onclick={() => onOpenAssessment(assessment.id)}
						>
							<span class="font-medium">{assessmentTypeLabel(assessment.type)}</span>
							{assessment.title}
							<span class="text-muted-foreground">{assessmentStatusLabel(assessment.status)}</span>
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
