<script lang="ts">
	/**
	 * Cockpit landing (UX-A-1, ADR-F014) — the canvas content for `/lq-ai`,
	 * rendered inside the shell layout (`(app)/+layout.svelte`). This is the
	 * view-switch the cockpit lands on (MILESTONES § F1: lands on the area list,
	 * never auto-lands in an area): area grid → matters under an area → matter
	 * conversation → unfiled conversations, all driven by URL state
	 * (`?area=&matter=&thread=&view=`) so every view deep-links + survives reload.
	 *
	 * Shared data (areas + activity + nowMs) comes from the shell via
	 * `CockpitState` context; `projects` + the launch `pendingDraft` are
	 * landing-local. All rollups are settled rows (ADR-F004).
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { libraryApi, projectsApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import { auth } from '$lib/lq-ai/auth/store';
	import type { MatterActivity } from '$lib/lq-ai/api/agents';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { Project } from '$lib/lq-ai/types';
	import { SETUP_DISMISSED_KEY, shouldAutoLaunchSetup } from './admin/setup/page-helpers';
	import AreaGrid from '$lib/lq-ai/cockpit/AreaGrid.svelte';
	import CenteredEntry from '$lib/lq-ai/cockpit/CenteredEntry.svelte';
	import ConversationHost from '$lib/lq-ai/cockpit/ConversationHost.svelte';
	import MattersPanel from '$lib/lq-ai/cockpit/MattersPanel.svelte';
	import { getCockpitState } from '$lib/lq-ai/cockpit/context.svelte';
	import { cockpitUrl, launchIntent, parseCockpitState, viewOf } from '$lib/lq-ai/cockpit/helpers';

	const cockpit = getCockpitState();

	const sel = $derived(parseCockpitState($page.url.searchParams));
	const view = $derived(viewOf(sel));
	const selectedArea = $derived(
		cockpit.areas?.find((a) => a.key === sel.area && a.configured) ?? null
	);
	const selectedMatter = $derived(
		cockpit.activity?.matters.find((m) => m.project_id === sel.matter) ?? null
	);
	const unitLabel = $derived(selectedArea?.unit_label ?? 'Matter');
	// UX-B-5: the areas a new matter may file under — only configured areas are
	// fileable (ADR-F002). Threaded to the new-matter dialog for explicit area
	// selection at creation.
	const configuredAreas = $derived(cockpit.areas?.filter((a) => a.configured) ?? []);

	// Landing-local: the matter composer needs the project list; a launch carries
	// its text to the FIRST matter composer reached (seeded once, then cleared).
	let projects = $state<Project[]>([]);
	let projectsError = $state<string | null>(null);
	let pendingDraft = $state('');

	async function loadProjects() {
		try {
			projects = await projectsApi.listProjects();
			projectsError = null;
		} catch (e: unknown) {
			projectsError = e instanceof LQAIApiError ? e.message : 'network error';
		}
	}

	/**
	 * B-7b (ADR-F067 D4) — auto-launch the guided setup wizard on a fresh org.
	 * A tenant-admin (the operator is fenced out of apply, ADR-F064) who hasn't
	 * completed or skipped the wizard on this browser, on an org whose Library is
	 * still empty (the direct G13 signal — seeded bindings are inert until
	 * something is adopted), is sent to the wizard. Skippable + always reachable
	 * from the admin nav. The probe never blocks the cockpit (any failure is
	 * swallowed), and short-circuits before any request for non-admins / operators
	 * / already-dismissed browsers.
	 */
	async function maybeAutoLaunchSetup() {
		const user = $auth.user;
		if (!user?.is_admin || user.role === 'operator') return;
		let dismissed = false;
		try {
			dismissed = localStorage.getItem(SETUP_DISMISSED_KEY) === '1';
		} catch {
			dismissed = true; // storage disabled — don't nag
		}
		if (dismissed) return;
		try {
			const lib = await libraryApi.getLibrary();
			if (
				shouldAutoLaunchSetup({
					isAdmin: user.is_admin,
					role: user.role,
					dismissed: false,
					libraryEmpty: lib.entries.length === 0
				})
			) {
				goto('/lq-ai/admin/setup');
			}
		} catch {
			// never block the cockpit landing on the first-run probe
		}
	}

	onMount(() => {
		void loadProjects();
		void maybeAutoLaunchSetup();
	});

	function nav(url: string) {
		goto(url, { keepFocus: true, noScroll: true });
	}

	function enterArea(area: PracticeArea) {
		nav(cockpitUrl({ area: area.key }));
	}

	function launchFromEntry(text: string) {
		// LAUNCHER, not composer (ADR-F002): resolve the typed intent to a
		// destination + carried draft. One configured area → enter it carrying
		// the note; otherwise the note is held and the user picks an area below.
		const intent = launchIntent(cockpit.areas ?? [], text);
		pendingDraft = intent.draft;
		if (intent.url) nav(intent.url);
	}

	function openMatter(matter: MatterActivity) {
		// Prefer the matter's OWN area so opening from the landing's recent list
		// (where sel.area is null) deep-links + back-navigates correctly; unfiled
		// matters (null key) open by id with no area, which the matter view allows.
		nav(cockpitUrl({ area: matter.practice_area_key ?? sel.area, matter: matter.project_id }));
	}

	function onMatterCreated(project: Project) {
		cockpit.loadActivity();
		loadProjects();
		nav(cockpitUrl({ area: sel.area, matter: project.id }));
	}

	function onMatterCreatedInline(project: Project) {
		// Quick-create from the composer: the select needs the option NOW —
		// append optimistically, then reconcile from the server.
		projects = [project, ...projects];
		cockpit.loadActivity();
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
		// deep-link/reload contract holds. If the user re-pointed the composer's
		// matter select, follow the REAL binding (the thread files under ITS
		// matter, not the open one). replaceState: the fresh-composer state isn't
		// a history entry worth keeping.
		const matterId = sel.unfiled ? null : (detail.projectId ?? sel.matter);
		goto(
			sel.unfiled && detail.projectId === null
				? cockpitUrl({ unfiled: true, thread: detail.threadId })
				: cockpitUrl({ area: sel.area, matter: matterId, thread: detail.threadId }),
			{ replaceState: true, keepFocus: true, noScroll: true }
		);
		cockpit.loadActivity();
	}
