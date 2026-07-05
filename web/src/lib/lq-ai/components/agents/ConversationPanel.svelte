<script module lang="ts">
	/**
	 * Pure, testable helper for building the `createRun` payload. Exported so
	 * unit tests can exercise the branching logic without a DOM (same pattern
	 * as DocumentEditorPanel.svelte + DocumentsPanel.svelte).
	 */
	import type { AgentRunCreate } from '$lib/lq-ai/api/agents';
	import { formatCostUSD } from '$lib/lq-ai/playbookCost';

	export function buildRunPayload(args: {
		prompt: string;
		/** '' = the "Default" option — `budget_profile` is OMITTED from the payload
		 *  and the server resolves the chain run-explicit > area default >
		 *  deployment default > balanced (SETUP-5a, ADR-F063). */
		budgetProfile: '' | 'economy' | 'balanced' | 'generous';
		detail?: { thread: { id: string } } | null;
		selectedMatterId?: string | null;
	}): AgentRunCreate {
		const { prompt, budgetProfile, detail, selectedMatterId } = args;
		const budget = budgetProfile === '' ? {} : { budget_profile: budgetProfile };
		if (detail) {
			return { prompt, ...budget, thread_id: detail.thread.id };
		}
		return { prompt, ...budget, project_id: selectedMatterId ?? null };
	}

	/**
	 * Format a settled run's estimated USD spend, or null when there is nothing
	 * to show. `cost_usd` arrives as a Decimal string (or number) on the wire; it
	 * is a rolling-average ESTIMATE (F2 Slice O-2, ADR-F053) — the UI labels it
	 * approximate. Reuses `formatCostUSD` for $-formatting consistency. Returns
	 * null for missing / non-finite / negative values so the caption is hidden.
	 */
	export function formatRunCostUSD(value: string | number | null | undefined): string | null {
		if (value == null) return null;
		const n = typeof value === 'number' ? value : Number(value);
		if (!Number.isFinite(n) || n < 0) return null;
		return formatCostUSD(n);
	}
