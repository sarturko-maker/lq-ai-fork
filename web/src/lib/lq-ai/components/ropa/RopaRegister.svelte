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
	import { onMount } from 'svelte';
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
		getProgrammeSummary,
		listDataCategories,
		listDataSubjectCategories,
		listProcessingActivities,
		listSystems,
		listVendors,
		type DataCategoryRead,
		type DataSubjectCategoryRead,
		type ExportFormat,
		type ProcessingActivityRead,
		type ProgrammeSummary,
		type SystemRead,
		type VendorRead
	} from '$lib/lq-ai/api/ropa';
	import { MOTION, motionMs } from '$lib/lq-ai/cockpit/helpers';
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

	let activities = $state<ProcessingActivityRead[] | null>(null);
	let systems = $state<SystemRead[] | null>(null);
	let vendors = $state<VendorRead[] | null>(null);
	let dataSubjects = $state<DataSubjectCategoryRead[] | null>(null);
	let dataCategories = $state<DataCategoryRead[] | null>(null);
	let summary = $state<ProgrammeSummary | null>(null);
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

	async function load() {
		loading = true;
		error = null;
		try {
			const [a, s, v, ds, dc, sum] = await Promise.all([
				listProcessingActivities(),
				listSystems(),
				listVendors(),
				listDataSubjectCategories(),
				listDataCategories(),
				getProgrammeSummary()
			]);
			activities = a;
			systems = s;
			vendors = v;
			dataSubjects = ds;
			dataCategories = dc;
			summary = sum;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load the ROPA register.';
		} finally {
			loading = false;
		}
	}

	onMount(load);

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
									<TableRow class="cursor-pointer" onclick={() => openActivity(a.id)}>
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
									<TableRow class="cursor-pointer" onclick={() => openSystem(s.id)}>
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
									<TableRow class="cursor-pointer" onclick={() => openVendor(v.id)}>
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
			{:else if (dataCategories?.length ?? 0) === 0}
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
		</div>
	{/if}
</PageShell>
