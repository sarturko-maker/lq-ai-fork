<script lang="ts">
	/**
	 * /lq-ai/accept-invite — unauthenticated invite-acceptance page (SETUP-3b,
	 * ADR-F061 addendum D1/D2). Reached from the emailed (or out-of-band) link;
	 * listed in the gate layout's isAuthExempt allowlist.
	 *
	 * The token is read from the query string once on mount and held in
	 * component state only — never logged, never stored. Missing/blank token →
	 * immediate invalid-link state, no request fired. On 201 the success panel
	 * shows the created account's email and links to sign-in (NO auto-login —
	 * the endpoint deliberately returns no tokens). The exempt-route layout
	 * renders the footer; this page must not add its own.
	 */
	import { onMount } from 'svelte';
	import { replaceState } from '$app/navigation';
	import { page } from '$app/stores';

	import { authApi } from '$lib/lq-ai/api';
	import type { AcceptInviteResponse } from '$lib/lq-ai/types';
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

	let password = $state('');
	let confirmPassword = $state('');
	let displayName = $state('');
	let validationError = $state<string | null>(null);
	let submitError = $state<string | null>(null);
	let busy = $state(false);
	let created = $state<AcceptInviteResponse | null>(null);

	onMount(() => {
		token = readToken($page.url.searchParams);
		// F7 — scrub the single-use token from the address bar (component state
		// keeps it); shared-machine history/autocomplete never see it.
		const scrubbed = stripTokenParam(window.location.href);
		if (scrubbed !== null) replaceState(scrubbed, {});
		mounted = true;
	});

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (!token) return;
		validationError = validateNewPassword(password, confirmPassword);
		submitError = null;
		if (validationError) return;
		busy = true;
		try {
			created = await authApi.acceptInvite({
				token,
				password,
				display_name: displayName.trim() || undefined
			});
		} catch (e) {
			// The backend collapses every bad token to one uniform 400 message;
			// surface it (and the 409 duplicate-user message) as-is.
			submitError = e instanceof Error ? e.message : 'Failed to accept the invitation.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head>
	<title>Accept invitation — LQ.AI Oscar Edition</title>
</svelte:head>

<div
	class="flex min-h-full flex-col items-center justify-center px-4 py-12"
	data-testid="lq-accept-invite-page"
>
	{#if !mounted}
		<!-- Token not read yet — render nothing rather than flash the wrong state. -->
	{:else if created}
		<div
			class="w-full max-w-md space-y-3 rounded-xl border border-border bg-background p-6 shadow-sm"
			data-testid="lq-accept-invite-success"
		>
			<h1 class="text-lg font-semibold text-foreground">You're all set</h1>
			<p class="text-sm text-muted-foreground">
				Your account <span class="font-medium text-foreground">{created.email}</span> has been
				created. Sign in with the password you just chose.
			</p>
			<Button href="/lq-ai/login" class="w-full" data-testid="lq-accept-invite-signin">
				Sign in
			</Button>
		</div>
	{:else if !token}
		<div
			class="w-full max-w-md space-y-3 rounded-xl border border-border bg-background p-6 shadow-sm"
			data-testid="lq-accept-invite-invalid"
		>
			<h1 class="text-lg font-semibold text-foreground">Invalid invitation link</h1>
			<p class="text-sm text-muted-foreground">
				This invitation link is missing or incomplete. Ask your administrator to send a new
				invitation.
			</p>
			<Button href="/lq-ai/login" variant="outline" class="w-full">Go to sign in</Button>
		</div>
	{:else}
		<form
			class="w-full max-w-md space-y-4 rounded-xl border border-border bg-background p-6 shadow-sm"
			novalidate
			onsubmit={submit}
			data-testid="lq-accept-invite-form"
		>
			<div>
				<h1 class="text-lg font-semibold text-foreground">Accept your invitation</h1>
				<p class="mt-1 text-sm text-muted-foreground">
					Choose a password to activate your LQ.AI account. At least {PASSWORD_MIN_LENGTH}
					characters.
				</p>
			</div>

			<FormControl id="lq-accept-password" label="Password" required>
				<Input
					id="lq-accept-password"
					type="password"
					autocomplete="new-password"
					bind:value={password}
					minlength={PASSWORD_MIN_LENGTH}
					required
					disabled={busy}
					data-testid="lq-accept-invite-password"
				/>
			</FormControl>

			<FormControl id="lq-accept-confirm" label="Confirm password" required>
				<Input
					id="lq-accept-confirm"
					type="password"
					autocomplete="new-password"
					bind:value={confirmPassword}
					minlength={PASSWORD_MIN_LENGTH}
					required
					disabled={busy}
					data-testid="lq-accept-invite-confirm"
				/>
			</FormControl>

			<FormControl id="lq-accept-display-name" label="Display name" optional>
				<Input
					id="lq-accept-display-name"
					type="text"
					autocomplete="name"
					bind:value={displayName}
					maxlength={200}
					disabled={busy}
					data-testid="lq-accept-invite-display-name"
				/>
			</FormControl>

			{#if validationError}
				<Alert intent="error">{validationError}</Alert>
			{/if}
			{#if submitError}
				<Alert intent="error">{submitError}</Alert>
			{/if}

			<Button type="submit" class="w-full" disabled={busy} data-testid="lq-accept-invite-submit">
				{busy ? 'Creating account…' : 'Create account'}
			</Button>
		</form>
	{/if}
</div>
