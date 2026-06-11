<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	// The OpenWebUI shell that lived at `/` was removed in F0-S6 (ADR-F006);
	// the LQ.AI shell is the only surface.
	onMount(() => {
		goto('/lq-ai', { replaceState: true });
	});
</script>
