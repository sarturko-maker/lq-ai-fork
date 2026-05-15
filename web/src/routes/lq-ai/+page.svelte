<script lang="ts">
  import { onMount } from 'svelte';
  import { initPreferences } from '$lib/lq-ai/stores/preferences';
  import GuidedDashboardWelcome from '$lib/lq-ai/components/GuidedDashboardWelcome.svelte';
  import GuidedDashboardTrustPanel from '$lib/lq-ai/components/GuidedDashboardTrustPanel.svelte';
  import FeaturedToolsRow from '$lib/lq-ai/components/FeaturedToolsRow.svelte';
  import GettingStartedChecklist from '$lib/lq-ai/components/GettingStartedChecklist.svelte';
  import RecentActivity from '$lib/lq-ai/components/RecentActivity.svelte';

  onMount(() => { initPreferences(); });
</script>

<div class="lq-dashboard">
  <GuidedDashboardWelcome />
  <GuidedDashboardTrustPanel />
  <FeaturedToolsRow />
  <GettingStartedChecklist />
  <RecentActivity />
</div>

<style>
  .lq-dashboard {
    padding: var(--lq-space-6);
    max-width: 1200px;
    margin: 0 auto;
  }
</style>