</script>

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
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import DownloadIcon from '@lucide/svelte/icons/download';
	import SearchIcon from '@lucide/svelte/icons/search';
	import SquareIcon from '@lucide/svelte/icons/square';
	import UsersIcon from '@lucide/svelte/icons/users';
	import { renderModelMarkdown } from '$lib/lq-ai/sanitize-markdown';
	import StepRow from './StepRow.svelte';
	import TabularPreview from './TabularPreview.svelte';
	import { tabularGridIdsForTurn } from '$lib/lq-ai/agents/tabular-preview';
	import { agentsApi, filesApi, matterFilesApi } from '$lib/lq-ai/api';
	import { isRedlineOutput } from '$lib/lq-ai/api/editor';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import type { AgentRun, AgentRunStep, AgentThreadDetailResponse } from '$lib/lq-ai/api/agents';
	import type { FileMeta, MatterFile, Project } from '$lib/lq-ai/types';
	import {
		MAX_POLL_FAILURES,
		POLL_INTERVAL_MS,
		agentWorking,
		cancellableRunId,
		composerEnabled,
		isStaleRunning,
		latestRunOf,
		groupTurnSteps,
		groupTurnTree,
		matterName,
		shouldContinuePollingThread,
		splitThink,
		statusBadge,
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
		dealVerdictLabel,
		dealVerdictTone,
		parseDealChangePayload,
		parseRopaChangePayload,
		parseRunPayload,
		parseStepPayload,
		type DealChangePayload
	} from '$lib/lq-ai/agents/run-stream';
	import { serverNowMs } from '$lib/lq-ai/agents/server-clock';
	import { consumeUIMessageStream, type UIMessagePart } from '$lib/lq-ai/sse/ui-message-stream';

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
	/**
	 * Bound OUT to the host (PRIV-9a): true while the agent is actively
	 * working. The cockpit host relays it to the co-visible ROPA register so
	 * the register polls live while the agent writes — mirroring the
	 * composer's own run-lock (`working` below).
	 */
	export let runActive = false;

	// `newmatter`: the user asked to create a matter from the composer —
	// the HOST owns the modal (page chrome) and writes the created id back
	// through the bound `selectedMatterId` (F0-S8).
	// `threadcreated`: the composer just created a NEW conversation (F1-S2)
	// — the cockpit host syncs its URL state from it (deep-link contract).
	const dispatch = createEventDispatcher<{
		settled: void;
		newmatter: void;
		threadcreated: { threadId: string; projectId: string | null };
		/** PRIV-9b (ADR-F024): one ROPA register row the agent just changed — the
		 * host lifts the id into a recently-changed set that washes the matching row. */
		ropachange: { kind: string; id: string; verb: string };
		/** ADR-F047 (Slice 4): the agent FRESHLY produced a redline .docx — the host
		 * slides the in-app editor in so the lawyer can review/edit it right away. */
		redlineready: { fileId: string; filename: string };
		/** F2 Tabular T6 (ADR-F055): the lawyer clicked Expand on an in-chat grid
		 * preview — the host opens it as a stage-takeover (docked TabularWorkspace). */
		expandgrid: { gridId: string };
	}>();

	let submitting = false;
	let submitError: string | null = null;
	// Budget profile for the next run — controls model tier ceiling / token spend.
	// '' = "Default": the payload omits budget_profile and the server resolves
	// run-explicit > area default > deployment default > balanced (ADR-F063).
	let budgetProfile: '' | 'economy' | 'balanced' | 'generous' = '';
	// PRIV-9a run-lock: the Stop control's in-flight + error state.
	let cancelling = false;
	let cancelError: string | null = null;
	// The run id from createRun, before the first poll surfaces it — bridges the
	// gap so Stop is targetable the instant the lock engages.
	let pendingRunId: string | null = null;

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

	// C7a (ADR-F046): the redline-download surface, inline under the run that made it.
	// `producedByRun[runId]` = the work-product files that run created (e.g. a redlined
	// .docx), keyed by File.created_by_run_id. Refreshed when the set of completed runs
	// changes; the durable surface is the matter Documents tab, so a fetch failure here
	// is non-fatal (the inline convenience just stays empty).
	let producedByRun: Record<string, MatterFile[]> = {};
	let producedGen = 0;
	let downloadingFileId: string | null = null;
	let inlineDownloadError = '';

	// ADR-F047 (Slice 4): auto-open the in-app editor when the agent FRESHLY produces
	// a redline — but never when merely revisiting a matter that already has old
	// outputs. We snapshot the redline ids that exist when the thread is FIRST opened
	// (the baseline) and only announce ids that appear later. The baseline must be
	// captured independently of the completed-run trigger below: in the headline flow
	// (a fresh conversation whose first ask is a redline) the redline-producing run is
	// itself the first completion, so seeding off "the first loadProducedFiles call"
	// would mark the new redline as already-seen and never open it. A memoized promise
	// guarantees the baseline is settled before any announcement.
	const announcedRedlineIds = new Set<string>();
	let redlineBaseline: Promise<void> | null = null;
	function ensureRedlineBaseline(projectId: string): Promise<void> {
		if (!redlineBaseline) {
			redlineBaseline = (async () => {
				try {
					const { files } = await matterFilesApi.listMatterFiles(projectId);
					for (const f of files) {
						if (f.created_by_run_id && isRedlineOutput(f.filename)) announcedRedlineIds.add(f.id);
					}
				} catch {
					// non-fatal — worst case a pre-existing redline auto-opens once.
				}
			})();
		}
		return redlineBaseline;
	}

	async function loadProducedFiles(projectId: string) {
		const gen = ++producedGen;
		// Don't announce a redline until the baseline (existing-at-thread-open) is settled.
		await ensureRedlineBaseline(projectId);
		try {
			const { files } = await matterFilesApi.listMatterFiles(projectId);
			if (gen !== producedGen) return;
			const map: Record<string, MatterFile[]> = {};
			for (const f of files) {
				if (f.created_by_run_id) (map[f.created_by_run_id] ??= []).push(f);
			}
			producedByRun = map;

			for (const f of files) {
				if (f.created_by_run_id && isRedlineOutput(f.filename) && !announcedRedlineIds.has(f.id)) {
					announcedRedlineIds.add(f.id);
					dispatch('redlineready', { fileId: f.id, filename: f.filename });
				}
			}
		} catch {
			// non-fatal — the Documents tab is the durable download surface.
		}
	}

	async function downloadProduced(file: MatterFile) {
		if (downloadingFileId) return; // one at a time
		downloadingFileId = file.id;
		inlineDownloadError = '';
		try {
			await filesApi.downloadFile(file.id, file.filename);
		} catch (e) {
			inlineDownloadError =
				e instanceof LQAIApiError ? e.message : 'Could not download — it may have been removed.';
		} finally {
			downloadingFileId = null;
		}
	}
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
		clearDealChips();
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
		clearDealChips(); // a new thread context — drop any prior run's verdict chips
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
			const isNewThread = !detail;
			const created = await agentsApi.createRun(
				buildRunPayload({ prompt: text, budgetProfile, detail, selectedMatterId })
			);
			// PRIV-9a: createRun returns the run already 'running' — seed it so the
			// Stop button is targetable before the first poll lands (no locked-but-
			// uncancellable window).
			pendingRunId = created.id;
			prompt = '';
			if (isNewThread) {
				dispatch('threadcreated', {
					threadId: created.thread_id,
					projectId: created.project_id
				});
			}
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

	// PRIV-9a: while the agent works the composer collapses to a single Stop
	// control. Stop calls the REAL backend cancel (not just a client stream
	// abort) so the durable run actually settles, then re-syncs by polling —
	// the settled `cancelled` row re-enables the composer (ADR-F004). Idempotent
	// server-side, so a finish-vs-stop race is harmless.
	async function cancelCurrentRun() {
		const runId = liveRunId;
		if (!runId || cancelling) return;
		cancelling = true;
		cancelError = null;
		try {
			await agentsApi.cancelRun(runId);
		} catch (e) {
			cancelError = e instanceof Error ? e.message : 'Failed to stop the run';
		} finally {
			cancelling = false;
		}
		// Re-sync to the settled status (startPolling also tears down the stream).
		if (currentThreadId) startPolling(currentThreadId);
	}

	// ---------------------------------------------------------------------
	// SSE v2 — F0-S7 (ADR-F006 wire spec; ADR-F004 render-determinism)
	// ---------------------------------------------------------------------

	let streamRunId: string | null = null;
	let streamAbort: AbortController | null = null;
	/** Live thinking-ribbon text — animation only, cleared as rows settle. */
	let liveReasoning = '';
	let liveReasoningBlock: string | null = null;
	// Live reasoning is rendered to HTML on a requestAnimationFrame throttle over a
	// bounded TAIL of the buffer — NOT a `$:` over the whole string. A reasoning model
	// (e.g. deepseek-v4-flash) streams 100k+ tokens at hundreds of deltas/sec; re-running
	// marked+DOMPurify over the full buffer per delta is O(n²) and freezes the tab before
	// the run finishes. The ribbon is ephemeral (the settled StepRow renders the final
	// reasoning), so rendering only the visible tail is sufficient and bounded.
	let liveReasoningHtml = '';
	let _reasoningRafPending = false;
	const LIVE_REASONING_TAIL = 8000;
	function scheduleLiveReasoningRender() {
		if (_reasoningRafPending) return;
		_reasoningRafPending = true;
		requestAnimationFrame(() => {
			_reasoningRafPending = false;
			if (!liveReasoning) {
				liveReasoningHtml = '';
				return;
			}
			const tail =
				liveReasoning.length > LIVE_REASONING_TAIL
					? liveReasoning.slice(-LIVE_REASONING_TAIL)
					: liveReasoning;
			liveReasoningHtml = renderModelMarkdown(tail);
			void autoScroll();
		});
	}
	let answerBuffers: Record<string, string> = {};

	/**
	 * C5b-3 (ADR-F032/F004): live negotiation verdict chips. As the agent responds to
	 * the counterparty (`respond_to_counterparty`), the backend drains one
	 * `data-deal-change` frame per item; we flash a transient chip per ref in the
	 * conversation. Animation only — the saved response .docx + run timeline are the
	 * record, so a dropped frame loses a chip, never data. Deduped by ref (latest
	 * verdict wins across retries); the whole set decays together after a short window.
	 */
	const DEAL_CHIP_DECAY_MS = 6000;
	let recentDealChanges: DealChangePayload[] = [];
	let dealChipTimer: ReturnType<typeof setTimeout> | null = null;
	/** Which run the live chips belong to — frames from a NEW run reset the set. */
	let dealChipRunId: string | null = null;

	function pushDealChip(runId: string, payload: DealChangePayload) {
		// Reset when a different run starts emitting (a fresh round / new thread run).
		// The chips are owned by the client-side decay timer (below), NOT re-delivered
		// by the server — data-deal-change is transient (drained once, no replay buffer,
		// not seeded to late subscribers), so they must survive stream transport churn
		// (clearStreamState deliberately leaves them — a clean-end-then-reopen of the
		// same run must not cut a still-valid chip short).
		if (dealChipRunId !== runId) {
			dealChipRunId = runId;
			recentDealChanges = [];
		}
		recentDealChanges = [...recentDealChanges.filter((c) => c.ref !== payload.ref), payload];
		if (dealChipTimer) clearTimeout(dealChipTimer);
		dealChipTimer = setTimeout(() => {
			recentDealChanges = [];
			dealChipTimer = null;
		}, DEAL_CHIP_DECAY_MS);
	}

	function clearDealChips() {
		if (dealChipTimer) clearTimeout(dealChipTimer);
		dealChipTimer = null;
		recentDealChanges = [];
		dealChipRunId = null;
	}

	function clearStreamState() {
		// NB: deliberately does NOT clear the live verdict chips. data-deal-change is
		// transient (drained once; no server replay), so the chips are kept alive by
		// their own decay timer — wiping them here would cut a still-valid chip short
		// on a clean stream end + re-open of the same running run. Chips reset on a run
		// change (pushDealChip) / thread switch (startPolling) / decay / destroy.
		streamAbort = null;
		streamRunId = null;
		liveReasoning = '';
		liveReasoningBlock = null;
		liveReasoningHtml = '';
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

	async function runStream(runId: string, threadId: string, gen: number, abort: AbortController) {
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
				scheduleLiveReasoningRender();
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
					liveReasoningHtml = '';
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
				liveReasoningHtml = '';
				return;
			}
			case 'data-ropa-change': {
				// PRIV-9b (ADR-F024): a ROPA register row just changed. Relay the id
				// up to the host, which washes the matching row in the co-visible
				// register. Animation only — the register's own poll/reconcile carries
				// the true rows (ADR-F004), so a dropped frame loses a flash, not data.
				const payload = parseRopaChangePayload(part.data);
				if (payload) dispatch('ropachange', payload);
				return;
			}
			case 'data-deal-change': {
				// C5b-3 (ADR-F032): the agent just decided a counterparty item. Flash a
				// transient verdict chip inline (Commercial has no register to wash).
				// Animation only — the saved response .docx + timeline are the record
				// (ADR-F004), so a dropped frame loses a chip, not data.
				const payload = parseDealChangePayload(part.data);
				if (payload) pushDealChip(runId, payload);
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
				const msg =
					e instanceof Error ? `${file.name}: ${e.message}` : `Upload failed: ${file.name}`;
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

	// Markdown → sanitized HTML for MODEL OUTPUT (untrusted input) now routes
	// through the shared `renderModelMarkdown` sink (AE6 / R-CONV-2) — one
	// media-forbid policy for answers, settled reasoning, and the live ribbon,
	// shared with the chat surface and the skill source view so none can drift.
	function answerHtmlFor(run: AgentRun): string {
		const visible = splitThink(run.final_answer).visible;
		if (!visible) return '';
		return renderModelMarkdown(visible);
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

	// C7a (ADR-F046): refresh the produced-files map when the set of COMPLETED runs
	// changes — a redline that just settled wrote an output File. Keyed on a cheap
	// signature so it doesn't refetch on every poll tick of a still-running turn.
	$: completedRunSig = detail
		? detail.runs
				.filter((t) => t.run.status === 'completed')
				.map((t) => t.run.id)
				.join(',')
		: '';
	$: matterFilesProjectId = detail?.thread.project_id ?? null;
	// Capture the redline baseline as soon as the thread's matter is known (before any
	// run completes), so a redline produced THIS session auto-opens (ADR-F047 Slice 4).
	$: if (matterFilesProjectId) void ensureRedlineBaseline(matterFilesProjectId);
	$: if (matterFilesProjectId && completedRunSig) {
		void loadProducedFiles(matterFilesProjectId);
	}
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
	// liveReasoningHtml is updated by scheduleLiveReasoningRender() (rAF-throttled,
	// tail-bounded) — NOT a `$:` over the full buffer, which was O(n²) and froze the tab
	// during long reasoning-model streams.
	// PRIV-9a run-lock + co-visible-register signal: the agent is actively
	// working (createRun in flight or the newest run still running, not stale)
	// → the composer shows only Stop, and `runActive` drives the host's register
	// poll. `liveRunId` is the run a Stop press cancels (null = nothing yet).
	$: working = agentWorking(detail, nowMs, submitting);
	// `pendingRunId` bridges the createRun→first-poll gap so Stop is never shown
	// without a run to cancel; cleared once the run is no longer active.
	$: liveRunId = cancellableRunId(detail, streamRunId) ?? pendingRunId;
	$: if (!working && pendingRunId) pendingRunId = null;
	$: runActive = working;
</script>

<!-- Reading order (F0-S8, maintainer feedback: "chatbox at the top makes
     it weird"): area header → conversation, top-down → composer DOCKED at
     the bottom, like claude.ai / Claude Code. F1-S2.1: the card renders
     only when it has content — the cockpit host passes no slots, and an
     EMPTY white bar floated over the fresh-composer view. -->
{#if $$slots.head || $$slots.copy || detail}
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
{/if}

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
				The last run never settled — it was likely interrupted by a backend restart. Start a new
				chat.
			</p>
		{/if}

		{#each detail.runs as turn, i (turn.run.id)}
			{@const turnSteps = visibleSteps(turn.steps, turn.run)}
			{@const turnAnswer = splitThink(turn.run.final_answer)}
			{@const turnHtml = answerHtmlFor(turn.run)}
			{@const turnCost = formatRunCostUSD(turn.run.cost_usd)}
			{@const turnGridIds = tabularGridIdsForTurn(turn.steps)}
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
					{@const rows = groupTurnSteps(turnSteps)}
					{@const segments = groupTurnTree(rows)}
					{@const turnLive =
						i === detail.runs.length - 1 && turn.run.status === 'running' && !stale}
					<!-- AE Task (AE6, ADR-F011 option-2): the turn's work as one
                 collapsible step list — Search-icon trigger + a left rail —
                 hand-built on a native <details> (the AE `task`/`tool`
                 registry items pull `collapsible` + `./code.json`, both
                 dodged across the AE series). The .ag-steps <li> structure
                 is kept so the live step-count specs still match. UX-B-5:
                 segments fold subagent delegations into a boundary block. -->
					<details class="ag-task" open data-testid="lq-ai-agents-task">
						<summary class="ag-task__trigger">
							<SearchIcon class="size-4" aria-hidden="true" />
							<span class="lq-text-label">{rows.length} step{rows.length === 1 ? '' : 's'}</span>
							<span class="ag-task__chevron"
								><ChevronDownIcon class="size-4" aria-hidden="true" /></span
							>
						</summary>
						<ol class="ag-steps">
							{#each segments as seg (seg.id)}
								{#if seg.kind === 'delegation'}
									<!-- UX-B-5: a subagent delegation boundary (ADR-F017). The
                       `task` call's children ran inside the subagent; rendered
                       indented under an honest "Delegated to <type>" header. The
                       boundary appears ONLY when delegation actually occurred. -->
									<li class="ag-step ag-delegation" data-testid="lq-ai-agents-delegation">
										<div class="ag-delegation__head">
											<UsersIcon class="size-4" aria-hidden="true" />
											<span class="lq-text-label ag-delegation__label">
												Delegated to {seg.subagentType ?? 'a subagent'}
											</span>
										</div>
										<StepRow row={seg.header} live={turnLive} />
										<ol class="ag-steps ag-steps--sub">
											{#each seg.children as child (child.id)}
												<li class="ag-step ag-step--nested">
													<StepRow row={child} live={turnLive} />
												</li>
											{/each}
											{#if seg.result}
												<li class="ag-step ag-step--nested">
													<StepRow row={seg.result} live={turnLive} />
												</li>
											{/if}
										</ol>
									</li>
								{:else}
									<li class="ag-step" class:ag-step--nested={seg.row.nested}>
										<StepRow row={seg.row} live={turnLive} />
									</li>
								{/if}
							{/each}
						</ol>
					</details>
				{:else if turn.run.status === 'running' && !stale && !liveReasoning}
					<p class="lq-text-body-sm ag-note">Waiting for the first step…</p>
				{/if}

				{#if i === detail.runs.length - 1 && turn.run.status === 'running' && !stale && recentDealChanges.length && turn.run.id === dealChipRunId}
					<!-- C5b-3 (ADR-F032): live negotiation verdict chips — one per
               counterparty item the agent just decided. Transient animation;
               the saved response .docx + timeline are the record (ADR-F004). The
               `turn.run.id === dealChipRunId` guard keeps chips under the run that
               emitted them (no mis-render if a different run becomes last). -->
					<ul class="ag-deal-chips" data-testid="lq-ai-agents-deal-chips">
						{#each recentDealChanges as chip (chip.ref)}
							<li
								class="ag-deal-chip ag-deal-chip--{dealVerdictTone(chip.verdict)}"
								data-testid="lq-ai-agents-deal-chip"
							>
								<span class="ag-deal-chip__ref">{chip.ref}</span>
								<span class="ag-deal-chip__verdict">{dealVerdictLabel(chip.verdict)}</span>
							</li>
						{/each}
					</ul>
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
							<div class="prose prose-sm dark:prose-invert max-w-none">
								<!-- eslint-disable-next-line svelte/no-at-html-tags — renderModelMarkdown-sanitized -->
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
									<div class="ag-thinking__body prose prose-sm dark:prose-invert max-w-none">
										<!-- eslint-disable-next-line svelte/no-at-html-tags — renderModelMarkdown-sanitized -->
										{@html renderModelMarkdown(turnAnswer.thinking)}
									</div>
								</details>
							{/if}
							{#if turnHtml}
								<div class="prose prose-sm dark:prose-invert max-w-none">
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
						The run hit its step cap ({turn.run.max_steps} steps) before finishing, so there is no final
						answer. The steps above show how far it got.
					</p>
				{:else if turn.run.status === 'failed'}
					<p class="lq-text-body-sm ag-error">
						Run failed: {turn.run.error ?? 'unknown error'}
					</p>
				{/if}

				<!-- F2 Tabular T2 (ADR-F055): one durable grid-preview card per grid this
				     turn finalized. Derived from the SETTLED finalize_tabular_review step
				     (re-renders identically on reload, ADR-F004); each fetches its own body. -->
				{#if turnGridIds.length > 0}
					<div class="ag-grids" data-testid="lq-ai-agents-grids">
						{#each turnGridIds as gridId (gridId)}
							<TabularPreview
								{gridId}
								on:expand={(e) => dispatch('expandgrid', { gridId: e.detail.gridId })}
							/>
						{/each}
					</div>
				{/if}

				<!-- F2 Slice O-2 (ADR-F053): a rough rolling-average cost estimate for the
				     settled run (NULL/hidden on timeout/error or before settlement). Labelled
				     approximate — it is not an exact bill (the routing log has no per-run id). -->
				{#if turnCost}
					<p
						class="lq-text-caption ag-cost"
						data-testid="lq-ai-agents-cost"
						title="Rough estimate from recent per-token cost — not an exact bill."
					>
						Est. cost ≈ {turnCost}
					</p>
				{/if}

				{#if producedByRun[turn.run.id]?.length}
					<!-- C7a (ADR-F046): the run's work product, downloadable inline. The
					     redlined .docx is persisted as a matter file; this hits the existing
					     GET /files/{id}/content. The Documents tab is the durable surface. -->
					<div class="ag-produced" data-testid="lq-ai-agents-produced">
						<p class="lq-text-label ag-produced__head">
							Document{producedByRun[turn.run.id].length === 1 ? '' : 's'} produced
						</p>
						{#each producedByRun[turn.run.id] as f (f.id)}
							<button
								type="button"
								class="ag-produced__file"
								disabled={downloadingFileId === f.id}
								data-testid="lq-ai-agents-download"
								on:click={() => downloadProduced(f)}
							>
								<DownloadIcon class="size-4" aria-hidden="true" />
								<!-- filename is plain text (a work-product label), never markdown/HTML -->
								<span class="ag-produced__name"
									>{downloadingFileId === f.id ? 'Downloading…' : f.filename}</span
								>
							</button>
						{/each}
						{#if inlineDownloadError}
							<p class="lq-text-caption ag-error">{inlineDownloadError}</p>
						{/if}
					</div>
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
	{#if working}
		<!-- PRIV-9a: "the chat locks — only a Stop button is clickable". The
		     input, matter select and attach are removed from the DOM (not just
		     disabled) so the only affordance is Stop. -->
		<div class="ag-working" data-testid="lq-ai-agents-working" role="status" aria-live="polite">
			<span class="lq-text-body-sm ag-working__label">
				<span class="ag-shimmer">The agent is working…</span>
			</span>
			<button
				type="button"
				class="ag-btn-stop"
				data-testid="lq-ai-agents-stop"
				aria-label="Stop the agent"
				disabled={!liveRunId || cancelling}
				on:click={cancelCurrentRun}
			>
				<SquareIcon class="size-3.5" aria-hidden="true" />
				{cancelling ? 'Stopping…' : 'Stop'}
			</button>
		</div>
		{#if cancelError}
			<p class="lq-text-body-sm ag-error">Couldn't stop the run: {cancelError}</p>
		{/if}
	{:else}
		{#if !detail}
			<div class="ag-matter">
				<label class="lq-text-label" for="ag-matter">Matter</label>
				<div class="ag-matter__row">
					<select
						id="ag-matter"
						data-testid="lq-ai-agents-matter-select"
						bind:value={selectedMatterId}
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
				disabled={!canSend}
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

		<div class="ag-budget">
			<label class="lq-text-label" for="ag-budget">Budget</label>
			<div class="ag-matter__row">
				<select
					id="ag-budget"
					data-testid="lq-ai-agents-budget-select"
					bind:value={budgetProfile}
				>
					<option value="">Default</option>
					<option value="economy">Economy</option>
					<option value="balanced">Balanced</option>
					<option value="generous">Generous</option>
				</select>
			</div>
			{#if budgetProfile === ''}
				<p class="lq-text-caption ag-note">Default — set by your area or deployment</p>
			{:else}
				<p class="lq-text-caption ag-note">Applies to this run — overrides the default</p>
			{/if}
		</div>

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
				disabled={!bindingProjectId || uploading}
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
				disabled={!canSend || needsMatter || !prompt.trim()}
			>
				{detail ? 'Send' : 'Run'}
			</button>
		</div>
	{/if}
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
	/* F1-S2.1: the panel's scoped palette migrated from the legacy --lq-*
	   set onto the semantic intent tokens (app.css) — it renders INSIDE the
	   cockpit, so it must sit on the same shade scale (theme-aware, incl.
	   dark). Spacing keeps the --lq-space-* constants (theme-neutral px).
	   Full markup/typography migration of this panel is rollout wave 1. */
	.ag-area-card,
	.ag-thread {
		background: var(--color-card);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: var(--lq-space-4);
	}

	.ag-area-card__head {
		display: flex;
		align-items: center;
		gap: var(--lq-space-2);
	}

	.ag-chip {
		background: var(--color-accent);
		color: var(--color-accent-foreground);
		border: 1px solid transparent;
		border-radius: var(--lq-radius-pill);
		padding: 0 var(--lq-space-2);
		font-size: 11px;
		line-height: 18px;
	}

	/* C5b-3 (ADR-F032): live negotiation verdict chips — one transient pill per
	   counterparty item the agent just decided, coloured by verdict tone on the
	   cockpit's status tokens. Animation only (the saved .docx is the record). */
	.ag-deal-chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--lq-space-1);
		margin: var(--lq-space-1) 0 var(--lq-space-2);
		padding: 0;
		list-style: none;
	}

	.ag-deal-chip {
		display: inline-flex;
		align-items: baseline;
		gap: var(--lq-space-1);
		border: 1px solid var(--chip-color, var(--color-border));
		background: var(--chip-wash, var(--color-muted));
		border-radius: var(--lq-radius-pill);
		padding: 0 var(--lq-space-2);
		font-size: 11px;
		line-height: 18px;
		animation: ag-deal-chip-in 160ms ease-out;
	}

	.ag-deal-chip__ref {
		font-weight: 600;
		color: var(--chip-color, var(--color-foreground));
	}

	.ag-deal-chip__verdict {
		color: var(--color-muted-foreground);
	}

	.ag-deal-chip--positive {
		--chip-color: var(--color-status-completed);
		--chip-wash: var(--color-status-completed-wash);
	}

	.ag-deal-chip--negative {
		--chip-color: var(--color-status-failed);
		--chip-wash: var(--color-status-failed-wash);
	}

	.ag-deal-chip--info {
		--chip-color: var(--color-status-running);
		--chip-wash: var(--color-status-running-wash);
	}

	.ag-deal-chip--warning {
		--chip-color: var(--color-status-attention);
		--chip-wash: var(--color-status-attention-wash);
	}

	.ag-deal-chip--neutral {
		--chip-color: var(--color-status-cancelled);
		--chip-wash: var(--color-status-cancelled-wash);
	}

	@keyframes ag-deal-chip-in {
		from {
			opacity: 0;
			transform: translateY(2px);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.ag-deal-chip {
			animation: none;
		}
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
		background: var(--color-card);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: var(--lq-space-4);
		margin-top: var(--lq-space-4);
		box-shadow: 0 -8px 24px oklch(0.25 0.02 262 / 0.07);
	}

	:global(.dark) .ag-composer {
		box-shadow: 0 -8px 24px oklch(0 0 0 / 0.4);
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
		border-color: var(--color-ring);
	}

	.ag-dropzone__hint {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--color-accent);
		border: 1px dashed var(--color-ring);
		border-radius: var(--radius-md);
		color: var(--color-accent-foreground);
		pointer-events: none;
	}

	.ag-composer textarea {
		width: 100%;
		border: 1px solid var(--color-input);
		border-radius: var(--radius-md);
		padding: var(--lq-space-2) var(--lq-space-3);
		font: inherit;
		resize: vertical;
		background: var(--color-muted);
		transition: border-color 150ms ease-out;
	}

	.ag-composer textarea:focus-visible {
		outline: 2px solid var(--color-ring);
		outline-offset: 1px;
	}

	.ag-matter,
	.ag-budget {
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
		border: 1px solid var(--color-input);
		border-radius: var(--radius-md);
		padding: var(--lq-space-1) var(--lq-space-2);
		font: inherit;
		background: var(--color-muted);
		color: var(--color-foreground);
	}

	.ag-matter select:focus-visible {
		outline: 2px solid var(--color-ring);
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
		border: 1px solid var(--color-border);
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
		border-color: transparent;
		background: var(--color-status-completed-wash);
	}

	.ag-upload--ready .ag-upload__status {
		color: var(--color-status-completed);
	}

	.ag-upload--failed {
		border-color: transparent;
		background: var(--color-status-failed-wash);
	}

	.ag-upload--failed .ag-upload__status {
		color: var(--color-status-failed);
	}

	.ag-upload__status {
		color: var(--color-muted-foreground);
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
		background: var(--color-primary);
		color: var(--color-primary-foreground);
		border: 0;
		border-radius: var(--radius-md);
		padding: var(--lq-space-2) var(--lq-space-4);
		cursor: pointer;
		font-weight: 500;
		font-size: 14px;
		line-height: 1.5;
		transition: filter 150ms ease-out;
	}

	.ag-btn-primary:hover {
		filter: brightness(0.95);
	}

	.ag-btn-primary:disabled {
		opacity: 0.5;
		cursor: default;
	}

	/* PRIV-9a run-lock: while the agent works the composer is replaced by a
	   single Stop control (the input/select/attach leave the DOM, not just
	   disabled) — "only the Stop button is clickable". */
	.ag-working {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--lq-space-3);
		padding: var(--lq-space-1) var(--lq-space-1) var(--lq-space-1) var(--lq-space-2);
	}

	.ag-btn-stop {
		display: inline-flex;
		align-items: center;
		gap: var(--lq-space-1);
		background: var(--color-muted);
		color: var(--color-foreground);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		padding: var(--lq-space-2) var(--lq-space-4);
		cursor: pointer;
		font: inherit;
		font-weight: 500;
		font-size: 14px;
		line-height: 1.5;
		transition:
			border-color 150ms ease-out,
			color 150ms ease-out;
	}

	.ag-btn-stop:hover:not(:disabled) {
		border-color: color-mix(in oklch, var(--color-destructive) 50%, transparent);
		color: var(--color-destructive);
	}

	.ag-btn-stop:disabled {
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
		border-top: 1px solid var(--color-border);
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
		border: 1px solid var(--color-border);
		color: var(--color-muted-foreground);
	}

	/* Run-state badges ride the status intent pairs (wash + strong),
	   matching the cockpit's StatusPill vocabulary. */
	.ag-badge--running {
		background: var(--color-status-running-wash);
		border-color: transparent;
		color: var(--color-status-running);
		animation: ag-pulse 1.6s ease-in-out infinite;
	}

	.ag-badge--ok {
		background: var(--color-status-completed-wash);
		border-color: transparent;
		color: var(--color-status-completed);
	}

	.ag-badge--warn {
		background: var(--color-status-attention-wash);
		border-color: transparent;
		color: var(--color-status-attention);
	}

	.ag-badge--error {
		background: var(--color-status-failed-wash);
		border-color: transparent;
		color: var(--color-status-failed);
	}

	/* AE Task (AE6): the turn's work as one collapsible step list. The
     trigger mirrors the AE `task` identity (search glyph + rotating chevron);
     the list carries the single left rail (AE puts the rail on the content,
     not per-step). */
	.ag-task {
		margin-top: var(--lq-space-2);
	}

	.ag-task__trigger {
		display: flex;
		align-items: center;
		gap: var(--lq-space-2);
		cursor: pointer;
		color: var(--color-muted-foreground);
		list-style: none;
	}

	.ag-task__trigger::-webkit-details-marker {
		display: none;
	}

	.ag-task__trigger:hover {
		color: var(--color-foreground);
	}

	.ag-task__chevron {
		margin-left: auto;
		transition: transform 150ms ease-out;
	}

	.ag-task[open] .ag-task__chevron {
		transform: rotate(180deg);
	}

	.ag-steps {
		list-style: none;
		margin: var(--lq-space-3) 0 0;
		padding: 0 0 0 var(--lq-space-4);
		border-left: 2px solid var(--color-border);
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-2);
	}

	.ag-step {
		min-width: 0;
	}

	/* Subagent steps (parent_step_id set, F0-S7): indented under their
     dispatch. The full tree view is F1; the linkage already renders. */
	.ag-step--nested {
		margin-left: var(--lq-space-4);
	}

	/* Subagent delegation boundary (UX-B-5, ADR-F017): the `task` call + the
     steps that ran inside the subagent, drawn as one bounded block so the
     handoff is legible — not a flat run of indented steps. Honest: rendered
     only when delegation actually occurred. */
	.ag-delegation {
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-2);
		padding: var(--lq-space-3);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-muted);
	}

	.ag-delegation__head {
		display: flex;
		align-items: center;
		gap: var(--lq-space-2);
		color: var(--color-foreground);
	}

	.ag-steps--sub {
		margin-top: 0;
	}

	/* The sub-list's own left rail + the children's per-step nudge would
     double-indent — the boundary already groups them, so flatten the nudge. */
	.ag-steps--sub .ag-step--nested {
		margin-left: 0;
	}

	/* AE Tool card + settled reasoning styles moved to StepRow.svelte (UX-B-5)
     so a top-level row and a subagent-nested child render identically. */

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
		background: var(--color-muted);
		border-radius: var(--radius-sm);
		padding: var(--lq-space-2) var(--lq-space-3);
		font-size: 13px;
		color: var(--color-muted-foreground);
		-webkit-mask-image: linear-gradient(to bottom, transparent 0, black 2.5em);
		mask-image: linear-gradient(to bottom, transparent 0, black 2.5em);
	}

	.ag-shimmer {
		background: linear-gradient(
			90deg,
			var(--color-muted-foreground) 25%,
			var(--color-primary) 50%,
			var(--color-muted-foreground) 75%
		);
		background-size: 200% 100%;
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
		animation: ag-shimmer 1.6s linear infinite;
	}

	.ag-answer {
		margin-top: var(--lq-space-4);
		border-top: 1px solid var(--color-border);
		padding-top: var(--lq-space-3);
	}

	.ag-btn-ghost {
		background: none;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		padding: 0 var(--lq-space-2);
		cursor: pointer;
		font: inherit;
		font-size: 12px;
		line-height: 22px;
		color: var(--color-muted-foreground);
		transition:
			border-color 150ms ease-out,
			color 150ms ease-out;
	}

	.ag-btn-ghost:hover {
		border-color: color-mix(in oklch, var(--color-primary) 40%, transparent);
		color: var(--color-primary);
	}

	.ag-btn-ghost:disabled {
		opacity: 0.5;
		cursor: default;
	}

	.ag-error {
		color: var(--color-destructive);
	}

	.ag-note {
		color: var(--color-muted-foreground);
	}

	/* C7a — produced work product (e.g. a redline output) download, inline under the run. */
	.ag-cost {
		margin-top: var(--lq-space-2);
		color: var(--color-muted-foreground);
	}

	.ag-produced {
		margin-top: var(--lq-space-3);
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-2);
	}

	.ag-produced__head {
		color: var(--color-muted-foreground);
	}

	.ag-produced__file {
		display: inline-flex;
		align-items: center;
		gap: var(--lq-space-2);
		align-self: flex-start;
		max-width: 100%;
		background: var(--color-card);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		padding: var(--lq-space-2) var(--lq-space-3);
		cursor: pointer;
		font: inherit;
		font-size: 13px;
		color: var(--color-foreground);
		transition:
			border-color 150ms ease-out,
			color 150ms ease-out;
	}

	.ag-produced__file:hover {
		border-color: color-mix(in oklch, var(--color-primary) 40%, transparent);
		color: var(--color-primary);
	}

	.ag-produced__file:disabled {
		opacity: 0.5;
		cursor: default;
	}

	.ag-produced__name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
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
