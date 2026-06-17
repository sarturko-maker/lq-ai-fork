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
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left';
	import InboxIcon from '@lucide/svelte/icons/inbox';
	import PlusIcon from '@lucide/svelte/icons/plus';
	import ShieldIcon from '@lucide/svelte/icons/shield';

	import { Button } from '$lib/components/ui/button/index.js';
	import { agentsApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import type { AgentThread, MatterActivity } from '$lib/lq-ai/api/agents';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { Project } from '$lib/lq-ai/types';
	import ConversationPanel from '$lib/lq-ai/components/agents/ConversationPanel.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import NewMatterDialog from './NewMatterDialog.svelte';
	import StatusPill from './StatusPill.svelte';
	import { MOTION, motionMs, timeAgo } from './helpers';

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
	const showList = $derived(!isStacked || !stackedShowPanel);
	const showPanel = $derived(!isStacked || stackedShowPanel);

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
</script>

<!-- The conversation workspace FLOATS as one card on the canvas (F1-S2.1
     elevation scale): recessed thread list inside it, conversation column
     to the right — three honest surface steps instead of one flat sheet. -->
<div
	class="h-full min-h-0 p-2 sm:p-3"
	data-testid="lq-cockpit-conversation"
	bind:clientWidth={hostWidth}
	in:fade|global={{ duration: motionMs(MOTION.base) }}
>
	<div
		class="flex h-full min-h-0 overflow-hidden rounded-xl border border-border bg-card shadow-sm"
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
				<div class="min-h-0 flex-1 overflow-y-auto scroll-smooth overscroll-contain">
					{#if matter || threadId}
						{#key panelKey}
							<!-- F2-M6: the conversation column shares the PageShell idiom
							     (`narrow` width + `tight` pad = px-4 py-4 sm:px-6). Fade on an
							     inner div (PageShell is a component; transitions need an element). -->
							<PageShell size="narrow" pad="tight">
								<div in:fade={{ duration: motionMs(MOTION.fast) }}>
									<ConversationPanel
										initialThreadId={threadId}
										matters={projects}
										mattersError={projectsError}
										bind:prompt
										bind:selectedMatterId
										on:settled={handleSettled}
										on:newmatter={() => (createOpen = true)}
										on:threadcreated={handleThreadCreated}
									/>
								</div>
							</PageShell>
						{/key}
					{:else}
						<div class="flex h-full items-center justify-center px-8">
							<div class="max-w-sm text-center">
								<div class="mx-auto flex size-10 items-center justify-center rounded-full bg-muted">
									<InboxIcon class="size-5 text-muted-foreground" aria-hidden="true" />
								</div>
								<h2 class="mt-3 text-base font-semibold text-foreground">Pick a conversation</h2>
								<p class="mt-1 text-sm text-muted-foreground">
									Unfiled conversations are read-and-resume only. Select one on the left to continue
									it.
								</p>
							</div>
						</div>
					{/if}
				</div>
			</section>
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
