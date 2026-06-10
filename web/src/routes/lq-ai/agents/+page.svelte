<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import DOMPurify from 'dompurify';
  import { marked } from 'marked';
  import { agentsApi } from '$lib/lq-ai/api';
  import type { AgentRun, AgentRunStep } from '$lib/lq-ai/api/agents';
  import {
    POLL_INTERVAL_MS,
    isStaleRunning,
    railItems,
    railStates,
    shouldContinuePolling,
    splitThink,
    statusBadge,
    stepDisplay
  } from './page-helpers';

  let prompt = '';
  let submitting = false;
  let submitError: string | null = null;

  let run: AgentRun | null = null;
  let steps: AgentRunStep[] = [];
  let currentRunId: string | null = null;
  let pollError: string | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let nowMs = Date.now();

  let previousRuns: AgentRun[] = [];
  let runsLoading = true;
  let runsError: string | null = null;

  async function loadRuns() {
    runsLoading = true;
    try {
      const page = await agentsApi.listRuns({ limit: 20 });
      previousRuns = page.runs;
      runsError = null;
      nowMs = Date.now();
    } catch (e) {
      runsError = e instanceof Error ? e.message : 'Failed to load runs';
    } finally {
      runsLoading = false;
    }
  }

  onMount(loadRuns);

  function stopPolling() {
    if (pollTimer !== null) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  onDestroy(stopPolling);

  async function poll(id: string) {
    try {
      const detail = await agentsApi.getRun(id);
      if (currentRunId !== id) return; // user switched runs mid-flight
      run = detail.run;
      steps = detail.steps;
      pollError = null;
      nowMs = Date.now();
      if (!shouldContinuePolling(detail.run, nowMs)) {
        stopPolling();
        loadRuns();
      }
    } catch (e) {
      if (currentRunId !== id) return;
      stopPolling();
      pollError = e instanceof Error ? e.message : 'Failed to poll the run';
    }
  }

  function startPolling(id: string) {
    stopPolling();
    currentRunId = id;
    pollError = null;
    poll(id);
    pollTimer = setInterval(() => poll(id), POLL_INTERVAL_MS);
  }

  async function submit() {
    const text = prompt.trim();
    if (!text || submitting) return;
    submitting = true;
    submitError = null;
    try {
      const created = await agentsApi.createRun({ prompt: text });
      prompt = '';
      run = created;
      steps = [];
      startPolling(created.id);
    } catch (e) {
      submitError = e instanceof Error ? e.message : 'Failed to start the run';
    } finally {
      submitting = false;
    }
  }

  function openRun(r: AgentRun) {
    run = r;
    steps = [];
    startPolling(r.id); // terminal runs settle after the first poll response
  }

  $: badge = run ? statusBadge(run, nowMs) : null;
  $: stale = run ? isStaleRunning(run, nowMs) : false;
  $: rail = railStates(steps, run?.status ?? null);
  $: tools = railItems(steps);
  $: answer = splitThink(run?.final_answer);
  $: answerHtml = answer.visible
    ? DOMPurify.sanitize(marked.parse(answer.visible, { async: false }) as string)
    : '';
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
      <section class="ag-area-card" data-testid="lq-ai-agents-area-card">
        <div class="ag-area-card__head">
          <h2 class="lq-text-panel-h">Commercial</h2>
          <span class="ag-chip">preview</span>
        </div>
        <p class="lq-text-body-sm ag-area-card__copy">
          Contract questions against a demo clause library. One hardcoded practice area this
          preview; configurable areas land in F1.
        </p>

        <form class="ag-composer" data-testid="lq-ai-agents-composer" on:submit|preventDefault={submit}>
          <label class="lq-text-label" for="ag-prompt">Ask the Commercial agent</label>
          <textarea
            id="ag-prompt"
            rows="3"
            placeholder="e.g. What is the liability cap under this contract?"
            bind:value={prompt}
            disabled={submitting}
          ></textarea>
          <div class="ag-composer__actions">
            <button type="submit" class="ag-btn-primary" disabled={submitting || !prompt.trim()}>
              {submitting ? 'Starting…' : 'Run'}
            </button>
          </div>
          {#if submitError}
            <p class="lq-text-body-sm ag-error">Couldn't start the run: {submitError}</p>
          {/if}
        </form>
      </section>

      {#if run}
        <section class="ag-run" data-testid="lq-ai-agents-run">
          <header class="ag-run__head">
            <p class="lq-text-body ag-run__prompt">{run.prompt}</p>
            {#if badge}
              <span class="ag-badge ag-badge--{badge.tone}">{badge.label}</span>
            {/if}
          </header>

          {#if pollError}
            <p class="lq-text-body-sm ag-error">Lost contact with the run: {pollError}</p>
          {/if}
          {#if stale}
            <p class="lq-text-body-sm ag-note">
              This run never settled — it was likely interrupted by a backend restart. Start a new
              run.
            </p>
          {/if}

          {#if steps.length > 0}
            <ol class="ag-steps">
              {#each steps as step (step.id)}
                {@const d = stepDisplay(step)}
                <li class="ag-step ag-step--{step.kind}">
                  <span class="ag-step__title lq-text-label">{d.title}</span>
                  {#if d.thinking}
                    <details class="ag-thinking">
                      <summary class="lq-text-caption">Reasoning</summary>
                      <pre>{d.thinking}</pre>
                    </details>
                  {/if}
                  {#if d.body}
                    {#if d.mono}
                      <pre class="ag-step__mono">{d.body}</pre>
                    {:else}
                      <p class="lq-text-body-sm ag-step__body">{d.body}</p>
                    {/if}
                  {/if}
                </li>
              {/each}
            </ol>
          {:else if run.status === 'running' && !stale}
            <p class="lq-text-body-sm ag-note">Waiting for the first step…</p>
          {/if}

          {#if run.status === 'completed' && answerHtml}
            <div class="ag-answer" data-testid="lq-ai-agents-answer">
              {#if answer.thinking}
                <details class="ag-thinking">
                  <summary class="lq-text-caption">Reasoning</summary>
                  <pre>{answer.thinking}</pre>
                </details>
              {/if}
              <div class="prose prose-sm max-w-none">
                <!-- eslint-disable-next-line svelte/no-at-html-tags — sanitized above -->
                {@html answerHtml}
              </div>
            </div>
          {:else if run.status === 'cap_exceeded'}
            <p class="lq-text-body-sm ag-note">
              The run hit its step cap ({run.max_steps} steps) before finishing, so there is no
              final answer. The steps above show how far it got.
            </p>
          {:else if run.status === 'failed'}
            <p class="lq-text-body-sm ag-error">Run failed: {run.error ?? 'unknown error'}</p>
          {/if}
        </section>
      {/if}

      <section class="ag-previous">
        <h2 class="lq-text-panel-h">Previous runs</h2>
        {#if runsLoading}
          <p class="lq-text-body-sm ag-note">Loading runs…</p>
        {:else if runsError}
          <p class="lq-text-body-sm ag-error">Couldn't load runs: {runsError}</p>
        {:else if previousRuns.length === 0}
          <p class="lq-text-body-sm ag-note">No runs yet — ask the agent something above.</p>
        {:else}
          <ul class="ag-runs-list" data-testid="lq-ai-agents-runs-list">
            {#each previousRuns as r (r.id)}
              {@const b = statusBadge(r, nowMs)}
              <li>
                <button type="button" class="ag-runs-list__row" on:click={() => openRun(r)}>
                  <span class="ag-runs-list__prompt">{r.prompt}</span>
                  <span class="ag-badge ag-badge--{b.tone}">{b.label}</span>
                  <span class="lq-text-caption ag-runs-list__when">
                    {new Date(r.started_at).toLocaleString()}
                  </span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    </section>

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
            </span>
          </li>
        {/each}
      </ul>
    </aside>
  </div>
</main>

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

  .ag-area-card,
  .ag-run,
  .ag-rail {
    background: var(--lq-canvas);
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius-lg);
    padding: var(--lq-space-4);
  }

  .ag-area-card__head {
    display: flex;
    align-items: center;
    gap: var(--lq-space-2);
  }

  .ag-area-card__copy {
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

  .ag-composer {
    display: flex;
    flex-direction: column;
    gap: var(--lq-space-2);
  }

  .ag-composer textarea {
    width: 100%;
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius);
    padding: var(--lq-space-2) var(--lq-space-3);
    font: inherit;
    resize: vertical;
    background: var(--lq-inset);
  }

  .ag-composer textarea:focus-visible {
    outline: 2px solid var(--lq-accent);
    outline-offset: 1px;
  }

  .ag-composer__actions {
    display: flex;
    justify-content: flex-end;
  }

  .ag-btn-primary {
    background: var(--lq-accent);
    color: white;
    border: 0;
    border-radius: var(--lq-radius);
    padding: var(--lq-space-2) var(--lq-space-4);
    cursor: pointer;
    font-weight: 500;
    font-size: 14px;
    line-height: 1.5;
  }

  .ag-btn-primary:hover {
    filter: brightness(0.95);
  }

  .ag-btn-primary:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .ag-run {
    margin-top: var(--lq-space-4);
  }

  .ag-run__head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: var(--lq-space-3);
    margin-bottom: var(--lq-space-3);
  }

  .ag-run__prompt {
    font-weight: 500;
    overflow-wrap: anywhere;
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

  .ag-steps {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--lq-space-2);
  }

  .ag-step {
    border-left: 2px solid var(--lq-border);
    padding-left: var(--lq-space-3);
  }

  .ag-step--tool_call {
    border-left-color: var(--lq-accent-border);
  }

  .ag-step--tool_result {
    border-left-color: var(--lq-accent);
  }

  .ag-step__title {
    color: var(--lq-text-secondary);
    display: block;
  }

  .ag-step__body {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    margin-top: var(--lq-space-1);
  }

  .ag-step__mono,
  .ag-thinking pre {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
    background: var(--lq-inset);
    border-radius: var(--lq-radius-sm);
    padding: var(--lq-space-2);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    margin: var(--lq-space-1) 0 0;
  }

  .ag-thinking summary {
    cursor: pointer;
    color: var(--lq-text-tertiary);
  }

  .ag-answer {
    margin-top: var(--lq-space-4);
    border-top: 1px solid var(--lq-border);
    padding-top: var(--lq-space-3);
  }

  .ag-previous {
    margin-top: var(--lq-space-6);
  }

  .ag-runs-list {
    list-style: none;
    margin: var(--lq-space-2) 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--lq-space-1);
  }

  .ag-runs-list__row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    gap: var(--lq-space-3);
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
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
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
