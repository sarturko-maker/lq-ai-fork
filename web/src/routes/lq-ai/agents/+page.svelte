<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import ConversationPanel from '$lib/lq-ai/components/agents/ConversationPanel.svelte';
  import NewMatterModal from '$lib/lq-ai/components/NewMatterModal.svelte';
  import { agentsApi, projectsApi } from '$lib/lq-ai/api';
  import type { AgentRunStep, AgentThread } from '$lib/lq-ai/api/agents';
  import type { Project } from '$lib/lq-ai/types';
  import {
    matterName,
    railItems,
    statusBadge,
    type RailState
  } from '$lib/lq-ai/agents/helpers';
  import { serverNowMs } from '$lib/lq-ai/agents/server-clock';

  // The conversation surface itself lives in ConversationPanel (F0-S7
  // extraction — the F1 cockpit re-homes it). This page is the area
  // home's chrome: header, conversation list, capability rail.

  let matters: Project[] = [];
  let mattersError: string | null = null;

  async function loadMatters() {
    try {
      matters = await projectsApi.listProjects(); // active, non-sandbox
      mattersError = null;
    } catch (e) {
      mattersError = e instanceof Error ? e.message : 'Failed to load matters';
    }
  }

  let threads: AgentThread[] = [];
  let threadsLoading = true;
  let threadsError: string | null = null;
  let threadsGeneration = 0;
  let nowMs = serverNowMs();
  let nowTimer: ReturnType<typeof setInterval> | null = null;

  // Generation-guarded: settle events and onMount can overlap, and the
  // older response must never overwrite the fresher list (same posture
  // as the panel's pollGeneration).
  async function loadThreads() {
    const gen = ++threadsGeneration;
    threadsLoading = true;
    try {
      const page = await agentsApi.listThreads({ limit: 20 });
      if (gen !== threadsGeneration) return;
      threads = page.threads;
      threadsError = null;
      nowMs = serverNowMs();
    } catch (e) {
      if (gen !== threadsGeneration) return;
      threadsError = e instanceof Error ? e.message : 'Failed to load conversations';
    } finally {
      if (gen === threadsGeneration) threadsLoading = false;
    }
  }

  onMount(() => {
    loadThreads();
    loadMatters();
    // Keep idle badges honest: a 'running' row must visually flip to Stale
    // even when nothing is being polled.
    nowTimer = setInterval(() => {
      nowMs = serverNowMs();
    }, 30_000);
  });

  onDestroy(() => {
    if (nowTimer !== null) clearInterval(nowTimer);
  });

  // Thread switching = remounting the panel ({#key}): internal state can
  // never leak across conversations. `requestedThreadId` is what the next
  // mount opens; bumping the epoch forces the remount.
  let panelEpoch = 0;
  let requestedThreadId: string | null = null;

  function openThread(t: AgentThread) {
    requestedThreadId = t.id;
    panelEpoch += 1;
  }

  function newChat() {
    requestedThreadId = null;
    panelEpoch += 1;
  }

  // Bound OUT of the panel: the rail renders page-side from the open
  // conversation's settled steps (ADR-F004).
  let railSteps: AgentRunStep[] = [];
  let rail: Record<string, RailState> = {};
  let matterBound = false;
  let hasConversation = false;

  // Bound BOTH WAYS: draft + matter selection live here so they survive
  // the {#key} remounts (the pre-S7 page never reset them on New chat /
  // open-thread — S7 review).
  let draftPrompt = '';
  let selectedMatterId = '';

  // "+ New matter" without leaving the agent (F0-S8): the SAME modal +
  // POST /projects plumbing as the Matters tab — full form, so the
  // privileged ⇒ tier-floor invariant rides along. This page owns the
  // overlay; the panel only requests it.
  let showNewMatter = false;

  function onMatterCreated(m: Project) {
    showNewMatter = false;
    // Bind immediately — the authoritative list refresh follows. Writing
    // the bound prop also clears any pending upload chips in the panel
    // (they belonged to the previously selected matter — F0-S5 invariant).
    matters = [...matters, m];
    selectedMatterId = m.id;
    void loadMatters();
  }

  $: tools = railItems(railSteps, matterBound);
</script>

