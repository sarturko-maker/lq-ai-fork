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
	 */
	import { onDestroy, onMount } from 'svelte';
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
	import CockpitHeader from './CockpitHeader.svelte';
	import ConversationHost from './ConversationHost.svelte';
	import MattersPanel from './MattersPanel.svelte';
	import { cockpitUrl, parseCockpitState, viewOf } from './helpers';

	let areas = $state<PracticeArea[] | null>(null);
	let areasError = $state<string | null>(null);
	let activity = $state<MatterActivityResponse | null>(null);
	let activityError = $state<string | null>(null);
	let projects = $state<Project[]>([]);
	let projectsError = $state<string | null>(null);

	let nowMs = $state(Date.now());
	let ticker: ReturnType<typeof setInterval> | null = null;

	const sel = $derived(parseCockpitState($page.url.searchParams));
	const view = $derived(viewOf(sel));
	const selectedArea = $derived(areas?.find((a) => a.key === sel.area && a.configured) ?? null);
	const selectedMatter = $derived(
		activity?.matters.find((m) => m.project_id === sel.matter) ?? null
	);
	const unitLabel = $derived(selectedArea?.unit_label ?? 'Matter');

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
		nav(cockpitUrl({ area: area.key }));
	}

	function openMatter(matter: MatterActivity) {
		nav(cockpitUrl({ area: sel.area, matter: matter.project_id }));
	}

	function onMatterCreated(project: Project) {
		loadActivity();
		loadProjects();
		nav(cockpitUrl({ area: sel.area, matter: project.id }));
	}

	function selectThread(threadId: string | null) {
		nav(
			sel.unfiled
				? cockpitUrl({ unfiled: true, thread: threadId })
				: cockpitUrl({ area: sel.area, matter: sel.matter, thread: threadId })
		);
	}
</script>

<div class="flex h-dvh min-h-0 flex-col bg-background text-foreground" data-testid="lq-cockpit">
	<CockpitHeader user={$auth.user ?? null} />
	<Resizable.PaneGroup direction="horizontal" autoSaveId="lq-cockpit-panes" class="min-h-0 flex-1">
		<Resizable.Pane defaultSize={18} minSize={13} maxSize={30}>
			<AreaRail
				{areas}
				{areasError}
				unfiled={activity?.unfiled ?? null}
				selectedAreaKey={sel.area}
				unfiledOpen={sel.unfiled}
				onSelectArea={enterArea}
				onSelectUnfiled={() => nav(cockpitUrl({ unfiled: true }))}
			/>
		</Resizable.Pane>
		<Resizable.Handle />
		<Resizable.Pane defaultSize={82}>
			<main class="h-full min-h-0 overflow-y-auto">
				{#if view === 'areas'}
					<AreaGrid
						{areas}
						{areasError}
						matters={activity?.matters ?? null}
						{nowMs}
						onEnterArea={enterArea}
					/>
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
							onBack={() => nav(cockpitUrl({ area: sel.area }))}
							onSelectThread={selectThread}
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
						onActivity={loadActivity}
					/>
				{:else}
					<!-- Selection points at something not loaded/not enterable
					     (stale deep link, unconfigured area) — land honestly. -->
					<AreaGrid
						{areas}
						{areasError}
						matters={activity?.matters ?? null}
						{nowMs}
						onEnterArea={enterArea}
					/>
				{/if}
			</main>
		</Resizable.Pane>
	</Resizable.PaneGroup>
</div>
