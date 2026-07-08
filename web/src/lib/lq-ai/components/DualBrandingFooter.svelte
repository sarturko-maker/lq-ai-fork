<script lang="ts">
	/**
	 * Shell footer. Until F0-S6 this carried the ADR-0001 clause-4 dual
	 * branding ("powered by Open WebUI"); the husk removal (ADR-F006) ended
	 * that obligation and made the claim false — the shell is standalone.
	 * Lineage is recorded in NOTICES.md § Web client provenance.
	 *
	 * BRAND-1b (ADR-F068) HARD LINE: the Apache-2.0 + LQ.AI attribution stays
	 * on every install. A white-labeled deployment renders
	 * "NAME — powered by LQ.AI Oscar Edition"; the default install keeps the
	 * original line. The `data-testid` below never renames.
	 */
	import { branding } from '$lib/lq-ai/branding/store';
</script>

<!-- F2-M2: raw gray-* swapped for semantic tokens (text-muted-foreground /
     border-border) so the footer follows the same `.dark` palette as the
     rest of the chrome instead of a parallel gray scale. -->
<footer
	class="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2 text-xs text-muted-foreground"
	data-testid="lq-ai-dual-branding-footer"
>
	<span>
		{#if $branding.customName}
			<strong>{$branding.productName}</strong> — powered by LQ.AI Oscar Edition
		{:else}
			<strong>LQ.AI Oscar Edition</strong> — Open-Source Legal AI
		{/if}
	</span>
	<span>Apache-2.0</span>
</footer>
