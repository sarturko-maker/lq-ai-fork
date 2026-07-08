<script lang="ts">
	/**
	 * /lq-ai/admin/areas/[key] — practice-area detail/edit (SETUP-4b, ADR-F062 addendum).
	 *
	 * Edit card (name/unit label/doctrine/tier floor) sends ONE PATCH containing
	 * only the dirty fields; the roster (agent_config) is a raw JSON textarea
	 * (D6); three bind cards (tool groups/skills/playbooks) show current
	 * bindings with Detach + an attach `<select>` of not-yet-bound catalog
	 * entries; a Danger Zone deletes the area with an inline confirm.
	 *
	 * B-1 (G13(a)): a bound row whose catalog entry isn't Library-adopted (or
	 * has no catalog entry at all — registry drift) gets a compact inline
	 * warning chip — `build_area_inventory` fail-closes on it server-side, so
	 * the agent silently never receives that capability at run time.
	 *
	 * Generation-B surface (plan D1): semantic tokens + ModalShell-free inline
	 * cards, Badge/Alert/FormControl/Table primitives only — no --lq-* here.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { titleFor } from '$lib/lq-ai/branding/store';
	import { adminApi, practiceAreasApi } from '$lib/lq-ai/api';
	import { auth } from '$lib/lq-ai/auth/store';
	import type { DeploymentCapabilitiesResponse } from '$lib/lq-ai/api/admin';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import { provenanceBadge } from '$lib/lq-ai/library/page-helpers';

	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import Alert from '$lib/lq-ai/components/primitives/Alert.svelte';
	import FormControl from '$lib/lq-ai/components/primitives/FormControl.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';

	import {
		catalogEntriesForKind,
		describeMutationError,
		libraryOnly
	} from '$lib/lq-ai/admin/page-helpers';
	import {
		bindingLabel,
		degradedBindingKeys,
		diffPatch,
		findAreaByKey,
		formatDeleteConflict,
		hasMultipleLedgerBearingGroups,
		orgSkillBadges,
		parseRosterDraft,
		pickerEmptyState,
		unboundOptions
	} from './page-helpers';

	const SELECT_CLASS =
		'h-8 rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30';

	const areaKey = $derived($page.params.key ?? '');

	let areas = $state<PracticeArea[]>([]);
	let catalog = $state<DeploymentCapabilitiesResponse | null>(null);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	const area = $derived(findAreaByKey(areas, areaKey));

	// Catalog projections via the SHARED helper (review fix 4 — the previous
	// inline copy here duplicated the list page's tested implementation).
	// STORE-2: the attach PICKERS are narrowed to Library-adopted entries only —
	// an area's bindings pick from the Library, never directly from the Store
	// (ADR-F065). Label lookups for ALREADY-BOUND rows use the FULL catalog: a
	// bound entry whose Library adoption was later removed (a valid D-F state —
	// "stays attached but stops resolving") must keep its human label rather
	// than regress to the raw key (STORE-2 review fix).
	const skillCatalogAll = $derived(catalogEntriesForKind(catalog, 'skill'));
	const toolCatalogAll = $derived(catalogEntriesForKind(catalog, 'tool'));
	const playbookCatalogAll = $derived(catalogEntriesForKind(catalog, 'playbook'));

	// B-2b (decision 5) — org-authored skill provenance, keyed by skill key. Reads the
	// FULL catalog response directly (skillCatalogAll's CatalogOption projection strips
	// source/author/approver) so a bound skill whose catalog entry resolves with
	// source='org' gets the "Org-authored · …" badge next to the degraded chip below.
	const orgSkillBadgeByKey = $derived(orgSkillBadges(catalog));
	const skillCatalog = $derived(libraryOnly(skillCatalogAll));
	const toolCatalog = $derived(libraryOnly(toolCatalogAll));
	const playbookCatalog = $derived(libraryOnly(playbookCatalogAll));

	// G13(a) — bound keys whose catalog entry isn't Library-adopted (or is
	// missing entirely). `build_area_inventory` fail-closes on these server-
	// side, so a bound-but-degraded capability never reaches the agent even
	// though the row shows it as "bound". Checked against the FULL per-kind
	// catalog, never `libraryOnly(...)` (see `degradedBindingKeys` docstring).
	const degradedGroupKeys = $derived(
		area ? degradedBindingKeys(toolCatalogAll, area.bound_tool_groups) : new Set<string>()
	);
	const degradedSkillKeys = $derived(
		area ? degradedBindingKeys(skillCatalogAll, area.bound_skills) : new Set<string>()
	);
	const degradedPlaybookKeys = $derived(
		area
			? degradedBindingKeys(
					playbookCatalogAll,
					area.bound_playbooks.map((pb) => String(pb.id))
				)
			: new Set<string>()
	);

	// Attach `<select>` option sets — computed here (not `{@const}`, which must be
	// an IMMEDIATE child of an {#if}/{:else}/etc., not nested inside a <section>).
	const groupOptions = $derived(area ? unboundOptions(toolCatalog, area.bound_tool_groups) : []);
	const skillOptions = $derived(area ? unboundOptions(skillCatalog, area.bound_skills) : []);
	const playbookOptions = $derived(
		area ? unboundOptions(playbookCatalog, area.bound_playbooks.map((pb) => pb.id)) : []
	);

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
			loadError = describeMutationError(e, 'Failed to load this practice area.');
		} finally {
			loading = false;
		}
	}

	function applyUpdated(updated: PracticeArea) {
		areas = areas.map((a) => (a.key === updated.key ? updated : a));
	}

	// ----- Edit card (name/unit label/doctrine/tier floor) -----
	let loadedKey = $state<string | null>(null);
	let draftName = $state('');
	let draftUnitLabel = $state('');
	let draftDoctrine = $state('');
	let draftTierFloor = $state('');
	// '' = Inherit deployment default (SETUP-5a, ADR-F063).
	let draftBudgetProfile = $state('');
	let draftRoster = $state('');
	let editSaving = $state(false);
	let editError = $state<string | null>(null);
	let rosterSaving = $state(false);
	let rosterError = $state<string | null>(null);

	// Reset the drafts ONLY when navigating to a different area — never when the
	// underlying `area` object merely refreshes after a save (that would clobber
	// an in-progress edit elsewhere on the page).
	$effect(() => {
		if (area && area.key !== loadedKey) {
			loadedKey = area.key;
			draftName = area.name;
			draftUnitLabel = area.unit_label;
			draftDoctrine = area.profile_md ?? '';
			draftTierFloor = area.default_tier_floor === null ? '' : String(area.default_tier_floor);
			draftBudgetProfile = area.default_budget_profile ?? '';
			draftRoster = JSON.stringify(area.agent_config ?? {}, null, 2);
		}
	});

	const rosterParsed = $derived(parseRosterDraft(draftRoster));

	async function saveEdit() {
		if (!area) return;
		const patch = diffPatch(area, {
			name: draftName,
			unit_label: draftUnitLabel,
			profile_md: draftDoctrine,
			default_tier_floor: draftTierFloor,
			default_budget_profile: draftBudgetProfile
		});
		if (Object.keys(patch).length === 0) return;
		editSaving = true;
		editError = null;
		try {
			const updated = await practiceAreasApi.updatePracticeArea(area.key, patch);
			applyUpdated(updated);
			draftName = updated.name;
			draftUnitLabel = updated.unit_label;
			draftDoctrine = updated.profile_md ?? '';
			draftTierFloor = updated.default_tier_floor === null ? '' : String(updated.default_tier_floor);
			draftBudgetProfile = updated.default_budget_profile ?? '';
		} catch (e) {
			editError = describeMutationError(e, 'Failed to save changes.');
		} finally {
			editSaving = false;
		}
	}

	async function saveRoster() {
		if (!area || rosterParsed.error || rosterParsed.value === null) return;
		rosterSaving = true;
		rosterError = null;
		try {
			const updated = await practiceAreasApi.updatePracticeArea(area.key, {
				agent_config: rosterParsed.value
			});
			applyUpdated(updated);
			draftRoster = JSON.stringify(updated.agent_config ?? {}, null, 2);
		} catch (e) {
			rosterError = describeMutationError(e, 'Failed to save the roster.');
		} finally {
			rosterSaving = false;
		}
	}

	// ----- Bind cards: tool groups / skills / playbooks -----
	let groupBusy = $state(false);
	let groupError = $state<string | null>(null);
	let groupSelection = $state('');

	let skillBusy = $state(false);
	let skillError = $state<string | null>(null);
	let skillSelection = $state('');

	let playbookBusy = $state(false);
	let playbookError = $state<string | null>(null);
	let playbookSelection = $state('');

	async function attachGroup() {
		if (!area || !groupSelection) return;
		groupBusy = true;
		groupError = null;
		try {
			await practiceAreasApi.attachToolGroup(area.key, groupSelection);
			groupSelection = '';
			await load();
		} catch (e) {
			groupError = describeMutationError(e, 'Failed to attach the tool group.');
		} finally {
			groupBusy = false;
		}
	}

	async function detachGroup(groupKey: string) {
		if (!area) return;
		groupBusy = true;
		groupError = null;
		try {
			await practiceAreasApi.detachToolGroup(area.key, groupKey);
			await load();
		} catch (e) {
			groupError = describeMutationError(e, 'Failed to detach the tool group.');
		} finally {
			groupBusy = false;
		}
	}

	async function attachSkillBinding() {
		if (!area || !skillSelection) return;
		skillBusy = true;
		skillError = null;
		try {
			await practiceAreasApi.attachSkill(area.key, skillSelection);
			skillSelection = '';
			await load();
		} catch (e) {
			skillError = describeMutationError(e, 'Failed to attach the skill.');
		} finally {
			skillBusy = false;
		}
	}

	async function detachSkillBinding(name: string) {
		if (!area) return;
		skillBusy = true;
		skillError = null;
		try {
			await practiceAreasApi.detachSkill(area.key, name);
			await load();
		} catch (e) {
			skillError = describeMutationError(e, 'Failed to detach the skill.');
		} finally {
			skillBusy = false;
		}
	}

	async function attachPlaybookBinding() {
		if (!area || !playbookSelection) return;
		playbookBusy = true;
		playbookError = null;
		try {
			await practiceAreasApi.attachPlaybook(area.key, playbookSelection);
			playbookSelection = '';
			await load();
		} catch (e) {
			playbookError = describeMutationError(e, 'Failed to attach the playbook.');
		} finally {
			playbookBusy = false;
		}
	}

	async function detachPlaybookBinding(id: string) {
		if (!area) return;
		playbookBusy = true;
		playbookError = null;
		try {
			await practiceAreasApi.detachPlaybook(area.key, id);
			await load();
		} catch (e) {
			playbookError = describeMutationError(e, 'Failed to detach the playbook.');
		} finally {
			playbookBusy = false;
		}
	}

	// ----- Danger zone -----
	let deleteConfirming = $state(false);
	let deleteBusy = $state(false);
	let deleteError = $state<string | null>(null);

	async function confirmDelete() {
		if (!area) return;
		deleteBusy = true;
		deleteError = null;
		try {
			await practiceAreasApi.deletePracticeArea(area.key);
			await goto('/lq-ai/admin/areas');
		} catch (e) {
			deleteError = formatDeleteConflict(e);
			deleteConfirming = false;
		} finally {
			deleteBusy = false;
		}
	}

	onMount(async () => {
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		if (!$auth.user.is_admin) {
			console.warn('non-admin attempted /lq-ai/admin/areas/[key]; redirecting');
			goto('/lq-ai');
			return;
		}
		await load();
	});
</script>

<svelte:head>
	<title>{$titleFor(`${area ? `${area.name} — ` : ''}Practice area`, 'admin')}</title>
</svelte:head>

<PageShell size="wide" data-testid="lq-admin-area-page">
	<a href="/lq-ai/admin/areas" class="text-sm text-muted-foreground hover:underline" data-testid="lq-admin-area-back-link">
		&larr; Practice areas
	</a>

	{#if loading}
		<p class="mt-6 text-sm text-muted-foreground">Loading…</p>
	{:else if loadError}
		<div class="mt-6">
			<Alert intent="error">{loadError}</Alert>
		</div>
	{:else if !area}
		<div class="mt-6 space-y-2" data-testid="lq-admin-area-not-found">
			<SectionHeader size="section" title="Practice area not found" />
			<p class="text-sm text-muted-foreground">
				No practice area with key <code>{areaKey}</code> exists.
			</p>
		</div>
	{:else}
		<SectionHeader title={area.name} subtitle={`Key: ${area.key}`} class="mt-3" />

		<!-- G13(a) — compact inline warning for a bound-but-degraded capability
		     (bound, but not in the Library, so the agent never receives it). -->
		{#snippet degradedBindingChip(degraded: boolean, testid: string)}
			{#if degraded}
				<span
					class="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300"
					data-testid={testid}
				>
					Not in your Library — the agent will not receive this.
					<a href="/lq-ai/admin/store" class="underline">Adopt in Store</a>
				</span>
			{/if}
		{/snippet}

		<!-- ----- Edit card ----- -->
		<section class="mt-6 space-y-3 rounded-lg border border-border p-4" aria-label="Edit">
			<SectionHeader size="section" title="Details" />
			<FormControl id="lq-area-name" label="Name">
				<Input id="lq-area-name" bind:value={draftName} data-testid="lq-admin-area-name" />
			</FormControl>
			<FormControl id="lq-area-unit-label" label="Unit label">
				<Input
					id="lq-area-unit-label"
					bind:value={draftUnitLabel}
					data-testid="lq-admin-area-unit-label"
				/>
			</FormControl>
			<FormControl
				id="lq-area-doctrine"
				label="Doctrine"
				optional
				help={`${draftDoctrine.length} / 20000 characters`}
			>
				<Textarea
					id="lq-area-doctrine"
					bind:value={draftDoctrine}
					rows={12}
					maxlength={20000}
					data-testid="lq-admin-area-doctrine"
				/>
			</FormControl>
			<FormControl id="lq-area-tier-floor" label="Tier floor" optional>
				<select
					id="lq-area-tier-floor"
					class={SELECT_CLASS}
					bind:value={draftTierFloor}
					data-testid="lq-admin-area-tier-floor"
				>
					<option value="">None</option>
					{#each [1, 2, 3, 4, 5] as tier (tier)}
						<option value={String(tier)}>{tier}</option>
					{/each}
				</select>
			</FormControl>
			<!-- SETUP-5a (ADR-F063): area default budget profile. "Inherit" sends an
			     explicit null ONLY when the field was changed (dirty-fields-only PATCH). -->
			<FormControl id="lq-area-budget-profile" label="Default budget profile" optional>
				<select
					id="lq-area-budget-profile"
					class={SELECT_CLASS}
					bind:value={draftBudgetProfile}
					data-testid="lq-admin-area-budget-profile"
				>
					<option value="">Inherit deployment default</option>
					<option value="economy">Economy</option>
					<option value="balanced">Balanced</option>
					<option value="generous">Generous</option>
				</select>
			</FormControl>
			{#if editError}
				<Alert intent="error">{editError}</Alert>
			{/if}
			<Button
				type="button"
				disabled={editSaving}
				onclick={saveEdit}
				data-testid="lq-admin-area-save"
			>
				{editSaving ? 'Saving…' : 'Save'}
			</Button>
		</section>

		<!-- ----- Roster card (D6) ----- -->
		<section class="mt-6 space-y-3 rounded-lg border border-border p-4" aria-label="Roster">
			<SectionHeader
				size="section"
				title="Subagent roster"
				subtitle="Declarative agent_config JSON — subagents, by-reference playbooks/MCPs."
			/>
			<p class="text-xs text-muted-foreground">
				A brand-new area has no bound skills yet — a subagent referencing a skill 404/400s until
				that skill is attached below (the server validates against the area's bound set).
			</p>
			<Textarea
				bind:value={draftRoster}
				rows={10}
				class="font-mono text-xs"
				data-testid="lq-admin-area-roster"
			/>
			{#if rosterParsed.error}
				<Alert intent="error">{rosterParsed.error}</Alert>
			{/if}
			{#if rosterError}
				<Alert intent="error">{rosterError}</Alert>
			{/if}
			<Button
				type="button"
				disabled={rosterSaving || !!rosterParsed.error}
				onclick={saveRoster}
				data-testid="lq-admin-area-roster-save"
			>
				{rosterSaving ? 'Saving…' : 'Save roster'}
			</Button>
		</section>

		<!-- ----- Tool groups ----- -->
		<section class="mt-6 space-y-3 rounded-lg border border-border p-4" aria-label="Tool groups">
			<SectionHeader size="section" title="Tool groups" />
			{#if hasMultipleLedgerBearingGroups(area.bound_tool_groups)}
				<p class="text-xs text-muted-foreground">
					Only the first group's live change feed streams (registry order).
				</p>
			{/if}
			<ul class="flex flex-col gap-1.5" data-testid="lq-admin-area-groups-list">
				{#each area.bound_tool_groups as groupKey (groupKey)}
					<li class="flex items-center justify-between gap-2 rounded-lg border border-border px-3 py-2">
						<span class="flex flex-wrap items-center gap-2">
							<span class="text-sm text-foreground">{bindingLabel(toolCatalogAll, groupKey)}</span>
							{@render degradedBindingChip(
								degradedGroupKeys.has(groupKey),
								`lq-admin-area-groups-degraded-${groupKey}`
							)}
						</span>
						<Button
							type="button"
							size="sm"
							variant="outline"
							disabled={groupBusy}
							onclick={() => detachGroup(groupKey)}
							data-testid={`lq-admin-area-groups-detach-${groupKey}`}
						>
							Detach
						</Button>
					</li>
				{:else}
					<li class="text-xs text-muted-foreground">No tool groups bound.</li>
				{/each}
			</ul>
			{#if groupError}
				<Alert intent="error">{groupError}</Alert>
			{/if}
			{#if groupOptions.length > 0}
				<div class="flex items-end gap-2">
					<select
						class={SELECT_CLASS}
						bind:value={groupSelection}
						disabled={groupBusy}
						data-testid="lq-admin-area-groups-attach-select"
					>
						<option value="">Choose a tool group…</option>
						{#each groupOptions as opt (opt.key)}
							<option value={opt.key}>{opt.label}</option>
						{/each}
					</select>
					<Button
						type="button"
						variant="outline"
						disabled={groupBusy || !groupSelection}
						onclick={attachGroup}
						data-testid="lq-admin-area-groups-attach"
					>
						Attach
					</Button>
				</div>
			{:else if pickerEmptyState(toolCatalog, groupOptions) === 'library-empty'}
				<p class="text-xs text-muted-foreground" data-testid="lq-admin-area-groups-empty">
					Your library has no tools yet —
					<a href="/lq-ai/admin/store" class="underline">browse the Store</a>.
				</p>
			{:else if pickerEmptyState(toolCatalog, groupOptions) === 'all-attached'}
				<p class="text-xs text-muted-foreground" data-testid="lq-admin-area-groups-empty">
					Everything in your library is already attached.
				</p>
			{/if}
		</section>

		<!-- ----- Skills ----- -->
		<section class="mt-6 space-y-3 rounded-lg border border-border p-4" aria-label="Skills">
			<SectionHeader size="section" title="Skills" />
			<ul class="flex flex-col gap-1.5" data-testid="lq-admin-area-skills-list">
				{#each area.bound_skills as skillName (skillName)}
					{@const orgBadge = orgSkillBadgeByKey.get(skillName)}
					<li class="flex items-center justify-between gap-2 rounded-lg border border-border px-3 py-2">
						<span class="flex flex-wrap items-center gap-2">
							<a
								href="/lq-ai/skills/{encodeURIComponent(skillName)}"
								class="text-sm text-foreground hover:underline"
							>
								{bindingLabel(skillCatalogAll, skillName)}
							</a>
							{#if orgBadge}
								<span
									class="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted px-2 py-0.5 text-xs text-muted-foreground"
									data-testid={`lq-admin-area-skill-org-${skillName}`}
								>
									{provenanceBadge(orgBadge)}
								</span>
							{/if}
							{@render degradedBindingChip(
								degradedSkillKeys.has(skillName),
								`lq-admin-area-skills-degraded-${skillName}`
							)}
						</span>
						<Button
							type="button"
							size="sm"
							variant="outline"
							disabled={skillBusy}
							onclick={() => detachSkillBinding(skillName)}
							data-testid={`lq-admin-area-skills-detach-${skillName}`}
						>
							Detach
						</Button>
					</li>
				{:else}
					<li class="text-xs text-muted-foreground">No skills bound.</li>
				{/each}
			</ul>
			{#if skillError}
				<Alert intent="error">{skillError}</Alert>
			{/if}
			{#if skillOptions.length > 0}
				<div class="flex items-end gap-2">
					<select
						class={SELECT_CLASS}
						bind:value={skillSelection}
						disabled={skillBusy}
						data-testid="lq-admin-area-skills-attach-select"
					>
						<option value="">Choose a skill…</option>
						{#each skillOptions as opt (opt.key)}
							<option value={opt.key}>{opt.label}</option>
						{/each}
					</select>
					<Button
						type="button"
						variant="outline"
						disabled={skillBusy || !skillSelection}
						onclick={attachSkillBinding}
						data-testid="lq-admin-area-skills-attach"
					>
						Attach
					</Button>
				</div>
			{:else if pickerEmptyState(skillCatalog, skillOptions) === 'library-empty'}
				<p class="text-xs text-muted-foreground" data-testid="lq-admin-area-skills-empty">
					Your library has no skills yet —
					<a href="/lq-ai/admin/store" class="underline">browse the Store</a>.
				</p>
			{:else if pickerEmptyState(skillCatalog, skillOptions) === 'all-attached'}
				<p class="text-xs text-muted-foreground" data-testid="lq-admin-area-skills-empty">
					Everything in your library is already attached.
				</p>
			{/if}
		</section>

		<!-- ----- Playbooks ----- -->
		<section class="mt-6 space-y-3 rounded-lg border border-border p-4" aria-label="Playbooks">
			<SectionHeader size="section" title="Playbooks" />
			<ul class="flex flex-col gap-1.5" data-testid="lq-admin-area-playbooks-list">
				{#each area.bound_playbooks as pb (pb.id)}
					<li class="flex items-center justify-between gap-2 rounded-lg border border-border px-3 py-2">
						<span class="flex flex-wrap items-center gap-2">
							<span class="text-sm text-foreground">{pb.name}</span>
							{@render degradedBindingChip(
								degradedPlaybookKeys.has(String(pb.id)),
								`lq-admin-area-playbooks-degraded-${pb.id}`
							)}
						</span>
						<Button
							type="button"
							size="sm"
							variant="outline"
							disabled={playbookBusy}
							onclick={() => detachPlaybookBinding(pb.id)}
							data-testid={`lq-admin-area-playbooks-detach-${pb.id}`}
						>
							Detach
						</Button>
					</li>
				{:else}
					<li class="text-xs text-muted-foreground">No playbooks bound.</li>
				{/each}
			</ul>
			{#if playbookError}
				<Alert intent="error">{playbookError}</Alert>
			{/if}
			{#if playbookOptions.length > 0}
				<div class="flex items-end gap-2">
					<select
						class={SELECT_CLASS}
						bind:value={playbookSelection}
						disabled={playbookBusy}
						data-testid="lq-admin-area-playbooks-attach-select"
					>
						<option value="">Choose a playbook…</option>
						{#each playbookOptions as opt (opt.key)}
							<option value={opt.key}>{opt.label}</option>
						{/each}
					</select>
					<Button
						type="button"
						variant="outline"
						disabled={playbookBusy || !playbookSelection}
						onclick={attachPlaybookBinding}
						data-testid="lq-admin-area-playbooks-attach"
					>
						Attach
					</Button>
				</div>
			{:else if pickerEmptyState(playbookCatalog, playbookOptions) === 'library-empty'}
				<p class="text-xs text-muted-foreground" data-testid="lq-admin-area-playbooks-empty">
					Your library has no playbooks yet —
					<a href="/lq-ai/admin/store" class="underline">browse the Store</a>.
				</p>
			{:else if pickerEmptyState(playbookCatalog, playbookOptions) === 'all-attached'}
				<p class="text-xs text-muted-foreground" data-testid="lq-admin-area-playbooks-empty">
					Everything in your library is already attached.
				</p>
			{/if}
		</section>

		<!-- ----- Danger zone ----- -->
		<section class="mt-6 space-y-3 rounded-lg border border-destructive/30 p-4" aria-label="Danger zone">
			<SectionHeader size="section" title="Danger zone" />
			{#if deleteError}
				<Alert intent="error">{deleteError}</Alert>
			{/if}
			{#if deleteConfirming}
				<div class="flex items-center gap-2">
					<span class="text-sm text-muted-foreground">Delete this practice area?</span>
					<Button
						type="button"
						variant="destructive"
						disabled={deleteBusy}
						onclick={confirmDelete}
						data-testid="lq-admin-area-delete-confirm"
					>
						Confirm
					</Button>
					<Button
						type="button"
						variant="ghost"
						disabled={deleteBusy}
						onclick={() => (deleteConfirming = false)}
						data-testid="lq-admin-area-delete-cancel"
					>
						Cancel
					</Button>
				</div>
			{:else}
				<Button
					type="button"
					variant="destructive"
					onclick={() => (deleteConfirming = true)}
					data-testid="lq-admin-area-delete-open"
				>
					Delete practice area
				</Button>
			{/if}
		</section>
	{/if}
</PageShell>
