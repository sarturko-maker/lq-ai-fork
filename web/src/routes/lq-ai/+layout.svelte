<script lang="ts">
	/**
	 * LQ.AI gate layout — auth + force-change-password + idle tracking for
	 * every route under `/lq-ai/*` except `/lq-ai/login` and
	 * `/lq-ai/change-password` (F1-S2: chrome moved out — the cockpit shell at
	 * `(app)/+layout.svelte` owns the viewport for every authenticated surface;
	 * UX-A folded all the legacy tool routes into it and retired the `(tools)`
	 * shell, so this gate just renders `<slot />` for protected routes).
	 *
	 * - No access token → redirect to /lq-ai/login.
	 * - Access token but `must_change_password` → redirect to /lq-ai/change-password.
	 * - Otherwise: render the child route.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { auth, clearSession } from '$lib/lq-ai/auth/store';
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

	// Cap how long we wait for the session check. A healthy /users/me answers
	// in well under a second; if it doesn't resolve in time the session can't
	// be verified (e.g. a slow/stuck token refresh on the server) and we must
	// NOT sit on a blank shell — we bounce to login instead. This is the
	// guard against the expired-session blank-screen: an un-refreshable
	// session used to leave getCurrentUser() pending forever, stranding the
	// gate before it could redirect.
	const SESSION_CHECK_TIMEOUT_MS = 8000;

	/** Distinct from a network/HTTP error so the gate can react specifically. */
	class SessionCheckTimeout extends Error {}

	function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
		let timer: ReturnType<typeof setTimeout>;
		const timeout = new Promise<never>((_, reject) => {
			timer = setTimeout(() => reject(new SessionCheckTimeout()), ms);
		});
		return Promise.race([promise, timeout]).finally(() => clearTimeout(timer)) as Promise<T>;
	}

	async function gate() {
		// `booted` gates protected content. It MUST end up true on every path:
		// the redirect targets (/lq-ai/login, /lq-ai/change-password) live under
		// THIS layout, so SvelteKit never remounts it and gate() never re-runs —
		// leaving `booted` false on a redirect path strands the whole layout
		// (and the page it bounced to) on a blank shell. That was the
		// expired-session blank-screen bug: a valid-but-stale token 401s on
		// /users/me, the catch bounced to login but skipped `booted = true`, so
		// login rendered into nothing. The `finally` closes every path;
		// `await goto(..., { replaceState: true })` makes navigation
		// deterministic before we flip `booted`.
		try {
			if (!$auth.access_token) {
				if (!isAuthExempt(pathname)) {
					await goto('/lq-ai/login', { replaceState: true });
				}
				return;
			}

			// Refresh `/users/me` to pick up server-side flag changes.
			const user = await withTimeout(authApi.getCurrentUser(), SESSION_CHECK_TIMEOUT_MS);
			if (user.must_change_password && pathname !== '/lq-ai/change-password') {
				await goto('/lq-ai/change-password', { replaceState: true });
			}
		} catch (e: unknown) {
			if (e instanceof PasswordChangeRequiredError) {
				await goto('/lq-ai/change-password', { replaceState: true });
			} else if (e instanceof LQAIApiError && e.status === 401) {
				// Expired/invalid session — the API client already cleared it on
				// the 401; bounce to login so the user can re-authenticate.
				await goto('/lq-ai/login', { replaceState: true });
			} else if (e instanceof SessionCheckTimeout) {
				// Couldn't verify the session in time. Don't render protected
				// content on an unverifiable session (and don't hang): clear it
				// and send the user to login.
				console.warn('lq-ai: session check timed out; redirecting to login');
				clearSession();
				await goto('/lq-ai/login', { replaceState: true });
			} else {
				// Transient/offline error — keep the optimistic render so a
				// flaky network doesn't force a re-login.
				console.error('lq-ai: failed to refresh user', e);
			}
		} finally {
			booted = true;
		}
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

<!--
	Auth-exempt routes (login / change-password) render REGARDLESS of `booted`:
	they are the gate's redirect targets and share this layout (no remount), so
	gating them on `booted` would blank them whenever the gate bounces an
	unauthenticated or expired session here. Protected routes still wait for the
	gate to settle so they never flash before auth resolves.
-->
{#if isAuthExempt(pathname)}
	<!-- Login / change-password keep the pre-S2 minimal shell. -->
	<div class="lq-shell">
		<main id="lq-main">
			<slot />
		</main>
		<DualBrandingFooter />
	</div>
{:else if booted}
	<slot />
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
