<script lang="ts">
  import { auth } from '$lib/lq-ai/auth/store';

  $: user = $auth.user;
  $: displayName = user?.display_name || user?.email || 'there';

  const now = new Date();
  const dayOfWeek = now.toLocaleDateString('en-US', { weekday: 'long' });
  const dateString = now.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
</script>

<header style="margin-bottom: var(--lq-space-6);">
  <h1 class="lq-text-welcome">Welcome back, {displayName}</h1>
  <p class="lq-text-caption" style="color: var(--lq-text-tertiary);">{dayOfWeek}, {dateString}</p>
</header>
