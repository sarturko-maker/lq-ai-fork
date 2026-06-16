<script lang="ts">
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import TrustDataResidencyCard from '$lib/lq-ai/components/TrustDataResidencyCard.svelte';
	import TrustProvidersCard from '$lib/lq-ai/components/TrustProvidersCard.svelte';
	import TrustExternalTurnsCard from '$lib/lq-ai/components/TrustExternalTurnsCard.svelte';
	import TrustArtifactsCard from '$lib/lq-ai/components/TrustArtifactsCard.svelte';
</script>

<!-- F2-M8: bespoke 1100px → PageShell `wide` (1024px), snapping onto the system
     reading widths (matches the M7b knowledge decision); color --lq-* → semantic.
     The Trust*Card internals keep their own accents — their R-slice owns them. -->
<PageShell size="wide" pad="compact" data-testid="lq-ai-trust-page">
	<div class="trust-stack">
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
</PageShell>

<style>
	.trust-stack {
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
		color: var(--muted-foreground);
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
