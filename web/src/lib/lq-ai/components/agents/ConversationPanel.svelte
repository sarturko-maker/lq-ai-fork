<script lang="ts">
  /**
   * The agents conversation surface — extracted from the agents route in
   * F0-S7 so the F1 cockpit re-homes it without re-touching the stream
   * wiring. Layout-agnostic: the host page provides the area header via
   * the `head`/`copy` slots and owns everything around it (conversation
   * list, capability rail); this component owns the composer, the
   * turn/step timeline, uploads, polling, and the SSE v2 stream.
   *
   * Thread switching is by REMOUNT: the host wraps the component in
   * `{#key …}` and passes `initialThreadId` — internal state can then
   * never leak across conversations (the F0-S5 chip-resurrection class
   * of bug is structurally gone).
   *
   * Live data flow (ADR-F004 — settled rows decide, streams animate):
   * polling is the contract; when a poll shows the newest run working,
   * the component hands off to `GET /agents/runs/{id}/stream` (AI SDK
   * UI Message Stream v1). `data-step` parts upsert the SAME detail
   * structure the poller fills; reasoning deltas feed only the
   * collapsed-by-default thinking ribbon; any stream failure falls
   * back to the poll loop; stream end triggers ONE reconcile fetch.
   */
  import { createEventDispatcher, onDestroy, onMount, tick } from 'svelte';
  import DOMPurify from 'dompurify';
  import { marked } from 'marked';
  import { agentsApi, filesApi } from '$lib/lq-ai/api';
  import { LQAIApiError } from '$lib/lq-ai/api/client';
  import type {
    AgentRun,
    AgentRunStep,
    AgentThreadDetailResponse
  } from '$lib/lq-ai/api/agents';
  import type { FileMeta, Project } from '$lib/lq-ai/types';
  import {
    MAX_POLL_FAILURES,
    POLL_INTERVAL_MS,
    composerEnabled,
    isStaleRunning,
    latestRunOf,
    matterName,
    shouldContinuePollingThread,
    splitThink,
    statusBadge,
    stepDigest,
    stepDisplay,
    threadRailStates,
    threadRailSteps,
    uploadsSettled,
    visibleSteps,
    type RailState
  } from '$lib/lq-ai/agents/helpers';
  import {
    applyAnswerText,
    applyRunPart,
    applyStepPart,
    parseRunPayload,
    parseStepPayload
  } from '$lib/lq-ai/agents/run-stream';
  import { serverNowMs } from '$lib/lq-ai/agents/server-clock';
  import {
    consumeUIMessageStream,
    type UIMessagePart
  } from '$lib/lq-ai/sse/ui-message-stream';

  /** Conversation to open at mount; null = fresh composer. Remount to switch. */
  export let initialThreadId: string | null = null;
  export let matters: Project[] = [];
  export let mattersError: string | null = null;
  /**
   * Composer draft + matter selection are PROPS (two-way bound by the
   * host) so they survive the {#key} remounts that switch threads —
   * the pre-S7 single-instance page never reset them on New chat /
   * open-thread, and neither must the remount design (S7 review).
   */
  export let prompt = '';
  export let selectedMatterId = '';

  // Bound OUT to the host (read-only there): the capability rail lives
  // in page chrome but derives from this conversation's settled steps.
  export let railSteps: AgentRunStep[] = [];
  export let rail: Record<string, RailState> = {};
  export let matterBound = false;
  export let hasConversation = false;

  // `newmatter`: the user asked to create a matter from the composer —
  // the HOST owns the modal (page chrome) and writes the created id back
  // through the bound `selectedMatterId` (F0-S8).
  const dispatch = createEventDispatcher<{ settled: void; newmatter: void }>();

  // Model output is untrusted input (CLAUDE.md): forbid media so a poisoned
  // answer can't beacon data out via auto-fetched remote resources — incl.
  // the SVG image elements DOMPurify's defaults allow (F0-S5 review:
  // <svg><image href>) auto-fetches exactly like <img src>).
  const SANITIZE_OPTS = {
    FORBID_TAGS: ['img', 'picture', 'audio', 'video', 'source', 'track', 'svg', 'image', 'use'],
    FORBID_ATTR: ['srcset', 'ping']
  };

  let submitting = false;
  let submitError: string | null = null;

  // F0-S4: selectedMatterId (prop above) binds the conversation to a
  // Matter so the agent gets the matter's document tools. '' = blank
  // workspace. Fixed at thread creation — follow-ups inherit the
  // thread's binding (ADR-F008).

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
  // Server-derived "now" (F0-S7): staleness cutoffs survive client clock
  // skew — every API response's Date header feeds serverNowMs().
  let nowMs = serverNowMs();
  let nowTimer: ReturnType<typeof setInterval> | null = null;

  // Set at teardown; post-await continuations (submit's startPolling,
  // uploadBatch's poller re-arm) must check it. The per-instance
  // generation counters CANNOT protect them: startPolling re-baselines
  // the very counter the guards compare against, so a continuation
  // resolving after destroy would otherwise re-arm timers — and open an
  // orphan stream — in a dead instance. Remount-based thread switching
  // makes destroy-mid-await an ordinary click, not an edge case (S7
  // review).
  let destroyed = false;

  // ---------------------------------------------------------------------
  // Bottom-docked composer auto-scroll (F0-S8). The conversation reads
  // top-down with the composer docked below it, so new content lands out
  // of view: pin the viewport to the CONVERSATION'S tail while the user
  // is already near it (force on the first snapshot — opening a thread
  // should show its latest turn). Never fight a user who scrolled up.
  //
  // The target is the thread-end anchor offset by the composer's height,
  // NOT the document bottom: the page's side column (rail + conversation
  // list) is usually taller than the conversation, and scrolling to the
  // document bottom would push the whole conversation off-screen.
  // ---------------------------------------------------------------------

  /** True until the first thread snapshot of this mount has rendered. */
  let firstSnapshot = true;
  /** In-flow marker between the thread and the docked composer. */
  let threadEndEl: HTMLDivElement | null = null;
  let composerEl: HTMLFormElement | null = null;

  /**
   * The element that actually scrolls this panel. NOT the document: the
   * LQ.AI shell pins `html { overflow-y: hidden }` and scrolls its
   * `<main id="lq-main">` — resolved generically (nearest scrollable
   * ancestor) so the F1 cockpit can re-home the panel into any layout.
   */
  function scrollContainer(): HTMLElement | null {
    let el: HTMLElement | null = threadEndEl?.parentElement ?? null;
    while (el) {
      if (/(auto|scroll)/.test(getComputedStyle(el).overflowY)) return el;
      el = el.parentElement;
    }
    return document.scrollingElement as HTMLElement | null;
  }

  /** Container scrollTop that puts the thread's tail just above the composer. */
  function tailScrollTop(container: HTMLElement): number | null {
    if (!threadEndEl) return null;
    const composerH = composerEl?.offsetHeight ?? 0;
    // Rects are viewport-relative: for the root scroller the viewport IS
    // the content origin minus scrollTop; for an inner container its own
    // rect.top is the origin.
    const anchorBottom =
      container === document.scrollingElement
        ? threadEndEl.getBoundingClientRect().bottom + container.scrollTop
        : threadEndEl.getBoundingClientRect().bottom -
          container.getBoundingClientRect().top +
          container.scrollTop;
    return Math.max(0, anchorBottom - container.clientHeight + composerH + 16);
  }

  async function autoScroll(force = false) {
    if (destroyed || !threadEndEl) return;
    const container = scrollContainer();
    if (!container) return;
    const before = tailScrollTop(container); // pre-render tail: were we reading it?
    if (before === null) return;
    if (!force && container.scrollTop < before - 240) return;
    await tick(); // let the new content render before measuring the target
    if (destroyed) return;
    const target = tailScrollTop(container);
    if (target !== null) container.scrollTop = target;
  }

  onMount(() => {
    if (initialThreadId) startPolling(initialThreadId);
    // Keep idle badges honest: a 'running' row must visually flip to Stale
    // even when nothing is being polled.
    nowTimer = setInterval(() => {
      nowMs = serverNowMs();
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
    destroyed = true;
    stopPolling();
    stopUploadPolling();
    stopStream();
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
      nowMs = serverNowMs();
      void autoScroll(firstSnapshot);
      firstSnapshot = false;
      if (shouldContinuePollingThread(next, nowMs)) {
        const latest = latestRunOf(next);
        if (latest && tryStartStream(latest.id, id, gen)) {
          // The stream replaces the poll loop until it ends or fails.
          pollTimer = null;
        } else {
          schedulePoll(id, gen);
        }
      } else {
        pollTimer = null;
        dispatch('settled');
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
    if (destroyed) return;
    stopPolling();
    stopStream();
    const gen = pollGeneration;
    currentThreadId = id;
    pollFailures = 0;
    pollError = null;
    void poll(id, gen);
  }

  function retryPolling() {
    if (currentThreadId) startPolling(currentThreadId);
  }

  async function submit() {
    const text = prompt.trim();
    if (!text || submitting) return;
    // ADR-F002: free-floating chat is not offered — a new conversation
    // needs a matter for its memory to accumulate into. The Run button
    // is disabled in this state; this guard keeps Enter-to-submit honest.
    if (!detail && !selectedMatterId) {
      submitError = 'Select a matter first — conversations live inside a matter.';
      return;
    }
    submitting = true;
    submitError = null;
    try {
      const created = await agentsApi.createRun(
        detail
          ? { prompt: text, thread_id: detail.thread.id }
          : { prompt: text, project_id: selectedMatterId }
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
      if (e instanceof LQAIApiError && e.status === 409 && detail) {
        // The server refused on fresher state than our snapshot — re-sync
        // so the composer greys out honestly instead of inviting retries.
        startPolling(detail.thread.id);
      }
    } finally {
      submitting = false;
    }
  }

  // ---------------------------------------------------------------------
  // SSE v2 — F0-S7 (ADR-F006 wire spec; ADR-F004 render-determinism)
  // ---------------------------------------------------------------------

  let streamRunId: string | null = null;
  let streamAbort: AbortController | null = null;
  /** Live thinking-ribbon text — animation only, cleared as rows settle. */
  let liveReasoning = '';
  let liveReasoningBlock: string | null = null;
  let answerBuffers: Record<string, string> = {};

  function clearStreamState() {
    streamAbort = null;
    streamRunId = null;
    liveReasoning = '';
    liveReasoningBlock = null;
    answerBuffers = {};
  }

  function stopStream() {
    streamAbort?.abort();
    clearStreamState();
  }

  /** Open the run's stream once; true = streaming (caller stops polling). */
  function tryStartStream(runId: string, threadId: string, gen: number): boolean {
    if (destroyed) return false;
    if (streamRunId === runId) return true;
    stopStream();
    streamRunId = runId;
    const abort = new AbortController();
    streamAbort = abort;
    void runStream(runId, threadId, gen, abort);
    return true;
  }

  async function runStream(
    runId: string,
    threadId: string,
    gen: number,
    abort: AbortController
  ) {
    try {
      const response = await agentsApi.streamRun(runId, abort.signal);
      if (!response.body) throw new Error('stream response had no body');
      await consumeUIMessageStream(response.body, {
        onPart: (part) => {
          if (gen !== pollGeneration) return; // superseded mid-stream
          handleStreamPart(runId, part);
        }
      });
    } catch (e) {
      if (abort.signal.aborted || gen !== pollGeneration) return;
      // Transport failure: the stream is animation — fall back to the
      // poll loop, which remains the contract (ADR-F004).
      clearStreamState();
      schedulePoll(threadId, gen);
      return;
    }
    if (gen !== pollGeneration) return;
    clearStreamState();
    // Clean end ([DONE]/EOF): reconcile once on the settled truth — full
    // final answer, fresh `continuable`, statuses the stream may have
    // missed — then tell the host a run settled.
    try {
      const next = await agentsApi.getThread(threadId);
      if (gen !== pollGeneration) return;
      detail = next;
      nowMs = serverNowMs();
      if (shouldContinuePollingThread(next, nowMs)) {
        schedulePoll(threadId, gen); // stream cut early; the run is still live
      } else {
        dispatch('settled');
      }
    } catch {
      if (gen === pollGeneration) schedulePoll(threadId, gen);
    }
  }

  function handleStreamPart(runId: string, part: UIMessagePart) {
    switch (part.type) {
      case 'reasoning-delta': {
        const blockId = typeof part.id === 'string' ? part.id : '';
        const delta = typeof part.delta === 'string' ? part.delta : '';
        if (!delta) return;
        if (liveReasoningBlock !== blockId && liveReasoning) liveReasoning += '\n\n';
        liveReasoningBlock = blockId;
        liveReasoning += delta;
        void autoScroll();
        return;
      }
      case 'data-step': {
        const payload = parseStepPayload(part.data);
        if (!payload || !detail) return;
        detail = applyStepPart(detail, payload);
        if (payload.kind === 'model_turn') {
          // The settled row now carries this turn's content — the ribbon
          // hands over to the timeline (settled rows decide).
          liveReasoning = '';
          liveReasoningBlock = null;
        }
        void autoScroll();
        return;
      }
      case 'text-delta': {
        const blockId = typeof part.id === 'string' ? part.id : '';
        const delta = typeof part.delta === 'string' ? part.delta : '';
        if (blockId && delta) answerBuffers[blockId] = (answerBuffers[blockId] ?? '') + delta;
        return;
      }
      case 'text-end': {
        const blockId = typeof part.id === 'string' ? part.id : '';
        const text = blockId ? answerBuffers[blockId] : undefined;
        if (text && detail) detail = applyAnswerText(detail, runId, text);
        if (blockId) delete answerBuffers[blockId];
        void autoScroll();
        return;
      }
      case 'data-run': {
        const payload = parseRunPayload(part.data);
        if (!payload || !detail) return;
        detail = applyRunPart(detail, runId, payload);
        liveReasoning = '';
        liveReasoningBlock = null;
        return;
      }
      default:
        // tool-* / start-step / data-plan parts: the rail and timeline
        // derive from the settled data-step mirrors; nothing else to do.
        return;
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
  let uploadPollFailures = 0;
  let fileInput: HTMLInputElement | null = null;
  let dragOver = false;

  // Ingestion can legitimately ride out a backend blip (the dev stack's
  // crash-recovery windows run ~10-20s) — tolerate more consecutive poll
  // failures than the thread poller before giving up honestly.
  const UPLOAD_MAX_POLL_FAILURES = 10;

  function stopUploadPolling() {
    uploadPollGeneration += 1;
    if (uploadPollTimer !== null) {
      clearTimeout(uploadPollTimer);
      uploadPollTimer = null;
    }
  }

  // Poll unsettled uploads (pending/processing → ready/failed) so the user
  // knows when the agent can actually ground on the document. Settled rows
  // only, same render-deterministic posture as the thread poll. Per-file
  // failures keep the last snapshot (never lose a chip); consecutive
  // all-failure rounds are capped so a dead backend can't fake 'pending…'
  // forever (F0-S5 review).
  async function pollUploads(gen: number) {
    let anyFailure = false;
    const refreshed = await Promise.all(
      uploads.map((f) =>
        f.ingestion_status === 'ready' || f.ingestion_status === 'failed'
          ? Promise.resolve(f)
          : filesApi.getFile(f.id).catch(() => {
              anyFailure = true;
              return f;
            })
      )
    );
    if (gen !== uploadPollGeneration) return;
    uploads = refreshed;
    uploadPollFailures = anyFailure ? uploadPollFailures + 1 : 0;
    if (uploadPollFailures >= UPLOAD_MAX_POLL_FAILURES) {
      uploadPollTimer = null;
      uploadError = 'Lost contact while checking ingestion — the statuses shown may be stale.';
      return;
    }
    if (!uploadsSettled(uploads)) {
      uploadPollTimer = setTimeout(() => {
        void pollUploads(gen);
      }, POLL_INTERVAL_MS);
    } else {
      uploadPollTimer = null;
    }
  }

  function startUploadPolling() {
    if (destroyed) return;
    stopUploadPolling();
    uploadPollFailures = 0;
    const gen = uploadPollGeneration;
    if (!uploadsSettled(uploads)) {
      uploadPollTimer = setTimeout(() => {
        void pollUploads(gen);
      }, POLL_INTERVAL_MS);
    }
  }

  // The whole batch files into the project captured at batch START — the
  // user switching the Matter select mid-batch must not split the batch
  // across matters (F0-S5 review).
  async function uploadBatch(files: File[]) {
    const target = bindingProjectId;
    if (!target || files.length === 0) return;
    uploadError = null;
    for (const file of files) {
      uploading = true;
      try {
        // ADR-F007 upload-time membership: POST /files with the matter's
        // project_id makes the document visible to search_documents /
        // read_document with no extra wiring.
        const uploaded = await filesApi.uploadFile(file, { project_id: target });
        uploads = [...uploads, uploaded];
      } catch (e) {
        // Accumulate — a later file's success must not erase an earlier
        // file's failure (F0-S5 review).
        const msg = e instanceof Error ? `${file.name}: ${e.message}` : `Upload failed: ${file.name}`;
        uploadError = uploadError ? `${uploadError} · ${msg}` : msg;
      } finally {
        uploading = false;
      }
    }
    startUploadPolling();
  }

  async function handlePicked(event: Event) {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = '';
    await uploadBatch(files);
  }

  // Upload chips belong to the matter they filed into — switching the
  // Matter on a fresh chat clears them (a 'ready' chip must never imply
  // the NEW matter's agent can ground on that file — F0-S5 review).
  // Watched reactively rather than via the select's change event so a
  // PROGRAMMATIC write to the bound prop — the page binding a matter it
  // just created through the modal (F0-S8) — clears them identically.
  let prevMatterId = selectedMatterId;
  $: if (selectedMatterId !== prevMatterId) {
    prevMatterId = selectedMatterId;
    onMatterChanged();
  }

  function onMatterChanged() {
    stopUploadPolling();
    uploads = [];
    uploadError = null;
  }

  function handleDragOver(event: DragEvent) {
    // ALWAYS claim the drag: without preventDefault the browser handles
    // the drop itself and navigates the tab to the dropped file,
    // destroying the page state (F0-S5 review). Unbound = no-op target.
    event.preventDefault();
    if (!bindingProjectId) return;
    dragOver = true;
  }

  function handleDragLeave() {
    dragOver = false;
  }

  async function handleDrop(event: DragEvent) {
    event.preventDefault();
    dragOver = false;
    if (!bindingProjectId) return; // an unbound upload has no home (ADR-F002)
    await uploadBatch(Array.from(event.dataTransfer?.files ?? []));
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

  /**
   * Markdown → sanitized HTML for MODEL OUTPUT (untrusted input). One
   * path for answers, settled reasoning, and the live ribbon (F0-S8:
   * thinking rendered as raw text while the answer got markdown).
   */
  function mdSafe(text: string): string {
    return DOMPurify.sanitize(marked.parse(text, { async: false }) as string, SANITIZE_OPTS);
  }

  function answerHtmlFor(run: AgentRun): string {
    const visible = splitThink(run.final_answer).visible;
    if (!visible) return '';
    return mdSafe(visible);
  }

  $: latestRun = latestRunOf(detail);
  $: badge = latestRun ? statusBadge(latestRun, nowMs) : null;
  $: stale = latestRun ? isStaleRunning(latestRun, nowMs) : false;
  // The staleness cutoff must end the STREAM exactly as it ends the
  // poll loop — otherwise a zombie SSE (plus the server's DB tail)
  // outlives the Stale badge (S7 review; the server applies the same
  // 330s cutoff from its side).
  $: if (stale && streamRunId !== null) {
    stopStream();
    dispatch('settled');
  }
  // A stale run's dangling tool calls must not pulse forever — render
  // settled; lit spans the conversation, the pulse only the newest run.
  $: railSteps = threadRailSteps(detail);
  $: rail = threadRailStates(detail, stale ? 'failed' : (latestRun?.status ?? null));
  // The rail is the honest model-visible universe: matter tools appear
  // only when the open conversation is matter-bound (or, pre-chat, when
  // a matter is selected in the composer).
  $: matterBound = detail ? detail.thread.project_id !== null : selectedMatterId !== '';
  $: hasConversation = detail !== null;
  // The Matter the composer would upload into: the open conversation's
  // binding, or the selected matter for a new chat. null = no home → no
  // attach (ADR-F002).
  $: bindingProjectId = detail ? detail.thread.project_id : selectedMatterId || null;
  // A clicked conversation that hasn't loaded yet must NOT show the
  // new-chat composer — Send in that window would silently create a NEW
  // thread (F0-S5 review).
  $: threadOpening = currentThreadId !== null && detail === null;
  $: canSend = !threadOpening && composerEnabled(detail, nowMs);
  // ADR-F002 (F0-S8): a NEW conversation requires a matter — the blank-
  // workspace option is gone; create-in-place covers the zero-matter case.
  $: needsMatter = !detail && !selectedMatterId;
  // Live reasoning rendered as markdown, sanitized like any model output.
  $: liveReasoningHtml = liveReasoning ? mdSafe(liveReasoning) : '';
</script>

<!-- Reading order (F0-S8, maintainer feedback: "chatbox at the top makes
     it weird"): area header → conversation, top-down → composer DOCKED at
     the bottom, like claude.ai / Claude Code. -->
<section class="ag-area-card" data-testid="lq-ai-agents-area-card">
  <div class="ag-area-card__head">
    <slot name="head" />
  </div>
  <slot name="copy" />
  {#if detail}
    <p class="lq-text-body-sm ag-thread-head">
      {#if matterName(matters, detail.thread.project_id)}
        <span
          class="ag-chip"
          data-testid="lq-ai-agents-run-matter"
          title={detail.thread.project_id}
        >
          {matterName(matters, detail.thread.project_id)}
        </span>
      {/if}
      <span class="ag-thread-head__title">{detail.thread.title}</span>
    </p>
  {/if}
</section>

{#if threadOpening}
  <p class="lq-text-body-sm ag-note">Loading the conversation…</p>
  {#if pollError}
    <!-- The FIRST fetch failing must not look like a silent no-op
         (F0-S5 review): surface it even before any detail exists. -->
    <p class="lq-text-body-sm ag-error">
      Couldn't open the conversation: {pollError}
      <button type="button" class="ag-btn-ghost" on:click={retryPolling}>Retry</button>
    </p>
  {/if}
{/if}

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
              <li class="ag-step ag-step--{step.kind}" class:ag-step--nested={step.parent_step_id}>
                {#if d.mono && d.body}
                  <!-- Tool calls/results collapse to a one-line digest
                       (F0-S8 — always-expanded tool bodies drowned the
                       conversation); the full args/output stay one
                       click away. The record is untouched (ADR-F004). -->
                  <details class="ag-step__fold">
                    <summary>
                      <span class="ag-step__title lq-text-label">{d.title}</span>
                      <span class="ag-step__digest lq-text-caption">{stepDigest(d.body)}</span>
                    </summary>
                    <pre class="ag-step__mono">{d.body}</pre>
                  </details>
                {:else}
                  <span class="ag-step__title lq-text-label">{d.title}</span>
                  {#if d.thinking}
                    <details class="ag-thinking">
                      <summary class="lq-text-caption">Reasoning</summary>
                      <div class="ag-thinking__body prose prose-sm max-w-none">
                        <!-- eslint-disable-next-line svelte/no-at-html-tags — mdSafe-sanitized -->
                        {@html mdSafe(d.thinking)}
                      </div>
                    </details>
                  {/if}
                  {#if d.body}
                    <p class="lq-text-body-sm ag-step__body">{d.body}</p>
                  {/if}
                {/if}
              </li>
            {/each}
          </ol>
        {:else if turn.run.status === 'running' && !stale && !liveReasoning}
          <p class="lq-text-body-sm ag-note">Waiting for the first step…</p>
        {/if}

        {#if i === detail.runs.length - 1 && turn.run.status === 'running' && !stale && liveReasoning}
          <!-- SSE v2 thinking ribbon (F0-S7): live reasoning deltas. Since
               F0-S8 it is AUTO-EXPANDED, markdown-rendered, and clamped to
               a tail-anchored window like claude.ai (it used to need a
               click). Pure animation; rows above are the record (ADR-F004)
               — when the turn settles this collapses into the timeline's
               one-line "Reasoning" row. -->
          <div class="ag-thinking-live" data-testid="lq-ai-agents-thinking-live">
            <p class="lq-text-caption ag-thinking-live__head">
              <span class="ag-shimmer">Thinking…</span>
            </p>
            <div class="ag-thinking-live__tail">
              <div class="prose prose-sm max-w-none">
                <!-- eslint-disable-next-line svelte/no-at-html-tags — mdSafe-sanitized -->
                {@html liveReasoningHtml}
              </div>
            </div>
          </div>
        {/if}

        {#if turn.run.status === 'completed'}
          {#if turnHtml || turnAnswer.thinking}
            <div class="ag-answer" data-testid="lq-ai-agents-answer">
              {#if turnAnswer.thinking}
                <details class="ag-thinking">
                  <summary class="lq-text-caption">Reasoning</summary>
                  <div class="ag-thinking__body prose prose-sm max-w-none">
                    <!-- eslint-disable-next-line svelte/no-at-html-tags — mdSafe-sanitized -->
                    {@html mdSafe(turnAnswer.thinking)}
                  </div>
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

<!-- Auto-scroll anchor: marks where the conversation ends in flow. -->
<div bind:this={threadEndEl} aria-hidden="true"></div>

<form
  bind:this={composerEl}
  class="ag-composer"
  data-testid="lq-ai-agents-composer"
  on:submit|preventDefault={submit}
>
  {#if !detail}
    <div class="ag-matter">
      <label class="lq-text-label" for="ag-matter">Matter</label>
      <div class="ag-matter__row">
        <select
          id="ag-matter"
          data-testid="lq-ai-agents-matter-select"
          bind:value={selectedMatterId}
          disabled={submitting}
        >
          <!-- ADR-F002 (F0-S8): no blank-workspace option — a conversation
               needs a matter; "+ New matter" covers the zero-matter case. -->
          <option value="" disabled>Select a matter…</option>
          {#each matters as m (m.id)}
            <option value={m.id}>{m.name}</option>
          {/each}
        </select>
        <button
          type="button"
          class="ag-btn-ghost"
          data-testid="lq-ai-agents-new-matter"
          disabled={submitting}
          on:click={() => dispatch('newmatter')}
        >
          + New matter
        </button>
      </div>
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
      title={needsMatter ? 'Select or create a matter first' : undefined}
      disabled={submitting || !canSend || needsMatter || !prompt.trim()}
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

<style>
  .ag-area-card,
  .ag-thread {
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

  .ag-chip {
    background: var(--lq-accent-soft);
    color: var(--lq-accent);
    border: 1px solid var(--lq-accent-border);
    border-radius: var(--lq-radius-pill);
    padding: 0 var(--lq-space-2);
    font-size: 11px;
    line-height: 18px;
  }

  /* Docked composer (F0-S8): its own card, stuck to the viewport bottom
     while the conversation scrolls above it — the claude.ai reading
     order. The page scrolls; this never detaches from the bottom edge. */
  .ag-composer {
    display: flex;
    flex-direction: column;
    gap: var(--lq-space-2);
    position: sticky;
    bottom: 0;
    z-index: 5;
    background: var(--lq-canvas);
    border: 1px solid var(--lq-border);
    border-radius: var(--lq-radius-lg);
    padding: var(--lq-space-4);
    margin-top: var(--lq-space-4);
    box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.06);
  }

  .ag-thread-head {
    display: flex;
    align-items: center;
    gap: var(--lq-space-2);
    min-width: 0;
    margin-top: var(--lq-space-2);
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

  .ag-matter__row {
    display: flex;
    align-items: center;
    gap: var(--lq-space-2);
  }

  .ag-matter__row select {
    flex: 1;
    min-width: 0;
  }

  .ag-matter__row .ag-btn-ghost {
    white-space: nowrap;
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

  /* Subagent steps (parent_step_id set, F0-S7): indented under their
     dispatch. The full tree view is F1; the linkage already renders. */
  .ag-step--nested {
    margin-left: var(--lq-space-4);
    border-left-style: dashed;
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

  .ag-step__mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
    background: var(--lq-inset);
    border-radius: var(--lq-radius-sm);
    padding: var(--lq-space-2);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    margin: var(--lq-space-1) 0 0;
  }

  /* Collapsed tool step: title + one-line digest on the summary row. */
  .ag-step__fold summary {
    display: flex;
    align-items: baseline;
    gap: var(--lq-space-2);
    cursor: pointer;
    min-width: 0;
  }

  .ag-step__fold summary .ag-step__title {
    display: inline;
    white-space: nowrap;
  }

  .ag-step__digest {
    color: var(--lq-text-tertiary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .ag-thinking summary {
    cursor: pointer;
    color: var(--lq-text-tertiary);
  }

  /* Settled reasoning, markdown-rendered (F0-S8) — quieter than the
     answer prose: inset panel, smaller type. */
  .ag-thinking__body {
    background: var(--lq-inset);
    border-radius: var(--lq-radius-sm);
    padding: var(--lq-space-2) var(--lq-space-3);
    margin-top: var(--lq-space-1);
    font-size: 13px;
    color: var(--lq-text-secondary);
  }

  /* Live ribbon (F0-S8): auto-expanded, clamped to a tail-anchored
     window — the newest reasoning is always the visible part, the top
     fades out, exactly the claude.ai affordance. */
  .ag-thinking-live {
    margin-top: var(--lq-space-2);
  }

  .ag-thinking-live__head {
    margin: 0 0 var(--lq-space-1);
  }

  .ag-thinking-live__tail {
    max-height: 10.5em;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    background: var(--lq-inset);
    border-radius: var(--lq-radius-sm);
    padding: var(--lq-space-2) var(--lq-space-3);
    font-size: 13px;
    color: var(--lq-text-secondary);
    -webkit-mask-image: linear-gradient(to bottom, transparent 0, black 2.5em);
    mask-image: linear-gradient(to bottom, transparent 0, black 2.5em);
  }

  .ag-shimmer {
    background: linear-gradient(
      90deg,
      var(--lq-text-tertiary) 25%,
      var(--lq-accent) 50%,
      var(--lq-text-tertiary) 75%
    );
    background-size: 200% 100%;
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    animation: ag-shimmer 1.6s linear infinite;
  }

  .ag-answer {
    margin-top: var(--lq-space-4);
    border-top: 1px solid var(--lq-border);
    padding-top: var(--lq-space-3);
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

  @keyframes ag-shimmer {
    from {
      background-position: 200% 0;
    }
    to {
      background-position: -200% 0;
    }
  }
</style>
