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
	import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left';
	import PlusIcon from '@lucide/svelte/icons/plus';
	import ShieldIcon from '@lucide/svelte/icons/shield';

	import { Button } from '$lib/components/ui/button/index.js';
	import { agentsApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import type { AgentThread, MatterActivity } from '$lib/lq-ai/api/agents';
	import type { Project } from '$lib/lq-ai/types';
	import ConversationPanel from '$lib/lq-ai/components/agents/ConversationPanel.svelte';
	import NewMatterDialog from './NewMatterDialog.svelte';
	import StatusPill from './StatusPill.svelte';
	import { timeAgo } from './helpers';

	let {
		matter = null,
		unitLabel = 'Matter',
		threadId,
		projects,
		projectsError,
		nowMs,
		onBack,
		onSelectThread,
		onThreadCreated,
		onMatterCreated,
		onActivity
	}: {
		/** null = the unfiled bucket (resume-only). */
		matter?: MatterActivity | null;
		unitLabel?: string;
		threadId: string | null;
		projects: Project[];
		projectsError: string | null;
		nowMs: number;
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

	onMount(loadThreads);

	function handleSettled() {
		loadThreads();
		onActivity();
	}

	function selectThread(id: string | null) {
		panelOwnedThread = null;
		onSelectThread(id);
	}

	function newConversation() {
		panelOwnedThread = null;
		composerEpoch += 1;
		onSelectThread(null);
	}

	function handleThreadCreated(event: CustomEvent<{ threadId: string; projectId: string | null }>) {
		panelOwnedThread = event.detail.threadId;
		onThreadCreated(event.detail);
		loadThreads();
	}
</script>

<div class="flex h-full min-h-0" data-testid="lq-cockpit-conversation">
	<aside class="flex w-72 shrink-0 flex-col border-r border-border bg-background">
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
		<nav class="flex-1 overflow-y-auto px-2 py-2" aria-label="Conversations">
			{#if threadsError}
				<p class="px-2 py-1 text-sm text-destructive">
					Couldn't load conversations: {threadsError}
				</p>
			{:else if threads === null}
				<div class="space-y-1 px-2 py-1" aria-hidden="true">
					{#each [0, 1, 2] as i (i)}
						<div class="h-9 animate-pulse rounded-md bg-muted"></div>
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
								class="flex w-full flex-col gap-0.5 rounded-md px-2.5 py-2 text-left transition-colors duration-150 hover:bg-muted/60 {threadId ===
								t.id
									? 'bg-accent'
									: ''}"
								data-testid="lq-cockpit-thread-row"
								onclick={() => selectThread(t.id)}
							>
								<span class="line-clamp-2 text-xs font-medium text-foreground">{t.title}</span>
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

	<section class="min-w-0 flex-1 overflow-y-auto">
		{#if matter || threadId}
			{#key panelKey}
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
			{/key}
		{:else}
			<div class="flex h-full items-center justify-center px-8">
				<div class="max-w-sm text-center">
					<h2 class="text-base font-semibold text-foreground">Pick a conversation</h2>
					<p class="mt-1 text-sm text-muted-foreground">
						Unfiled conversations are read-and-resume only. Select one on the left to continue it.
					</p>
				</div>
			</div>
		{/if}
	</section>
</div>

<NewMatterDialog
	bind:open={createOpen}
	{unitLabel}
	onCreated={(project) => {
		selectedMatterId = project.id;
		onMatterCreated(project);
		onActivity();
	}}
/>