</script>

{#snippet landingView()}
	<!-- The centered intent LAUNCHER above the (de-emphasised) area grid. A
	     launcher, not a composer (ADR-F002): it routes into the area→matter flow
	     rather than starting an unbound thread. -->
	<CenteredEntry areas={cockpit.areas} onLaunch={launchFromEntry} />
	<AreaGrid
		areas={cockpit.areas}
		areasError={cockpit.areasError}
		matters={cockpit.activity?.matters ?? null}
		nowMs={cockpit.nowMs}
		onEnterArea={enterArea}
		onOpenMatter={openMatter}
	/>
{/snippet}

{#if view === 'areas'}
	{@render landingView()}
{:else if view === 'matters' && selectedArea}
	<MattersPanel
		area={selectedArea}
		areas={configuredAreas}
		matters={cockpit.activity?.matters ?? null}
		mattersError={cockpit.activityError}
		nowMs={cockpit.nowMs}
		onBack={() => nav(cockpitUrl({}))}
		onOpenMatter={openMatter}
		onCreated={onMatterCreated}
	/>
{:else if view === 'matter' && selectedMatter}
	{#key selectedMatter.project_id}
		<ConversationHost
			matter={selectedMatter}
			{unitLabel}
			areas={configuredAreas}
			threadId={sel.thread}
			{projects}
			{projectsError}
			nowMs={cockpit.nowMs}
			initialDraft={pendingDraft}
			onDraftConsumed={() => (pendingDraft = '')}
			onBack={() => nav(cockpitUrl({ area: sel.area }))}
			onSelectThread={selectThread}
			{onThreadCreated}
			onMatterCreated={onMatterCreatedInline}
			onActivity={() => cockpit.loadActivity()}
		/>
	{/key}
{:else if view === 'unfiled'}
	<ConversationHost
		matter={null}
		areas={configuredAreas}
		threadId={sel.thread}
		{projects}
		{projectsError}
		nowMs={cockpit.nowMs}
		onBack={() => nav(cockpitUrl({}))}
		onSelectThread={selectThread}
		{onThreadCreated}
		onMatterCreated={onMatterCreatedInline}
		onActivity={() => cockpit.loadActivity()}
	/>
{:else}
	<!-- Selection points at something not loaded/not enterable (stale deep link,
	     unconfigured area) — land honestly. -->
	{@render landingView()}
{/if}
