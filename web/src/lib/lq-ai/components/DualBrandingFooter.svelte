<script lang="ts">
	/**
	 * Shell footer. Until F0-S6 this carried the ADR-0001 clause-4 dual
	 * branding ("powered by Open WebUI"); the husk removal (ADR-F006) ended
	 * that obligation and made the claim false — the shell is standalone.
	 * Lineage is recorded in NOTICES.md § Web client provenance.
	 */
</script>

<!-- F2-M2: raw gray-* swapped for semantic tokens (text-muted-foreground /
     border-border) so the footer follows the same `.dark` palette as the
     rest of the chrome instead of a parallel gray scale. -->
<footer
	class="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2 text-xs text-muted-foreground"
	data-testid="lq-ai-dual-branding-footer"
>
	<span>
		<strong>LQ.AI</strong> — Open-Source Legal AI
	</span>
	<span>Apache-2.0</span>
</footer>
