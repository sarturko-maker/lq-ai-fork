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
		listProcessingActivities,
		listSystems,
		type ExportFormat,
		type ProcessingActivityRead,
		type SystemRead
	} from '$lib/lq-ai/api/ropa';
	import { MOTION, motionMs } from '$lib/lq-ai/cockpit/helpers';
	import ProcessingActivityDetail from './ProcessingActivityDetail.svelte';
	import SystemDetail from './SystemDetail.svelte';
	import {
		EMPTY_ACTIVITIES,
		EMPTY_SYSTEMS,
		REGISTER_TABS,
		controllerRoleLabel,
		lawfulBasisLabel,
		systemTypeLabel,
		type RegisterTab
	} from './format';

	let activities = $state<ProcessingActivityRead[] | null>(null);
	let systems = $state<SystemRead[] | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let tab = $state<RegisterTab>('activities');
	let selectedActivityId = $state<string | null>(null);
	let selectedSystemId = $state<string | null>(null);

	const selectedActivity = $derived(
		activities?.find((a) => a.id === selectedActivityId) ?? null
	);
	const selectedSystem = $derived(systems?.find((s) => s.id === selectedSystemId) ?? null);

	const registerEmpty = $derived(
		(activities?.length ?? 0) === 0 && (systems?.length ?? 0) === 0
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
			const [a, s] = await Promise.all([listProcessingActivities(), listSystems()]);
			activities = a;
			systems = s;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load the ROPA register.';
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function selectTab(next: RegisterTab) {
		tab = next;
		selectedActivityId = null;
		selectedSystemId = null;
	}

	function openActivity(id: string) {
		tab = 'activities';
		selectedSystemId = null;
		selectedActivityId = id;
	}

	function openSystem(id: string) {
		tab = 'systems';
		selectedActivityId = null;
		selectedSystemId = id;
	}

	function backToList() {
		selectedActivityId = null;
		selectedSystemId = null;
	}
</script>

<PageShell size="wide">
	{#if selectedActivity}
		<ProcessingActivityDetail
			activity={selectedActivity}
			onBack={backToList}
			onOpenSystem={openSystem}
		/>
	{:else if selectedSystem}
		<SystemDetail system={selectedSystem} onBack={backToList} onOpenActivity={openActivity} />
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
			{:else if (systems?.length ?? 0) === 0}
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
									<TableCell class="text-muted-foreground">{s.processing_activities.length}</TableCell>
								</TableRow>
							{/each}
						</TableBody>
					</Table>
				</div>
			{/if}
		</div>
	{/if}
</PageShell>
