<script lang="ts">
	/**
	 * /lq-ai/saved-prompts — standalone Saved Prompts surface (D7
	 * deliverable per the M1 frontend design spec).
	 *
	 * Wraps `SavedPromptsPanel` (the in-chat side panel) with `alwaysOpen`
	 * + `insertLabel="Use in chat"` so users get a full-width browseable
	 * list rather than the compressed side-of-composer view. Same CRUD,
	 * promote-to-skill, and export-as-SKILL.md affordances.
	 *
	 * "Use in chat" navigates to /lq-ai/chats with the prompt body stashed
	 * in sessionStorage (`lq-ai:composer-prefill`); ChatPanel reads + clears
	 * that key on mount and pre-populates the composer. sessionStorage —
	 * not a URL query param — keeps prompt content out of referrers, server
	 * logs, and browser history (matters for legal-sensitive text).
	 */
	import { goto } from '$app/navigation';
	import SavedPromptsPanel from '$lib/lq-ai/components/SavedPromptsPanel.svelte';

	function useInChat(text: string): void {
		if (typeof window !== 'undefined' && window.sessionStorage) {
			window.sessionStorage.setItem('lq-ai:composer-prefill', text);
		}
		void goto('/lq-ai/chats');
	}
</script>

<main class="lq-saved-prompts-page" data-testid="lq-ai-saved-prompts-page">
	<header class="lq-page-header">
		<h1 class="lq-text-page-h">Saved prompts</h1>
		<p class="lq-text-body lq-page-intro">
			Reusable prompt fragments scoped to your account. Insert into a chat,
			edit them in place, or promote one to a skill when a fragment outgrows
			its prompt and starts deserving inputs / examples / a versioned home.
		</p>
	</header>

	<SavedPromptsPanel alwaysOpen insertLabel="Use in chat" onInsert={useInChat} />
</main>

<style>
	.lq-saved-prompts-page {
		padding: var(--lq-space-6);
		max-width: 920px;
		margin: 0 auto;
	}
	.lq-page-header {
		margin-bottom: var(--lq-space-5);
	}
	.lq-page-intro {
		color: var(--lq-text-secondary);
		margin-top: var(--lq-space-2);
		max-width: 60ch;
	}
</style>
