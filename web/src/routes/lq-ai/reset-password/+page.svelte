<script lang="ts">
	/**
	 * /lq-ai/reset-password — unauthenticated dual-state page (SETUP-3b,
	 * ADR-F061 addendum D3). Listed in the gate layout's isAuthExempt allowlist.
	 *
	 * No/blank `?token=` → the REQUEST form: email in, and ALWAYS the same
	 * "if an account exists, an email has been sent" message — mirroring the
	 * API's uniform 202, so the page never confirms account existence.
	 *
	 * With a token → the CONFIRM form: new password + confirmation (client
	 * floor mirrors password_min_length = 12), then a sign-in link. The token
	 * is read once on mount, held in component state only — never logged,
	 * never stored. No auto-login (the endpoint returns no tokens and revokes
	 * every session). The exempt-route layout renders the footer.
	 */
	import { onMount } from 'svelte';
	import { afterNavigate, replaceState } from '$app/navigation';
	import { page } from '$app/stores';

	import { authApi } from '$lib/lq-ai/api';
	import {
		PASSWORD_MIN_LENGTH,
		readToken,
		stripTokenParam,
		validateNewPassword
	} from '$lib/lq-ai/auth/lifecycle-helpers';
	import Alert from '$lib/lq-ai/components/primitives/Alert.svelte';
	import FormControl from '$lib/lq-ai/components/primitives/FormControl.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';

	let token = $state<string | null>(null);
	let mounted = $state(false);

	// Request state (no token)
	let email = $state('');
	let requestSent = $state(false);
	let requestError = $state<string | null>(null);

	// Confirm state (token present)
	let newPassword = $state('');
	let confirmPassword = $state('');
	let validationError = $state<string | null>(null);
	let confirmError = $state<string | null>(null);
	let resetDone = $state(false);

	let busy = $state(false);

	onMount(() => {
		token = readToken($page.url.searchParams);
		mounted = true;
	});

	// F7 — scrub the single-use token from the address bar (component state
	// keeps it); shared-machine history/autocomplete never see it. This runs in
	// `afterNavigate`, not inline in `onMount`: on a direct/full page load
	// SvelteKit's router has not finished initializing yet when `onMount`
	// fires, and calling `replaceState()` at that point throws ("Cannot call
	// replaceState(...) before router is initialized"), which used to abort
	// `onMount` before `mounted` was set — the page rendered nothing forever
	// (G7). `afterNavigate` fires once the router has committed the initial
	// navigation, including on a full page load, so it's safe here; `mounted`
	// is set unconditionally in `onMount` above regardless of the scrub.
	afterNavigate(() => {
		const scrubbed = stripTokenParam(window.location.href);
		if (scrubbed !== null) replaceState(scrubbed, {});
	});

	async function submitRequest(event: SubmitEvent) {
		event.preventDefault();
		requestError = null;
		busy = true;
		try {
			await authApi.passwordResetRequest(email.trim());
			// Uniform outcome — the API always 202s; the copy never confirms
			// whether an account exists (anti-enumeration, ADR-F061 D7).
			requestSent = true;
		} catch (e) {
			// Transport/rate-limit failure only — still no existence signal.
			requestError = e instanceof Error ? e.message : 'Could not send the request. Try again.';
		} finally {
			busy = false;
		}
	}

	async function submitConfirm(event: SubmitEvent) {
		event.preventDefault();
		if (!token) return;
		validationError = validateNewPassword(newPassword, confirmPassword);
		confirmError = null;
		if (validationError) return;
		busy = true;
		try {
			await authApi.passwordResetConfirm({ token, new_password: newPassword });
			resetDone = true;
		} catch (e) {
			// The backend collapses every bad token to one uniform 400 — surface it.
			confirmError = e instanceof Error ? e.message : 'Failed to reset the password.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head>
	<title>Reset password — LQ.AI Oscar Edition</title>
</svelte:head>

<div
	class="flex min-h-full flex-col items-center justify-center px-4 py-12"
	data-testid="lq-reset-password-page"
>
	{#if !mounted}
		<!-- Token not read yet — render nothing rather than flash the wrong state. -->
	{:else if token}
		{#if resetDone}
			<div
				class="w-full max-w-md space-y-3 rounded-xl border border-border bg-background p-6 shadow-sm"
				data-testid="lq-reset-password-success"
			>
				<h1 class="text-lg font-semibold text-foreground">Password reset</h1>
				<p class="text-sm text-muted-foreground">
					Your password has been changed and every existing session signed out. Sign in with your
					new password.
				</p>
				<Button href="/lq-ai/login" class="w-full" data-testid="lq-reset-password-signin">
					Sign in
				</Button>
			</div>
		{:else}
			<form
				class="w-full max-w-md space-y-4 rounded-xl border border-border bg-background p-6 shadow-sm"
				novalidate
				onsubmit={submitConfirm}
				data-testid="lq-reset-password-confirm-form"
			>
				<div>
					<h1 class="text-lg font-semibold text-foreground">Choose a new password</h1>
					<p class="mt-1 text-sm text-muted-foreground">
						At least {PASSWORD_MIN_LENGTH} characters. Existing sessions will be signed out.
					</p>
				</div>

				<FormControl id="lq-reset-new-password" label="New password" required>
					<Input
						id="lq-reset-new-password"
						type="password"
						autocomplete="new-password"
						bind:value={newPassword}
						minlength={PASSWORD_MIN_LENGTH}
						required
						disabled={busy}
						data-testid="lq-reset-password-new"
					/>
				</FormControl>

				<FormControl id="lq-reset-confirm-password" label="Confirm new password" required>
					<Input
						id="lq-reset-confirm-password"
						type="password"
						autocomplete="new-password"
						bind:value={confirmPassword}
						minlength={PASSWORD_MIN_LENGTH}
						required
						disabled={busy}
						data-testid="lq-reset-password-confirm"
					/>
				</FormControl>

				{#if validationError}
					<Alert intent="error">{validationError}</Alert>
				{/if}
				{#if confirmError}
					<Alert intent="error">{confirmError}</Alert>
				{/if}

				<Button type="submit" class="w-full" disabled={busy} data-testid="lq-reset-password-submit">
					{busy ? 'Resetting…' : 'Reset password'}
				</Button>
			</form>
		{/if}
	{:else if requestSent}
		<div
			class="w-full max-w-md space-y-3 rounded-xl border border-border bg-background p-6 shadow-sm"
			data-testid="lq-reset-password-request-sent"
		>
			<h1 class="text-lg font-semibold text-foreground">Check your email</h1>
			<p class="text-sm text-muted-foreground">
				If an account exists for that address, an email with a reset link has been sent. The link
				is single-use and expires within the hour.
			</p>
			<Button href="/lq-ai/login" variant="outline" class="w-full">Back to sign in</Button>
		</div>
	{:else}
		<form
			class="w-full max-w-md space-y-4 rounded-xl border border-border bg-background p-6 shadow-sm"
			novalidate
			onsubmit={submitRequest}
			data-testid="lq-reset-password-request-form"
		>
			<div>
				<h1 class="text-lg font-semibold text-foreground">Reset your password</h1>
				<p class="mt-1 text-sm text-muted-foreground">
					Enter your account's email address and we'll send a reset link.
				</p>
			</div>

			<FormControl id="lq-reset-email" label="Email" required>
				<Input
					id="lq-reset-email"
					type="email"
					autocomplete="username"
					bind:value={email}
					required
					disabled={busy}
					data-testid="lq-reset-password-email"
				/>
			</FormControl>

			{#if requestError}
				<Alert intent="error">{requestError}</Alert>
			{/if}

			<Button
				type="submit"
				class="w-full"
				disabled={busy || !email.trim()}
				data-testid="lq-reset-password-request-submit"
			>
				{busy ? 'Sending…' : 'Send reset link'}
			</Button>

			<p class="text-center text-sm">
				<a class="text-muted-foreground underline-offset-4 hover:underline" href="/lq-ai/login">
					Back to sign in
				</a>
			</p>
		</form>
	{/if}
</div>
