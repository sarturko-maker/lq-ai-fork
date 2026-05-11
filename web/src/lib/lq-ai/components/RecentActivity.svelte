<script lang="ts">
  import { onMount } from 'svelte';
  import { chatsApi } from '$lib/lq-ai/api';
  import type { Chat } from '$lib/lq-ai/types';

  let chats: Chat[] = [];
  let loading = true;
  let error = false;

  onMount(async () => {
    try {
      // /chats/search requires minLength=1 for q; use listChats instead
      // for the recent-activity view which needs no query term.
      const page = await chatsApi.listChats({ limit: 5 });
      chats = page.items;
    } catch {
      error = true;
    } finally {
      loading = false;
    }
  });

  function formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }
</script>

<section style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--lq-space-4); margin-bottom: var(--lq-space-6);">
  <!-- Recent chats -->
  <div class="activity-card">
    <p class="lq-text-label" style="margin-bottom: var(--lq-space-3);">Recent chats</p>

    {#if loading}
      <p class="lq-text-body-sm" style="color: var(--lq-text-tertiary);">Loading…</p>
    {:else if error}
      <p class="lq-text-body-sm" style="color: var(--lq-text-tertiary);">Could not load recent chats.</p>
    {:else if chats.length === 0}
      <p class="lq-text-body-sm" style="color: var(--lq-text-tertiary);">No chats yet. <a href="/lq-ai/chats" style="color: var(--lq-accent); text-decoration: none;">Start one →</a></p>
    {:else}
      <ul class="chat-list">
        {#each chats as chat (chat.id)}
          <li>
            <a href="/lq-ai/chats" class="chat-row">
              <span class="chat-title lq-text-body-sm">{chat.title || 'Untitled chat'}</span>
              <span class="chat-date lq-text-caption">{formatDate(chat.updated_at)}</span>
            </a>
          </li>
        {/each}
      </ul>
      <a href="/lq-ai/chats" class="view-all lq-text-body-sm">View all chats →</a>
    {/if}
  </div>

  <!-- Recent matters — Wave C placeholder -->
  <div class="activity-card placeholder-card">
    <p class="lq-text-label" style="margin-bottom: var(--lq-space-3);">Recent matters</p>
    <p class="lq-text-body-sm" style="color: var(--lq-text-tertiary);">
      Matter workspace is coming in a future release. Chats linked to matters will appear here.
    </p>
    <p class="lq-text-caption" style="margin-top: var(--lq-space-3); color: var(--lq-text-tertiary);">Wave C</p>
  </div>
</section>

<style>
  .activity-card {
    background: var(--lq-canvas);
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius-lg);
    padding: var(--lq-space-4);
  }

  .placeholder-card {
    background: var(--lq-inset);
  }

  .chat-list {
    list-style: none;
    margin: 0 0 var(--lq-space-3) 0;
    padding: 0;
  }

  .chat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--lq-space-2);
    padding: var(--lq-space-2) 0;
    border-bottom: 1px solid var(--lq-border);
    text-decoration: none;
    color: var(--lq-text);
  }
  .chat-list li:last-child .chat-row { border-bottom: none; }
  .chat-row:hover .chat-title { color: var(--lq-accent); }

  .chat-title {
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .chat-date {
    flex-shrink: 0;
    color: var(--lq-text-tertiary);
  }

  .view-all {
    color: var(--lq-accent);
    text-decoration: none;
  }
  .view-all:hover { text-decoration: underline; }

  @media (max-width: 640px) {
    section {
      grid-template-columns: 1fr;
    }
  }
</style>
