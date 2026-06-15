<script lang="ts">
	/**
	 * Cockpit v0 — the F1-S2 landing surface (ADR-F002 "glass cockpit",
	 * MILESTONES § F1). Lands on the AREA LIST; the LEFT rail is the
	 * persistent map (practice areas + the unfiled bucket); the main pane
	 * renders the selection: area grid → matters under an area → matter
	 * conversation view. Selection is URL state (`?area=&matter=&thread=`)
	 * so every view deep-links and survives reload.
	 *
	 * All rollups derive from settled rows via GET /agents/matters
	 * (ADR-F004 — never stream state); area keys stay presentation/URL
	 * state only until S3's schema (MILESTONES pre-F1 guard).
	 *
	 * F1-S2.1 responsive contract (maintainer review: "at half-screen the
	 * content squashes"): ≥880px the rail is a collapsible paneforge pane
	 * (header toggle, collapsed state persists via autoSaveId); <880px the
	 * rail leaves the pane group entirely and becomes an off-canvas drawer
	 * behind the same header toggle.
	 */
	import { onDestroy, onMount } from 'svelte';
	import { fade, fly } from 'svelte/transition';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import * as Resizable from '$lib/components/ui/resizable/index.js';
	import { agentsApi, practiceAreasApi, projectsApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import type { MatterActivity, MatterActivityResponse } from '$lib/lq-ai/api/agents';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { Project } from '$lib/lq-ai/types';
	import { auth } from '$lib/lq-ai/auth/store';
	import { serverNowMs } from '$lib/lq-ai/agents/server-clock';
	import AreaGrid from './AreaGrid.svelte';
	import AreaRail from './AreaRail.svelte';
	import CenteredEntry from './CenteredEntry.svelte';
	import CockpitHeader from './CockpitHeader.svelte';
	import ConversationHost from './ConversationHost.svelte';
	import MattersPanel from './MattersPanel.svelte';
	import { cockpitUrl, launchIntent, MOTION, motionMs, parseCockpitState, viewOf } from './helpers';

	let areas = $state<PracticeArea[] | null>(null);
	let areasError = $state<string | null>(null);
	let activity = $state<MatterActivityResponse | null>(null);
	let activityError = $state<string | null>(null);
	let projects = $state<Project[]>([]);
	let projectsError = $state<string | null>(null);

	let nowMs = $state(Date.now());
	let ticker: ReturnType<typeof setInterval> | null = null;

	// F2-M4: a centered-entry submission carries its text here so the FIRST
	// matter composer reached after the launch opens with it as a draft —
	// whether routed directly (sole configured area) or after the user picks an
	// area. ConversationHost seeds it once on mount and clears it via
	// onDraftConsumed, so a second matter is never re-seeded. Carry window: if
	// the user opens some other existing matter before fulfilling the launch it
	// also receives the draft — acceptable, it is their last typed intent and
	// fully editable. NOT a thread — the launcher never starts a conversation
	// (ADR-F002).
	let pendingDraft = $state('');

	const sel = $derived(parseCockpitState($page.url.searchParams));
	const view = $derived(viewOf(sel));
	const selectedArea = $derived(areas?.find((a) => a.key === sel.area && a.configured) ?? null);
	const selectedMatter = $derived(
		activity?.matters.find((m) => m.project_id === sel.matter) ?? null
	);
	const unitLabel = $derived(selectedArea?.unit_label ?? 'Matter');

	// --- Responsive shell state -------------------------------------------
	let viewportWidth = $state(1280);
	const isNarrow = $derived(viewportWidth < 880);
	// paneforge Pane instance (collapse/expand/isCollapsed — verified 1.0.2
	// API); only bound in the WIDE layout.
	let railPane = $state<ReturnType<typeof Resizable.Pane> | null>(null);
	let railCollapsed = $state(false);
	let drawerOpen = $state(false);
	// A flex-grow transition animates collapse/expand, but it must NOT
	// apply while the user drags the resizer (it would rubber-band) and
	// must respect prefers-reduced-motion (review fix — the slice's own
	// motion gate).
	let resizing = $state(false);
	const reducedMotion =
		typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

	$effect(() => {
		if (!isNarrow) {
			// Leaving the narrow layout always closes the drawer.
			drawerOpen = false;
		} else {
			// The Handle unmounts with the rail pane; its onDraggingChange
			// never fires false mid-drag — unlatch (review fix).
			resizing = false;
		}
	});

	// The drawer is a modal surface: move focus into it on open (Escape
	// and the scrim close it; full focus trapping is deferred on record).
	let drawerEl = $state<HTMLElement | null>(null);
	$effect(() => {
		if (drawerOpen) drawerEl?.focus();
	});

	function toggleRail() {
		if (isNarrow) {
			drawerOpen = !drawerOpen;
			return;
		}
		if (!railPane) return;
		if (railPane.isCollapsed()) railPane.expand();
		else railPane.collapse();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && drawerOpen) drawerOpen = false;
	}
	// ----------------------------------------------------------------------

	function errText(e: unknown): string {
		return e instanceof LQAIApiError ? e.message : 'network error';
	}

	async function loadAreas() {
		try {
			areas = (await practiceAreasApi.listPracticeAreas()).practice_areas;
			areasError = null;
		} catch (e: unknown) {
			areasError = errText(e);
		}
	}

	async function loadActivity() {
		try {
			activity = await agentsApi.listMatters();
			activityError = null;
		} catch (e: unknown) {
			activityError = errText(e);
		}
	}

	async function loadProjects() {
		try {
			projects = await projectsApi.listProjects();
			projectsError = null;
		} catch (e: unknown) {
			projectsError = errText(e);
		}
	}

	onMount(() => {
		loadAreas();
		loadActivity();
		loadProjects();
		nowMs = serverNowMs();
		ticker = setInterval(() => {
			nowMs = serverNowMs();
		}, 30_000);
	});

	onDestroy(() => {
		if (ticker) clearInterval(ticker);
	});

	function nav(url: string) {
		goto(url, { keepFocus: true, noScroll: true });
	}

	function enterArea(area: PracticeArea) {
		drawerOpen = false;
		nav(cockpitUrl({ area: area.key }));
	}

	function openUnfiled() {
		drawerOpen = false;
		nav(cockpitUrl({ unfiled: true }));
	}

	function launchFromEntry(text: string) {
		// LAUNCHER, not composer (ADR-F002): resolve the typed intent to a
		// destination + carried draft. One configured area → enter it carrying
		// the note; otherwise the note is held and the user picks an area below.
		const intent = launchIntent(areas ?? [], text);
		pendingDraft = intent.draft;
		if (intent.url) nav(intent.url);
	}

	function openMatter(matter: MatterActivity) {
		nav(cockpitUrl({ area: sel.area, matter: matter.project_id }));
	}

	function onMatterCreated(project: Project) {
		loadActivity();
		loadProjects();
		nav(cockpitUrl({ area: sel.area, matter: project.id }));
	}

	function onMatterCreatedInline(project: Project) {
		// Quick-create from the composer: the select needs the option NOW —
		// append optimistically, then reconcile from the server.
		projects = [project, ...projects];
		loadActivity();
		loadProjects();
	}

	function selectThread(threadId: string | null) {
		nav(
			sel.unfiled
				? cockpitUrl({ unfiled: true, thread: threadId })
				: cockpitUrl({ area: sel.area, matter: sel.matter, thread: threadId })
		);
	}

	function onThreadCreated(detail: { threadId: string; projectId: string | null }) {
		// Sync the URL to the conversation the panel just created so the
		// deep-link/reload contract holds for the primary flow. replaceState:
		// the fresh-composer state isn't a history entry worth keeping. If
		// the user re-pointed the composer's matter select, follow the REAL
		// binding (the thread files under ITS matter, not the open one).
		const matterId = sel.unfiled ? null : (detail.projectId ?? sel.matter);
		goto(
			sel.unfiled && detail.projectId === null
				? cockpitUrl({ unfiled: true, thread: detail.threadId })
				: cockpitUrl({ area: sel.area, matter: matterId, thread: detail.threadId }),
			{ replaceState: true, keepFocus: true, noScroll: true }
		);
		loadActivity();
	}
