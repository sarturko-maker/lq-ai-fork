<script lang="ts">
	/**
	 * /lq-ai/admin/capabilities — REDIRECT STUB (STORE-2 D-D, ADR-F065).
	 *
	 * Superseded by the Store (`/lq-ai/admin/store`) + Library
	 * (`/lq-ai/admin/library`) split: the old page conflated "everything LQ
	 * ships" with "what this org uses". The route stays alive so old
	 * bookmarks land somewhere real. This SPA has `ssr = false` and no
	 * `+page.ts` files anywhere — the app's only redirect idiom is
	 * `onMount` -> `goto`, so that's what this stub does (no SvelteKit
	 * `redirect()`, which needs a server-side load function this app
	 * doesn't have).
	 *
	 * The old page's two non-Library sections were relocated, not dropped:
	 * the MCP "coming soon" placeholder moved to the Store page; the
	 * read-only Models section was DROPPED — it only re-projected the
	 * already member-visible `GET /api/v1/models` (the SETUP-4b review's own
	 * "check who can ALREADY see the data" lesson), and the operator Models
	 * page (`/lq-ai/admin/models`) is the authoritative surface for it.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { auth } from '$lib/lq-ai/auth/store';

	onMount(() => {
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		if (!$auth.user.is_admin) {
			console.warn('non-admin attempted /lq-ai/admin/capabilities; redirecting');
			goto('/lq-ai');
			return;
		}
		goto('/lq-ai/admin/library', { replaceState: true });
	});
</script>

<svelte:head>
	<title>Library — LQ.AI Oscar Edition admin</title>
</svelte:head>