<main class="ag-page" data-testid="lq-ai-agents-page">
  <header class="ag-header">
    <h1 class="lq-text-page-h">Agents</h1>
    <p class="lq-text-body ag-header__sub">
      Practice-area deep agents. State what you need; the agent picks its tools and works in front
      of you.
    </p>
  </header>

  <div class="ag-layout">
    <section class="ag-main">
      {#key panelEpoch}
        <ConversationPanel
          initialThreadId={requestedThreadId}
          {matters}
          {mattersError}
          bind:prompt={draftPrompt}
          bind:selectedMatterId
          bind:railSteps
          bind:rail
          bind:matterBound
          bind:hasConversation
          on:settled={loadThreads}
          on:newmatter={() => (showNewMatter = true)}
        >
          <svelte:fragment slot="head">
            <h2 class="lq-text-panel-h">Commercial</h2>
            <span class="ag-chip">preview</span>
            {#if hasConversation}
              <button
                type="button"
                class="ag-btn-ghost ag-new-chat"
                data-testid="lq-ai-agents-new-chat"
                on:click={newChat}
              >
                New chat
              </button>
            {/if}
          </svelte:fragment>
          <svelte:fragment slot="copy">
            <p class="lq-text-body-sm ag-area-copy">
              Bind a matter to ground answers in its documents — the agent searches and reads them
              itself, and follow-ups continue the same conversation. One hardcoded practice area
              this preview; configurable areas land in F1.
            </p>
          </svelte:fragment>
        </ConversationPanel>
      {/key}
    </section>

    <!-- Side column (F0-S8): the main column is the CONVERSATION —
         capability rail and the conversations list live beside it, so
         the timeline reads top-down into the docked composer. -->
    <div class="ag-side">
      <aside class="ag-rail" data-testid="lq-ai-agents-rail">
        <h2 class="lq-text-panel-h">Capabilities</h2>
        <p class="lq-text-caption ag-rail__sub">
          Everything the agent can call. Lights up as it works.
        </p>
        <ul>
          {#each tools as tool (tool.name)}
            {@const state = rail[tool.name] ?? 'dim'}
            <li class="ag-rail__tool ag-rail__tool--{state}" title={tool.name}>
              <span class="ag-rail__dot" aria-hidden="true"></span>
              <span class="ag-rail__text">
                <span class="lq-text-body-sm ag-rail__name">{tool.label}</span>
                <span class="lq-text-caption ag-rail__hint">{tool.hint}</span>
                <span class="ag-sr-only">
                  {state === 'active'
                    ? 'in use'
                    : state === 'lit'
                      ? 'used in this conversation'
                      : 'not used yet'}
                </span>
              </span>
            </li>
          {/each}
        </ul>
      </aside>

      <section class="ag-previous">
        <h2 class="lq-text-panel-h">Conversations</h2>
        {#if threadsLoading}
          <p class="lq-text-body-sm ag-note">Loading conversations…</p>
        {:else if threadsError}
          <p class="lq-text-body-sm ag-error">Couldn't load conversations: {threadsError}</p>
        {:else if threads.length === 0}
          <p class="lq-text-body-sm ag-note">No conversations yet — ask the agent something.</p>
        {:else}
          <ul class="ag-runs-list" data-testid="lq-ai-agents-runs-list">
            {#each threads as t (t.id)}
              <li>
                <button type="button" class="ag-runs-list__row" on:click={() => openThread(t)}>
                  <span class="ag-runs-list__prompt">
                    {#if t.project_id}
                      <span class="ag-chip">{matterName(matters, t.project_id)}</span>
                    {/if}
                    {t.title}
                  </span>
                  {#if t.last_run_status}
                    {@const b = statusBadge(
                      { status: t.last_run_status, started_at: t.last_run_at, error: null },
                      nowMs
                    )}
                    <span class="ag-badge ag-badge--{b.tone}">{b.label}</span>
                  {/if}
                  <span class="lq-text-caption ag-runs-list__when">
                    {new Date(t.last_run_at).toLocaleString()}
                  </span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    </div>
  </div>
</main>

{#if showNewMatter}
  <NewMatterModal onClose={() => (showNewMatter = false)} onCreated={onMatterCreated} />
{/if}

<style>
  .ag-page {
    padding: var(--lq-space-6);
    max-width: 1200px;
    margin: 0 auto;
  }

  .ag-header {
    margin-bottom: var(--lq-space-4);
  }

  .ag-header__sub {
    color: var(--lq-text-secondary);
    margin-top: var(--lq-space-1);
  }

  .ag-layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 280px;
    gap: var(--lq-space-4);
    align-items: start;
  }

  @media (max-width: 900px) {
    .ag-layout {
      grid-template-columns: 1fr;
    }
  }

  .ag-side {
    display: flex;
    flex-direction: column;
    gap: var(--lq-space-4);
    min-width: 0;
  }

  .ag-rail,
  .ag-previous {
    background: var(--lq-canvas);
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius-lg);
    padding: var(--lq-space-4);
  }

  /* Slotted into the panel's card head (parent-scoped by design). */
  .ag-new-chat {
    margin-left: auto;
  }

  .ag-area-copy {
    color: var(--lq-text-secondary);
    margin: var(--lq-space-2) 0 var(--lq-space-3);
  }

  .ag-chip {
    background: var(--lq-accent-soft);
    color: var(--lq-accent);
    border: 1px solid var(--lq-accent-border);
    border-radius: var(--lq-radius-pill);
    padding: 0 var(--lq-space-2);
    font-size: 11px;
    line-height: 18px;
  }

  .ag-badge {
    border-radius: var(--lq-radius-pill);
    padding: 0 var(--lq-space-2);
    font-size: 11px;
    line-height: 18px;
    white-space: nowrap;
    border: 1px solid var(--lq-border);
    color: var(--lq-text-secondary);
  }

  .ag-badge--running {
    background: var(--lq-accent-soft);
    border-color: var(--lq-accent-border);
    color: var(--lq-accent);
    animation: ag-pulse 1.6s ease-in-out infinite;
  }

  .ag-badge--ok {
    background: var(--lq-accent-soft);
    border-color: var(--lq-accent-border);
    color: var(--lq-accent);
  }

  .ag-badge--warn {
    background: var(--lq-warn-soft);
    border-color: var(--lq-warn-border);
    color: var(--lq-warn);
  }

  .ag-badge--error {
    background: var(--lq-error-soft);
    border-color: var(--lq-error-border);
    color: var(--lq-error);
  }

  .ag-runs-list {
    list-style: none;
    margin: var(--lq-space-2) 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--lq-space-1);
  }

  /* Narrow side-column rows (F0-S8): title on top, badge + timestamp
     wrap beneath — the old 3-column grid presumed main-column width. */
  .ag-runs-list__row {
    display: flex;
    flex-wrap: wrap;
    column-gap: var(--lq-space-2);
    row-gap: 2px;
    align-items: center;
    width: 100%;
    text-align: left;
    background: none;
    border: 1px solid transparent;
    border-radius: var(--lq-radius);
    padding: var(--lq-space-2) var(--lq-space-3);
    cursor: pointer;
    font: inherit;
  }

  .ag-runs-list__row:hover {
    background: var(--lq-inset);
    border-color: var(--lq-border);
  }

  .ag-runs-list__prompt {
    flex: 1 1 100%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }

  .ag-runs-list__when {
    color: var(--lq-text-tertiary);
  }

  .ag-rail ul {
    list-style: none;
    margin: var(--lq-space-3) 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--lq-space-2);
  }

  .ag-rail__sub {
    color: var(--lq-text-tertiary);
    display: block;
    margin-top: var(--lq-space-1);
  }

  .ag-rail__tool {
    display: flex;
    align-items: flex-start;
    gap: var(--lq-space-2);
    transition: opacity 0.2s ease;
  }

  .ag-rail__tool--dim {
    opacity: 0.45;
  }

  .ag-rail__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--lq-border);
    margin-top: 5px;
    flex: none;
  }

  .ag-rail__tool--lit .ag-rail__dot {
    background: var(--lq-accent);
  }

  .ag-rail__tool--active .ag-rail__dot {
    background: var(--lq-accent);
    animation: ag-pulse 1s ease-in-out infinite;
  }

  .ag-rail__text {
    display: flex;
    flex-direction: column;
  }

  .ag-rail__hint {
    color: var(--lq-text-tertiary);
  }

  .ag-btn-ghost {
    background: none;
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius-sm);
    padding: 0 var(--lq-space-2);
    cursor: pointer;
    font: inherit;
    font-size: 12px;
    line-height: 22px;
    color: var(--lq-text-secondary);
  }

  .ag-btn-ghost:hover {
    border-color: var(--lq-accent-border);
    color: var(--lq-accent);
  }

  .ag-sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  .ag-error {
    color: var(--lq-error);
  }

  .ag-note {
    color: var(--lq-text-secondary);
  }

  @keyframes ag-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.4;
    }
  }
</style>
