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

<div class="min-h-screen flex flex-col bg-white dark:bg-gray-950 text-gray-900 dark:text-gray-100">
	<header
		class="px-4 py-2 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between"
		data-testid="lq-ai-header"
	>
		<a href="/lq-ai" class="flex items-center gap-2">
			<span class="inline-flex items-center justify-center h-8 w-8 rounded bg-indigo-600 text-white font-semibold">
				LQ
			</span>
			<span class="text-base font-semibold">LQ.AI</span>
			<span class="text-xs text-gray-400">/ legal AI for in-house teams</span>
		</a>
		{#if $auth.user}
			<div class="text-sm text-gray-600 dark:text-gray-300 flex items-center gap-2">
				<span>{$auth.user.email}</span>
				<button
					type="button"
					class="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
					on:click={async () => {
						await authApi.logout();
						goto('/lq-ai/login');
					}}
					data-testid="lq-ai-logout-btn"
				>
					Sign out
				</button>
			</div>
		{/if}
	</header>

	<main class="flex-1 flex flex-col overflow-hidden">
		{#if booted}
			<slot />
		{:else}
			<div class="flex-1 flex items-center justify-center text-gray-500 text-sm">Loading…</div>
		{/if}
	</main>

	<DualBrandingFooter />
</div>