</script>

<svelte:window bind:innerWidth={viewportWidth} onkeydown={handleKeydown} />

{#snippet railContent()}
	<AreaRail
		{areas}
		{areasError}
		unfiled={activity?.unfiled ?? null}
		selectedAreaKey={sel.area}
		unfiledOpen={sel.unfiled}
		onSelectArea={enterArea}
		onSelectUnfiled={openUnfiled}
	/>
{/snippet}

{#snippet landingView()}
	<!-- F2-M4: the centered intent LAUNCHER above the (de-emphasised) area
	     grid. A launcher, not a composer (ADR-F002): it routes into the
	     area→matter flow rather than starting an unbound thread. -->
	<CenteredEntry {areas} onLaunch={launchFromEntry} />
	<AreaGrid
		{areas}
		{areasError}
		matters={activity?.matters ?? null}
		{nowMs}
		onEnterArea={enterArea}
		onOpenMatter={openMatter}
	/>
{/snippet}

{#snippet mainViews()}
	{#if view === 'areas'}
		{@render landingView()}
	{:else if view === 'matters' && selectedArea}
		<MattersPanel
			area={selectedArea}
			matters={activity?.matters ?? null}
			mattersError={activityError}
			{nowMs}
			onBack={() => nav(cockpitUrl({}))}
			onOpenMatter={openMatter}
			onCreated={onMatterCreated}
		/>
	{:else if view === 'matter' && selectedMatter}
		{#key selectedMatter.project_id}
			<ConversationHost
				matter={selectedMatter}
				{unitLabel}
				threadId={sel.thread}
				{projects}
				{projectsError}
				{nowMs}
				initialDraft={pendingDraft}
				onDraftConsumed={() => (pendingDraft = '')}
				onBack={() => nav(cockpitUrl({ area: sel.area }))}
				onSelectThread={selectThread}
				{onThreadCreated}
				onMatterCreated={onMatterCreatedInline}
				onActivity={loadActivity}
			/>
		{/key}
	{:else if view === 'unfiled'}
		<ConversationHost
			matter={null}
			threadId={sel.thread}
			{projects}
			{projectsError}
			{nowMs}
			onBack={() => nav(cockpitUrl({}))}
			onSelectThread={selectThread}
			{onThreadCreated}
			onMatterCreated={onMatterCreatedInline}
			onActivity={loadActivity}
		/>
	{:else}
		<!-- Selection points at something not loaded/not enterable
		     (stale deep link, unconfigured area) — land honestly. -->
		{@render landingView()}
	{/if}
{/snippet}

<div class="flex h-dvh min-h-0 flex-col bg-background text-foreground" data-testid="lq-cockpit">
	<CockpitHeader
		user={$auth.user ?? null}
		railHidden={isNarrow ? !drawerOpen : railCollapsed}
		onToggleRail={toggleRail}
	/>
	<div class="relative min-h-0 flex-1">
		<!-- ONE pane group across both layouts: the rail pane (and its
		     handle) leave the group below the breakpoint, but the MAIN pane
		     never remounts — a live conversation survives crossing 880px. -->
		<Resizable.PaneGroup direction="horizontal" autoSaveId="lq-cockpit-panes" class="h-full">
			{#if !isNarrow}
				<Resizable.Pane
					id="cockpit-rail"
					order={1}
					collapsible
					collapsedSize={0}
					defaultSize={18}
					minSize={13}
					maxSize={30}
					class={resizing || reducedMotion ? '' : 'transition-[flex-grow] duration-200 ease-out'}
					bind:this={railPane}
					onCollapse={() => (railCollapsed = true)}
					onExpand={() => (railCollapsed = false)}
				>
					{@render railContent()}
				</Resizable.Pane>
				<!-- Resizer affordance (F1-S2.1): invisible at rest beyond the
				     hairline, indigo on hover/drag. -->
				<Resizable.Handle
					class="transition-colors duration-150 ease-out hover:bg-primary/40 data-[active]:bg-primary/60"
					onDraggingChange={(d) => (resizing = d)}
				/>
			{/if}
			<Resizable.Pane id="cockpit-main" order={2} defaultSize={82}>
				<main class="h-full min-h-0 overflow-y-auto scroll-smooth overscroll-contain">
					{@render mainViews()}
				</main>
			</Resizable.Pane>
		</Resizable.PaneGroup>
		{#if isNarrow && drawerOpen}
			<!-- Scrim: tokenized wash, never a black sheet. -->
			<button
				type="button"
				class="absolute inset-0 z-30 cursor-default bg-foreground/20"
				aria-label="Close navigation"
				transition:fade={{ duration: motionMs(MOTION.base) }}
				onclick={() => (drawerOpen = false)}
			></button>
			<div
				class="absolute inset-y-0 left-0 z-40 w-72 max-w-[85%] border-r border-border bg-background shadow-lg outline-none"
				data-testid="lq-cockpit-drawer"
				role="dialog"
				aria-modal="true"
				aria-label="Practice areas"
				tabindex="-1"
				bind:this={drawerEl}
				transition:fly={{ x: -24, duration: motionMs(MOTION.base), opacity: 0.4 }}
			>
				{@render railContent()}
			</div>
		{/if}
	</div>
</div>
