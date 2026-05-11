<script lang="ts">
	/**
	 * LQ.AI shell layout. Acts as the auth gate + force-change-password gate
	 * for every route under `/lq-ai/*` except `/lq-ai/login` and
	 * `/lq-ai/change-password`.
	 *
	 * - No access token → redirect to /lq-ai/login.
	 * - Access token but `must_change_password` → redirect to /lq-ai/change-password.
	 * - Otherwise: render the child route.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { auth } from '$lib/lq-ai/auth/store';
	import { authApi } from '$lib/lq-ai/api';
	import { LQAIApiError, PasswordChangeRequiredError } from '$lib/lq-ai/api/client';
	import DualBrandingFooter from '$lib/lq-ai/components/DualBrandingFooter.svelte';
	import TopTabBar from '$lib/lq-ai/components/TopTabBar.svelte';
	import AmbientTrustChrome from '$lib/lq-ai/components/AmbientTrustChrome.svelte';
	import '$lib/lq-ai/styles/practice.css';
	import '$lib/lq-ai/styles/typography.css';

	let booted = false;

	function isAuthExempt(pathname: string): boolean {
		return pathname === '/lq-ai/login' || pathname === '/lq-ai/change-password';
	}

	$: pathname = $page.url.pathname;

	async function gate() {
		if (!$auth.access_token) {
			if (!isAuthExempt(pathname)) {
				goto('/lq-ai/login');
			}
			booted = true;
			return;
		}

		// Refresh `/users/me` to pick up server-side flag changes.
		try {
			const user = await authApi.getCurrentUser();
			if (user.must_change_password && pathname !== '/lq-ai/change-password') {
				goto('/lq-ai/change-password');
				return;
			}
		} catch (e: unknown) {
			if (e instanceof PasswordChangeRequiredError) {
				goto('/lq-ai/change-password');
				return;
			}
			if (e instanceof LQAIApiError && e.status === 401) {
				goto('/lq-ai/login');
				return;
			}
			console.error('lq-ai: failed to refresh user', e);
		}
		booted = true;
	}

	onMount(() => {
		gate();
	});
</script>

{#if booted}
	<div class="lq-shell">
		{#if !isAuthExempt(pathname)}
			<header class="lq-topbar">
				<a class="lq-brand" href="/lq-ai">
					<span class="lq-brand-lq">LQ</span>.AI
				</a>
				<AmbientTrustChrome />
			</header>
			<TopTabBar user={$auth.user ?? null} pathname={pathname} />
		{/if}
		<main id="lq-main">
			<slot />
		</main>
		<DualBrandingFooter />
	</div>
{/if}

<style>
	.lq-shell { background: var(--lq-canvas); color: var(--lq-text); min-height: 100vh; display: flex; flex-direction: column; }
	.lq-topbar {
		display: flex; align-items: center; justify-content: space-between;
		padding: var(--lq-space-3) var(--lq-space-4);
		border-bottom: 1px solid var(--lq-border);
		background: var(--lq-canvas);
	}
	.lq-brand {
		font-size: 16px; font-weight: 600; color: var(--lq-text);
		text-decoration: none;
	}
	.lq-brand-lq { color: var(--lq-accent); }
	main { flex: 1; }
</style>
