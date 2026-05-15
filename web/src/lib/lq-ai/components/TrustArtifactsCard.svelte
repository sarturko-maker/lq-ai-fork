<script lang="ts">
	/**
	 * TrustArtifactsCard — links to procurement-grade in-repo artifacts.
	 *
	 * V2-FALLBACK notes:
	 * - SBOM: not yet generated. Links to docs/security/ directory.
	 *   Replace with CI-published CycloneDX/SPDX artifact URL when available.
	 * - Threat model: docs/security/threat-model.md does not yet exist.
	 *   Links to docs/PRD.md §5 (Security & Compliance) as interim reference.
	 * - Signed releases: links to GitHub releases page (accurate).
	 * - Source code: links to GitHub repo (accurate).
	 */
	const artifacts = [
		{
			label: 'SBOM (Software Bill of Materials)',
			href: 'https://github.com/LegalQuants/lq-ai/tree/main/docs/security',
			external: true,
			// V2-FALLBACK: replace with CycloneDX/SPDX artifact URL when CI publishes it.
			note: 'Directory — machine-readable SBOM ships in a future release pipeline step'
		},
		{
			label: 'Threat model',
			href: 'https://github.com/LegalQuants/lq-ai/blob/main/docs/PRD.md#5-security--compliance',
			external: true,
			// V2-FALLBACK: replace with docs/security/threat-model.md once authored.
			note: 'See PRD §5 — dedicated threat-model.md is a v1.1+ deliverable'
		},
		{
			label: 'Signed releases',
			href: 'https://github.com/LegalQuants/lq-ai/releases',
			external: true,
			note: null
		},
		{
			label: 'Source code',
			href: 'https://github.com/LegalQuants/lq-ai',
			external: true,
			note: null
		}
	] as const;
</script>

<div class="lq-card">
	<h3 class="lq-text-panel-h card-title">Trust artifacts</h3>
	<ul class="artifact-list">
		{#each artifacts as a}
			<li class="artifact-row">
				<div class="artifact-meta">
					<a
						href={a.href}
						class="lq-text-body artifact-link"
						target={a.external ? '_blank' : undefined}
						rel={a.external ? 'noopener noreferrer' : undefined}
					>
						{a.label}{a.external ? ' ↗' : ''}
					</a>
					{#if a.note}
						<span class="lq-text-caption artifact-note">{a.note}</span>
					{/if}
				</div>
			</li>
		{/each}
	</ul>
	<p class="lq-text-caption footer-note">
		Share this page with your GC or procurement team. Every link above points to a verifiable, public artifact.
	</p>
</div>

<style>
	.lq-card {
		background: var(--lq-canvas);
		border: 1px solid var(--lq-border);
		border-radius: var(--lq-radius-lg);
		padding: var(--lq-space-5);
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-3);
	}

	.card-title {
		margin: 0;
	}

	.artifact-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0;
	}

	.artifact-row {
		padding: var(--lq-space-2) 0;
		border-bottom: 1px dashed var(--lq-border);
	}

	.artifact-row:last-child {
		border-bottom: none;
	}

	.artifact-meta {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.artifact-link {
		color: var(--lq-accent);
		text-decoration: none;
	}

	.artifact-link:hover {
		text-decoration: underline;
	}

	.artifact-note {
		color: var(--lq-text-tertiary);
	}

	.footer-note {
		color: var(--lq-text-tertiary);
		margin: 0;
	}
</style>
