<script lang="ts">
	/**
	 * The two-tier ROPA register (read-only) — PRIV-3, ADR-F018/F019.
	 *
	 * Surfaces the company's deployment-global ROPA inventory inside a Privacy
	 * matter: a Processing Activities register and a Systems register, switchable,
	 * with row → detail and cross-links between the two. Rendered in LQ.AI's own
	 * F013 design language (charcoal + scarce-blue accent, our primitives) — NOT
	 * Oscar's/OneTrust's chrome. Read-only: the Privacy Deep Agent writes the
	 * register (guarded, code-validated tools); the user reads and owns it.
	 */
	import { onDestroy, onMount } from 'svelte';
	import { fade } from 'svelte/transition';

	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table/index.js';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';
	import {
		downloadArticle30,
		getDataFlow,
		getProgrammeSummary,
		listDataCategories,
		listDataSubjectCategories,
		listProcessingActivities,
		listSystems,
		listVendors,
		type DataCategoryRead,
		type DataFlowGraph,
		type DataSubjectCategoryRead,
		type ExportFormat,
		type ProcessingActivityRead,
		type ProgrammeSummary,
		type SystemRead,
		type VendorRead
	} from '$lib/lq-ai/api/ropa';
	import { POLL_INTERVAL_MS } from '$lib/lq-ai/agents/helpers';
	import { MOTION, motionMs } from '$lib/lq-ai/cockpit/helpers';
	import DataFlowView from './DataFlowView.svelte';
	import ProcessingActivityDetail from './ProcessingActivityDetail.svelte';
	import ProgrammeDashboard from './ProgrammeDashboard.svelte';
	import SystemDetail from './SystemDetail.svelte';
	import VendorDetail from './VendorDetail.svelte';
	import {
		EMPTY_ACTIVITIES,
		EMPTY_DATA_CATEGORIES,
		EMPTY_DATA_SUBJECTS,
		EMPTY_SYSTEMS,
		EMPTY_VENDORS,
		REGISTER_TABS,
		controllerRoleLabel,
		dpaStatusLabel,
		lawfulBasisLabel,
		systemTypeLabel,
		vendorRoleLabel,
		type RegisterTab
	} from './format';

	let {
		// PRIV-9a: true while the Privacy agent is actively working — drives the
		// live poll so the agent's writes appear here as they commit. The host
		// (ConversationHost) relays it from the conversation's run state.
		runActive = false,
		// Bumped by the host when a run settles — triggers one reconcile fetch so
		// the final write is never missed even if the last poll tick raced it.
		reloadKey = 0,
		// PRIV-9b (ADR-F024): ids of register rows the agent just changed (hoisted
		// + decayed by the host). A matching activity/system/vendor row gets a
		// transient wash. Animation only — the polled rows above are the truth.
		changedIds = new Set<string>()
	}: { runActive?: boolean; reloadKey?: number; changedIds?: Set<string> } = $props();

	let activities = $state<ProcessingActivityRead[] | null>(null);
	let systems = $state<SystemRead[] | null>(null);
	let vendors = $state<VendorRead[] | null>(null);
	let dataSubjects = $state<DataSubjectCategoryRead[] | null>(null);
	let dataCategories = $state<DataCategoryRead[] | null>(null);
	let summary = $state<ProgrammeSummary | null>(null);
	let graph = $state<DataFlowGraph | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let tab = $state<RegisterTab>('overview');
	let selectedActivityId = $state<string | null>(null);
	let selectedSystemId = $state<string | null>(null);
	let selectedVendorId = $state<string | null>(null);

	const selectedActivity = $derived(activities?.find((a) => a.id === selectedActivityId) ?? null);
	const selectedSystem = $derived(systems?.find((s) => s.id === selectedSystemId) ?? null);
	const selectedVendor = $derived(vendors?.find((v) => v.id === selectedVendorId) ?? null);

	const registerEmpty = $derived(
		(activities?.length ?? 0) === 0 &&
			(systems?.length ?? 0) === 0 &&
			(vendors?.length ?? 0) === 0 &&
			(dataSubjects?.length ?? 0) === 0 &&
			(dataCategories?.length ?? 0) === 0
	);

	const EXPORT_FORMATS: { fmt: ExportFormat; label: string }[] = [
		{ fmt: 'xlsx', label: 'Excel' },
		{ fmt: 'csv', label: 'CSV' },
		{ fmt: 'json', label: 'JSON' }
	];
	let exporting = $state<ExportFormat | null>(null);
	let exportError = $state<string | null>(null);

	async function doExport(fmt: ExportFormat) {
		exportError = null;
		exporting = fmt;
		try {
			await downloadArticle30(fmt);
		} catch (e) {
			exportError = e instanceof Error ? e.message : 'Export failed.';
		} finally {
			exporting = null;
		}
	}

	// Out-of-order guard: a slow fetch must not clobber a fresher one — the
	// live poll and the settle-reconcile can overlap (mirrors ConversationPanel).
	let loadGeneration = 0;
	// Timer-chain ownership guard: bumped on every stop so a tick from a
	// superseded chain (e.g. runActive flipped false→true during an in-flight
	// fetch) refuses to re-arm — one live poll loop at a time.
	let pollGeneration = 0;
	let pollTimer: ReturnType<typeof setTimeout> | null = null;
	let destroyed = false;

	/**
	 * Re-read the whole register. `quiet` = a live refresh (poll tick or settle
	 * reconcile): keep the current rows on screen — never flip back to the
	 * skeleton, and never blank the table to an error on a transient blip (the
	 * PRIV-9a UX bar: no flicker while the agent works). The first mount load is
	 * loud (shows the skeleton, surfaces a hard error).
	 */
	async function load(quiet = false) {
		const gen = ++loadGeneration;
		if (!quiet) {
			loading = true;
			error = null;
		}
		try {
			const [a, s, v, ds, dc, sum, gr] = await Promise.all([
				listProcessingActivities(),
				listSystems(),
				listVendors(),
				listDataSubjectCategories(),
				listDataCategories(),
				getProgrammeSummary(),
				getDataFlow()
			]);
			if (gen !== loadGeneration) return; // superseded by a newer load
			activities = a;
			systems = s;
			vendors = v;
			dataSubjects = ds;
			dataCategories = dc;
			summary = sum;
			graph = gr;
			if (!quiet) error = null;
		} catch (e) {
			if (gen !== loadGeneration) return;
			// A quiet refresh swallows transient errors and keeps the last good
			// register on screen; the next tick (or the settle reconcile) retries.
			if (!quiet) error = e instanceof Error ? e.message : 'Failed to load the ROPA register.';
		} finally {
			if (!quiet) loading = false;
		}
	}

	// PRIV-9a live update — poll while a run is active (the conversation's 2s
	// cadence), self-rescheduling so requests can't pile up. The $effect below
	// starts it when a run begins and tears it down the moment it settles; the
	// host then bumps `reloadKey` for one final reconcile. `gen` threads the
	// chain identity so a tick whose chain was superseded never re-arms.
	function schedulePoll(gen: number) {
		pollTimer = setTimeout(() => {
			void pollTick(gen);
		}, POLL_INTERVAL_MS);
	}

	async function pollTick(gen: number) {
		if (gen !== pollGeneration) return; // chain superseded before this fired
		await load(true);
		// Settled mid-flight, unmounted, or superseded during the fetch: don't re-arm.
		if (destroyed || !runActive || gen !== pollGeneration) return;
		schedulePoll(gen);
	}

	function stopPoll() {
		pollGeneration += 1; // retire the current chain
		if (pollTimer !== null) {
			clearTimeout(pollTimer);
			pollTimer = null;
		}
	}

	onMount(() => {
		void load();
	});

	onDestroy(() => {
		destroyed = true;
		stopPoll();
	});

	// Start/stop the live poll as the run starts/ends; the cleanup retires the
	// chain when `runActive` flips false or the component unmounts.
	$effect(() => {
		if (!runActive) return;
		const gen = pollGeneration;
		schedulePoll(gen);
		return () => stopPoll();
	});

	// Settle reconcile: when the host bumps reloadKey (a run just settled), pull
	// once more so the final write lands even if it raced the last poll tick.
	// svelte-ignore state_referenced_locally
	let lastReloadKey = reloadKey;
	$effect(() => {
		if (reloadKey === lastReloadKey) return;
		lastReloadKey = reloadKey;
		void load(true);
	});

	function clearSelection() {
		selectedActivityId = null;
		selectedSystemId = null;
		selectedVendorId = null;
	}

	function selectTab(next: RegisterTab) {
		tab = next;
		clearSelection();
	}

	function openActivity(id: string) {
		tab = 'activities';
		clearSelection();
		selectedActivityId = id;
	}

	function openSystem(id: string) {
		tab = 'systems';
		clearSelection();
		selectedSystemId = id;
	}

	function openVendor(id: string) {
		tab = 'vendors';
		clearSelection();
		selectedVendorId = id;
	}

	function backToList() {
		clearSelection();
	}
