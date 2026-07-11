<script module lang="ts">
	/**
	 * Pure, unit-tested presenters for the in-app Word editor chrome (ADR-F047,
	 * Slice 4). The codebase has no @testing-library/svelte, so logic is tested at
	 * the helper layer (pattern: MemoryPanel / DocumentsPanel); the template is glue.
	 */
	import type { EditorSaveState } from '$lib/lq-ai/api/editor';

	/** The save-state pill text. */
	export function saveStateLabel(s: EditorSaveState): string {
		switch (s) {
			case 'loading':
				return 'Opening…';
			case 'saving':
				return 'Saving…';
			case 'dirty':
				return 'Unsaved changes';
			case 'saved':
			case 'clean':
				return 'Saved';
		}
	}

	/** Tone for the save-state dot: positive (saved), warning (unsaved), neutral (in-flight). */
	export function saveStateTone(s: EditorSaveState): 'positive' | 'warning' | 'neutral' {
		if (s === 'dirty') return 'warning';
		if (s === 'saved' || s === 'clean') return 'positive';
		return 'neutral';
	}

	/** The dot is animated while the editor is loading or mid-save. */
	export function saveStatePulses(s: EditorSaveState): boolean {
		return s === 'loading' || s === 'saving';
	}

	export type EditorPhase = 'loading' | 'error' | 'ready';

	/**
	 * Whether "Done — hand back" is clickable (ADR-F047 Slice 5): the editor is up
	 * ('ready') and no save / hand-back is currently in flight. Enablement deliberately
	 * does NOT wait on Collabora's `Document_Loaded` postMessage (reliable on a real open
	 * but it can lag/flake) — the click itself guarantees the save (a dirty/unknown doc
	 * is saved before handing back), so a stuck postMessage never traps the lawyer with a
	 * dead button.
	 */
	export function canHandBack(
		phase: EditorPhase,
		saveState: EditorSaveState,
		handingBack: boolean
	): boolean {
		return phase === 'ready' && saveState !== 'saving' && !handingBack;
	}

	/**
	 * The editable suggested chat message the hand-back primes into the composer
	 * (ADR-F047 Slice 5). The lawyer instructs the agent via the normal chat box; this
	 * is just a sensible default they can edit or replace — it names the document and
	 * asks the agent to re-read + incorporate, which drives review_edited_document.
	 */
	export function handBackInstruction(filename: string): string {
		return (
			`I've reviewed and edited "${filename}" in the editor. ` +
			'Please re-read it, incorporate my changes, and continue.'
		);
	}

	/**
	 * One tick of the save-before-hand-back wait (ADR-F047 Slice 5): given whether a
	 * 'saving' has been observed and the current save-state, decide whether the save has
	 * LANDED, FAILED (came back to 'dirty' after saving — edits still unsaved), or is
	 * still PENDING. Pure so the load-bearing "never hand back unsaved work" decision is
	 * unit-tested; only the polling loop + timeout around it are untested glue.
	 */
	export function saveTickOutcome(
		sawSaving: boolean,
		s: EditorSaveState
	): 'saved' | 'failed' | 'pending' {
		if (s === 'saved' || s === 'clean') return 'saved';
		if (sawSaving && s === 'dirty') return 'failed';
		return 'pending';
	}

	/**
	 * What a `reloadNonce` bump does (ADR-F081: the agent updated THIS document's
	 * bytes in place). With nothing unsaved the panel reloads immediately (a fresh
	 * Collabora session over the new bytes); with unsaved edits — or a save still
	 * in flight — it shows the update banner instead, because a forced reload
	 * would destroy them. Pure so the "never destroy unsaved work" call is
	 * unit-tested; the effect around it is glue.
	 */
	export function reloadNonceAction(s: EditorSaveState): 'reload' | 'banner' {
		return s === 'dirty' || s === 'saving' ? 'banner' : 'reload';
	}

	/**
	 * Minimal shape of Collabora's same-origin client map (internal API). We do NOT
	 * use its `getScaleZoom` (it reports a base-2 zoom delta, but the real pixel
	 * scaling is ~1.2×/level, so a computed jump undershoots) — we iterate off the
	 * MEASURED `_docPixelSize` instead (see `nextFitAction`).
	 */
	export type CoolMap = {
		getSize?: () => { x: number };
		getZoom?: () => number;
		getMinZoom?: () => number;
		getMaxZoom?: () => number;
		setZoom?: (z: number) => void;
		_docLayer?: { _docPixelSize?: { x: number } | null } | null;
	};

	export type FitAction = { kind: 'grow' | 'shrink' | 'done'; zoom?: number };

	// The target band for the doc width as a fraction of the pane width: fill at
	// least 92% but never overflow (a touch under 100% leaves the page edge inside
	// the pane). Discrete zoom steps mean we can't always land inside the band; the
	// caller grows toward it and backs off one level on overflow.
	const FIT_MIN_RATIO = 0.92;
	const FIT_MAX_RATIO = 0.99;

	/**
	 * One step of an ITERATIVE fit-to-width, given the current doc width, pane
	 * width and zoom level. Collabora's `getScaleZoom` reports a base-2 zoom delta
	 * but its actual doc-pixel scaling is ~1.2×/level, so a single computed jump
	 * lands short — instead we adjust ONE level at a time off the MEASURED doc width
	 * (version-agnostic) and re-measure next tick:
	 *   - overflowing the pane → shrink one level and accept (no horizontal scroll);
	 *   - underfilling → grow one level toward the pane;
	 *   - within the band (or clamped at min/max) → done.
	 * Pure + defensive: not-ready inputs return `done` so a caller never loops.
	 */
	export function nextFitAction(s: {
		docPx: number | null | undefined;
		containerW: number | null | undefined;
		zoom: number;
		min: number;
		max: number;
	}): FitAction {
		const { docPx, containerW, zoom, min, max } = s;
		if (!containerW || !docPx || docPx <= 0 || !Number.isFinite(zoom)) return { kind: 'done' };
		const ratio = docPx / containerW;
		if (ratio > FIT_MAX_RATIO)
			return zoom > min ? { kind: 'shrink', zoom: zoom - 1 } : { kind: 'done' };
		if (ratio < FIT_MIN_RATIO)
			return zoom < max ? { kind: 'grow', zoom: zoom + 1 } : { kind: 'done' };
		return { kind: 'done' };
	}
