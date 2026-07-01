<script lang="ts">
	/**
	 * Conversation surface for one matter (or the unfiled bucket) —
	 * re-homes the layout-agnostic ConversationPanel (built for exactly
	 * this in F0-S7) next to the matter's conversation list. Thread
	 * switching is by REMOUNT ({#key}), the panel's contract; composer
	 * draft + matter selection live HERE so they survive those remounts.
	 *
	 * Unfiled mode is resume-only: ADR-F002 offers no unbound composer —
	 * legacy threads stay readable and continuable, new conversations
	 * start inside a matter.
	 */
	import { onMount, tick } from 'svelte';
	import { fade, fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left';
	import InboxIcon from '@lucide/svelte/icons/inbox';
	import PlusIcon from '@lucide/svelte/icons/plus';
	import ShieldIcon from '@lucide/svelte/icons/shield';

	import { Button } from '$lib/components/ui/button/index.js';
	import * as Resizable from '$lib/components/ui/resizable';
	import { agentsApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import type { AgentThread, MatterActivity } from '$lib/lq-ai/api/agents';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { Project } from '$lib/lq-ai/types';
	import ConversationPanel from '$lib/lq-ai/components/agents/ConversationPanel.svelte';
	import RopaRegister from '$lib/lq-ai/components/ropa/RopaRegister.svelte';
	import ComplianceRegister from '$lib/lq-ai/components/compliance/ComplianceRegister.svelte';
	import MemoryPanel from '$lib/lq-ai/components/matter/MemoryPanel.svelte';
	import DocumentsPanel from '$lib/lq-ai/components/matter/DocumentsPanel.svelte';
	import GridsPanel from '$lib/lq-ai/components/matter/GridsPanel.svelte';
	import TabularWorkspace from '$lib/lq-ai/components/TabularWorkspace.svelte';
	import CapabilitiesPanel from '$lib/lq-ai/components/matter/CapabilitiesPanel.svelte';
	import DocumentEditorPanel, {
		handBackInstruction
	} from '$lib/lq-ai/components/matter/DocumentEditorPanel.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import NewMatterDialog from './NewMatterDialog.svelte';
	import StatusPill from './StatusPill.svelte';
	import { getCockpitState } from './context.svelte';
	import { MOTION, motionMs, timeAgo } from './helpers';

	const cockpit = getCockpitState();

	let {
		matter = null,
		unitLabel = 'Matter',
		areas = [],
		threadId,
		projects,
		projectsError,
		nowMs,
		initialDraft = '',
		onDraftConsumed,
		onBack,
		onSelectThread,
		onThreadCreated,
		onMatterCreated,
		onActivity
	}: {
		/** null = the unfiled bucket (resume-only). */
		matter?: MatterActivity | null;
		unitLabel?: string;
		/** Configured areas the new-matter dialog may file under (UX-B-5). */
		areas?: PracticeArea[];
		threadId: string | null;
		projects: Project[];
		projectsError: string | null;
		nowMs: number;
		/** F2-M4: a launcher draft to seed the fresh composer once on mount. */
		initialDraft?: string;
		/** Called after the launcher draft has been consumed (parent clears it). */
		onDraftConsumed?: () => void;
		onBack: () => void;
		onSelectThread: (threadId: string | null) => void;
		/** The composer created a NEW conversation — sync URL state (replaceState). */
		onThreadCreated: (detail: { threadId: string; projectId: string | null }) => void;
		/** A matter was quick-created from the composer — refresh the projects list. */
		onMatterCreated: (project: Project) => void;
		onActivity: () => void;
	} = $props();

	let threads = $state<AgentThread[] | null>(null);
	let threadsTotal = $state(0);
	let threadsError = $state<string | null>(null);
	// Out-of-order guard: a slow onMount fetch must not clobber a fresher
	// post-settle refresh (the legacy pages' generation pattern).
	let threadsGeneration = 0;

	// Composer draft + matter selection survive thread remounts (panel
	// contract). The cockpit remounts THIS component per matter ({#key}),
	// so capturing the INITIAL matter here is the design, not a bug —
	// the user may still re-point the composer's select for the next
	// conversation without the host fighting it.
	let prompt = $state('');
	// svelte-ignore state_referenced_locally
	let selectedMatterId = $state(matter?.project_id ?? '');
	let composerEpoch = $state(0);
	let createOpen = $state(false);

	// The thread the LIVE panel itself just created: when the URL catches
	// up to it (asynchronously, via replaceState) the {#key} must stay
	// STABLE — the panel is already showing that conversation mid-run and
	// a remount would drop the live stream. Cleared on every explicit
	// user selection (row click / New conversation), never reactively —
	// the URL update races the prop change.
	let panelOwnedThread = $state<string | null>(null);
	const panelKey = $derived(
		`${threadId !== null && threadId === panelOwnedThread ? 'live' : (threadId ?? 'fresh')}:${composerEpoch}`
	);

	// F1-S2.1 stacked mode: below 720px of HOST width the fixed w-72 aside
	// would crush the conversation — show list OR conversation, with a back
	// row. Width starts optimistic (side-by-side) so the first paint at
	// desktop sizes doesn't flash the stacked layout.
	let hostWidth = $state(1024);
	const isStacked = $derived(hostWidth < 720);
	// svelte-ignore state_referenced_locally
	let stackedShowPanel = $state(threadId !== null);

	// In-app Word editor (ADR-F047, Slice 4): when the agent redlines a document
	// (or the lawyer opens one from Documents), the editor slides in on the RIGHT
	// while the conversation stays on the left — so the lawyer edits the doc and
	// keeps talking to the agent side by side (the round-2 hand-back loop). The
	// shell collapses its practice-area rail (via cockpit.editorOpen) to free the
	// width. The conversation NEVER remounts when the editor opens/closes (the
	// live-SSE invariant): the conversation card is always the first flex child;
	// the editor is a sibling that flies in.
	let editorOpen = $state(false);
	let editorFileId = $state<string | null>(null);
	let editorFilename = $state('');

	// F2 Tabular T6 (ADR-F055): a grid is a review WORKSPACE, not a modal. Opening
	// one (Grids tab row / in-chat preview Expand) flies the full grid + docked
	// cell drawer in on the RIGHT — the SAME stage-takeover as the editor, so the
	// conversation stays MOUNTED (live SSE survives) and the shell rail collapses.
	// Mutually exclusive with the editor (one stage at a time).
	let gridOpen = $state(false);
	let gridId = $state<string | null>(null);

	// The thread list yields to the editor (focus on edit + the live chat); the
	// conversation column stays mounted and takes the freed width.
	const showList = $derived((!isStacked || !stackedShowPanel) && !editorOpen && !gridOpen);
	const showPanel = $derived(!isStacked || stackedShowPanel);

	// PRIV-3 (ADR-F019): a Privacy matter surfaces the company's read-only ROPA
	// register alongside the conversation via one calm toggle. AI Compliance does the
	// same with its AI-systems register (below); areas with no register see neither.
	const isPrivacyMatter = $derived(matter?.practice_area_key === 'privacy');
	// AIC-1 (ADR-F057): an AI Compliance matter surfaces the deployment-global
	// AI-systems register the same way a Privacy matter surfaces the ROPA register.
	// `isRegisterMatter` generalises the split-view gating over both; the render
	// slots pick the concrete component. Other areas see neither register.
	const isComplianceMatter = $derived(matter?.practice_area_key === 'ai-compliance');
	const isRegisterMatter = $derived(isPrivacyMatter || isComplianceMatter);
	const registerTabLabel = $derived(isComplianceMatter ? 'AI systems' : 'ROPA register');
	// C3c-2: every matter also gets a "Memory" tab onto its working-memory tier
	// (area-agnostic — ADR-F042/F044). C7a adds a "Documents" tab onto the matter's
	// files (incl. downloadable redline outputs — ADR-F046). 'register' is only for a
	// register-bearing area (Privacy ROPA / AI Compliance AI-systems).
	let matterTab = $state<
		'conversation' | 'register' | 'memory' | 'documents' | 'grids' | 'capabilities'
	>(
		'conversation'
	);

	// PRIV-9a: when a register matter (Privacy / AI Compliance) has the width, show
	// chat + the register side by side (resizable) instead of the one-at-a-time
	// toggle, so the user watches the register change as the agent works. Below the budget
	// (register ~400px + chat ~480px) we fall back to the toggle. The outer
	// thread list (w-72 = 288px) is subtracted from the host width.
	const SPLIT_MIN_PANEL = 880;
	const canSplitRegister = $derived(
		isRegisterMatter && !isStacked && !editorOpen && !gridOpen && hostWidth - 288 >= SPLIT_MIN_PANEL
	);

	// The tab strip for a real matter. 'conversation' always; 'register' only for
	// a narrow register matter (when wide it's co-visible in the split, not a tab);
	// 'memory' for every matter (C3c-2). The unfiled bucket (matter === null) gets
	// no strip — its resume-only flow stays single-pane.
	const matterTabs = $derived([
		{ id: 'conversation' as const, label: 'Conversation' },
		...(isRegisterMatter && !canSplitRegister
			? [{ id: 'register' as const, label: registerTabLabel }]
			: []),
		...(matter
			? [
					{ id: 'memory' as const, label: 'Memory' },
					{ id: 'documents' as const, label: 'Documents' },
					// F2 Tabular T7 (ADR-F055): the matter's agentic grids — derived
					// artifacts, sibling to Documents (source files). Full-width panel.
					{ id: 'grids' as const, label: 'Grids' },
					// ADR-F054: the capability panel — toggle the area's skills/tools/playbooks
					// (+ MCP placeholder) for this matter. Full-width panel like Memory/Documents.
					{ id: 'capabilities' as const, label: 'Capabilities' }
				]
			: [])
	]);

	// Memory, Documents and Capabilities are full-width panels: the conversation region
	// stays mounted but hidden behind any of them (the no-remount invariant — C3c-2).
	const matterPanelOpen = $derived(
		matterTab === 'memory' ||
			matterTab === 'documents' ||
			matterTab === 'grids' ||
			matterTab === 'capabilities'
	);

	// If the active tab leaves the strip (e.g. a Privacy matter widens past the
	// split budget, retiring the 'register' tab), fall back to the conversation so
	// the strip never shows nothing selected. Self-healing, no loop: the reset
	// lands on 'conversation', which is always present.
	$effect(() => {
		if (!matterTabs.some((t) => t.id === matterTab)) matterTab = 'conversation';
	});

	// Run-lock + live-register signals (PRIV-9a). `runActive` is bound OUT of the
	// conversation panel (the agent is working); `registerReloadKey` is bumped on
	// settle so the co-visible register does one final reconcile fetch.
	let runActive = $state(false);
	let registerReloadKey = $state(0);

	// PRIV-9b (ADR-F024): the ids of ROPA rows the agent just changed, hoisted
	// HERE (survives any register remount) and passed to RopaRegister to wash the
	// matching rows. The window must comfortably exceed the register's ~2s poll so
	// a row that only arrives on the NEXT poll still flashes; it resets on each new
	// change, so a burst of edits keeps the wash alive then fades together. The
	// fade itself is CSS (RopaRegister); this just bounds how long ids stay "fresh".
	const CHANGED_DECAY_MS = 5000;
	let recentlyChangedIds = $state<Set<string>>(new Set());
	let changedDecayTimer: ReturnType<typeof setTimeout> | null = null;

	function handleRopaChange(event: CustomEvent<{ kind: string; id: string; verb: string }>) {
		// Reassign (not mutate) so the prop reference changes — Svelte reactivity is
		// assignment-driven, and RopaRegister re-evaluates `changedIds.has(id)`.
		const next = new Set(recentlyChangedIds);
		next.add(event.detail.id);
		recentlyChangedIds = next;
		if (changedDecayTimer !== null) clearTimeout(changedDecayTimer);
		changedDecayTimer = setTimeout(() => {
			recentlyChangedIds = new Set();
			changedDecayTimer = null;
		}, CHANGED_DECAY_MS);
	}

	// Clear the decay timer if the host unmounts mid-window (per-matter remount).
	$effect(() => () => {
		if (changedDecayTimer !== null) clearTimeout(changedDecayTimer);
	});

	// Keep the stacked pane in sync with URL-driven thread changes (review
	// fix): a threadId ARRIVING (composer-created sync, history forward)
	// must show the panel — otherwise crossing the width threshold later
	// unmounts a live conversation, and back/forward desyncs URL from
	// pane. Transitions TO null stay hands-off: newConversation() already
	// chose the panel, backToList() already chose the list.
	// svelte-ignore state_referenced_locally
	let lastThreadId = threadId;
	$effect(() => {
		if (threadId !== lastThreadId) {
			lastThreadId = threadId;
			if (threadId !== null) stackedShowPanel = true;
		}
	});

	async function loadThreads() {
		const generation = ++threadsGeneration;
		try {
			const resp = matter
				? await agentsApi.listThreads({ projectId: matter.project_id, limit: 100 })
				: await agentsApi.listThreads({ unfiled: true, limit: 100 });
			if (generation !== threadsGeneration) return;
			threads = resp.threads;
			threadsTotal = resp.total_count;
			threadsError = null;
		} catch (e: unknown) {
			if (generation !== threadsGeneration) return;
			threadsError = e instanceof LQAIApiError ? e.message : 'network error';
		}
	}

	onMount(() => {
		loadThreads();
		// F2-M4: seed the composer from a launcher draft exactly once. This
		// host remounts per matter ({#key}), and the parent clears the draft on
		// consume, so only the FIRST matter reached after a launch gets it.
		if (initialDraft && !prompt) {
			prompt = initialDraft;
			onDraftConsumed?.();
		}
	});

	function handleSettled() {
		loadThreads();
		onActivity();
		// PRIV-9a: a run settled — nudge the co-visible register to reconcile its
		// final state (the live poll stops a tick before the very last write).
		registerReloadKey += 1;
	}

	function selectThread(id: string | null) {
		panelOwnedThread = null;
		stackedShowPanel = true;
		onSelectThread(id);
	}

	function newConversation() {
		panelOwnedThread = null;
		composerEpoch += 1;
		stackedShowPanel = true;
		onSelectThread(null);
	}

	function backToList() {
		// Stacked-mode back: unmounting the panel drops any live stream view,
		// but the run itself is durable (F1-S1) — the list shows its pill.
		// Clear the URL thread too (review fix): a reload/share of the list
		// view must not reopen the conversation.
		stackedShowPanel = false;
		panelOwnedThread = null;
		onSelectThread(null);
	}

	function handleThreadCreated(event: CustomEvent<{ threadId: string; projectId: string | null }>) {
		panelOwnedThread = event.detail.threadId;
		stackedShowPanel = true;
		onThreadCreated(event.detail);
		loadThreads();
	}

	function openEditor(fileId: string, filename: string) {
		// One stage at a time — close a grid workspace if it's up.
		gridOpen = false;
		gridId = null;
		editorFileId = fileId;
		editorFilename = filename;
		editorOpen = true;
		// Bring the conversation back beside the editor (don't leave Memory/Documents
		// occupying the left column).
		matterTab = 'conversation';
		// Below the side-by-side budget the editor needs the whole pane to be usable.
		if (isStacked) stackedShowPanel = true;
	}

	function closeEditor() {
		editorOpen = false;
		editorFileId = null;
	}

	// F2 Tabular T6: open a grid as a stage-takeover (from the Grids tab or the
	// in-chat preview's Expand). Mirrors openEditor — conversation beside the grid,
	// not the Grids list; the editor yields (one stage at a time).
	function openGrid(id: string) {
		editorOpen = false;
		editorFileId = null;
		gridId = id;
		gridOpen = true;
		matterTab = 'conversation';
		if (isStacked) stackedShowPanel = true;
	}

	// Closing returns to the Grids list so the breadcrumb "‹ Grids" is literal
	// regardless of where the grid was opened from.
	function closeGrid() {
		gridOpen = false;
		gridId = null;
		if (matter) matterTab = 'grids';
	}

	// ADR-F047 Slice 5 "Done — hand back": the editor has confirmed the save. Return
	// control to the conversation — close the editor, bring the conversation into view,
	// and prime the composer with an editable suggested instruction. The lawyer's own
	// chat message resumes the run (the existing submit() → createRun({prompt, thread_id})
	// path); on the next turn the agent calls review_edited_document to re-read the edits.
	async function handBackFromEditor(filename: string) {
		closeEditor();
		if (isStacked) stackedShowPanel = true;
		prompt = handBackInstruction(filename);
		// Focus the composer so the lawyer can edit/send immediately (best-effort;
		// the conversation pane must be mounted first).
		await tick();
		document.getElementById('ag-prompt')?.focus();
	}

	// The agent just produced a redline → slide the editor in automatically
	// (the maintainer's flow: the document opens for review the moment it's ready).
	// But never yank the lawyer off a DIFFERENT document they're already editing — a
	// new redline (e.g. from a parallel run) waits in the Documents tab instead.
	function handleRedlineReady(event: CustomEvent<{ fileId: string; filename: string }>) {
		if (editorOpen && editorFileId !== event.detail.fileId) return;
		openEditor(event.detail.fileId, event.detail.filename);
	}

	// Reflect editor state to the shell so it gracefully collapses the practice-area
	// rail while editing, and restore it (reset to false) when this host unmounts
	// (per-matter remount) or the editor closes.
	$effect(() => {
		// The grid stage-takeover collapses the shell rail just like the editor.
		cockpit.editorOpen = editorOpen || gridOpen;
		return () => {
			cockpit.editorOpen = false;
		};
	});
</script>

{#snippet conversationPane()}
	{#key panelKey}
		<!-- F2-M6: the conversation column shares the PageShell idiom (`narrow`
		     width + `tight` pad). Fade on an inner div (PageShell is a component). -->
		<PageShell size="narrow" pad="tight">
			<div in:fade={{ duration: motionMs(MOTION.fast) }}>
				<ConversationPanel
					initialThreadId={threadId}
					matters={projects}
					mattersError={projectsError}
					bind:prompt
					bind:selectedMatterId
					bind:runActive
					on:settled={handleSettled}
					on:newmatter={() => (createOpen = true)}
					on:threadcreated={handleThreadCreated}
					on:ropachange={handleRopaChange}
					on:compliancechange={handleRopaChange}
					on:redlineready={handleRedlineReady}
					on:expandgrid={(e) => openGrid(e.detail.gridId)}
				/>
			</div>
		</PageShell>
	{/key}
{/snippet}

<!-- The conversation workspace FLOATS as one card on the canvas (F1-S2.1
     elevation scale): recessed thread list inside it, conversation column
     to the right — three honest surface steps instead of one flat sheet. -->
<div
	class="h-full min-h-0 p-2 sm:p-3"
	data-testid="lq-cockpit-conversation"
	bind:clientWidth={hostWidth}
	in:fade|global={{ duration: motionMs(MOTION.base) }}
>
	<!-- Conversation card + (optional) editor, side by side. The card is ALWAYS the
	     first child so the live conversation never remounts when the editor opens or
	     closes (ADR-F047); the editor flies in from the right as a sibling. On a narrow
	     (stacked) host a 50/50 split is unusable, so the card is hidden (kept MOUNTED —
	     live SSE survives) and the editor takes the whole pane. -->
	<div class="flex h-full min-h-0 gap-2 sm:gap-3">
		<div
			class="flex h-full min-h-0 overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-[flex-grow] duration-200 ease-out {editorOpen ||
			gridOpen
				? 'min-w-0 flex-1 basis-0'
				: 'w-full'}"
			class:hidden={(editorOpen || gridOpen) && isStacked}
		>
			{#if showList}
				<aside
					class="flex min-h-0 shrink-0 flex-col {isStacked
						? 'w-full'
						: 'w-72 border-r border-border bg-muted/40'}"
				>
					<div class="shrink-0 border-b border-border px-4 py-3">
						<button
							type="button"
							class="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors duration-150 hover:text-foreground"
							onclick={onBack}
						>
							<ChevronLeftIcon class="size-3.5" aria-hidden="true" />
							{matter ? `${unitLabel}s` : 'Practice areas'}
						</button>
						<h2 class="mt-1.5 truncate text-sm font-semibold text-foreground">
							{#if matter}
								{matter.name}
								{#if matter.privileged}
									<ShieldIcon
										class="ml-1 inline size-3.5 align-[-2px] text-muted-foreground"
										aria-label="Privileged"
									/>
								{/if}
							{:else}
								Unfiled conversations
							{/if}
						</h2>
						{#if matter}
							<Button
								size="sm"
								variant="outline"
								class="mt-2.5 w-full gap-1.5"
								data-testid="lq-cockpit-new-conversation"
								onclick={newConversation}
							>
								<PlusIcon class="size-4" aria-hidden="true" />
								New conversation
							</Button>
						{:else}
							<p class="mt-1.5 text-xs text-muted-foreground">
								Legacy conversations without a {unitLabel.toLowerCase()}. Resume them here — new
								conversations start inside a {unitLabel.toLowerCase()}.
							</p>
						{/if}
					</div>
					<nav
						class="min-h-0 flex-1 overflow-y-auto scroll-smooth overscroll-contain px-2 py-2"
						aria-label="Conversations"
					>
						{#if threadsError}
							<p class="px-2 py-1 text-sm text-destructive">
								Couldn't load conversations: {threadsError}
							</p>
						{:else if threads === null}
							<div class="space-y-1 px-2 py-1" aria-hidden="true">
								{#each [0, 1, 2] as i (i)}
									<div class="h-12 animate-pulse rounded-md bg-muted/70"></div>
								{/each}
							</div>
						{:else if threads.length === 0}
							<p class="px-2 py-1 text-xs text-muted-foreground">
								{matter ? 'No conversations yet — ask the agent something.' : 'Nothing here.'}
							</p>
						{:else}
							<ul class="space-y-0.5">
								{#each threads as t (t.id)}
									<li>
										<button
											type="button"
											class="flex w-full flex-col gap-0.5 rounded-md px-2.5 py-2 text-left text-foreground transition-colors duration-150 ease-out hover:bg-muted/60 {threadId ===
											t.id
												? 'bg-accent text-accent-foreground'
												: ''}"
											data-testid="lq-cockpit-thread-row"
											onclick={() => selectThread(t.id)}
										>
											<span class="line-clamp-2 text-xs font-medium">{t.title}</span>
											<span class="flex items-center justify-between gap-2">
												<StatusPill status={t.last_run_status} lastRunAt={t.last_run_at} {nowMs} />
												<span class="text-[11px] text-muted-foreground tabular-nums">
													{timeAgo(t.last_run_at, nowMs)}
												</span>
											</span>
										</button>
									</li>
								{/each}
							</ul>
							{#if threads !== null && threadsTotal > threads.length}
								<p class="px-2.5 py-2 text-[11px] text-muted-foreground tabular-nums">
									Showing {threads.length} of {threadsTotal} — older conversations are on the legacy agents
									page.
								</p>
							{/if}
						{/if}
					</nav>
				</aside>
			{/if}

			{#if showPanel}
				<section class="flex min-h-0 min-w-0 flex-1 flex-col">
					{#if isStacked}
						<div class="shrink-0 border-b border-border px-4 py-2">
							<button
								type="button"
								class="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors duration-150 hover:text-foreground"
								data-testid="lq-cockpit-back-to-list"
								onclick={backToList}
							>
								<ChevronLeftIcon class="size-3.5" aria-hidden="true" />
								Conversations
							</button>
						</div>
					{/if}
					{#if matter}
						<!-- PRIV-3 + C3c-2: switch the panel column between the conversation,
					     the company ROPA register (Privacy only), and the matter's Memory. -->
						<div
							class="flex shrink-0 gap-1 border-b border-border px-4 py-2"
							role="tablist"
							aria-label="Matter view"
						>
							{#each matterTabs as t (t.id)}
								<button
									type="button"
									role="tab"
									aria-selected={matterTab === t.id}
									class="rounded-md px-2.5 py-1 text-xs font-medium transition-colors duration-150 {matterTab ===
									t.id
										? 'bg-muted text-foreground'
										: 'text-muted-foreground hover:text-foreground'}"
									data-testid="lq-cockpit-matter-tab-{t.id}"
									onclick={() => (matterTab = t.id)}
								>
									{t.label}
								</button>
							{/each}
						</div>
					{/if}
					<!-- Conversation + register region: stays MOUNTED (hidden while Memory or
				     Documents is open) so the live run stream + runActive keep flowing — never
				     remounted on a tab switch (the invariant the narrow fallback below protects). -->
					<div class="flex min-h-0 flex-1 flex-col" class:hidden={matterPanelOpen}>
						{#if canSplitRegister}
							<!-- PRIV-9a co-visible: chat | register, resizable, each scrolls
					     independently — watch the register change as the agent works. -->
							<div class="min-h-0 flex-1">
								<Resizable.PaneGroup
									direction="horizontal"
									autoSaveId="lq-priv-covisible"
									class="h-full"
								>
									<Resizable.Pane id="priv-chat" order={1} defaultSize={56} minSize={38}>
										<div class="h-full min-h-0 overflow-y-auto scroll-smooth overscroll-contain">
											{@render conversationPane()}
										</div>
									</Resizable.Pane>
									<Resizable.Handle
										class="transition-colors duration-150 ease-out hover:bg-primary/40 data-[active]:bg-primary/60"
									/>
									<Resizable.Pane id="priv-register" order={2} defaultSize={44} minSize={30}>
										<div
											class="h-full min-h-0 overflow-y-auto scroll-smooth overscroll-contain border-l border-border"
										>
											{#if isComplianceMatter}
												<ComplianceRegister
													{runActive}
													reloadKey={registerReloadKey}
													changedIds={recentlyChangedIds}
												/>
											{:else}
												<RopaRegister
													{runActive}
													reloadKey={registerReloadKey}
													changedIds={recentlyChangedIds}
												/>
											{/if}
										</div>
									</Resizable.Pane>
								</Resizable.PaneGroup>
							</div>
						{:else}
							<div class="min-h-0 flex-1 overflow-y-auto scroll-smooth overscroll-contain">
								{#if isRegisterMatter}
									<!-- Narrow fallback: chat and register are one-at-a-time, but the
							     conversation stays MOUNTED (hidden while the register shows) so its
							     run-state keeps flowing — the register still live-updates as the
							     agent works, just not side by side, and switching tabs never drops a
							     live stream. -->
									<div class="h-full" class:hidden={matterTab === 'register'}>
										{@render conversationPane()}
									</div>
									{#if matterTab === 'register'}
										{#if isComplianceMatter}
											<ComplianceRegister
												{runActive}
												reloadKey={registerReloadKey}
												changedIds={recentlyChangedIds}
											/>
										{:else}
											<RopaRegister
												{runActive}
												reloadKey={registerReloadKey}
												changedIds={recentlyChangedIds}
											/>
										{/if}
									{/if}
								{:else if matter || threadId}
									{@render conversationPane()}
								{:else}
									<div class="flex h-full items-center justify-center px-8">
										<div class="max-w-sm text-center">
											<div
												class="mx-auto flex size-10 items-center justify-center rounded-full bg-muted"
											>
												<InboxIcon class="size-5 text-muted-foreground" aria-hidden="true" />
											</div>
											<h2 class="mt-3 text-base font-semibold text-foreground">
												Pick a conversation
											</h2>
											<p class="mt-1 text-sm text-muted-foreground">
												Unfiled conversations are read-and-resume only. Select one on the left to
												continue it.
											</p>
										</div>
									</div>
								{/if}
							</div>
						{/if}
					</div>
					{#if matterTab === 'memory' && matter}
						<!-- Memory tab: full-width read panel over the C3c-1 GET/revert. -->
						<div class="min-h-0 flex-1 overflow-y-auto scroll-smooth overscroll-contain">
							<MemoryPanel
								projectId={matter.project_id}
								{runActive}
								reloadKey={registerReloadKey}
								{nowMs}
							/>
						</div>
					{/if}
					{#if matterTab === 'documents' && matter}
						<!-- Documents tab (C7a, ADR-F046): full-width read panel onto the matter's
					     files; each row downloads via GET /files/{id}/content. -->
						<div class="min-h-0 flex-1 overflow-y-auto scroll-smooth overscroll-contain">
							<DocumentsPanel
								projectId={matter.project_id}
								{runActive}
								reloadKey={registerReloadKey}
								{nowMs}
								onOpenEditor={openEditor}
							/>
						</div>
					{/if}
					{#if matterTab === 'grids' && matter}
						<!-- Grids tab (F2 Tabular T7, ADR-F055): full-width read panel listing the
					     matter's agentic grids; each row opens the reused grid at /tabular/[id]
					     and can be soft-deleted. reloadKey pulls once when a run settles. -->
						<div class="min-h-0 flex-1 overflow-y-auto scroll-smooth overscroll-contain">
							<GridsPanel
								projectId={matter.project_id}
								reloadKey={registerReloadKey}
								{nowMs}
								onOpenGrid={openGrid}
							/>
						</div>
					{/if}
					{#if matterTab === 'capabilities' && matter}
						<!-- Capabilities tab (ADR-F054): full-width panel to toggle the area's
					     skills/tools/playbooks (+ MCP placeholder) for this matter. The run
					     composition reads the same toggles. Run-locked (paused while working). -->
						<div class="min-h-0 flex-1 overflow-y-auto scroll-smooth overscroll-contain">
							<CapabilitiesPanel
								projectId={matter.project_id}
								{runActive}
								reloadKey={registerReloadKey}
							/>
						</div>
					{/if}
				</section>
			{/if}
		</div>
		{#if editorOpen && editorFileId}
			<div
				class="flex h-full min-h-0 min-w-0 flex-[2_1_0%] overflow-hidden rounded-xl border border-border bg-card shadow-sm"
				transition:fly={{ x: 28, duration: motionMs(MOTION.base), opacity: 0.5, easing: cubicOut }}
				data-testid="lq-cockpit-editor"
			>
				<DocumentEditorPanel
					fileId={editorFileId}
					filename={editorFilename}
					onClose={closeEditor}
					onHandBack={handBackFromEditor}
				/>
			</div>
		{/if}
		{#if gridOpen && gridId}
			<!-- F2 Tabular T6 (ADR-F055): the grid workspace flies in as a sibling of
			     the conversation card — same stage-takeover as the editor, so the
			     conversation stays mounted (live SSE survives). -->
			<div
				class="flex h-full min-h-0 min-w-0 flex-[2_1_0%] overflow-hidden rounded-xl border border-border bg-card shadow-sm"
				transition:fly={{ x: 28, duration: motionMs(MOTION.base), opacity: 0.5, easing: cubicOut }}
				data-testid="lq-cockpit-grid"
			>
				<TabularWorkspace {gridId} onClose={closeGrid} />
			</div>
		{/if}
	</div>
</div>

<NewMatterDialog
	bind:open={createOpen}
	{unitLabel}
	practiceAreaId={matter?.practice_area_id ?? null}
	{areas}
	onCreated={(project) => {
		selectedMatterId = project.id;
		onMatterCreated(project);
		onActivity();
	}}
/>
