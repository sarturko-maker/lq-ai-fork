<!--
  /lq-ai/learn — Learn surface landing page.

  Three gateway tiles to the sub-routes, plus a brief intro that frames
  what the surface is and who it is for. Every claim on the sub-pages
  links back to a verifiable file path in source.
-->
<script lang="ts">
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
</script>

<!-- F2-M7b: bespoke 960px → PageShell `default` (896px), snapping onto the
     system reading widths; color --lq-* → semantic + F013 calm. -->
<PageShell size="default" pad="compact" data-testid="lq-ai-learn-page">
	<header class="lq-page-header">
		<h1 class="lq-text-page-h">Learn</h1>
		<div class="lq-learn-intro">
			<p class="lq-text-body lq-learn-intro-p">
				A guided introduction to LQ.AI for everyone — practicing attorneys curious about what the
				project does, security and procurement teams evaluating it for deployment, engineers
				exploring the architecture, and anyone considering contributing a skill. The three sections
				below address a different question: what it does, how it works, and how to contribute.
			</p>
			<p class="lq-text-body lq-learn-intro-p">
				Every claim on these pages is backed by a path to verify it in the codebase. If the docs say
				something the code does not do, the code is canonical — please
				<a
					href="https://github.com/LegalQuants/lq-ai/issues"
					class="lq-link"
					target="_blank"
					rel="noopener noreferrer">open an issue</a
				>.
			</p>
		</div>
	</header>

	<div class="lq-learn-grid">
		<a class="lq-learn-card" href="/lq-ai/learn/use" data-testid="lq-ai-learn-card-use">
			<span class="lq-learn-card-icon" aria-hidden="true">📋</span>
			<h2 class="lq-learn-card-title">How to Use</h2>
			<p class="lq-learn-card-desc">
				What every feature does, in plain language. With links to source for every claim.
			</p>
			<span class="lq-learn-card-cta">Explore →</span>
		</a>

		<a class="lq-learn-card" href="/lq-ai/learn/how" data-testid="lq-ai-learn-card-how">
			<span class="lq-learn-card-icon" aria-hidden="true">🔍</span>
			<h2 class="lq-learn-card-title">How It Works</h2>
			<p class="lq-learn-card-desc">
				Interactive playgrounds that show how the system fits together. Click any visualization to
				verify claims against the source.
			</p>
			<span class="lq-learn-card-cta">Explore →</span>
		</a>

		<a class="lq-learn-card" href="/lq-ai/learn/build" data-testid="lq-ai-learn-card-build">
			<span class="lq-learn-card-icon" aria-hidden="true">🔧</span>
			<h2 class="lq-learn-card-title">How to Build</h2>
			<p class="lq-learn-card-desc">
				How to contribute a skill, a mini-PRD, or a bug fix. What's open right now.
			</p>
			<span class="lq-learn-card-cta">Explore →</span>
		</a>
	</div>
</PageShell>

<style>
	.lq-page-header {
		margin-bottom: var(--lq-space-6);
	}

	.lq-learn-intro {
		margin-top: var(--lq-space-3);
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-3);
		max-width: 68ch;
	}

	.lq-learn-intro-p {
		color: var(--muted-foreground);
		line-height: 1.6;
	}

	.lq-link {
		color: var(--brand);
		text-decoration: underline;
	}

	.lq-link:hover {
		opacity: 0.8;
	}

	.lq-learn-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: var(--lq-space-4);
	}

	.lq-learn-card {
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-3);
		padding: var(--lq-space-6);
		border: 1px solid var(--border);
		border-radius: var(--lq-radius-lg);
		background: var(--card);
		text-decoration: none;
		color: var(--foreground);
		transition: background-color 0.15s ease;
	}

	/* F013: flat, border-led cards — hover washes to muted, no float shadow
	   (shadows reserved for true elevation); the scarce blue is for focus only. */
	.lq-learn-card:hover {
		background: var(--muted);
	}

	.lq-learn-card:focus-visible {
		outline: 2px solid var(--ring);
		outline-offset: 2px;
	}

	.lq-learn-card-icon {
		font-size: 28px;
		line-height: 1;
	}

	.lq-learn-card-title {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
		color: var(--foreground);
	}

	.lq-learn-card-desc {
		margin: 0;
		font-size: 14px;
		color: var(--muted-foreground);
		line-height: 1.5;
		flex: 1;
	}

	.lq-learn-card-cta {
		font-size: 14px;
		font-weight: 500;
		color: var(--brand);
		margin-top: var(--lq-space-2);
	}
</style>
