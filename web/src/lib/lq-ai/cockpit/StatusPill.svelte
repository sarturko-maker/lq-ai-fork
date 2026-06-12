<script lang="ts">
	/**
	 * Run-status pill on the F1-S2 status intent tokens: soft wash
	 * background + strong dot/text, pulsing dot while running — never a
	 * saturated chip. Reuses the agents-surface `statusBadge` semantics
	 * (incl. the stale-running belt) so the cockpit and the legacy agents
	 * page can never disagree about a thread's state (ADR-F004: settled
	 * rows decide).
	 */
	import type { AgentRunStatus } from '$lib/lq-ai/api/agents';
	import { statusBadge, type StatusTone } from '$lib/lq-ai/agents/helpers';

	let {
		status,
		lastRunAt,
		nowMs
	}: {
		status: AgentRunStatus | null;
		lastRunAt: string | null;
		nowMs: number;
	} = $props();

	const TONE_CLASSES: Record<StatusTone, string> = {
		running: 'bg-status-running-wash text-status-running',
		ok: 'bg-status-completed-wash text-status-completed',
		error: 'bg-status-failed-wash text-status-failed',
		warn: 'bg-status-attention-wash text-status-attention',
		neutral: 'bg-status-cancelled-wash text-status-cancelled'
	};

	const badge = $derived(
		status === null
			? null
			: statusBadge({ status, started_at: lastRunAt ?? '', error: null }, nowMs)
	);
</script>

{#if badge}
	<span
		class="inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums {TONE_CLASSES[
			badge.tone
		]}"
		data-testid="lq-cockpit-status-pill"
	>
		<span
			class="size-1.5 rounded-full bg-current {badge.tone === 'running' ? 'animate-pulse' : ''}"
			aria-hidden="true"
		></span>
		{badge.label}
	</span>
{/if}
