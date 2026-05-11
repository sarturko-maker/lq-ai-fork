<script lang="ts">
  // Transitional — Task 4 (Wave B v2) replaces this with the Guided Dashboard.
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  onMount(() => goto('/lq-ai/chats', { replaceState: true }));
</script>

<div class="lq-shell" style="padding: var(--lq-space-8); text-align: center;">
  <p class="lq-text-body" style="color: var(--lq-text-tertiary);">Redirecting to chats…</p>
</div>
