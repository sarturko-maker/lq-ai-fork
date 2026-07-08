<script lang="ts">
	/**
	 * /lq-ai/admin/areas — practice-area list + create (SETUP-4b, ADR-F062 addendum).
	 *
	 * Lists every practice area in server (position) order with its status, tier
	 * floor, and bound-capability counts; ↑/↓ reorder buttons call
	 * `POST /practice-areas/reorder` with the full desired key order. "New
	 * practice area" creates a registry-bounded area (key/name/unit
	 * label/doctrine/tier floor/tool groups); the roster (agent_config) is edited
	 * on the detail page only (D6).
	 *
	 * Generation-B surface (plan D1): semantic tokens + ModalShell/Table/Badge/
	 * Alert/FormControl only — no --lq-* on this page.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import ArrowDownIcon from '@lucide/svelte/icons/arrow-down';
	import ArrowUpIcon from '@lucide/svelte/icons/arrow-up';

	import { titleFor } from '$lib/lq-ai/branding/store';
	import { adminApi, practiceAreasApi } from '$lib/lq-ai/api';
	import { auth } from '$lib/lq-ai/auth/store';
	import type { DeploymentCapabilitiesResponse } from '$lib/lq-ai/api/admin';
	import type { PracticeArea, PracticeAreaCreateBody } from '$lib/lq-ai/api/practiceAreas';

	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table/index.js';
	import Alert from '$lib/lq-ai/components/primitives/Alert.svelte';
	import FormControl from '$lib/lq-ai/components/primitives/FormControl.svelte';
	import ModalShell from '$lib/lq-ai/components/primitives/ModalShell.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';

	import { describeMutationError } from '$lib/lq-ai/admin/page-helpers';
	import {
		areaStatusView,
		availableGroupOptions,
		boundCountsLabel,
		moveKey,
		validateAreaKey
	} from './page-helpers';

	const SELECT_CLASS =
		'h-8 rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30';

	let areas = $state<PracticeArea[]>([]);
	let catalog = $state<DeploymentCapabilitiesResponse | null>(null);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	let reorderBusy = $state(false);
	let reorderError = $state<string | null>(null);

	// ----- New practice area modal -----
	let newModalOpen = $state(false);
	let newKey = $state('');
	let newName = $state('');
	let newUnitLabel = $state('');
	let newDoctrine = $state('');
	let newTierFloor = $state('');
	let newGroups = $state<Set<string>>(new Set());
	let newKeyError = $state<string | null>(null);
	let newSubmitError = $state<string | null>(null);
	let newSubmitting = $state(false);

	const groupOptions = $derived(availableGroupOptions(catalog));

	async function load() {
		loading = true;
		loadError = null;
		try {
			const [list, caps] = await Promise.all([
				practiceAreasApi.listPracticeAreas(),
				adminApi.getDeploymentCapabilities()
			]);
			areas = list.practice_areas;
			catalog = caps;
		} catch (e) {
			loadError = describeMutationError(e, 'Failed to load practice areas.');
		} finally {
			loading = false;
		}
	}

	async function reorder(key: string, direction: 'up' | 'down') {
		if (reorderBusy) return;
		const currentKeys = areas.map((a) => a.key);
		const nextKeys = moveKey(currentKeys, key, direction);
		if (nextKeys === currentKeys) return;
		reorderBusy = true;
		reorderError = null;
		try {
			const resp = await practiceAreasApi.reorderPracticeAreas(nextKeys);
			areas = resp.practice_areas;
		} catch (e) {
			reorderError = describeMutationError(e, 'Failed to reorder practice areas.');
			// A mismatch means a stale client — refetch to reconcile with the server.
			await load();
		} finally {
			reorderBusy = false;
		}
	}

	function openNewModal() {
		newKey = '';
		newName = '';
		newUnitLabel = '';
		newDoctrine = '';
		newTierFloor = '';
		newGroups = new Set();
		newKeyError = null;
		newSubmitError = null;
		newModalOpen = true;
	}

	function toggleGroup(key: string) {
		const next = new Set(newGroups);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		newGroups = next;
	}

	async function submitNew(event: SubmitEvent) {
		event.preventDefault();
		newKeyError = validateAreaKey(newKey);
		if (newKeyError) return;
		newSubmitError = null;
		newSubmitting = true;
		try {
			const body: PracticeAreaCreateBody = {
				key: newKey.trim(),
				name: newName.trim(),
				unit_label: newUnitLabel.trim(),
				profile_md: newDoctrine.trim() || null,
				default_tier_floor: newTierFloor === '' ? null : Number(newTierFloor),
				tool_groups: Array.from(newGroups)
			};
			const created = await practiceAreasApi.createPracticeArea(body);
			newModalOpen = false;
			await goto(`/lq-ai/admin/areas/${encodeURIComponent(created.key)}`);
		} catch (e) {
			newSubmitError = describeMutationError(e, 'Failed to create the practice area.');
		} finally {
			newSubmitting = false;
		}
	}

	onMount(async () => {
		// Per-page admin guard (Users-page precedent — no admin-layout guard exists).
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		if (!$auth.user.is_admin) {
			console.warn('non-admin attempted /lq-ai/admin/areas; redirecting');
			goto('/lq-ai');
			return;
		}
		await load();
	});
</script>

<svelte:head>
	<title>{$titleFor('Practice areas', 'admin')}</title>
</svelte:head>

<PageShell size="wide" data-testid="lq-admin-areas-page">
	<div class="flex items-start justify-between gap-4">
		<SectionHeader
			title="Practice areas"
			subtitle="The deployment's practice areas — doctrine, roster, and bound capabilities."
		/>
		<Button type="button" onclick={openNewModal} data-testid="lq-admin-areas-new-open">
			New practice area
		</Button>
	</div>

	{#if reorderError}
		<div class="mt-4">
			<Alert intent="error">{reorderError}</Alert>
		</div>
	{/if}

	<section class="mt-6">
		{#if loadError}
			<Alert intent="error">{loadError}</Alert>
		{:else if loading}
			<p class="text-sm text-muted-foreground">Loading practice areas…</p>
		{:else if areas.length === 0}
			<p class="text-sm text-muted-foreground">No practice areas yet.</p>
		{:else}
			<div class="rounded-lg border border-border">
				<Table data-testid="lq-admin-areas-table">
					<TableHeader>
						<TableRow>
							<TableHead>Name</TableHead>
							<TableHead>Key</TableHead>
							<TableHead>Unit label</TableHead>
							<TableHead>Status</TableHead>
							<TableHead>Tier floor</TableHead>
							<TableHead>Bound</TableHead>
							<TableHead class="text-right">Reorder</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each areas as area, i (area.key)}
							{@const status = areaStatusView(area)}
							<TableRow data-testid="lq-admin-areas-row">
								<TableCell class="font-medium">
									<a
										href={`/lq-ai/admin/areas/${encodeURIComponent(area.key)}`}
										class="text-foreground hover:underline"
									>
										{area.name}
									</a>
								</TableCell>
								<TableCell class="text-muted-foreground">{area.key}</TableCell>
								<TableCell class="text-muted-foreground">{area.unit_label}</TableCell>
								<TableCell>
									<Badge variant={status.tone} title={status.title}>{status.label}</Badge>
								</TableCell>
								<TableCell class="text-muted-foreground">
									{area.default_tier_floor ?? '—'}
								</TableCell>
								<TableCell class="text-muted-foreground">{boundCountsLabel(area)}</TableCell>
								<TableCell class="text-right whitespace-nowrap">
									<Button
										type="button"
										size="icon-xs"
										variant="ghost"
										disabled={i === 0 || reorderBusy}
										onclick={() => reorder(area.key, 'up')}
										aria-label={`Move ${area.name} up`}
										data-testid="lq-admin-areas-reorder-up"
									>
										<ArrowUpIcon />
									</Button>
									<Button
										type="button"
										size="icon-xs"
										variant="ghost"
										disabled={i === areas.length - 1 || reorderBusy}
										onclick={() => reorder(area.key, 'down')}
										aria-label={`Move ${area.name} down`}
										data-testid="lq-admin-areas-reorder-down"
									>
										<ArrowDownIcon />
									</Button>
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>
			</div>
		{/if}
	</section>
</PageShell>

{#if newModalOpen}
	<ModalShell bind:open={newModalOpen} title="New practice area" contentClass="sm:max-w-lg">
		<form id="lq-new-area-form" class="flex flex-col gap-4" novalidate onsubmit={submitNew}>
			<FormControl
				id="lq-new-area-key"
				label="Key"
				required
				error={newKeyError}
				help="Lowercase, hyphenated slug — becomes the stable machine identifier and URL segment."
			>
				<Input
					id="lq-new-area-key"
					bind:value={newKey}
					placeholder="litigation"
					required
					disabled={newSubmitting}
					aria-invalid={!!newKeyError}
					aria-describedby={newKeyError ? 'lq-new-area-key-error' : undefined}
					data-testid="lq-admin-areas-new-key"
				/>
			</FormControl>

			<FormControl id="lq-new-area-name" label="Name" required>
				<Input
					id="lq-new-area-name"
					bind:value={newName}
					placeholder="Litigation"
					required
					disabled={newSubmitting}
					data-testid="lq-admin-areas-new-name"
				/>
			</FormControl>

			<FormControl
				id="lq-new-area-unit-label"
				label="Unit label"
				required
				help="The unit-of-work noun the UI renders (e.g. 'Matter', 'Programme', 'Case')."
			>
				<Input
					id="lq-new-area-unit-label"
					bind:value={newUnitLabel}
					placeholder="Case"
					required
					disabled={newSubmitting}
					data-testid="lq-admin-areas-new-unit-label"
				/>
			</FormControl>

			<FormControl id="lq-new-area-doctrine" label="Doctrine" optional>
				<Textarea
					id="lq-new-area-doctrine"
					bind:value={newDoctrine}
					rows={5}
					maxlength={20000}
					placeholder="# Litigation area doctrine"
					disabled={newSubmitting}
					data-testid="lq-admin-areas-new-doctrine"
				/>
			</FormControl>

			<FormControl id="lq-new-area-tier-floor" label="Tier floor" optional>
				<select
					id="lq-new-area-tier-floor"
					class={SELECT_CLASS}
					bind:value={newTierFloor}
					disabled={newSubmitting}
					data-testid="lq-admin-areas-new-tier-floor"
				>
					<option value="">None</option>
					{#each [1, 2, 3, 4, 5] as tier (tier)}
						<option value={String(tier)}>{tier}</option>
					{/each}
				</select>
			</FormControl>

			<FormControl id="lq-new-area-groups" label="Tool groups" optional>
				{#if groupOptions.length === 0}
					<p class="text-xs text-muted-foreground">No registry tool groups available.</p>
				{:else}
					<ul class="flex flex-col gap-2">
						{#each groupOptions as opt (opt.key)}
							<li>
								<label class="flex items-start gap-2 text-sm text-foreground">
									<input
										type="checkbox"
										class="mt-0.5"
										checked={newGroups.has(opt.key)}
										onchange={() => toggleGroup(opt.key)}
										disabled={newSubmitting}
										data-testid={`lq-admin-areas-new-group-${opt.key}`}
									/>
									<span>
										<span class="font-medium">{opt.label}</span>
										{#if opt.description}
											<span class="block text-xs text-muted-foreground">{opt.description}</span>
										{/if}
									</span>
								</label>
							</li>
						{/each}
					</ul>
				{/if}
			</FormControl>

			{#if newSubmitError}
				<Alert intent="error">{newSubmitError}</Alert>
			{/if}
		</form>

		{#snippet footer()}
			<Button
				type="button"
				variant="outline"
				disabled={newSubmitting}
				onclick={() => (newModalOpen = false)}
			>
				Cancel
			</Button>
			<Button
				type="submit"
				form="lq-new-area-form"
				disabled={newSubmitting}
				data-testid="lq-admin-areas-new-submit"
			>
				{newSubmitting ? 'Creating…' : 'Create practice area'}
			</Button>
		{/snippet}
	</ModalShell>
{/if}
