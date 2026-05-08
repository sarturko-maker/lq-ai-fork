<script lang="ts">
	import { goto } from '$app/navigation';

	import { authApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import DualBrandingFooter from '$lib/lq-ai/components/DualBrandingFooter.svelte';

	let email = '';
	let password = '';
	let error: string | null = null;
	let busy = false;

	async function submit() {
		error = null;
		busy = true;
		try {
			const res = await authApi.login({ email, password });
			if (res.user.must_change_password) {
				goto('/lq-ai/change-password');
			} else {
				goto('/lq-ai');
			}
		} catch (e: unknown) {
			if (e instanceof LQAIApiError) {
				error = e.status === 401 ? 'Invalid email or password.' : e.message;
			} else if (e instanceof Error) {
				error = e.message;
			} else {
				error = 'Login failed.';
			}
		} finally {
			busy = false;
		}
	}
</script>

<div
	class="min-h-screen flex flex-col bg-white dark:bg-gray-950 text-gray-900 dark:text-gray-100"
	data-testid="lq-ai-login-page"
>
	<main class="flex-1 flex items-center justify-center">
		<form
			class="max-w-sm w-full p-6 rounded-lg shadow border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 space-y-3"
			on:submit|preventDefault={submit}
		>
			<div class="flex items-center gap-2">
				<span
					class="inline-flex items-center justify-center h-9 w-9 rounded bg-indigo-600 text-white font-semibold"
				>
					LQ
				</span>
				<div>
					<h1 class="text-lg font-semibold">Sign in to LQ.AI</h1>
					<p class="text-xs text-gray-500">Open-source legal AI for in-house teams.</p>
				</div>
			</div>

			<label class="block">
				<span class="text-sm">Email</span>
				<input
					type="email"
					autocomplete="username"
					required
					class="mt-1 block w-full text-sm border border-gray-300 rounded px-2 py-1 dark:bg-gray-800"
					bind:value={email}
					data-testid="lq-ai-login-email"
				/>
			</label>

			<label class="block">
				<span class="text-sm">Password</span>
				<input
					type="password"
					autocomplete="current-password"
					required
					class="mt-1 block w-full text-sm border border-gray-300 rounded px-2 py-1 dark:bg-gray-800"
					bind:value={password}
					data-testid="lq-ai-login-password"
				/>
			</label>

			{#if error}
				<div
					class="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded px-2 py-1"
					data-testid="lq-ai-login-error"
				>
					{error}
				</div>
			{/if}

			<button
				type="submit"
				class="w-full px-3 py-2 rounded-md bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 text-sm font-medium"
				disabled={busy}
				data-testid="lq-ai-login-submit"
			>
				{busy ? 'Signing in…' : 'Sign in'}
			</button>

			<p class="text-xs text-gray-500 text-center">
				First-run? Check the API logs for the auto-generated admin password (per Quickstart Step
				2).
			</p>
		</form>
	</main>
	<DualBrandingFooter />
</div>
