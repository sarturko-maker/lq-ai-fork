<!--
	Alert — a semantic message banner (R1a). `role="alert"` for the error/warning
	intents so assistive tech announces it; `info` is a passive note. Replaces the
	per-component hand-rolled error blocks (nmm-submit-error, akm-error, …) across
	the rollout. Error uses the destructive token pair; both light and dark read AA.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		intent = 'error',
		children
	}: {
		intent?: 'error' | 'warning' | 'info';
		children: Snippet;
	} = $props();

	const TONE: Record<string, string> = {
		// `dark:text-red-300` lifts the error text to >=4.5:1 (AA) over the tinted
		// wash on charcoal — bare `text-destructive` only reaches 3.7:1 in dark (R1a review).
		error: 'border-destructive/30 bg-destructive/10 text-destructive dark:text-red-300',
		warning: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
		info: 'border-border bg-muted text-muted-foreground'
	};
</script>

<div
	role={intent === 'info' ? undefined : 'alert'}
	class="rounded-lg border px-3 py-2 text-sm {TONE[intent]}"
>
	{@render children()}
</div>