</script>

<script lang="ts">
	/**
	 * In-app Word editor panel (ADR-F047, Slice 4). Hosts the Collabora/CODE
	 * editor in an iframe over WOPI, wrapped in our own Vercel-charcoal chrome so
	 * it reads as part of the cockpit, not a third-party tool. The lawyer opens an
	 * agent-redlined `.docx`, edits/comments, and Ctrl-S saves back through the
	 * Slice-3 WOPI PutFile (first save snapshots the agent draft, then mutates the
	 * live doc in place).
	 *
	 * Launch: mint a file-scoped session + resolve the loader URL in parallel
	 * (`openEditorSession`), then form-POST the `access_token` into the iframe so
	 * it never lands in a URL. The editor is same-origin (the nginx Collabora
	 * proxy), so its postMessage events are origin-checkable; we map them to a
	 * Saved / Unsaved indicator. Collabora never sees the user's session JWT.
	 */
	import { onDestroy, onMount, tick } from 'svelte';
	import { fade } from 'svelte/transition';
	import CheckIcon from '@lucide/svelte/icons/check';
	import FileTextIcon from '@lucide/svelte/icons/file-text';
	import XIcon from '@lucide/svelte/icons/x';

	import { Button } from '$lib/components/ui/button/index.js';
	import { editorApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import type { EditorSession } from '$lib/lq-ai/types';
	// `EditorSaveState` is imported in the `<script module>` block above; Svelte
	// merges both blocks into one module, so a re-import here is a duplicate.

	let {
		fileId,
		filename,
		reloadNonce = 0,
		onClose,
		onHandBack
	}: {
		fileId: string;
		filename: string;
		// ADR-F081: bumped by the host when the agent updates THIS file's bytes in
		// place — the panel reloads (or banners, if edits are unsaved). Optional.
		reloadNonce?: number;
		onClose: () => void;
		// ADR-F047 Slice 5: hand back to the agent. Optional — when absent (e.g. a
		// view-only mount) the button is not rendered and the editor is save+close only.
		onHandBack?: (filename: string) => void;
	} = $props();

	let phase = $state<EditorPhase>('loading');
	let errorMsg = $state('');
	let editorSrc = $state('');
	let session = $state<EditorSession | null>(null);
	let saveState = $state<EditorSaveState>('loading');
	let formEl = $state<HTMLFormElement | null>(null);
	let iframeEl = $state<HTMLIFrameElement | null>(null);
	// False until the fit-to-width has converged (or its safety cap fires). Drives
	// an overlay so the lawyer never sees Collabora's cold ~30% render jump to the
	// fitted size — they just see a spinner, then the document at the right width.
	let fitted = $state(false);
	// ADR-F047 Slice 5 "Done — hand back": true while saving-before-handing-back; the
	// error shows if that save fails (we never hand back unsaved work).
	let handingBack = $state(false);
	let handBackError = $state('');
	// ADR-F081: the agent updated this document while the lawyer has unsaved edits —
	// show the dismissible "Reload latest" banner instead of destroying their work.
	let updateBanner = $state(false);

	// Reskin: open Collabora in its slim CLASSIC toolbar (not the heavy tabbed
	// notebookbar) and drop the properties sidebar + ruler, so the editor reads
	// as a clean document surface under our own chrome rather than the full
	// LibreOffice UI. The menubar is hidden after load via postMessage. Deeper
	// charcoal theming of the residual toolbar is incremental (ADR-F047 / #13224).
	const UI_DEFAULTS = 'UIMode=classic;TextRuler=false;TextSidebar=false';

	// A stable iframe name (the form's POST target). One editor open at a time,
	// but key off fileId so a remount targets a fresh frame.
	const frameName = $derived(`lq-editor-frame-${fileId}`);

	// Out-of-order guard: opening a different file must not let a slow first load
	// clobber the second.
	let loadGen = 0;

	async function load(id: string = fileId) {
		const gen = ++loadGen;
		teardownFit();
		stopReadyPings();
		fitted = false;
		phase = 'loading';
		saveState = 'loading';
		errorMsg = '';
		// Any (re)load serves the current bytes — a pending update banner is stale.
		updateBanner = false;
		try {
			const { src, session: s } = await editorApi.openEditorSession(id, window.location.origin);
			if (gen !== loadGen) return; // superseded by a newer open
			editorSrc = src;
			session = s;
			phase = 'ready';
			// The iframe + hidden form render now; POST the file-scoped token into the
			// frame. Collabora's initial fit doesn't matter — the fit poll + the resize
			// observer (scheduleFitToWidth) drive the page to the pane width once the
			// client map appears and re-fit on any later width change.
			await tick();
			if (gen !== loadGen) return;
			formEl?.submit();
		} catch (e) {
			if (gen !== loadGen) return;
			errorMsg =
				e instanceof LQAIApiError
					? e.message
					: e instanceof Error
						? e.message
						: 'Could not open the editor.';
			phase = 'error';
		}
	}

	// (Re)launch whenever the target file changes — reading fileId as the load
	// argument here is what registers the effect's dependency on it.
	$effect(() => {
		void load(fileId);
	});

	// ADR-F081: the host bumped reloadNonce — the agent rewrote THIS file's bytes in
	// place (same fileId, so the load effect above never re-fires). Clean → reload a
	// fresh Collabora session over the new bytes; unsaved edits (or a save mid-flight)
	// → banner, never a destructive reload. Tracking the LAST value (DocumentsPanel's
	// reloadKey pattern) also inertly absorbs the initial value on mount — whether
	// that is 0 (first open) or a carried-over count (the host's nonce survives an
	// editor close/reopen).
	// svelte-ignore state_referenced_locally
	let lastReloadNonce = reloadNonce;
	$effect(() => {
		if (reloadNonce === lastReloadNonce) return;
		lastReloadNonce = reloadNonce;
		if (reloadNonceAction(saveState) === 'banner') updateBanner = true;
		else void load(fileId);
	});

	// "Reload latest" from the update banner: the lawyer chose to drop their unsaved
	// edits and open the agent's new version. load() clears the banner itself.
	function reloadLatest() {
		void load(fileId);
	}

	// Collabora posts save/load status to our origin (CheckFileInfo
	// PostMessageOrigin). The editor is same-origin, so reject anything else.
	function onMessage(e: MessageEvent) {
		if (e.origin !== window.location.origin) return;
		let msg: { MessageId?: unknown; Values?: unknown };
		try {
			msg = typeof e.data === 'string' ? JSON.parse(e.data) : e.data;
		} catch {
			return;
		}
		if (!msg || typeof msg.MessageId !== 'string') return;
		// COOL answered → it's listening; stop the readiness pings.
		stopReadyPings();
		const values = (msg.Values ?? undefined) as
			| { Status?: string; Modified?: boolean; success?: boolean }
			| undefined;
		const next = editorApi.saveStateFromMessage(msg.MessageId, values);
		if (next) saveState = next;
		// Once the document is up, drop Collabora's own menubar (our chrome owns the
		// frame) and (re)start the fit-to-width poll. This is belt-and-suspenders
		// with the onFrameLoad trigger — whichever signal lands first starts it.
		if (msg.MessageId === 'App_LoadingStatus' && values?.Status === 'Document_Loaded') {
			postToEditor({ MessageId: 'Hide_Menubar' });
			scheduleFitToWidth();
		}
	}

	// Send a command to the editor iframe (Collabora's postMessage API).
	function postToEditor(message: Record<string, unknown>) {
		iframeEl?.contentWindow?.postMessage(JSON.stringify(message), window.location.origin);
	}

	// `CoolMap` + the pure `nextFitAction(...)` live in the `<script module>` block
	// above (unit-tested); this reaches the live map off the same-origin iframe.
	function getCoolMap(): CoolMap | undefined {
		return (iframeEl?.contentWindow as unknown as { app?: { map?: CoolMap } } | null | undefined)
			?.app?.map;
	}

	// One iterative fit step against the live map. Collabora opens a Writer doc at a
	// stuck low zoom and exposes NO zoom postMessage, so we drive the same-origin
	// client map directly — adjusting ONE level per call off the MEASURED doc width
	// (its getScaleZoom is base-2 but the real pixel scaling is ~1.2×/level, so a
	// single computed jump lands short). Returns true once converged (so the poll
	// stops). Fully guarded — if a Collabora version renames these internals every
	// call no-ops and we simply keep Collabora's default zoom.
	function applyFitStep(): boolean {
		try {
			const map = getCoolMap();
			const docPx = map?._docLayer?._docPixelSize?.x;
			const containerW = map?.getSize?.().x;
			if (!map?.setZoom || !map.getZoom || !docPx || docPx <= 0 || !containerW) return false;
			const action = nextFitAction({
				docPx,
				containerW,
				zoom: map.getZoom(),
				min: map.getMinZoom?.() ?? 1,
				max: map.getMaxZoom?.() ?? 18
			});
			if (action.kind === 'done') return true;
			map.setZoom(action.zoom as number);
			// A shrink is the overflow back-off → the highest no-overflow level → done;
			// a grow keeps iterating next tick.
			return action.kind === 'shrink';
		} catch {
			/* graceful: keep Collabora's default zoom */
			return false;
		}
	}

	// Two cooperating mechanisms, both off the same-origin map (NOT the unreliable
	// one-shot Document_Loaded postMessage): (1) a readiness POLL that iterates the
	// fit as soon as the client map appears — the doc just loaded and there may be
	// no resize event to drive it — and reveals the editor (fitted=true) once it
	// converges or a safety cap fires; (2) a ResizeObserver that re-runs the poll
	// after the pane settles at a NEW width (slide-in, the practice-area rail
	// collapsing, a browser-window resize), so the page keeps filling the pane
	// instead of leaving whitespace to the right.
	let fitPoll: ReturnType<typeof setInterval> | null = null;
	let fitObserver: ResizeObserver | null = null;
	let fitObserverTimer: ReturnType<typeof setTimeout> | null = null;
	function stopFitPoll() {
		if (fitPoll) {
			clearInterval(fitPoll);
			fitPoll = null;
		}
	}
	function teardownFit() {
		stopFitPoll();
		if (fitObserver) {
			fitObserver.disconnect();
			fitObserver = null;
		}
		if (fitObserverTimer) {
			clearTimeout(fitObserverTimer);
			fitObserverTimer = null;
		}
	}
	function mapReadyToFit(): boolean {
		const map = getCoolMap();
		return !!(
			map?.setZoom &&
			map.getZoom &&
			map.getSize?.().x &&
			(map._docLayer?._docPixelSize?.x ?? 0) > 0
		);
	}
	function startFitPoll() {
		stopFitPoll();
		// Count the two phases SEPARATELY: Collabora's cold boot can take ~15-20s
		// before the doc renders, and we must not burn the iteration budget waiting.
		let waitTicks = 0; // ticks before the client map + doc pixels exist
		let fitTicks = 0; // ticks spent actually iterating the fit, once ready
		let lastPaneW = -1; // Collabora's getSize().x last tick (it lags element resize)
		fitPoll = setInterval(() => {
			// The WHOLE tick is guarded: every same-origin map reach below
			// (mapReadyToFit, getSize, applyFitStep) can in principle throw on a
			// cross-navigated/torn-down frame, and a throw must never pin the spinner
			// or leak the interval — on any failure we reveal and stop, degrading to
			// Collabora's own zoom (the slice's "never breaks the editor" contract).
			try {
				if (!mapReadyToFit()) {
					waitTicks += 1;
					if (waitTicks >= 100) {
						fitted = true; // ~40s ceiling for the doc to appear at all → reveal
						stopFitPoll();
					}
					return;
				}
				fitTicks += 1;
				const paneW = getCoolMap()?.getSize?.().x ?? -1;
				const done = applyFitStep();
				// Collabora's getSize() can lag the iframe resize by a tick or two; only
				// conclude when the fit is done AND the measured pane width has stopped
				// changing — otherwise a shrink computed against a stale (large) width
				// would wrongly look fitted and leave the doc overflowing the new width.
				const stable = paneW === lastPaneW;
				lastPaneW = paneW;
				if (done && stable) {
					fitted = true; // converged at a settled width → reveal the editor
					stopFitPoll();
					return;
				}
				if (fitTicks >= 30) {
					fitted = true; // ~12s of iterating: reveal regardless so we never hang
					stopFitPoll();
				}
			} catch {
				fitted = true; // a thrown reach must not hang the spinner / leak the timer
				stopFitPoll();
			}
		}, 400);
	}
	function installFitObserver() {
		if (fitObserver || typeof ResizeObserver === 'undefined' || !iframeEl) return;
		fitObserver = new ResizeObserver(() => {
			if (fitObserverTimer) clearTimeout(fitObserverTimer);
			// Re-converge after the pane settles. fitted stays true, so this never
			// re-shows the overlay — it just keeps the page filling the new width.
			fitObserverTimer = setTimeout(() => startFitPoll(), 200);
		});
		fitObserver.observe(iframeEl);
	}
	function scheduleFitToWidth() {
		installFitObserver();
		startFitPoll();
	}

	// Collabora only starts emitting its lifecycle postMessages (App_LoadingStatus,
	// Doc_ModifiedStatus, …) once the host announces it is listening — and cool.js
	// registers its own message listener slightly AFTER the iframe `load` fires, so
	// a single ping races it. Ping until COOL answers (onMessage stops us), capped.
	let readyPings: ReturnType<typeof setInterval> | null = null;
	function stopReadyPings() {
		if (readyPings) {
			clearInterval(readyPings);
			readyPings = null;
		}
	}
	function onFrameLoad() {
		// The iframe navigated (the form-POST landed the document). Start the
		// fit-to-width poll here too — it does NOT depend on the unreliable
		// Document_Loaded postMessage, just the same-origin client map appearing.
		scheduleFitToWidth();
		let tries = 0;
		stopReadyPings();
		readyPings = setInterval(() => {
			postToEditor({ MessageId: 'Host_PostmessageReady' });
			if (++tries >= 20) stopReadyPings(); // ~10s ceiling
		}, 500);
	}

	// "Done — hand back" (ADR-F047 Slice 5): guarantee the lawyer's edits are saved,
	// then return control to the conversation (the parent closes the editor + primes
	// the composer; the lawyer's own chat message resumes the run). Never hand back on
	// unsaved work — a dirty doc is saved first and only handed back once the save lands.
	function waitForSaved(timeoutMs: number): Promise<boolean> {
		return new Promise((resolve) => {
			let sawSaving = saveState === 'saving';
			const started = Date.now();
			const iv = setInterval(() => {
				if (saveState === 'saving') sawSaving = true;
				const outcome = saveTickOutcome(sawSaving, saveState);
				if (outcome === 'saved') {
					clearInterval(iv);
					resolve(true);
				} else if (outcome === 'failed' || Date.now() - started > timeoutMs) {
					// failed = save came back to 'dirty' (edits still unsaved); or timed out.
					clearInterval(iv);
					resolve(false);
				}
			}, 150);
		});
	}

	async function requestHandBack() {
		if (handingBack || !onHandBack) return;
		handBackError = '';
		if (saveState === 'saved' || saveState === 'clean') {
			onHandBack(filename); // nothing unsaved — hand back immediately
			return;
		}
		handingBack = true;
		postToEditor({ MessageId: 'Action_Save' });
		const ok = await waitForSaved(15000);
		handingBack = false;
		if (ok) onHandBack(filename);
		else handBackError = 'Could not save your changes — please try again before handing back.';
	}

	onMount(() => {
		window.addEventListener('message', onMessage);
	});
	onDestroy(() => {
		window.removeEventListener('message', onMessage);
		stopReadyPings();
		teardownFit();
	});

	const tone = $derived(saveStateTone(saveState));
</script>

<!-- `w-full` is load-bearing: this section is the flex child of the 2/3 editor
     card slot (ConversationHost `lq-cockpit-editor`); without it the section
     shrinks to its content (~iframe intrinsic width) and leaves whitespace to the
     right of the document instead of filling the slot. -->
<section
	class="flex h-full w-full min-h-0 flex-col bg-card"
	data-testid="lq-document-editor"
	aria-label="Document editor"
>
	<!-- Our chrome — a slim charcoal bar over the canvas, so the editor reads as
	     part of the cockpit rather than a third-party app. -->
	<header
		class="flex h-11 shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-3"
	>
		<div class="flex min-w-0 items-center gap-2">
			<FileTextIcon class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
			<span class="truncate text-sm font-medium text-foreground" title={filename}>{filename}</span>
		</div>
		<div class="flex shrink-0 items-center gap-3">
			{#if phase === 'ready' && saveState !== 'loading'}
				<span
					class="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground"
					data-testid="lq-editor-savestate"
					aria-live="polite"
				>
					<span
						class="size-1.5 rounded-full {tone === 'positive'
							? 'bg-brand'
							: tone === 'warning'
								? 'bg-amber-500'
								: 'bg-muted-foreground'} {saveStatePulses(saveState) ? 'animate-pulse' : ''}"
						aria-hidden="true"
					></span>
					{saveStateLabel(saveState)}
				</span>
			{/if}
			{#if onHandBack}
				{#if handBackError}
					<span
						class="max-w-xs truncate text-xs text-destructive"
						data-testid="lq-editor-handback-error"
					>
						{handBackError}
					</span>
				{/if}
				<Button
					type="button"
					variant="default"
					size="sm"
					class="h-7 gap-1.5 px-2.5"
					data-testid="lq-editor-handback"
					disabled={!canHandBack(phase, saveState, handingBack)}
					onclick={requestHandBack}
				>
					{#if handingBack}
						<span
							class="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
							aria-hidden="true"
						></span>
						Saving…
					{:else}
						<CheckIcon class="size-3.5" aria-hidden="true" />
						Done — hand back
					{/if}
				</Button>
			{/if}
			<Button
				type="button"
				variant="ghost"
				size="sm"
				class="h-7 gap-1.5 px-2"
				data-testid="lq-editor-close"
				onclick={onClose}
			>
				<XIcon class="size-3.5" aria-hidden="true" />
				Close
			</Button>
		</div>
	</header>

	{#if updateBanner}
		<!-- ADR-F081: the agent updated this document in place while the lawyer has
		     unsaved edits — offer the reload, never force it. -->
		<div
			class="flex shrink-0 items-center justify-between gap-3 border-b border-border bg-muted/60 px-3 py-2"
			data-testid="lq-editor-update-banner"
			transition:fade={{ duration: 120 }}
		>
			<p class="min-w-0 text-xs text-muted-foreground">
				The agent updated this document. Reload to open the latest version — unsaved changes here
				will be lost.
			</p>
			<div class="flex shrink-0 items-center gap-1.5">
				<Button
					type="button"
					variant="outline"
					size="sm"
					class="h-7 px-2.5"
					data-testid="lq-editor-reload-latest"
					onclick={reloadLatest}
				>
					Reload latest
				</Button>
				<Button
					type="button"
					variant="ghost"
					size="sm"
					class="h-7 px-2"
					aria-label="Dismiss update notice"
					data-testid="lq-editor-update-dismiss"
					onclick={() => (updateBanner = false)}
				>
					<XIcon class="size-3.5" aria-hidden="true" />
				</Button>
			</div>
		</div>
	{/if}

	<div class="relative min-h-0 flex-1">
		{#if phase === 'loading'}
			<div
				class="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-card"
				data-testid="lq-editor-loading"
				in:fade={{ duration: 120 }}
			>
				<span
					class="size-6 animate-spin rounded-full border-2 border-border border-t-brand"
					aria-hidden="true"
				></span>
				<p class="text-sm text-muted-foreground">Opening document…</p>
			</div>
		{:else if phase === 'error'}
			<div
				class="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center"
				data-testid="lq-editor-error"
			>
				<p class="text-sm font-medium text-foreground">Couldn’t open the editor</p>
				<p class="max-w-prose text-sm text-muted-foreground">{errorMsg}</p>
				<Button type="button" variant="outline" size="sm" onclick={() => load()}>Try again</Button>
			</div>
		{/if}
		{#if phase === 'ready'}
			<!-- Hidden launcher: POSTs the file-scoped token into the frame so it
			     never appears in a URL/history. Submitted once per load(). -->
			<form
				bind:this={formEl}
				method="POST"
				action={editorSrc}
				target={frameName}
				class="hidden"
				aria-hidden="true"
			>
				<input type="hidden" name="access_token" value={session?.access_token ?? ''} />
				<input
					type="hidden"
					name="access_token_ttl"
					value={String(session?.access_token_ttl ?? '')}
				/>
				<input type="hidden" name="ui_defaults" value={UI_DEFAULTS} />
			</form>
			<iframe
				bind:this={iframeEl}
				onload={onFrameLoad}
				name={frameName}
				title="Document editor"
				class="size-full border-0 bg-card"
				data-testid="lq-editor-frame"
				allow="clipboard-read; clipboard-write"
			></iframe>
			{#if !fitted}
				<!-- Cover Collabora's cold ~30% first render until the fit converges, then
				     fade out — the lawyer sees a spinner, then the document already at the
				     right width (no visible zoom jump). -->
				<div
					class="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-card"
					data-testid="lq-editor-fitting"
					out:fade={{ duration: 160 }}
				>
					<span
						class="size-6 animate-spin rounded-full border-2 border-border border-t-brand"
						aria-hidden="true"
					></span>
					<p class="text-sm text-muted-foreground">Opening document…</p>
				</div>
			{/if}
		{/if}
	</div>
</section>
