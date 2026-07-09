<script lang="ts">
	/**
	 * PlaybookPositionsReadonly — the FROZEN positions of an org-playbook
	 * proposal, rendered read-only for the admin review queue (B-4, ADR-F067
	 * D2/D3). The playbook analogue of the skill queue's raw_yaml/body `<pre>`.
	 *
	 * The positions come from untrusted JSONB (any authenticated author's
	 * playbook, frozen at propose time). Every free-text field is rendered via
	 * plain `{}` interpolation — Svelte auto-escapes it — so there is NO `@html`
	 * sink here at all (stricter than the skill body's sanitized-markdown path,
	 * and correct: positions are structured data, not authored markdown). Arrays
	 * are guarded defensively against malformed snapshots.
	 */
	import type { OrgPlaybookPositionRead } from '$lib/lq-ai/api/admin';

	let { positions = [] }: { positions?: OrgPlaybookPositionRead[] } = $props();

	const SEVERITY_LABEL: Record<string, string> = {
		critical: 'Critical',
		high: 'High',
		medium: 'Medium',
		low: 'Low'
	};

	const safePositions = $derived(Array.isArray(positions) ? positions : []);

	function tiersOf(p: OrgPlaybookPositionRead) {
		const t = Array.isArray(p?.fallback_tiers) ? p.fallback_tiers : [];
		return [...t]
			.filter((x) => x && typeof x === 'object')
			.sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0));
	}
	function keywordsOf(p: OrgPlaybookPositionRead): string[] {
		return Array.isArray(p?.detection_keywords) ? p.detection_keywords : [];
	}
	function examplesOf(p: OrgPlaybookPositionRead): string[] {
		return Array.isArray(p?.detection_examples) ? p.detection_examples : [];
	}
	function severityLabel(s: string): string {
		return SEVERITY_LABEL[s] ?? s ?? '—';
	}
</script>

<div class="flex flex-col gap-3">
	{#if safePositions.length === 0}
		<p class="text-xs text-muted-foreground" data-testid="lq-playbook-ro-empty">
			This playbook has no positions.
		</p>
	{:else}
		{#each safePositions as position, i (i)}
			{@const tiers = tiersOf(position)}
			{@const keywords = keywordsOf(position)}
			{@const examples = examplesOf(position)}
			<article
				class="rounded-md border border-border bg-muted/40 p-3"
				data-testid="lq-playbook-ro-position"
				data-position-index={i}
			>
				<div class="flex flex-wrap items-baseline justify-between gap-2">
					<h4 class="text-sm font-medium text-foreground" data-testid="lq-playbook-ro-issue">
						{position.issue || `Position ${i + 1}`}
					</h4>
					<span class="text-xs text-muted-foreground" data-testid="lq-playbook-ro-severity">
						Severity if missing: {severityLabel(position.severity_if_missing)}
					</span>
				</div>

				{#if position.description}
					<p class="mt-1 text-xs whitespace-pre-wrap text-muted-foreground">
						{position.description}
					</p>
				{/if}

				{#if position.standard_language}
					<div class="mt-2">
						<p class="text-xs font-medium text-muted-foreground">Standard language</p>
						<pre
							class="mt-1 max-h-48 overflow-auto rounded bg-muted p-2 text-xs whitespace-pre-wrap"
							data-testid="lq-playbook-ro-standard">{position.standard_language}</pre>
					</div>
				{/if}

				{#if position.redline_strategy}
					<p class="mt-2 text-xs text-muted-foreground">
						<span class="font-medium">Redline strategy:</span>
						{position.redline_strategy}
					</p>
				{/if}

				{#if tiers.length > 0}
					<div class="mt-2">
						<p class="text-xs font-medium text-muted-foreground">Fallback tiers</p>
						<ol class="mt-1 flex flex-col gap-1">
							{#each tiers as tier, ti (ti)}
								<li
									class="rounded border border-border p-2 text-xs"
									data-testid="lq-playbook-ro-tier"
								>
									<span class="font-medium text-foreground">Rank {tier.rank}</span>
									{#if tier.description}
										<span class="text-muted-foreground"> — {tier.description}</span>
									{/if}
									{#if tier.language}
										<pre
											class="mt-1 overflow-auto whitespace-pre-wrap text-muted-foreground">{tier.language}</pre>
									{/if}
								</li>
							{/each}
						</ol>
					</div>
				{/if}

				{#if keywords.length > 0}
					<div class="mt-2 flex flex-wrap items-center gap-1">
						<span class="text-xs font-medium text-muted-foreground">Detection keywords:</span>
						{#each keywords as kw, ki (ki)}
							<span
								class="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground"
							>
								{kw}
							</span>
						{/each}
					</div>
				{/if}

				{#if examples.length > 0}
					<div class="mt-2">
						<p class="text-xs font-medium text-muted-foreground">Detection examples</p>
						<ul class="mt-1 flex flex-col gap-1">
							{#each examples as ex, ei (ei)}
								<li
									class="rounded border border-border p-2 text-xs whitespace-pre-wrap text-muted-foreground"
								>
									{ex}
								</li>
							{/each}
						</ul>
					</div>
				{/if}
			</article>
		{/each}
	{/if}
</div>
