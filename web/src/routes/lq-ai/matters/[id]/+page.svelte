<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { projectsApi } from '$lib/lq-ai/api';
  import type { Project } from '$lib/lq-ai/types';
  import MatterRail from '$lib/lq-ai/components/MatterRail.svelte';
  import ChatPanel from '$lib/lq-ai/components/ChatPanel.svelte';

  let matter: Project | null = null;
  let loading = true;
  let error: string | null = null;
  let activeChatId: string | undefined = undefined;

  $: matterId = $page.params.id;

  async function loadMatter() {
    if (!matterId) return;
    loading = true;
    try {
      matter = await projectsApi.getProject(matterId);
      error = null;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load matter';
    } finally {
      loading = false;
    }
  }

  function handleMatterUpdate(next: Project) {
    matter = next;
  }

  async function handleMatterArchived() {
    // Archive flow already completed by MatterRailMetadata; navigate away.
    await goto('/lq-ai/matters');
  }

  onMount(loadMatter);
</script>

{#if loading}
  <p class="lq-text-body" style="padding: var(--lq-space-6); color: var(--lq-text-secondary);">Loading matter…</p>
{:else if error || !matter}
  <p class="lq-text-body" style="padding: var(--lq-space-6); color: var(--lq-error, #b91c1c);">{error ?? 'Matter not found'}</p>
{:else}
  <div class="matter-workspace">
    <MatterRail
      {matter}
      bind:activeChatId
      onMatterUpdate={handleMatterUpdate}
      onMatterArchived={handleMatterArchived}
    />
    <div class="matter-chat-pane">
      <ChatPanel
        projectIdFilter={matter.id}
        initialChatId={activeChatId}
        on:kbsAttached={loadMatter}
      />
    </div>
  </div>
{/if}

<style>
  .matter-workspace {
    display: flex;
    height: 100%;
    min-height: 0;
  }

  .matter-chat-pane {
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
  }

  /* Match the outer layout's overflow-y: auto on main — the rail scrolls
     within itself if it overflows; the chat panel manages its own scroll
     internally. */
</style>
