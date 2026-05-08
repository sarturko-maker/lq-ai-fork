<script lang="ts">
	/**
	 * Inference Tier badge per PRD §3.13. C8 surfaces this as a small badge;
	 * D2 builds the click-for-details panel. M1 shows tier number + colour.
	 */
	export let tier: 1 | 2 | 3 | 4 | 5 | null | undefined = null;
	export let provider: string | null | undefined = null;

	const tierColour: Record<number, string> = {
		1: 'bg-emerald-100 text-emerald-800 border-emerald-300',
		2: 'bg-sky-100 text-sky-800 border-sky-300',
		3: 'bg-amber-100 text-amber-800 border-amber-300',
		4: 'bg-orange-100 text-orange-800 border-orange-300',
		5: 'bg-rose-100 text-rose-800 border-rose-300'
	};

	$: classes = tier ? tierColour[tier] : 'bg-gray-100 text-gray-700 border-gray-300';
	$: label = tier ? `Tier ${tier}` : 'Tier ?';
	$: title = provider ? `${label} — ${provider}` : `${label} (D2 will surface details)`;
</script>

<span
	class="inline-flex items-center px-2 py-0.5 rounded border text-xs font-medium {classes}"
	{title}
	data-testid="lq-ai-tier-badge"
>
	{label}
</span>
