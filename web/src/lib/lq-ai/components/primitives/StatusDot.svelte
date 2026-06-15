<!--
	StatusDot — minimal dot-status (F2-VL1, ADR-F013 §6).

	A single coloured dot + a muted label, the calm alternative to a filled
	pill on minimal surfaces (the cockpit grid / matter rows). The filled
	`status-*` pill (cockpit/StatusPill.svelte) is retained for dense data
	tables. Tones map onto the existing F1-S2 `--status-*` intent tokens —
	`running` resolves to the scarce `--brand` blue (VL0 set `--status-running`
	= brand), so this needs no new token scale. `idle` is faint metadata.
	Presentation only; `label` is an escaped text binding (no `{@html}`).
-->
<script module lang="ts">
	export type DotStatus = 'running' | 'completed' | 'failed' | 'cancelled' | 'attention' | 'idle';

	const DOT: Record<DotStatus, string> = {
		running: 'bg-status-running',
		completed: 'bg-status-completed',
		failed: 'bg-status-failed',
		cancelled: 'bg-status-cancelled',
		// `attention` = the stale/cap-reached belt (StatusPill's `warn` tone);
		// `--status-attention` already exists, so this is no new token scale.
		attention: 'bg-status-attention',
		idle: 'bg-muted-foreground/40'
	};

	/** The dot's background colour class for a status tone. */
	export function statusDotClass(status: DotStatus): string {
		return DOT[status];
	}
</script>

<script lang="ts">
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		status,
		label = '',
		class: klass = '',
		...rest
	}: {
		status: DotStatus;
		label?: string;
		class?: string;
	} & HTMLAttributes<HTMLSpanElement> = $props();
</script>

<span class="text-caption text-muted-foreground inline-flex items-center gap-2 {klass}" {...rest}>
	<span
		class="size-[7px] shrink-0 rounded-full {statusDotClass(status)} {status === 'running'
			? 'animate-pulse'
			: ''}"
		aria-hidden="true"
	></span>
	{#if label}{label}{/if}
</span>
