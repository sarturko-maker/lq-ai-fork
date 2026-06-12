<script lang="ts">
	/**
	 * LQ.AI gate layout — auth + force-change-password + idle tracking for
	 * every route under `/lq-ai/*` except `/lq-ai/login` and
	 * `/lq-ai/change-password` (F1-S2: chrome moved out — the cockpit at
	 * `/lq-ai` owns its own viewport; legacy tool routes carry the tab
	 * chrome via the `(tools)` group layout).
	 *
	 * - No access token → redirect to /lq-ai/login.
	 * - Access token but `must_change_password` → redirect to /lq-ai/change-password.
	 * - Otherwise: render the child route.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { auth } from '$lib/lq-ai/auth/store';
	import { authApi } from '$lib/lq-ai/api';
	import { LQAIApiError, PasswordChangeRequiredError } from '$lib/lq-ai/api/client';
	import DualBrandingFooter from '$lib/lq-ai/components/DualBrandingFooter.svelte';
	import SessionTimeoutWarning from '$lib/lq-ai/components/SessionTimeoutWarning.svelte';
	import { startTracker, stopTracker, noteActivity } from '$lib/lq-ai/stores/sessionActivity';
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

	let activityHandler: (() => void) | null = null;

	onMount(() => {
		gate();
		if (!isAuthExempt($page.url.pathname)) {
			startTracker(() => goto('/lq-ai/login?reason=idle-timeout'));
			activityHandler = () => noteActivity();
			(['mousedown', 'keydown', 'scroll', 'touchstart'] as const).forEach((e) =>
				window.addEventListener(e, activityHandler!, { passive: true })
			);
		}
	});

	onDestroy(() => {
		stopTracker();
		if (activityHandler) {
			(['mousedown', 'keydown', 'scroll', 'touchstart'] as const).forEach((e) =>
				window.removeEventListener(e, activityHandler!)
			);
			activityHandler = null;
		}
	});
</script>

{#if booted}
	{#if isAuthExempt(pathname)}
		<!-- Login / change-password keep the pre-S2 minimal shell. -->
		<div class="lq-shell">
			<main id="lq-main">
				<slot />
			</main>
			<DualBrandingFooter />
		</div>
	{:else}
		<slot />
	{/if}
	<SessionTimeoutWarning />
{/if}

<style>
	.lq-shell {
		background: var(--lq-canvas);
		color: var(--lq-text);
		height: 100vh;
		display: flex;
		flex-direction: column;
	}
	main {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
	}
</style>
