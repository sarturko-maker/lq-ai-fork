<script lang="ts">
	import TrustDataResidencyCard from '$lib/lq-ai/components/TrustDataResidencyCard.svelte';
	import TrustProvidersCard from '$lib/lq-ai/components/TrustProvidersCard.svelte';
	import TrustExternalTurnsCard from '$lib/lq-ai/components/TrustExternalTurnsCard.svelte';
	import TrustArtifactsCard from '$lib/lq-ai/components/TrustArtifactsCard.svelte';
</script>

<div class="trust-page">
	<div class="trust-header">
		<h1 class="lq-text-page-h">Trust &amp; Privacy</h1>
		<p class="lq-text-body intro-body">
			This is what we know about your deployment. Every claim here links to an artifact you can
			verify in this repo or on your operator's machine.
		</p>
	</div>

	<div class="trust-grid">
		<TrustDataResidencyCard />
		<TrustProvidersCard />
		<TrustExternalTurnsCard />
		<TrustArtifactsCard />
	</div>
</div>

<style>
	.trust-page {
		padding: var(--lq-space-6);
		max-width: 1100px;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-6);
	}

	.trust-header {
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-2);
	}

	.intro-body {
		color: var(--lq-text-secondary);
		max-width: 680px;
	}

	.trust-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--lq-space-6);
	}

	@media (max-width: 720px) {
		.trust-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
