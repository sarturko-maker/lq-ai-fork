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

<!-- F2-M2: shell chrome migrated off `--lq-*` to semantic Tailwind. This is
     the robust dark-mode fix for the legacy shell — the AE5 "light column in
     dark mode" quirk came from depending on `--lq-canvas` (whose `:root.dark`
     bridge loses the cascade on some routes); `bg-background`/`text-foreground`
     are `.dark`-class-driven and match the cockpit. Brand accent unifies to
     `text-primary` (the cockpit's single accent). `main` keeps its own scroll
     (app.css pins `html { overflow-y: hidden }`); `min-h-0` lets the flex
     column shrink correctly. -->
<div class="flex h-screen flex-col bg-background text-foreground">
	<header
		class="flex shrink-0 items-center justify-between border-b border-border bg-background px-4 py-3"
	>
		<a class="text-base font-semibold tracking-tight text-foreground no-underline" href="/lq-ai">
			<span class="text-primary">LQ</span>.AI
		</a>
		<div class="inline-flex items-center gap-3">
			<AmbientTrustChrome />
			<a
				href="/lq-ai/settings/appearance"
				aria-label="Settings"
				title="Settings"
				class="rounded-sm px-2 py-1 text-muted-foreground no-underline transition-colors duration-150 hover:text-foreground"
				>⚙</a
			>
		</div>
	</header>
	<TopTabBar user={$auth.user ?? null} {pathname} />
	<main id="lq-main" class="min-h-0 flex-1 overflow-y-auto">
		<slot />
	</main>
	<DualBrandingFooter />
</div>
