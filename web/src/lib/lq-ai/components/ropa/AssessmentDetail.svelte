<script lang="ts">
	/**
	 * One privacy assessment (PIA / DPIA / LIA / TIA) + its risk findings and the
	 * processing activities it covers (PRIV-A3). Read-only detail in LQ.AI's F013
	 * style; cross-links back to the ROPA activities it assesses (click an activity
	 * → the parent opens that activity's detail). The Privacy agent is the sole,
	 * audited writer (ADR-F019) — this view only reads.
	 */
	import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table/index.js';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';
	import type { AssessmentRead } from '$lib/lq-ai/api/ropa';
	import {
		assessmentStatusLabel,
		assessmentTypeLabel,
		riskLevelLabel,
		riskStatusLabel
	} from './format';

	let {
		assessment,
		onBack,
		onOpenActivity
	}: {
		assessment: AssessmentRead;
		onBack: () => void;
		onOpenActivity: (id: string) => void;
	} = $props();
</script>

<div class="space-y-5" data-testid="lq-assessment-detail">
	<button
		type="button"
		class="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors duration-150 hover:text-foreground"
		onclick={onBack}
	>
		<ChevronLeftIcon class="size-3.5" aria-hidden="true" />
		Register
	</button>

	<div class="flex flex-wrap items-start justify-between gap-3">
		<SectionHeader size="page" title={assessment.title} subtitle="Privacy assessment" />
		<div class="flex flex-wrap gap-1.5">
			<Badge variant="secondary">{assessmentTypeLabel(assessment.type)}</Badge>
			<Badge variant="outline">{assessmentStatusLabel(assessment.status)}</Badge>
			{#if assessment.risk_rating === 'high'}
				<Badge variant="destructive">High risk</Badge>
			{:else if assessment.risk_rating}
				<Badge variant="outline">{riskLevelLabel(assessment.risk_rating)} risk</Badge>
			{/if}
		</div>
	</div>

	<dl class="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-[10rem_1fr]">
		<dt class="text-muted-foreground">Type</dt>
		<dd class="text-foreground">{assessmentTypeLabel(assessment.type)}</dd>

		<dt class="text-muted-foreground">Status</dt>
		<dd class="text-foreground">{assessmentStatusLabel(assessment.status)}</dd>

		<dt class="text-muted-foreground">Risk rating</dt>
		<dd class="text-foreground">
			{assessment.risk_rating ? riskLevelLabel(assessment.risk_rating) : 'Not yet rated'}
		</dd>

		{#if assessment.summary}
			<dt class="text-muted-foreground">Summary</dt>
			<dd class="text-foreground">{assessment.summary}</dd>
		{/if}

		{#if assessment.conditions}
			<dt class="text-muted-foreground">Conditions</dt>
			<dd class="text-foreground">{assessment.conditions}</dd>
		{/if}
	</dl>

	<div class="space-y-2">
		<h3 class="text-sm font-semibold tracking-tight text-foreground">
			Risks
			<span class="text-muted-foreground">({assessment.risks.length})</span>
		</h3>
		{#if assessment.risks.length === 0}
			<p class="text-sm text-muted-foreground">No risks recorded for this assessment yet.</p>
		{:else}
			<div class="rounded-lg border border-border">
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead>Risk</TableHead>
							<TableHead>Likelihood</TableHead>
							<TableHead>Impact</TableHead>
							<TableHead>Status</TableHead>
							<TableHead>Mitigation</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each assessment.risks as risk (risk.id)}
							<TableRow>
								<TableCell class="text-foreground">{risk.description}</TableCell>
								<TableCell>
									{#if risk.likelihood === 'high'}
										<Badge variant="destructive">{riskLevelLabel(risk.likelihood)}</Badge>
									{:else}
										<Badge variant="outline">{riskLevelLabel(risk.likelihood)}</Badge>
									{/if}
								</TableCell>
								<TableCell>
									{#if risk.impact === 'high'}
										<Badge variant="destructive">{riskLevelLabel(risk.impact)}</Badge>
									{:else}
										<Badge variant="outline">{riskLevelLabel(risk.impact)}</Badge>
									{/if}
								</TableCell>
								<TableCell class="text-muted-foreground">{riskStatusLabel(risk.status)}</TableCell>
								<TableCell class="text-muted-foreground">{risk.mitigation ?? '—'}</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>
			</div>
		{/if}
	</div>

	<div class="space-y-2">
		<h3 class="text-sm font-semibold tracking-tight text-foreground">
			Activities assessed
			<span class="text-muted-foreground">({assessment.processing_activities.length})</span>
		</h3>
		{#if assessment.processing_activities.length === 0}
			<p class="text-sm text-muted-foreground">
				This assessment is not linked to any processing activity yet.
			</p>
		{:else}
			<ul class="flex flex-wrap gap-1.5">
				{#each assessment.processing_activities as activity (activity.id)}
					<li>
						<button
							type="button"
							class="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs text-foreground transition-colors duration-150 hover:bg-muted"
							onclick={() => onOpenActivity(activity.id)}
						>
							{activity.name}
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
