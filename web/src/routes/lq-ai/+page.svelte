<script lang="ts">
	/**
	 * `/lq-ai` — the cockpit landing surface (F1-S2). Login lands here;
	 * the tool-centric guided dashboard retired with this slice
	 * (MILESTONES § F1: "F3 then only promotes routes, never rebuilds
	 * this surface"). Preferences init feeds the header's Tools-menu
	 * gating (autonomous opt-in).
	 */
	import { onMount } from 'svelte';
	import { initPreferences } from '$lib/lq-ai/stores/preferences';
	import Cockpit from '$lib/lq-ai/cockpit/Cockpit.svelte';

	onMount(() => {
		initPreferences();
	});
</script>

<Cockpit />
