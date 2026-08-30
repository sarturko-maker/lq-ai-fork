<script lang="ts">
	/**
	 * /lq-ai/admin/intake-mailboxes — bind mailboxes to a practice area + owner
	 * (INTAKE-5a, ADR-F086).
	 *
	 * The API has existed since INTAKE-1 (`api/app/api/admin_intake_mailboxes.py`);
	 * this is its first page. A binding is `(provider, inbox_id) -> address,
	 * practice area, owner user` plus the run defaults (`default_budget_profile`,
	 * `max_steps`) new runs on this mailbox's threads inherit. There are no
	 * secrets anywhere in this API — nothing here is a token or credential.
	 *
	 * Create binds `provider`/`inbox_id`/`address`/`practice_area_id` for good —
	 * the server never lets a PATCH touch them (rebind by deleting and
	 * recreating). Edit only ever touches `active`/`owner_user_id`/
	 * `default_budget_profile`/`max_steps`. Delete is a soft-delete, confirmed
	 * through ModalShell rather than a bare `confirm()` (a live mailbox stops
	 * routing mail into an area the moment it's disconnected here).
	 *
	 * Users/Areas-page precedent: semantic tokens + ModalShell/Table/Badge/
	 * Alert/FormControl only — no --lq-* on this page (F013).
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { titleFor } from '$lib/lq-ai/branding/store';
	import { adminApi, intakeMailboxesApi, practiceAreasApi } from '$lib/lq-ai/api';
	import { auth } from '$lib/lq-ai/auth/store';
	import type {
		IntakeMailbox,
		IntakeMailboxBudgetProfile
	} from '$lib/lq-ai/api/intakeMailboxes';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { AdminUserRow } from '$lib/lq-ai/types';

	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
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

	import {
		areaNameFor,
		budgetProfileLabel,
		buildAreaNameMap,
		buildUserEmailMap,
		describeMutationError,
		formatDateTime,
		mailboxStatusView,
		ownerEmailFor,
		parseBudgetProfile,
		parseMaxSteps,
		validateAddress,
		validateInboxId,
		validateMaxSteps,
		validateOwner,
		validatePracticeArea
	} from './page-helpers';

	const SELECT_CLASS =
		'h-8 rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30';

	let mailboxes = $state<IntakeMailbox[]>([]);
	let areas = $state<PracticeArea[]>([]);
	let users = $state<AdminUserRow[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	const areaMap = $derived(buildAreaNameMap(areas));
	const userMap = $derived(buildUserEmailMap(users));

	async function load() {
		loading = true;
		loadError = null;
		try {
			// listUsers has no "all" sentinel — a page well past this org's headcount
			// covers every real deployment; a picker beyond that is its own slice.
			const [mailboxList, areaList, userList] = await Promise.all([
				intakeMailboxesApi.listIntakeMailboxes(),
				practiceAreasApi.listPracticeAreas(),
				adminApi.listUsers({ limit: 200 })
			]);
			mailboxes = mailboxList;
			areas = areaList.practice_areas;
			users = userList.users;
		} catch (e) {
			loadError = describeMutationError(e, 'Failed to load intake mailboxes.');
		} finally {
			loading = false;
		}
	}

	// ----- New mailbox modal -----
	let newModalOpen = $state(false);
	let newProvider = $state('agentmail');
	let newInboxId = $state('');
	let newAddress = $state('');
	let newPracticeAreaId = $state('');
	let newOwnerUserId = $state('');
	let newBudgetProfile = $state('');
	let newMaxSteps = $state('');
	let newInboxIdError = $state<string | null>(null);
	let newAddressError = $state<string | null>(null);
	let newPracticeAreaError = $state<string | null>(null);
	let newOwnerError = $state<string | null>(null);
	let newMaxStepsError = $state<string | null>(null);
	let newSubmitError = $state<string | null>(null);
	let newSubmitting = $state(false);

	function openNewModal() {
		newProvider = 'agentmail';
		newInboxId = '';
		newAddress = '';
		newPracticeAreaId = '';
		newOwnerUserId = '';
		newBudgetProfile = '';
		newMaxSteps = '';
		newInboxIdError = null;
		newAddressError = null;
		newPracticeAreaError = null;
		newOwnerError = null;
		newMaxStepsError = null;
		newSubmitError = null;
		newModalOpen = true;
	}

	async function submitNew(event: SubmitEvent) {
		event.preventDefault();
		newInboxIdError = validateInboxId(newInboxId);
		newAddressError = validateAddress(newAddress);
		newPracticeAreaError = validatePracticeArea(newPracticeAreaId);
		newOwnerError = validateOwner(newOwnerUserId);
		newMaxStepsError = validateMaxSteps(newMaxSteps);
		if (
			newInboxIdError ||
			newAddressError ||
			newPracticeAreaError ||
			newOwnerError ||
			newMaxStepsError
		) {
			return;
		}
		newSubmitError = null;
		newSubmitting = true;
		try {
			const created = await intakeMailboxesApi.createIntakeMailbox({
				provider: newProvider.trim() || undefined,
				inbox_id: newInboxId.trim(),
				address: newAddress.trim(),
				practice_area_id: newPracticeAreaId,
				owner_user_id: newOwnerUserId,
				default_budget_profile: parseBudgetProfile(newBudgetProfile),
				max_steps: parseMaxSteps(newMaxSteps)
			});
			mailboxes = [created, ...mailboxes];
			newModalOpen = false;
		} catch (e) {
			newSubmitError = describeMutationError(e, 'Failed to bind the intake mailbox.');
		} finally {
			newSubmitting = false;
		}
	}

	// ----- Edit mailbox modal -----
	let editModalOpen = $state(false);
	let editTarget = $state<IntakeMailbox | null>(null);
	let editActive = $state(true);
	let editOwnerUserId = $state('');
	let editBudgetProfile = $state('');
	let editMaxSteps = $state('');
	let editOwnerError = $state<string | null>(null);
	let editMaxStepsError = $state<string | null>(null);
	let editSubmitError = $state<string | null>(null);
	let editSubmitting = $state(false);

	function openEditModal(row: IntakeMailbox) {
		editTarget = row;
		editActive = row.active;
		editOwnerUserId = row.owner_user_id;
		editBudgetProfile = row.default_budget_profile ?? '';
		editMaxSteps = row.max_steps === null ? '' : String(row.max_steps);
		editOwnerError = null;
		editMaxStepsError = null;
		editSubmitError = null;
		editModalOpen = true;
	}

	async function submitEdit(event: SubmitEvent) {
		event.preventDefault();
		if (!editTarget) return;
		editOwnerError = validateOwner(editOwnerUserId);
		editMaxStepsError = validateMaxSteps(editMaxSteps);
		if (editOwnerError || editMaxStepsError) return;
		editSubmitError = null;
		editSubmitting = true;
		try {
			const updated = await intakeMailboxesApi.updateIntakeMailbox(editTarget.id, {
				active: editActive,
				owner_user_id: editOwnerUserId,
				default_budget_profile: parseBudgetProfile(editBudgetProfile),
				max_steps: parseMaxSteps(editMaxSteps)
			});
			mailboxes = mailboxes.map((m) => (m.id === updated.id ? updated : m));
			editModalOpen = false;
			editTarget = null;
		} catch (e) {
			editSubmitError = describeMutationError(e, 'Failed to update the intake mailbox.');
		} finally {
			editSubmitting = false;
		}
	}

	// ----- Delete confirm modal -----
	let deleteModalOpen = $state(false);
	let deleteTarget = $state<IntakeMailbox | null>(null);
	let deleteError = $state<string | null>(null);
	let deleteBusy = $state(false);

	function openDeleteModal(row: IntakeMailbox) {
		deleteTarget = row;
		deleteError = null;
		deleteModalOpen = true;
	}

	async function confirmDelete() {
		if (!deleteTarget) return;
		deleteBusy = true;
		deleteError = null;
		try {
			await intakeMailboxesApi.deleteIntakeMailbox(deleteTarget.id);
			mailboxes = mailboxes.filter((m) => m.id !== deleteTarget?.id);
			deleteModalOpen = false;
			deleteTarget = null;
		} catch (e) {
			deleteError = describeMutationError(e, 'Failed to disconnect the intake mailbox.');
		} finally {
			deleteBusy = false;
		}
	}

	onMount(async () => {
		// Per-page admin guard (Users/Areas-page precedent — no admin-layout guard exists).
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		if (!$auth.user.is_admin) {
			console.warn('non-admin attempted /lq-ai/admin/intake-mailboxes; redirecting');
			goto('/lq-ai');
			return;
		}
		await load();
	});
</script>

<svelte:head>
	<title>{$titleFor('Intake mailboxes', 'admin')}</title>
</svelte:head>

<PageShell size="wide" data-testid="lq-admin-intake-mailboxes-page">
	<div class="flex items-start justify-between gap-4">
		<SectionHeader
			title="Intake mailboxes"
			subtitle="Bind an inbox to a practice area and an owner — every thread it receives becomes a matter under that area, opened on that owner's behalf."
		/>
		<Button
			type="button"
			onclick={openNewModal}
			disabled={areas.length === 0}
			data-testid="lq-admin-intake-mailboxes-new-open"
		>
			Bind mailbox
		</Button>
	</div>

	{#if !loading && areas.length === 0 && !loadError}
		<div class="mt-4">
			<Alert intent="info">
				No practice areas exist yet. Create one on the
				<a href="/lq-ai/admin/areas" class="underline">Practice areas</a> page before binding a
				mailbox.
			</Alert>
		</div>
	{/if}

	<section class="mt-6">
		{#if loadError}
			<Alert intent="error">{loadError}</Alert>
		{:else if loading}
			<p class="text-sm text-muted-foreground">Loading intake mailboxes…</p>
		{:else if mailboxes.length === 0}
			<p class="text-sm text-muted-foreground">
				No intake mailboxes bound yet. Use "Bind mailbox" to connect one.
			</p>
		{:else}
			<div class="rounded-lg border border-border">
				<Table data-testid="lq-admin-intake-mailboxes-table">
					<TableHeader>
						<TableRow>
							<TableHead>Address</TableHead>
							<TableHead>Provider</TableHead>
							<TableHead>Practice area</TableHead>
							<TableHead>Owner</TableHead>
							<TableHead>Status</TableHead>
							<TableHead>Budget profile</TableHead>
							<TableHead class="text-right">Actions</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each mailboxes as row (row.id)}
							{@const status = mailboxStatusView(row)}
							<TableRow data-testid="lq-admin-intake-mailboxes-row">
								<TableCell class="max-w-56 truncate font-medium text-foreground" title={row.address}>
									{row.address}
								</TableCell>
								<TableCell class="text-muted-foreground">{row.provider}</TableCell>
								<TableCell class="text-muted-foreground">
									{areaNameFor(areaMap, row.practice_area_id)}
								</TableCell>
								<TableCell class="text-muted-foreground">
									{ownerEmailFor(userMap, row.owner_user_id)}
								</TableCell>
								<TableCell>
									<Badge variant={status.tone}>{status.label}</Badge>
								</TableCell>
								<TableCell class="text-muted-foreground">
									{budgetProfileLabel(row.default_budget_profile)}
								</TableCell>
								<TableCell class="text-right whitespace-nowrap">
									<Button
										type="button"
										variant="outline"
										size="sm"
										onclick={() => openEditModal(row)}
										data-testid="lq-admin-intake-mailboxes-edit"
									>
										Edit
									</Button>
									<Button
										type="button"
										variant="destructive"
										size="sm"
										onclick={() => openDeleteModal(row)}
										data-testid="lq-admin-intake-mailboxes-delete"
									>
										Disconnect
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
	<ModalShell bind:open={newModalOpen} title="Bind mailbox" contentClass="sm:max-w-lg">
		<form id="lq-new-mailbox-form" class="flex flex-col gap-4" novalidate onsubmit={submitNew}>
			<FormControl
				id="lq-new-mailbox-provider"
				label="Provider"
				help="The inbox provider — 'agentmail' unless this deployment runs another."
			>
				<Input
					id="lq-new-mailbox-provider"
					bind:value={newProvider}
					placeholder="agentmail"
					disabled={newSubmitting}
					data-testid="lq-admin-intake-mailboxes-new-provider"
				/>
			</FormControl>

			<FormControl
				id="lq-new-mailbox-inbox-id"
				label="Inbox id"
				required
				error={newInboxIdError}
				help="The provider's identifier for this inbox — not the email address."
			>
				<Input
					id="lq-new-mailbox-inbox-id"
					bind:value={newInboxId}
					placeholder="inbox_abc123"
					required
					disabled={newSubmitting}
					aria-invalid={!!newInboxIdError}
					aria-describedby={newInboxIdError ? 'lq-new-mailbox-inbox-id-error' : undefined}
					data-testid="lq-admin-intake-mailboxes-new-inbox-id"
				/>
			</FormControl>

			<FormControl
				id="lq-new-mailbox-address"
				label="Address"
				required
				error={newAddressError}
				help="The email address senders use to reach this mailbox."
			>
				<Input
					id="lq-new-mailbox-address"
					type="email"
					bind:value={newAddress}
					placeholder="intake@example.com"
					required
					disabled={newSubmitting}
					aria-invalid={!!newAddressError}
					aria-describedby={newAddressError ? 'lq-new-mailbox-address-error' : undefined}
					data-testid="lq-admin-intake-mailboxes-new-address"
				/>
			</FormControl>

			<FormControl
				id="lq-new-mailbox-area"
				label="Practice area"
				required
				error={newPracticeAreaError}
				help="Every matter this mailbox opens is filed under this area."
			>
				<select
					id="lq-new-mailbox-area"
					class={SELECT_CLASS}
					bind:value={newPracticeAreaId}
					disabled={newSubmitting}
					aria-invalid={!!newPracticeAreaError}
					data-testid="lq-admin-intake-mailboxes-new-area"
				>
					<option value="">Choose a practice area…</option>
					{#each areas as area (area.id)}
						<option value={area.id}>{area.name}</option>
					{/each}
				</select>
			</FormControl>

			<FormControl
				id="lq-new-mailbox-owner"
				label="Owner"
				required
				error={newOwnerError}
				help="Owns every candidate matter and run this mailbox produces, and gives every approval."
			>
				<select
					id="lq-new-mailbox-owner"
					class={SELECT_CLASS}
					bind:value={newOwnerUserId}
					disabled={newSubmitting}
					aria-invalid={!!newOwnerError}
					data-testid="lq-admin-intake-mailboxes-new-owner"
				>
					<option value="">Choose an owner…</option>
					{#each users as user (user.id)}
						<option value={user.id}>{user.email}</option>
					{/each}
				</select>
			</FormControl>

			<FormControl
				id="lq-new-mailbox-budget"
				label="Budget profile"
				optional
				help="The run default for threads on this mailbox. Inherit uses the area's own default."
			>
				<select
					id="lq-new-mailbox-budget"
					class={SELECT_CLASS}
					bind:value={newBudgetProfile}
					disabled={newSubmitting}
					data-testid="lq-admin-intake-mailboxes-new-budget"
				>
					<option value="">Inherit</option>
					<option value="economy">Economy</option>
					<option value="balanced">Balanced</option>
					<option value="generous">Generous</option>
				</select>
			</FormControl>

			<FormControl
				id="lq-new-mailbox-max-steps"
				label="Max steps"
				optional
				error={newMaxStepsError}
				help="Caps the agent's step count on this mailbox's runs (1–600). Leave blank to use the deployment default."
			>
				<Input
					id="lq-new-mailbox-max-steps"
					type="number"
					min="1"
					max="600"
					bind:value={newMaxSteps}
					placeholder="e.g. 60"
					disabled={newSubmitting}
					aria-invalid={!!newMaxStepsError}
					aria-describedby={newMaxStepsError ? 'lq-new-mailbox-max-steps-error' : undefined}
					data-testid="lq-admin-intake-mailboxes-new-max-steps"
				/>
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
				form="lq-new-mailbox-form"
				disabled={newSubmitting}
				data-testid="lq-admin-intake-mailboxes-new-submit"
			>
				{newSubmitting ? 'Binding…' : 'Bind mailbox'}
			</Button>
		{/snippet}
	</ModalShell>
{/if}

{#if editModalOpen && editTarget}
	<ModalShell
		bind:open={editModalOpen}
		title={`Edit ${editTarget.address}`}
		contentClass="sm:max-w-lg"
	>
		<form id="lq-edit-mailbox-form" class="flex flex-col gap-4" novalidate onsubmit={submitEdit}>
			<p class="text-xs text-muted-foreground">
				Provider, inbox id, address, and practice area are set at binding time and can't be
				changed here — disconnect and re-bind to change them.
			</p>

			<FormControl id="lq-edit-mailbox-active" label="Status">
				<label class="flex items-center gap-2 text-sm text-foreground">
					<input
						id="lq-edit-mailbox-active"
						type="checkbox"
						bind:checked={editActive}
						disabled={editSubmitting}
						data-testid="lq-admin-intake-mailboxes-edit-active"
					/>
					Active — this mailbox is being polled for new mail
				</label>
			</FormControl>

			<FormControl
				id="lq-edit-mailbox-owner"
				label="Owner"
				required
				error={editOwnerError}
				help="Owns every candidate matter and run this mailbox produces, and gives every approval."
			>
				<select
					id="lq-edit-mailbox-owner"
					class={SELECT_CLASS}
					bind:value={editOwnerUserId}
					disabled={editSubmitting}
					aria-invalid={!!editOwnerError}
					data-testid="lq-admin-intake-mailboxes-edit-owner"
				>
					{#each users as user (user.id)}
						<option value={user.id}>{user.email}</option>
					{/each}
				</select>
			</FormControl>

			<FormControl
				id="lq-edit-mailbox-budget"
				label="Budget profile"
				optional
				help="The run default for threads on this mailbox. Inherit uses the area's own default."
			>
				<select
					id="lq-edit-mailbox-budget"
					class={SELECT_CLASS}
					bind:value={editBudgetProfile}
					disabled={editSubmitting}
					data-testid="lq-admin-intake-mailboxes-edit-budget"
				>
					<option value="">Inherit</option>
					<option value="economy">Economy</option>
					<option value="balanced">Balanced</option>
					<option value="generous">Generous</option>
				</select>
			</FormControl>

			<FormControl
				id="lq-edit-mailbox-max-steps"
				label="Max steps"
				optional
				error={editMaxStepsError}
				help="Caps the agent's step count on this mailbox's runs (1–600). Leave blank to use the deployment default."
			>
				<Input
					id="lq-edit-mailbox-max-steps"
					type="number"
					min="1"
					max="600"
					bind:value={editMaxSteps}
					placeholder="e.g. 60"
					disabled={editSubmitting}
					aria-invalid={!!editMaxStepsError}
					aria-describedby={editMaxStepsError ? 'lq-edit-mailbox-max-steps-error' : undefined}
					data-testid="lq-admin-intake-mailboxes-edit-max-steps"
				/>
			</FormControl>

			<p class="text-xs text-muted-foreground">
				Bound {formatDateTime(editTarget.created_at)} · last updated {formatDateTime(
					editTarget.updated_at
				)}
			</p>

			{#if editSubmitError}
				<Alert intent="error">{editSubmitError}</Alert>
			{/if}
		</form>

		{#snippet footer()}
			<Button
				type="button"
				variant="outline"
				disabled={editSubmitting}
				onclick={() => (editModalOpen = false)}
			>
				Cancel
			</Button>
			<Button
				type="submit"
				form="lq-edit-mailbox-form"
				disabled={editSubmitting}
				data-testid="lq-admin-intake-mailboxes-edit-submit"
			>
				{editSubmitting ? 'Saving…' : 'Save'}
			</Button>
		{/snippet}
	</ModalShell>
{/if}

{#if deleteModalOpen && deleteTarget}
	<ModalShell
		bind:open={deleteModalOpen}
		title="Disconnect this mailbox?"
		description={`${deleteTarget.address} will stop being polled for new mail. Threads it already opened keep their matters and conversations — only the binding is removed. Re-binding the same inbox id later restores it as a new binding.`}
		contentClass="sm:max-w-md"
	>
		{#if deleteError}
			<Alert intent="error">{deleteError}</Alert>
		{/if}

		{#snippet footer()}
			<Button
				type="button"
				variant="outline"
				disabled={deleteBusy}
				onclick={() => (deleteModalOpen = false)}
			>
				Cancel
			</Button>
			<Button
				type="button"
				variant="destructive"
				disabled={deleteBusy}
				onclick={confirmDelete}
				data-testid="lq-admin-intake-mailboxes-delete-confirm"
			>
				{deleteBusy ? 'Disconnecting…' : 'Disconnect'}
			</Button>
		{/snippet}
	</ModalShell>
{/if}
