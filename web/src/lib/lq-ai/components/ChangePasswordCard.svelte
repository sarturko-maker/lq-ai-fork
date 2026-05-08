<script lang="ts">
	import { authApi } from '../api';

	export let onComplete: () => void = () => undefined;

	let currentPassword = '';
	let newPassword = '';
	let confirmPassword = '';
	let busy = false;
	let error: string | null = null;

	async function submit() {
		error = null;
		if (newPassword.length < 12) {
			error = 'New password must be at least 12 characters.';
			return;
		}
		if (newPassword !== confirmPassword) {
			error = 'New password and confirmation do not match.';
			return;
		}
		if (newPassword === currentPassword) {
			error = 'New password must differ from the current password.';
			return;
		}
		busy = true;
		try {
			await authApi.changePassword({
				current_password: currentPassword,
				new_password: newPassword
			});
			// Server revoked our sessions; the auth store is now empty.
			onComplete();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Failed to change password.';
		} finally {
			busy = false;
		}
	}
</script>

<form
	class="max-w-md mx-auto mt-12 p-6 rounded-lg shadow border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 space-y-3"
	on:submit|preventDefault={submit}
	data-testid="lq-ai-change-password-form"
>
	<h1 class="text-lg font-semibold text-gray-900 dark:text-gray-100">Change your password</h1>
	<p class="text-sm text-gray-600 dark:text-gray-400">
		The first-run admin account requires a password change before any other action. Your new
		password must be at least 12 characters and differ from the current one.
	</p>

	<label class="block">
		<span class="text-sm text-gray-700 dark:text-gray-200">Current password</span>
		<input
			type="password"
			class="mt-1 block w-full text-sm border border-gray-300 rounded px-2 py-1 dark:bg-gray-800"
			bind:value={currentPassword}
			required
			data-testid="lq-ai-current-password"
		/>
	</label>

	<label class="block">
		<span class="text-sm text-gray-700 dark:text-gray-200">New password</span>
		<input
			type="password"
			class="mt-1 block w-full text-sm border border-gray-300 rounded px-2 py-1 dark:bg-gray-800"
			bind:value={newPassword}
			minlength="12"
			required
			data-testid="lq-ai-new-password"
		/>
	</label>

	<label class="block">
		<span class="text-sm text-gray-700 dark:text-gray-200">Confirm new password</span>
		<input
			type="password"
			class="mt-1 block w-full text-sm border border-gray-300 rounded px-2 py-1 dark:bg-gray-800"
			bind:value={confirmPassword}
			minlength="12"
			required
			data-testid="lq-ai-confirm-password"
		/>
	</label>

	{#if error}
		<div
			class="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded px-2 py-1"
			data-testid="lq-ai-change-password-error"
		>
			{error}
		</div>
	{/if}

	<button
		type="submit"
		class="w-full px-3 py-2 rounded-md bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 text-sm font-medium"
		disabled={busy}
		data-testid="lq-ai-change-password-submit"
	>
		{busy ? 'Changing…' : 'Change password'}
	</button>
</form>
