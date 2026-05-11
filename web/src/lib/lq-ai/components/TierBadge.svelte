<script lang="ts">
	/**
	 * Inference Tier badge per PRD §3.13.
	 *
	 * Now delegates to TrustPill (variant="tier") so the LQ.AI ambient chrome
	 * stays visually consistent. Public API preserved — callers are unchanged.
	 *
	 * Prop mapping:
	 *   tier      → label ("Tier N" / "Tier ?") + TrustTone override
	 *   provider  → tooltip text (title on wrapper span)
	 *   interactive → onClick forwarded to TrustPill; false = no handler
	 *
	 * The component continues to dispatch a Svelte "open" event so existing
	 * callers using `on:open` don't need to change.
	 *
	 * Tone mapping (closest match from TrustPill's palette):
	 *   Tier 1 (was emerald) → sage
	 *   Tier 2 (was sky)     → neutral
	 *   Tier 3 (was amber)   → amber
	 *   Tier 4 (was orange)  → amber
	 *   Tier 5 (was rose)    → red
	 *   unknown              → neutral
	 */
	import { createEventDispatcher } from 'svelte';
	import TrustPill from './TrustPill.svelte';
	import type { TrustTone } from './TrustPill.svelte';

	export let tier: 1 | 2 | 3 | 4 | 5 | null | undefined = null;
	export let provider: string | null | undefined = null;
	/**
	 * When `false` the badge renders as a static pill (no click /
	 * keyboard handlers). Used by surfaces where the parent has its
	 * own interaction model (admin alias UI, model picker resolution
	 * preview).
	 */
	export let interactive: boolean = true;

	const dispatch = createEventDispatcher<{ open: void }>();

	const tierTone: Record<number, TrustTone> = {
		1: 'sage',
		2: 'neutral',
		3: 'amber',
		4: 'amber',
		5: 'red'
	};

	$: label = tier ? `Tier ${tier}` : 'Tier ?';
	$: tone = (tier ? tierTone[tier] : 'neutral') as TrustTone;
	$: title = provider
		? `${label} — ${provider} (click for details)`
		: `${label} — click for details`;
	$: handleClick = interactive ? () => dispatch('open') : undefined;
</script>

<!--
  Wrap in a span so we can attach `title` (hover tooltip) and
  `data-testid` without modifying TrustPill's public API.
  `display: contents` keeps the wrapper invisible in layout.
-->
<span {title} data-testid="lq-ai-tier-badge" style="display: contents">
	<TrustPill variant="tier" {label} {tone} onClick={handleClick} />
</span>