</script>

<PageShell size="wide">
	{#if selectedActivity}
		<ProcessingActivityDetail
			activity={selectedActivity}
			onBack={backToList}
			onOpenSystem={openSystem}
			onOpenVendor={openVendor}
		/>
	{:else if selectedSystem}
		<SystemDetail system={selectedSystem} onBack={backToList} onOpenActivity={openActivity} />
	{:else if selectedVendor}
		<VendorDetail vendor={selectedVendor} onBack={backToList} onOpenActivity={openActivity} />
	{:else}
		<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
			<SectionHeader
				size="page"
				title="ROPA register"
				subtitle="The company's Records of Processing Activities — maintained by the Privacy agent, owned by you."
			/>

			<!-- Article 30 export (PRIV-4a): the extractable RoPA deliverable. -->
			<div class="flex shrink-0 flex-col items-start gap-1 sm:items-end">
				<div class="flex items-center gap-1.5">
					<span class="mr-1 text-xs font-medium text-muted-foreground">Export Article 30</span>
					{#each EXPORT_FORMATS as f (f.fmt)}
						<Button
							type="button"
							variant="outline"
							size="sm"
							disabled={registerEmpty || exporting !== null}
							onclick={() => doExport(f.fmt)}
						>
							{exporting === f.fmt ? 'Preparing…' : f.label}
						</Button>
					{/each}
				</div>
				{#if exportError}
					<p class="text-xs text-destructive">{exportError}</p>
				{/if}
			</div>
		</div>

		<!-- Two-tier switch: calm, single accent on the active register. -->
		<div
			class="mt-4 inline-flex gap-1 rounded-lg border border-border bg-muted/40 p-1"
			role="tablist"
		>
			{#each REGISTER_TABS as t (t.id)}
				<button
					type="button"
					role="tab"
					aria-selected={tab === t.id}
					class="rounded-md px-3 py-1.5 text-sm font-medium transition-colors duration-150 {tab ===
					t.id
						? 'bg-background text-foreground shadow-sm'
						: 'text-muted-foreground hover:text-foreground'}"
					onclick={() => selectTab(t.id)}
				>
					{t.label}
				</button>
			{/each}
		</div>

		<div class="mt-4" in:fade={{ duration: motionMs(MOTION.fast) }}>
			{#if loading}
				<p class="text-sm text-muted-foreground">Loading the register…</p>
			{:else if error}
				<p class="text-sm text-destructive">{error}</p>
			{:else if tab === 'overview'}
				{#if summary}
					<ProgrammeDashboard {summary} />
				{/if}
			{:else if tab === 'data-flow'}
				{#if graph}
					<DataFlowView {graph} />
				{/if}
			{:else if tab === 'activities'}
				{#if (activities?.length ?? 0) === 0}
					<p class="max-w-prose text-sm text-muted-foreground">{EMPTY_ACTIVITIES}</p>
				{:else}
					<div class="rounded-lg border border-border">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead>Name</TableHead>
									<TableHead>Lawful basis</TableHead>
									<TableHead>Role</TableHead>
									<TableHead>Retention</TableHead>
									<TableHead>Special category</TableHead>
									<TableHead>Systems</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each activities ?? [] as a (a.id)}
									<TableRow
										class="lq-reg-row cursor-pointer{changedIds.has(a.id)
											? ' lq-row-changed'
											: ''}"
										onclick={() => openActivity(a.id)}
									>
										<TableCell class="font-medium text-foreground">{a.name}</TableCell>
										<TableCell>
											<Badge variant="secondary">{lawfulBasisLabel(a.lawful_basis)}</Badge>
										</TableCell>
										<TableCell class="text-muted-foreground"
											>{controllerRoleLabel(a.controller_role)}</TableCell
										>
										<TableCell class="text-muted-foreground">{a.retention}</TableCell>
										<TableCell>
											{#if a.special_category}
												<Badge variant="destructive">Special category</Badge>
											{:else}
												<span class="text-muted-foreground">—</span>
											{/if}
										</TableCell>
										<TableCell class="text-muted-foreground">{a.systems.length}</TableCell>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					</div>
				{/if}
			{:else if tab === 'systems'}
				{#if (systems?.length ?? 0) === 0}
					<p class="max-w-prose text-sm text-muted-foreground">{EMPTY_SYSTEMS}</p>
				{:else}
					<div class="rounded-lg border border-border">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead>Name</TableHead>
									<TableHead>Type</TableHead>
									<TableHead>Hosting location</TableHead>
									<TableHead>AI</TableHead>
									<TableHead>Activities</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each systems ?? [] as s (s.id)}
									<TableRow
										class="lq-reg-row cursor-pointer{changedIds.has(s.id)
											? ' lq-row-changed'
											: ''}"
										onclick={() => openSystem(s.id)}
									>
										<TableCell class="font-medium text-foreground">{s.name}</TableCell>
										<TableCell>
											<Badge variant="secondary">{systemTypeLabel(s.system_type)}</Badge>
										</TableCell>
										<TableCell class="text-muted-foreground">{s.hosting_location ?? '—'}</TableCell>
										<TableCell>
											{#if s.ai_usage}
												<Badge variant="outline">Uses AI</Badge>
											{:else}
												<span class="text-muted-foreground">—</span>
											{/if}
										</TableCell>
										<TableCell class="text-muted-foreground"
											>{s.processing_activities.length}</TableCell
										>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					</div>
				{/if}
			{:else if tab === 'vendors'}
				{#if (vendors?.length ?? 0) === 0}
					<p class="max-w-prose text-sm text-muted-foreground">{EMPTY_VENDORS}</p>
				{:else}
					<div class="rounded-lg border border-border">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead>Name</TableHead>
									<TableHead>Role</TableHead>
									<TableHead>Country</TableHead>
									<TableHead>DPA status</TableHead>
									<TableHead>Activities</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each vendors ?? [] as v (v.id)}
									<TableRow
										class="lq-reg-row cursor-pointer{changedIds.has(v.id)
											? ' lq-row-changed'
											: ''}"
										onclick={() => openVendor(v.id)}
									>
										<TableCell class="font-medium text-foreground">{v.name}</TableCell>
										<TableCell>
											<Badge variant="secondary">{vendorRoleLabel(v.vendor_role)}</Badge>
										</TableCell>
										<TableCell class="text-muted-foreground">{v.country ?? '—'}</TableCell>
										<TableCell>
											<Badge variant="outline">{dpaStatusLabel(v.dpa_status)}</Badge>
										</TableCell>
										<TableCell class="text-muted-foreground"
											>{v.processing_activities.length}</TableCell
										>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					</div>
				{/if}
			{:else if tab === 'data-subjects'}
				{#if (dataSubjects?.length ?? 0) === 0}
					<p class="max-w-prose text-sm text-muted-foreground">{EMPTY_DATA_SUBJECTS}</p>
				{:else}
					<div class="rounded-lg border border-border">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead>Category of data subjects</TableHead>
									<TableHead>Activities</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each dataSubjects ?? [] as c (c.id)}
									<TableRow>
										<TableCell class="font-medium text-foreground">{c.name}</TableCell>
										<TableCell class="text-muted-foreground"
											>{c.processing_activities.length}</TableCell
										>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					</div>
				{/if}
			{:else if tab === 'data-categories'}
				{#if (dataCategories?.length ?? 0) === 0}
					<p class="max-w-prose text-sm text-muted-foreground">{EMPTY_DATA_CATEGORIES}</p>
				{:else}
					<div class="rounded-lg border border-border">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead>Category of personal data</TableHead>
									<TableHead>Activities</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each dataCategories ?? [] as c (c.id)}
									<TableRow>
										<TableCell class="font-medium text-foreground">{c.name}</TableCell>
										<TableCell class="text-muted-foreground"
											>{c.processing_activities.length}</TableCell
										>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					</div>
				{/if}
			{/if}
		</div>
	{/if}
</PageShell>

<style>
	/* PRIV-9b (ADR-F024): a row the agent just changed gets a brief green wash
	   (the `--status-completed` intent: "just written") so the eye lands on where
	   the change happened, then fades. The transition lives on the BASE row so
	   both the wash-in (class added when the id enters the host's recently-changed
	   set) and the fade-out (class removed when the host's decay clears it) animate.
	   `:global` because shadcn `TableRow` renders the <tr> outside this scope.
	   Reduced-motion → the wash applies and clears instantly (no animation). */
	:global(tr.lq-reg-row) {
		transition: background-color 600ms ease-out;
	}
	:global(tr.lq-reg-row.lq-row-changed) {
		background-color: var(--color-status-completed-wash);
	}
	@media (prefers-reduced-motion: reduce) {
		:global(tr.lq-reg-row) {
			transition: none;
		}
	}
</style>
