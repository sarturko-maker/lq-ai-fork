<script lang="ts">
	import { goto } from '$app/navigation';
	import ChangePasswordCard from '$lib/lq-ai/components/ChangePasswordCard.svelte';
</script>

<div data-testid="lq-ai-change-password-page" class="flex-1 flex items-center justify-center">
	<ChangePasswordCard
		onComplete={() => {
			// Server revoked all sessions; the auth store is empty. Send the
			// user back through the login page so they re-auth with their
			// new password.
			goto('/lq-ai/login');
		}}
	/>
</div>
