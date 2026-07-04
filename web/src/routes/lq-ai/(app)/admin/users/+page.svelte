<script lang="ts">
	/**
	 * /lq-ai/admin/users — tenant user management (SETUP-3b, ADR-F061).
	 *
	 * One place to manage the tenant's users (D5 — role management consolidated
	 * here from /admin/developer): the users table (role change, disable/enable
	 * with an inline confirm step) plus the pending-invites section (create via
	 * modal, resend, revoke). When SMTP is off the create/resend response
	 * carries `accept_url` for out-of-band handover — shown with copy-to-
	 * clipboard, never logged or persisted (ADR-F061 D6).
	 *
	 * D6: platform-operator rows stay visible with a distinct badge and every
	 * action locked (the server 403s regardless — the UI mirrors the fence and
	 * never offers 'operator' as a role choice or filter). Self rows are
	 * action-locked too (self-disable is refused server-side; self-demotion is
	 * an easy lockout).
	 *
	 * Generation-B surface (plan D4): semantic tokens + ModalShell/Table/Badge/
	 * Alert/FormControl only — no --lq-* on this page.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { adminApi } from '$lib/lq-ai/api';
	import { auth } from '$lib/lq-ai/auth/store';
	import type { AdminUserRow, InviteResponse, InviteRow, UserRole } from '$lib/lq-ai/types';

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
		buildListQuery,
		describeMutationError,
		formatDateTime,
		formatRelativeDate,
		inviteStatusView,
		isOperatorRow,
		isPendingInvite,
		isRowActionLocked,
		userStatus,
		validateInviteEmail
	} from './page-helpers';

	const SELECT_CLASS =
		'h-8 rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30';

	// ----- Users table state -----
	let users = $state<AdminUserRow[]>([]);
	let totalCount = $state(0);
	let limit = $state(50);
	let offset = $state(0);
	let usersLoading = $state(true);
	let usersError = $state<string | null>(null);
	let roleFilter = $state<UserRole | ''>('');
	let emailQuery = $state('');
	let actionError = $state<string | null>(null);
	// Inline confirm step for disable/enable: id of the row awaiting confirm.
	let confirmToggleId = $state<string | null>(null);
	let busyUserId = $state<string | null>(null);

	// ----- Invites state -----
	let invites = $state<InviteRow[]>([]);
	let invitesLoading = $state(true);
	let invitesError = $state<string | null>(null);
	let inviteActionError = $state<string | null>(null);
	let busyInviteId = $state<string | null>(null);
	// Resend result carrying an accept_url (SMTP off) — shown inline, dismissable.
	let resendResult = $state<InviteResponse | null>(null);

	// ----- Invite modal state -----
	let inviteModalOpen = $state(false);
	let inviteEmail = $state('');
	let inviteRole = $state<UserRole>('member');
	let inviteEmailError = $state<string | null>(null);
	let inviteSubmitError = $state<string | null>(null);
	let inviteSubmitting = $state(false);
	// 201 result — flips the modal body to the success/handover panel.
	let inviteResult = $state<InviteResponse | null>(null);

	// Copy-to-clipboard feedback (keyed by URL so the two panels don't cross-talk).
	let copiedUrl = $state<string | null>(null);

	const selfId = $derived($auth.user?.id ?? null);

	async function loadUsers() {
		usersLoading = true;
		usersError = null;
		try {
			const resp = await adminApi.listUsers(buildListQuery(roleFilter, emailQuery, limit, offset));
			users = resp.users;
			totalCount = resp.total_count;
		} catch (e) {
			usersError = describeMutationError(e, 'Failed to load users.');
		} finally {
			usersLoading = false;
		}
	}

	async function loadInvites() {
		invitesLoading = true;
		invitesError = null;
		try {
			const resp = await adminApi.listInvites();
			invites = resp.invites;
		} catch (e) {
			invitesError = describeMutationError(e, 'Failed to load invites.');
		} finally {
			invitesLoading = false;
		}
	}

	function applyFilters() {
		offset = 0;
		void loadUsers();
	}

	function prevPage() {
		if (offset > 0) {
			offset = Math.max(0, offset - limit);
			void loadUsers();
		}
	}

	function nextPage() {
		if (offset + limit < totalCount) {
			offset += limit;
			void loadUsers();
		}
	}

	async function handleRoleChange(row: AdminUserRow, newRole: UserRole) {
		actionError = null;
		busyUserId = row.id;
		try {
			// UserRoleResponse (F6): user_id/email/role/is_admin — not a full row.
			const updated = await adminApi.patchUserRole(row.id, newRole);
			users = users.map((u) =>
				u.id === row.id ? { ...u, role: updated.role, is_admin: updated.is_admin } : u
			);
		} catch (e) {
			actionError = describeMutationError(e, 'Failed to update role.');
			// Resync so the row's select snaps back to the server-side role.
			await loadUsers();
		} finally {
			busyUserId = null;
		}
	}

	async function confirmToggleDisabled(row: AdminUserRow) {
		actionError = null;
		busyUserId = row.id;
		try {
			const resp = row.disabled_at
				? await adminApi.enableUser(row.id)
				: await adminApi.disableUser(row.id);
			users = users.map((u) => (u.id === row.id ? { ...u, disabled_at: resp.disabled_at } : u));
		} catch (e) {
			actionError = describeMutationError(
				e,
				row.disabled_at ? 'Failed to enable the account.' : 'Failed to disable the account.'
			);
		} finally {
			busyUserId = null;
			confirmToggleId = null;
		}
	}

	function openInviteModal() {
		inviteEmail = '';
		inviteRole = 'member';
		inviteEmailError = null;
		inviteSubmitError = null;
		inviteResult = null;
		inviteModalOpen = true;
	}

	async function submitInvite(event: SubmitEvent) {
		event.preventDefault();
		inviteEmailError = validateInviteEmail(inviteEmail);
		inviteSubmitError = null;
		if (inviteEmailError) return;
		inviteSubmitting = true;
		try {
			inviteResult = await adminApi.createInvite({
				email: inviteEmail.trim(),
				role: inviteRole
			});
			await loadInvites();
		} catch (e) {
			inviteSubmitError = describeMutationError(e, 'Failed to create the invite.');
		} finally {
			inviteSubmitting = false;
		}
	}

	async function handleResend(invite: InviteRow) {
		inviteActionError = null;
		resendResult = null;
		busyInviteId = invite.id;
		try {
			resendResult = await adminApi.resendInvite(invite.id);
			await loadInvites();
		} catch (e) {
			inviteActionError = describeMutationError(e, 'Failed to resend the invite.');
		} finally {
			busyInviteId = null;
		}
	}

	async function handleRevoke(invite: InviteRow) {
		inviteActionError = null;
		busyInviteId = invite.id;
		try {
			await adminApi.revokeInvite(invite.id);
			await loadInvites();
		} catch (e) {
			inviteActionError = describeMutationError(e, 'Failed to revoke the invite.');
		} finally {
			busyInviteId = null;
		}
	}

	async function copyAcceptUrl(url: string) {
		try {
			await navigator.clipboard.writeText(url);
			copiedUrl = url;
			setTimeout(() => {
				copiedUrl = null;
			}, 1500);
		} catch {
			// Clipboard can fail in restrictive contexts; the URL stays visible
			// inline so manual copy still works.
		}
	}

	onMount(async () => {
		// Per-page admin guard (audit-log precedent — there is no admin layout guard).
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		if (!$auth.user.is_admin) {
			console.warn('non-admin attempted /lq-ai/admin/users; redirecting');
			goto('/lq-ai');
			return;
		}
		await Promise.all([loadUsers(), loadInvites()]);
	});
</script>

<svelte:head>
	<title>Users — LQ.AI Oscar Edition admin</title>
</svelte:head>

{#snippet acceptUrlPanel(invite: InviteResponse)}
	<!-- SMTP-off handover: the single-use link, shown once for out-of-band
	     delivery. Never logged; not retrievable again (resend mints a new one). -->
	<div
		class="space-y-2 rounded-lg border border-border bg-muted p-3 text-sm text-foreground"
		data-testid="lq-admin-users-accept-url-panel"
	>
		<p class="font-medium">Email delivery is not configured — hand this link over out-of-band.</p>
		<div class="flex items-stretch gap-2">
			<code
				class="min-w-0 flex-1 overflow-x-auto rounded border border-border bg-background px-2 py-1 text-xs whitespace-nowrap"
				data-testid="lq-admin-users-accept-url"
			>
				{invite.accept_url}
			</code>
			<Button
				type="button"
				variant="outline"
				size="sm"
				onclick={() => invite.accept_url && copyAcceptUrl(invite.accept_url)}
				data-testid="lq-admin-users-accept-url-copy"
			>
				{copiedUrl === invite.accept_url ? 'Copied' : 'Copy'}
			</Button>
		</div>
		<p class="text-xs text-muted-foreground">
			Single-use link for {invite.email} — expires {formatDateTime(invite.expires_at)}. It will not
			be shown again; use Resend to issue a fresh one.
		</p>
	</div>
{/snippet}

<PageShell size="wide" data-testid="lq-admin-users-page">
	<div class="flex items-start justify-between gap-4">
		<SectionHeader
			title="Users"
			subtitle="Manage this workspace's accounts: roles, access, and invitations."
		/>
		<Button type="button" onclick={openInviteModal} data-testid="lq-admin-users-invite-open">
			Invite user
		</Button>
	</div>

	<!-- ----- Users table ----- -->
	<section class="mt-6 space-y-3" aria-label="Users">
		<form
			class="flex flex-wrap items-end gap-3"
			onsubmit={(e) => {
				e.preventDefault();
				applyFilters();
			}}
		>
			<label class="flex flex-col gap-1">
				<span class="text-[13px] font-medium text-foreground">Role</span>
				<!-- all/admin/member/viewer only — role=operator 400s server-side by design (D6) -->
				<select
					class={SELECT_CLASS}
					bind:value={roleFilter}
					onchange={applyFilters}
					data-testid="lq-admin-users-role-filter"
				>
					<option value="">All roles</option>
					<option value="admin">admin</option>
					<option value="member">member</option>
					<option value="viewer">viewer</option>
				</select>
			</label>
			<label class="flex min-w-48 flex-1 flex-col gap-1 sm:max-w-xs">
				<span class="text-[13px] font-medium text-foreground">Email</span>
				<Input
					type="text"
					placeholder="Search email…"
					bind:value={emailQuery}
					data-testid="lq-admin-users-email-filter"
				/>
			</label>
			<Button type="submit" variant="outline" disabled={usersLoading}>
				{usersLoading ? 'Loading…' : 'Apply'}
			</Button>
		</form>

		{#if actionError}
			<Alert intent="error">{actionError}</Alert>
		{/if}

		{#if usersError}
			<Alert intent="error">{usersError}</Alert>
		{:else if usersLoading}
			<p class="text-sm text-muted-foreground">Loading users…</p>
		{:else if users.length === 0}
			<p class="text-sm text-muted-foreground">No users match.</p>
		{:else}
			<div class="rounded-lg border border-border">
				<Table data-testid="lq-admin-users-table">
					<TableHeader>
						<TableRow>
							<TableHead>Email</TableHead>
							<TableHead>Role</TableHead>
							<TableHead>Status</TableHead>
							<TableHead>Last login</TableHead>
							<TableHead class="text-right">Actions</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each users as user (user.id)}
							{@const locked = isRowActionLocked(user, selfId)}
							{@const status = userStatus(user)}
							<TableRow data-testid="lq-admin-users-row">
								<TableCell class="max-w-56 truncate font-medium text-foreground" title={user.email}>
									{user.email}
									{#if selfId === user.id}
										<span class="ml-1 text-xs text-muted-foreground">(you)</span>
									{/if}
								</TableCell>
								<TableCell>
									{#if isOperatorRow(user)}
										<!-- D6: visible, badged, locked — never a select option. -->
										<Badge variant="outline" data-testid="lq-admin-users-operator-badge">
											Platform operator
										</Badge>
									{:else}
										<select
											class={SELECT_CLASS}
											value={user.role}
											disabled={locked || busyUserId === user.id}
											title={locked ? "You can't change your own role." : undefined}
											onchange={(e) =>
												handleRoleChange(user, (e.target as HTMLSelectElement).value as UserRole)}
											aria-label={`Role for ${user.email}`}
											data-testid="lq-admin-users-role-select"
										>
											<option value="admin">admin</option>
											<option value="member">member</option>
											<option value="viewer">viewer</option>
										</select>
									{/if}
								</TableCell>
								<TableCell>
									<Badge variant={status.tone}>{status.label}</Badge>
								</TableCell>
								<TableCell class="text-muted-foreground">
									{formatRelativeDate(user.last_login_at)}
								</TableCell>
								<TableCell class="text-right whitespace-nowrap">
									{#if !locked}
										{#if confirmToggleId === user.id}
											<span class="mr-2 text-xs text-muted-foreground">
												{user.disabled_at ? 'Enable this account?' : 'Disable this account?'}
											</span>
											<Button
												type="button"
												variant={user.disabled_at ? 'default' : 'destructive'}
												size="sm"
												disabled={busyUserId === user.id}
												onclick={() => confirmToggleDisabled(user)}
												data-testid="lq-admin-users-toggle-confirm"
											>
												Confirm
											</Button>
											<Button
												type="button"
												variant="ghost"
												size="sm"
												disabled={busyUserId === user.id}
												onclick={() => (confirmToggleId = null)}
											>
												Cancel
											</Button>
										{:else}
											<Button
												type="button"
												variant="outline"
												size="sm"
												disabled={busyUserId !== null}
												onclick={() => (confirmToggleId = user.id)}
												data-testid="lq-admin-users-toggle"
											>
												{user.disabled_at ? 'Enable' : 'Disable'}
											</Button>
										{/if}
									{/if}
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>
			</div>

			<div class="flex flex-wrap items-center justify-between gap-2">
				<span class="text-xs text-muted-foreground">
					Showing {offset + 1}–{Math.min(offset + limit, totalCount)} of {totalCount}
				</span>
				<div class="flex gap-2">
					<Button type="button" variant="outline" size="sm" onclick={prevPage} disabled={offset === 0}>
						Prev
					</Button>
					<Button
						type="button"
						variant="outline"
						size="sm"
						onclick={nextPage}
						disabled={offset + limit >= totalCount}
					>
						Next
					</Button>
				</div>
			</div>
		{/if}
	</section>

	<!-- ----- Invites ----- -->
	<section class="mt-10 space-y-3" aria-label="Invitations">
		<SectionHeader
			size="section"
			title="Invitations"
			subtitle="Pending invites can be resent (issues a fresh link) or revoked."
		/>

		{#if inviteActionError}
			<Alert intent="error">{inviteActionError}</Alert>
		{/if}

		{#if resendResult}
			<div class="space-y-1">
				{#if resendResult.accept_url}
					{@render acceptUrlPanel(resendResult)}
				{:else}
					<Alert intent="info">Invitation email re-sent to {resendResult.email}.</Alert>
				{/if}
				<Button type="button" variant="ghost" size="sm" onclick={() => (resendResult = null)}>
					Dismiss
				</Button>
			</div>
		{/if}

		{#if invitesError}
			<Alert intent="error">{invitesError}</Alert>
		{:else if invitesLoading}
			<p class="text-sm text-muted-foreground">Loading invites…</p>
		{:else if invites.length === 0}
			<p class="text-sm text-muted-foreground">
				No invitations yet. Use "Invite user" to onboard a colleague.
			</p>
		{:else}
			<div class="rounded-lg border border-border">
				<Table data-testid="lq-admin-invites-table">
					<TableHeader>
						<TableRow>
							<TableHead>Email</TableHead>
							<TableHead>Role</TableHead>
							<TableHead>Status</TableHead>
							<TableHead>Created</TableHead>
							<TableHead>Expires</TableHead>
							<TableHead class="text-right">Actions</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each invites as invite (invite.id)}
							{@const view = inviteStatusView(invite.status)}
							<TableRow data-testid="lq-admin-invites-row">
								<TableCell class="max-w-56 truncate font-medium text-foreground" title={invite.email}>
									{invite.email}
								</TableCell>
								<TableCell class="text-muted-foreground">{invite.role}</TableCell>
								<TableCell>
									<Badge variant={view.tone}>{view.label}</Badge>
								</TableCell>
								<TableCell class="text-muted-foreground">
									{formatRelativeDate(invite.created_at)}
								</TableCell>
								<TableCell class="text-muted-foreground">
									{formatDateTime(invite.expires_at)}
								</TableCell>
								<TableCell class="text-right whitespace-nowrap">
									{#if isPendingInvite(invite)}
										<Button
											type="button"
											variant="outline"
											size="sm"
											disabled={busyInviteId !== null}
											onclick={() => handleResend(invite)}
											data-testid="lq-admin-invites-resend"
										>
											{busyInviteId === invite.id ? 'Working…' : 'Resend'}
										</Button>
										<Button
											type="button"
											variant="destructive"
											size="sm"
											disabled={busyInviteId !== null}
											onclick={() => handleRevoke(invite)}
											data-testid="lq-admin-invites-revoke"
										>
											Revoke
										</Button>
									{/if}
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>
			</div>
		{/if}
	</section>
</PageShell>

{#if inviteModalOpen}
	<ModalShell bind:open={inviteModalOpen} title="Invite user" contentClass="sm:max-w-lg">
		{#if inviteResult}
			<div class="flex flex-col gap-3" data-testid="lq-admin-users-invite-success">
				{#if inviteResult.email_sent}
					<p class="text-sm text-foreground">
						An invitation email has been sent to <span class="font-medium">{inviteResult.email}</span>.
					</p>
				{:else if inviteResult.accept_url}
					{@render acceptUrlPanel(inviteResult)}
				{/if}
			</div>
		{:else}
			<form id="lq-invite-form" class="flex flex-col gap-4" novalidate onsubmit={submitInvite}>
				<FormControl id="lq-invite-email" label="Email" required error={inviteEmailError}>
					<Input
						id="lq-invite-email"
						type="email"
						bind:value={inviteEmail}
						placeholder="colleague@example.com"
						required
						disabled={inviteSubmitting}
						aria-invalid={!!inviteEmailError}
						aria-describedby={inviteEmailError ? 'lq-invite-email-error' : undefined}
						data-testid="lq-admin-users-invite-email"
					/>
				</FormControl>

				<FormControl
					id="lq-invite-role"
					label="Role"
					help="Admins manage users and workspace settings; members do day-to-day work; viewers are read-only."
				>
					<!-- admin/member/viewer only — 'operator' is never offered (ADR-F061 D3). -->
					<select
						id="lq-invite-role"
						class={SELECT_CLASS}
						bind:value={inviteRole}
						disabled={inviteSubmitting}
						data-testid="lq-admin-users-invite-role"
					>
						<option value="member">member</option>
						<option value="admin">admin</option>
						<option value="viewer">viewer</option>
					</select>
				</FormControl>

				{#if inviteSubmitError}
					<Alert intent="error">{inviteSubmitError}</Alert>
				{/if}
			</form>
		{/if}

		{#snippet footer()}
			{#if inviteResult}
				<Button type="button" onclick={() => (inviteModalOpen = false)}>Done</Button>
			{:else}
				<Button
					type="button"
					variant="outline"
					disabled={inviteSubmitting}
					onclick={() => (inviteModalOpen = false)}
				>
					Cancel
				</Button>
				<Button
					type="submit"
					form="lq-invite-form"
					disabled={inviteSubmitting}
					data-testid="lq-admin-users-invite-submit"
				>
					{inviteSubmitting ? 'Creating invite…' : 'Create invite'}
				</Button>
			{/if}
		{/snippet}
	</ModalShell>
{/if}
