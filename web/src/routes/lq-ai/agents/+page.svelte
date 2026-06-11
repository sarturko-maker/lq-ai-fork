<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import DOMPurify from 'dompurify';
  import { marked } from 'marked';
  import { agentsApi, filesApi, projectsApi } from '$lib/lq-ai/api';
  import { LQAIApiError } from '$lib/lq-ai/api/client';
  import type {
    AgentRun,
    AgentRunStep,
    AgentThread,
    AgentThreadDetailResponse
  } from '$lib/lq-ai/api/agents';
  import type { FileMeta, Project } from '$lib/lq-ai/types';
  import {
    MAX_POLL_FAILURES,
    POLL_INTERVAL_MS,
    composerEnabled,
    isStaleRunning,
    latestRunOf,
    railItems,
    railStates,
    shouldContinuePollingThread,
    splitThink,
    statusBadge,
    stepDisplay,
    threadRailSteps,
    uploadsSettled,
    visibleSteps
  } from './page-helpers';

  // Model output is untrusted input (CLAUDE.md): forbid media so a poisoned
  // answer can't beacon data out via auto-fetched remote resources.
  const SANITIZE_OPTS = {
    FORBID_TAGS: ['img', 'picture', 'audio', 'video', 'source', 'track'],
    FORBID_ATTR: ['srcset', 'ping']
  };

  let prompt = '';
  let submitting = false;
  let submitError: string | null = null;

  // F0-S4: bind the conversation to a Matter so the agent gets the
  // matter's document tools. '' = blank workspace. Fixed at thread
  // creation — follow-ups inherit the thread's binding (ADR-F008).
  let matters: Project[] = [];
  let selectedMatterId = '';
  let mattersError: string | null = null;

  async function loadMatters() {
    try {
      matters = await projectsApi.listProjects(); // active, non-sandbox
      mattersError = null;
    } catch (e) {
      mattersError = e instanceof Error ? e.message : 'Failed to load matters';
    }
  }

  // Honest fallback: a conversation can be bound to a matter that is no
  // longer in the active dropdown list (archived since, or the sandbox) —
  // say so rather than dressing the placeholder up as a name (F0-S4 review).
  function matterName(projectId: string | null): string | null {
    if (!projectId) return null;
    return matters.find((m) => m.id === projectId)?.name ?? 'Matter (not in your active list)';
  }

  // ---------------------------------------------------------------------
  // Conversation (thread) state + polling — F0-S5 (ADR-F008)
  // ---------------------------------------------------------------------

  let detail: AgentThreadDetailResponse | null = null;
  let currentThreadId: string | null = null;
  let pollError: string | null = null;
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  // Bumped on every start/stop; a settling response from an older generation
  // is discarded, so stale snapshots can never overwrite a settled thread.
  let pollGeneration = 0;
  let pollFailures = 0;
  let nowMs = Date.now();
  let nowTimer: ReturnType<typeof setInterval> | null = null;

  let threads: AgentThread[] = [];
  let threadsLoading = true;
  let threadsError: string | null = null;

  async function loadThreads() {
    threadsLoading = true;
    try {
      const page = await agentsApi.listThreads({ limit: 20 });
      threads = page.threads;
      threadsError = null;
      nowMs = Date.now();
    } catch (e) {
      threadsError = e instanceof Error ? e.message : 'Failed to load conversations';
    } finally {
      threadsLoading = false;
    }
  }

  onMount(() => {
    loadThreads();
    loadMatters();
    // Keep idle badges honest: a 'running' row must visually flip to Stale
    // even when nothing is being polled.
    nowTimer = setInterval(() => {
      nowMs = Date.now();
    }, 30_000);
  });

  function stopPolling() {
    pollGeneration += 1;
    if (pollTimer !== null) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  onDestroy(() => {
    stopPolling();
    stopUploadPolling();
    if (nowTimer !== null) clearInterval(nowTimer);
  });

  function schedulePoll(id: string, gen: number) {
    pollTimer = setTimeout(() => {
      void poll(id, gen);
    }, POLL_INTERVAL_MS);
  }

  // Self-rescheduling: the next request is only issued after the previous
  // one settles, so responses can never arrive out of order or pile up.
  async function poll(id: string, gen: number) {
    try {
      const next = await agentsApi.getThread(id);
      if (gen !== pollGeneration) return; // superseded: thread switched or page left
      detail = next;
      pollFailures = 0;
      pollError = null;
      nowMs = Date.now();
      if (shouldContinuePollingThread(next, nowMs)) {
        schedulePoll(id, gen);
      } else {
        pollTimer = null;
        loadThreads();
      }
    } catch (e) {
      if (gen !== pollGeneration) return;
      pollFailures += 1;
      if (pollFailures < MAX_POLL_FAILURES) {
        schedulePoll(id, gen); // tolerate transient blips; the run is still live server-side
      } else {
        pollTimer = null;
        pollError = e instanceof Error ? e.message : 'Failed to poll the conversation';
      }
    }
  }

  function startPolling(id: string) {
    stopPolling();
    const gen = pollGeneration;
    currentThreadId = id;
    pollFailures = 0;
    pollError = null;
    void poll(id, gen);
  }

  function retryPolling() {
    if (currentThreadId) startPolling(currentThreadId);
  }

  function openThread(t: AgentThread) {
    detail = null;
    uploads = [];
    uploadError = null;
    startPolling(t.id);
  }

  function newChat() {
    stopPolling();
    detail = null;
    currentThreadId = null;
    pollError = null;
    uploads = [];
    uploadError = null;
    prompt = '';
  }

  async function submit() {
    const text = prompt.trim();
    if (!text || submitting) return;
    submitting = true;
    submitError = null;
    try {
      const created = await agentsApi.createRun(
        detail
          ? { prompt: text, thread_id: detail.thread.id }
          : { prompt: text, project_id: selectedMatterId || undefined }
      );
      prompt = '';
      startPolling(created.thread_id);
    } catch (e) {
      submitError =
        e instanceof LQAIApiError && e.status === 429
          ? 'You already have runs in flight — wait for one to finish.'
          : e instanceof LQAIApiError && e.status === 409
            ? 'This conversation is busy or can no longer continue — try again or start a new chat.'
            : e instanceof Error
              ? e.message
              : 'Failed to start the run';
    } finally {
      submitting = false;
    }
  }

  // ---------------------------------------------------------------------
  // Composer file upload — F0-S5 (promoted from Backlog; ADR-F007 path)
  // ---------------------------------------------------------------------

  let uploads: FileMeta[] = [];
  let uploading = false;
  let uploadError: string | null = null;
  let uploadPollTimer: ReturnType<typeof setTimeout> | null = null;
  let uploadPollGeneration = 0;
  let fileInput: HTMLInputElement | null = null;
  let dragOver = false;

  function stopUploadPolling() {
    uploadPollGeneration += 1;
    if (uploadPollTimer !== null) {
      clearTimeout(uploadPollTimer);
      uploadPollTimer = null;
    }
  }

  // Poll unsettled uploads (pending/processing → ready/failed) so the user
  // knows when the agent can actually ground on the document. Settled rows
  // only, same render-deterministic posture as the thread poll.
  async function pollUploads(gen: number) {
    try {
      const refreshed = await Promise.all(
        uploads.map((f) =>
          f.ingestion_status === 'ready' || f.ingestion_status === 'failed'
            ? Promise.resolve(f)
            : filesApi.getFile(f.id)
        )
      );
      if (gen !== uploadPollGeneration) return;
      uploads = refreshed;
    } catch {
      // Transient: keep the last snapshot and try again on the next tick.
    }
    if (gen !== uploadPollGeneration) return;
    if (!uploadsSettled(uploads)) {
      uploadPollTimer = setTimeout(() => {
        void pollUploads(gen);
      }, POLL_INTERVAL_MS);
    } else {
      uploadPollTimer = null;
    }
  }

  function startUploadPolling() {
    stopUploadPolling();
    const gen = uploadPollGeneration;
    if (!uploadsSettled(uploads)) {
      uploadPollTimer = setTimeout(() => {
        void pollUploads(gen);
      }, POLL_INTERVAL_MS);
    }
  }

  async function uploadOne(file: File) {
    if (!bindingProjectId) return; // an unbound upload has no home (ADR-F002)
    uploading = true;
    uploadError = null;
    try {
      // ADR-F007 upload-time membership: POST /files with the matter's
      // project_id makes the document visible to search_documents /
      // read_document with no extra wiring.
      const uploaded = await filesApi.uploadFile(file, { project_id: bindingProjectId });
      uploads = [...uploads, uploaded];
      startUploadPolling();
    } catch (e) {
      uploadError = e instanceof Error ? e.message : `Upload failed: ${file.name}`;
    } finally {
      uploading = false;
    }
  }

  async function handlePicked(event: Event) {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = '';
    for (const f of files) await uploadOne(f);
  }

  function handleDragOver(event: DragEvent) {
    if (!bindingProjectId) return;
    event.preventDefault();
    dragOver = true;
  }

  function handleDragLeave() {
    dragOver = false;
  }

  async function handleDrop(event: DragEvent) {
    dragOver = false;
    if (!bindingProjectId) return;
    event.preventDefault();
    const files = Array.from(event.dataTransfer?.files ?? []);
    for (const f of files) await uploadOne(f);
  }

  function uploadStatusLabel(f: FileMeta): string {
    switch (f.ingestion_status) {
      case 'ready':
        return 'ready';
      case 'failed':
        return 'failed';
      case 'processing':
        return 'processing…';
      default:
        return 'pending…';
    }
  }

  // ---------------------------------------------------------------------
  // Derived view state
  // ---------------------------------------------------------------------

  function answerHtmlFor(run: AgentRun): string {
    const visible = splitThink(run.final_answer).visible;
    if (!visible) return '';
    return DOMPurify.sanitize(marked.parse(visible, { async: false }) as string, SANITIZE_OPTS);
  }

  $: latestRun = latestRunOf(detail);
  $: badge = latestRun ? statusBadge(latestRun, nowMs) : null;
  $: stale = latestRun ? isStaleRunning(latestRun, nowMs) : false;
  // A stale run's dangling tool calls must not pulse forever — render settled.
  $: railSteps = threadRailSteps(detail);
  $: rail = railStates(railSteps, stale ? 'failed' : (latestRun?.status ?? null));
  // The rail is the honest model-visible universe: matter tools appear
  // only when the open conversation is matter-bound (or, pre-chat, when
  // a matter is selected in the composer).
  $: matterBound = detail ? detail.thread.project_id !== null : selectedMatterId !== '';
  $: tools = railItems(railSteps, matterBound);
  // The Matter the composer would upload into: the open conversation's
  // binding, or the selected matter for a new chat. null = no home → no
  // attach (ADR-F002).
  $: bindingProjectId = detail ? detail.thread.project_id : selectedMatterId || null;
  $: canSend = composerEnabled(detail, nowMs);
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
          {#if detail}
            <button
              type="button"
              class="ag-btn-ghost ag-area-card__new"
              data-testid="lq-ai-agents-new-chat"
              on:click={newChat}
            >
              New chat
            </button>
          {/if}
        </div>
        <p class="lq-text-body-sm ag-area-card__copy">
          Bind a matter to ground answers in its documents — the agent searches and reads them
          itself, and follow-ups continue the same conversation. One hardcoded practice area this
          preview; configurable areas land in F1.
        </p>

        <form class="ag-composer" data-testid="lq-ai-agents-composer" on:submit|preventDefault={submit}>
          {#if detail}
            <p class="lq-text-body-sm ag-thread-head">
              {#if matterName(detail.thread.project_id)}
                <span
                  class="ag-chip"
                  data-testid="lq-ai-agents-run-matter"
                  title={detail.thread.project_id}
                >
                  {matterName(detail.thread.project_id)}
                </span>
              {/if}
              <span class="ag-thread-head__title">{detail.thread.title}</span>
            </p>
          {:else}
            <div class="ag-matter">
              <label class="lq-text-label" for="ag-matter">Matter</label>
              <select
                id="ag-matter"
                data-testid="lq-ai-agents-matter-select"
                bind:value={selectedMatterId}
                disabled={submitting}
              >
                <option value="">No matter — blank workspace</option>
                {#each matters as m (m.id)}
                  <option value={m.id}>{m.name}</option>
                {/each}
              </select>
              {#if mattersError}
                <p class="lq-text-caption ag-error">Couldn't load matters: {mattersError}</p>
              {/if}
            </div>
          {/if}

          <label class="lq-text-label" for="ag-prompt">
            {detail ? 'Continue the conversation' : 'Ask the Commercial agent'}
          </label>
          <div
            class="ag-dropzone"
            class:ag-dropzone--over={dragOver}
            role="region"
            aria-label="Message and file drop area"
            on:dragover={handleDragOver}
            on:dragleave={handleDragLeave}
            on:drop={handleDrop}
          >
            <textarea
              id="ag-prompt"
              rows="3"
              placeholder={detail
                ? 'e.g. And what about the indemnity?'
                : 'e.g. What is the liability cap under this contract?'}
              bind:value={prompt}
              disabled={submitting || !canSend}
            ></textarea>
            {#if dragOver}
              <div class="ag-dropzone__hint lq-text-body-sm">Drop to upload into the matter</div>
            {/if}
          </div>

          {#if uploads.length > 0 || uploadError}
            <ul class="ag-uploads" data-testid="lq-ai-agents-uploads">
              {#each uploads as f (f.id)}
                <li
                  class="ag-upload ag-upload--{f.ingestion_status ?? 'pending'}"
                  data-testid="lq-ai-agents-upload-chip"
                  title={f.ingestion_error ?? f.filename}
                >
                  <span class="ag-upload__name">{f.filename}</span>
                  <span class="ag-upload__status lq-text-caption">{uploadStatusLabel(f)}</span>
                </li>
              {/each}
              {#if uploadError}
                <li class="lq-text-caption ag-error">{uploadError}</li>
              {/if}
            </ul>
          {/if}

          <div class="ag-composer__actions">
            <input
              bind:this={fileInput}
              type="file"
              class="ag-hidden-input"
              multiple
              on:change={handlePicked}
              data-testid="lq-ai-agents-file-input"
            />
            <button
              type="button"
              class="ag-btn-ghost"
              data-testid="lq-ai-agents-attach-btn"
              disabled={!bindingProjectId || uploading || submitting}
              title={bindingProjectId
                ? 'Upload documents into the matter — the agent can search them once ready'
                : 'Select a Matter first — an upload needs a home'}
              on:click={() => fileInput?.click()}
            >
              {uploading ? 'Uploading…' : '+ Attach'}
            </button>
            <button
              type="submit"
              class="ag-btn-primary"
              disabled={submitting || !canSend || !prompt.trim()}
            >
              {submitting ? 'Starting…' : detail ? 'Send' : 'Run'}
            </button>
          </div>
          {#if detail && !detail.continuable && !shouldContinuePollingThread(detail, nowMs)}
            <p class="lq-text-body-sm ag-note" data-testid="lq-ai-agents-not-continuable">
              This conversation can't take a follow-up{latestRun && latestRun.status !== 'completed'
                ? ` (last run ${latestRun.status === 'cap_exceeded' ? 'hit its step cap' : latestRun.status})`
                : ''} — start a new chat.
            </p>
          {/if}
          {#if submitError}
            <p class="lq-text-body-sm ag-error">Couldn't start the run: {submitError}</p>
          {/if}
        </form>
      </section>

      {#if detail}
        <section class="ag-thread" data-testid="lq-ai-agents-thread">
          {#if pollError}
            <p class="lq-text-body-sm ag-error">
              Lost contact with the conversation: {pollError}
              <button type="button" class="ag-btn-ghost" on:click={retryPolling}>Retry</button>
            </p>
          {/if}
          {#if stale}
            <p class="lq-text-body-sm ag-note">
              The last run never settled — it was likely interrupted by a backend restart. Start a
              new chat.
            </p>
          {/if}

          {#each detail.runs as turn, i (turn.run.id)}
            {@const turnSteps = visibleSteps(turn.steps, turn.run)}
            {@const turnAnswer = splitThink(turn.run.final_answer)}
            {@const turnHtml = answerHtmlFor(turn.run)}
            <section class="ag-run" data-testid="lq-ai-agents-run">
              <header class="ag-run__head">
                <p class="lq-text-body ag-run__prompt">{turn.run.prompt}</p>
                {#if i === detail.runs.length - 1 && badge}
                  <span class="ag-badge ag-badge--{badge.tone}" role="status" aria-live="polite">
                    {badge.label}
                  </span>
                {/if}
              </header>

              {#if turnSteps.length > 0}
                <ol class="ag-steps">
                  {#each turnSteps as step (step.id)}
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
              {:else if turn.run.status === 'running' && !stale}
                <p class="lq-text-body-sm ag-note">Waiting for the first step…</p>
              {/if}

              {#if turn.run.status === 'completed'}
                {#if turnHtml || turnAnswer.thinking}
                  <div class="ag-answer" data-testid="lq-ai-agents-answer">
                    {#if turnAnswer.thinking}
                      <details class="ag-thinking">
                        <summary class="lq-text-caption">Reasoning</summary>
                        <pre>{turnAnswer.thinking}</pre>
                      </details>
                    {/if}
                    {#if turnHtml}
                      <div class="prose prose-sm max-w-none">
                        <!-- eslint-disable-next-line svelte/no-at-html-tags — sanitized above -->
                        {@html turnHtml}
                      </div>
                    {:else}
                      <p class="lq-text-body-sm ag-note">
                        The model returned only reasoning — no final answer text.
                      </p>
                    {/if}
                  </div>
                {:else}
                  <p class="lq-text-body-sm ag-note">The run completed without a final answer.</p>
                {/if}
              {:else if turn.run.status === 'cap_exceeded'}
                <p class="lq-text-body-sm ag-note">
                  The run hit its step cap ({turn.run.max_steps} steps) before finishing, so there
                  is no final answer. The steps above show how far it got.
                </p>
              {:else if turn.run.status === 'failed'}
                <p class="lq-text-body-sm ag-error">
                  Run failed: {turn.run.error ?? 'unknown error'}
                </p>
              {/if}
            </section>
          {/each}
        </section>
      {/if}

      <section class="ag-previous">
        <h2 class="lq-text-panel-h">Conversations</h2>
        {#if threadsLoading}
          <p class="lq-text-body-sm ag-note">Loading conversations…</p>
        {:else if threadsError}
          <p class="lq-text-body-sm ag-error">Couldn't load conversations: {threadsError}</p>
        {:else if threads.length === 0}
          <p class="lq-text-body-sm ag-note">No conversations yet — ask the agent something above.</p>
        {:else}
          <ul class="ag-runs-list" data-testid="lq-ai-agents-runs-list">
            {#each threads as t (t.id)}
              <li>
                <button type="button" class="ag-runs-list__row" on:click={() => openThread(t)}>
                  <span class="ag-runs-list__prompt">
                    {#if t.project_id}
                      <span class="ag-chip">{matterName(t.project_id)}</span>
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
  .ag-thread,
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

  .ag-area-card__new {
    margin-left: auto;
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

  .ag-thread-head {
    display: flex;
    align-items: center;
    gap: var(--lq-space-2);
    min-width: 0;
  }

  .ag-thread-head__title {
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .ag-dropzone {
    position: relative;
  }

  .ag-dropzone--over textarea {
    border-color: var(--lq-accent);
  }

  .ag-dropzone__hint {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--lq-accent-soft);
    border: 1px dashed var(--lq-accent);
    border-radius: var(--lq-radius);
    color: var(--lq-accent);
    pointer-events: none;
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

  .ag-matter {
    display: flex;
    flex-direction: column;
    gap: var(--lq-space-1);
  }

  .ag-matter select {
    width: 100%;
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius);
    padding: var(--lq-space-1) var(--lq-space-2);
    font: inherit;
    background: var(--lq-inset);
  }

  .ag-matter select:focus-visible {
    outline: 2px solid var(--lq-accent);
    outline-offset: 1px;
  }

  .ag-uploads {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: var(--lq-space-1);
  }

  .ag-upload {
    display: inline-flex;
    align-items: center;
    gap: var(--lq-space-1);
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius-pill);
    padding: 0 var(--lq-space-2);
    font-size: 12px;
    line-height: 20px;
    max-width: 100%;
  }

  .ag-upload__name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 220px;
  }

  .ag-upload--ready {
    border-color: var(--lq-accent-border);
    background: var(--lq-accent-soft);
  }

  .ag-upload--ready .ag-upload__status {
    color: var(--lq-accent);
  }

  .ag-upload--failed {
    border-color: var(--lq-error-border);
    background: var(--lq-error-soft);
  }

  .ag-upload--failed .ag-upload__status {
    color: var(--lq-error);
  }

  .ag-upload__status {
    color: var(--lq-text-tertiary);
  }

  .ag-hidden-input {
    display: none;
  }

  .ag-composer__actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--lq-space-2);
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

  .ag-thread {
    margin-top: var(--lq-space-4);
    display: flex;
    flex-direction: column;
    gap: var(--lq-space-4);
  }

  .ag-run + .ag-run {
    border-top: 1px solid var(--lq-border);
    padding-top: var(--lq-space-3);
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

  .ag-btn-ghost:disabled {
    opacity: 0.5;
    cursor: default;
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
