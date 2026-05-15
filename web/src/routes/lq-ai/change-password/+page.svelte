<script lang="ts">
	import { goto } from '$app/navigation';
	import ChangePasswordCard from '$lib/lq-ai/components/ChangePasswordCard.svelte';
	import TrustPill from '$lib/lq-ai/components/TrustPill.svelte';
</script>

<div data-testid="lq-ai-change-password-page" class="flex-1 flex flex-col items-center justify-center gap-3">
	<div class="lq-notice">
		<TrustPill variant="warn" label="Password change required before continuing" />
	</div>
	<ChangePasswordCard
		onComplete={() => {
			// Server revoked all sessions; the auth store is empty. Send the
			// user back through the login page so they re-auth with their
			// new password.
			goto('/lq-ai/login');
		}}
	/>
</div>

<style>
	.lq-notice {
		display: flex;
		align-items: center;
		gap: var(--lq-space-2);
	}
</style>
