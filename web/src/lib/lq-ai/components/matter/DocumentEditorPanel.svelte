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
	import FileTextIcon from '@lucide/svelte/icons/file-text';
	import XIcon from '@lucide/svelte/icons/x';

	import { Button } from '$lib/components/ui/button/index.js';
	import { editorApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import type { EditorSession } from '$lib/lq-ai/types';
	// `EditorSaveState` is imported in the `<script module>` block above; Svelte
	// merges both blocks into one module, so a re-import here is a duplicate.

	let { fileId, filename, onClose }: { fileId: string; filename: string; onClose: () => void } =
		$props();

	let phase = $state<'loading' | 'error' | 'ready'>('loading');
	let errorMsg = $state('');
	let editorSrc = $state('');
	let session = $state<EditorSession | null>(null);
	let saveState = $state<EditorSaveState>('loading');
	let formEl = $state<HTMLFormElement | null>(null);
	let iframeEl = $state<HTMLIFrameElement | null>(null);

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
		phase = 'loading';
		saveState = 'loading';
		errorMsg = '';
		try {
			const { src, session: s } = await editorApi.openEditorSession(id, window.location.origin);
			if (gen !== loadGen) return; // superseded by a newer open
			editorSrc = src;
			session = s;
			phase = 'ready';
			// The iframe + hidden form render now; POST the token into the frame.
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
		// Once the document is up, drop Collabora's own menubar — our chrome owns
		// the frame (the toolbar stays for editing actions).
		if (msg.MessageId === 'App_LoadingStatus' && values?.Status === 'Document_Loaded') {
			postToEditor({ MessageId: 'Hide_Menubar' });
		}
	}

	// Send a command to the editor iframe (Collabora's postMessage API).
	function postToEditor(message: Record<string, unknown>) {
		iframeEl?.contentWindow?.postMessage(JSON.stringify(message), window.location.origin);
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
		let tries = 0;
		stopReadyPings();
		readyPings = setInterval(() => {
			postToEditor({ MessageId: 'Host_PostmessageReady' });
			if (++tries >= 20) stopReadyPings(); // ~10s ceiling
		}, 500);
	}

	onMount(() => {
		window.addEventListener('message', onMessage);
	});
	onDestroy(() => {
		window.removeEventListener('message', onMessage);
		stopReadyPings();
	});

	const tone = $derived(saveStateTone(saveState));
</script>

<section
	class="flex h-full min-h-0 flex-col bg-card"
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
		{/if}
	</div>
</section>
