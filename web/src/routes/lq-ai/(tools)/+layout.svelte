<script lang="ts">
	/**
	 * Legacy tool-surface chrome — the pre-F1-S2 shell (header, TopTabBar,
	 * scrollable `#lq-main`, footer), now scoped to the `(tools)` route
	 * group. The cockpit at `/lq-ai` replaced it as the landing surface;
	 * these routes keep working unchanged (LEGACY: bugfix-only) until F3
	 * demotes tool tabs to in-context capabilities. Auth/idle gating lives
	 * in the parent gate layout.
	 */
	import { page } from '$app/stores';

	import { auth } from '$lib/lq-ai/auth/store';
	import DualBrandingFooter from '$lib/lq-ai/components/DualBrandingFooter.svelte';
	import TopTabBar from '$lib/lq-ai/components/TopTabBar.svelte';
	import AmbientTrustChrome from '$lib/lq-ai/components/AmbientTrustChrome.svelte';

	$: pathname = $page.url.pathname;
</script>

<div class="lq-shell">
	<header class="lq-topbar">
		<a class="lq-brand" href="/lq-ai">
			<span class="lq-brand-lq">LQ</span>.AI
		</a>
		<div style="display: inline-flex; align-items: center; gap: var(--lq-space-3);">
			<AmbientTrustChrome />
			<a
				href="/lq-ai/settings/appearance"
				aria-label="Settings"
				title="Settings"
				style="color: var(--lq-text-secondary); text-decoration: none; padding: var(--lq-space-1) var(--lq-space-2); border-radius: var(--lq-radius-sm);"
				>⚙</a
			>
		</div>
	</header>
	<TopTabBar user={$auth.user ?? null} {pathname} />
	<main id="lq-main">
		<slot />
	</main>
	<DualBrandingFooter />
</div>

<style>
	/* src/app.css pins html { overflow-y: hidden !important; } so the shell
	   can manage its own scroll containers. The LQ.AI shell's
	   non-chat surfaces (settings, admin sub-routes, trust page) need a
	   scrollable main; the chat shell already wraps itself in flex+
	   overflow-hidden and manages internal scroll, so adding overflow-y
	   here doesn't disturb it. min-height: 0 lets flex children shrink
	   correctly inside the column. */
	.lq-shell {
		background: var(--lq-canvas);
		color: var(--lq-text);
		height: 100vh;
		display: flex;
		flex-direction: column;
	}
	.lq-topbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--lq-space-3) var(--lq-space-4);
		border-bottom: 1px solid var(--lq-border);
		background: var(--lq-canvas);
		flex-shrink: 0;
	}
	.lq-brand {
		font-size: 16px;
		font-weight: 600;
		color: var(--lq-text);
		text-decoration: none;
	}
	.lq-brand-lq {
		color: var(--lq-accent);
	}
	main {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
	}
</style>
