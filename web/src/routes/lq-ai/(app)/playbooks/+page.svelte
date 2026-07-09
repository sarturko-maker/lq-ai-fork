<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { titleFor } from '$lib/lq-ai/branding/store';
	import { listPlaybooks, listPlaybookProposals, proposePlaybook } from '$lib/lq-ai/api/playbooks';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import { auth } from '$lib/lq-ai/auth/store';
	import PlaybookDisclaimerBanner from '$lib/lq-ai/components/PlaybookDisclaimerBanner.svelte';
	import PlaybookExecuteModal from '$lib/lq-ai/components/PlaybookExecuteModal.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import type { OrgSkillVersionState, Playbook } from '$lib/lq-ai/types';

	import {
		canProposePlaybook,
		describeMutationError,
		formatVersion,
		isOpenProposalConflict,
		proposePlaybookSuccessMessage,
		sortPlaybooksByName
	} from './page-helpers';

	let playbooks: Playbook[] = [];
	let loading = false;
	let listError: string | null = null;

	let selectedPlaybook: Playbook | null = null;

	// ADR-F067 D2/D3 (B-4) — "Propose to Library" row action, mirroring the
	// skill harness's B-2b propose flow.
	$: currentUserId = $auth.user?.id ?? null;
	let proposingId: string | null = null;
	let proposeSuccess: string | null = null;
	let proposeSuccessTimer: ReturnType<typeof setTimeout> | null = null;
	let actionError: string | null = null;
	// Rows locked after an "open proposal already exists" 409 — disabled +
	// tooltip until the caller reloads (deliberately NOT precomputed).
	let lockedRowIds = new Set<string>();
	let lockedTooltips = new Map<string, string>();
	// Inline proposal-STATUS chip per row (playbooks have no [id]/edit history
	// route). Lazily fetched for OWNED rows only after the table renders — a
	// bounded N+1 (a user authors few playbooks), best-effort, failures silent.
	let proposalStatus = new Map<string, { state: OrgSkillVersionState; version_no: number }>();

	async function load(): Promise<void> {
		loading = true;
		listError = null;
		try {
			const fetched = await listPlaybooks();
			playbooks = sortPlaybooksByName(fetched);
			void loadProposalStatuses(playbooks);
		} catch (err) {
			listError = err instanceof LQAIApiError ? err.message : 'Failed to load playbooks.';
		} finally {
			loading = false;
		}
	}

	async function loadProposalStatuses(rows: Playbook[]): Promise<void> {
		const uid = $auth.user?.id ?? null;
		const owned = rows.filter((p) => canProposePlaybook(p, uid));
		await Promise.all(
			owned.map(async (p) => {
				try {
					const proposals = await listPlaybookProposals(p.id);
					if (proposals.length > 0) {
						const latest = proposals[0]; // GET returns newest version first
						proposalStatus = new Map(proposalStatus).set(p.id, {
							state: latest.state,
							version_no: latest.version_no
						});
					}
				} catch {
					// Best-effort — a missing/forbidden history just yields no chip.
				}
			})
		);
	}

	async function propose(p: Playbook): Promise<void> {
		proposingId = p.id;
		actionError = null;
		try {
			const res = await proposePlaybook(p.id);
			if (proposeSuccessTimer) clearTimeout(proposeSuccessTimer);
			proposeSuccess = proposePlaybookSuccessMessage(p.name, res);
			proposeSuccessTimer = setTimeout(() => {
				proposeSuccess = null;
				proposeSuccessTimer = null;
			}, 8000);
			proposalStatus = new Map(proposalStatus).set(p.id, {
				state: res.state,
				version_no: res.version_no
			});
		} catch (e) {
			console.error('playbooks: propose failed', e);
			actionError = describeMutationError(e, 'Failed to propose this playbook to the Library.');
			if (isOpenProposalConflict(e)) {
				lockedRowIds = new Set(lockedRowIds).add(p.id);
				lockedTooltips = new Map(lockedTooltips).set(p.id, actionError);
			}
		} finally {
			proposingId = null;
		}
	}

	function statusLabel(state: OrgSkillVersionState): string {
		switch (state) {
			case 'proposed':
				return 'Proposed';
			case 'approved':
				return 'Approved';
			case 'rejected':
				return 'Rejected';
			case 'superseded':
				return 'Superseded';
			case 'revoked':
				return 'Revoked';
		}
	}

	function openExecute(p: Playbook): void {
		selectedPlaybook = p;
	}

	function closeExecute(): void {
		selectedPlaybook = null;
	}

	onMount(load);

	onDestroy(() => {
		if (proposeSuccessTimer) clearTimeout(proposeSuccessTimer);
	});
</script>

<svelte:head>
	<title>{$titleFor('Playbooks', 'dot')}</title>
</svelte:head>

<PageShell size="wide" pad="compact">
	<div class="lq-playbooks-page">
		<header class="lq-playbooks-page__header">
			<div class="lq-playbooks-page__heading">
				<h1>Playbooks</h1>
				<button
					type="button"
					class="lq-playbooks-page__cta"
					data-testid="lq-playbooks-generate-cta"
					on:click={() => goto('/lq-ai/playbooks/easy')}
				>
					Generate from prior agreements
				</button>
			</div>
			<p class="lq-playbooks-page__subtitle">
				Apply a playbook to review a contract against your standard positions. The executor walks
				each position, classifies how the contract compares, and drafts redlines where it deviates.
			</p>
		</header>

		<PlaybookDisclaimerBanner />

		{#if actionError}
			<div class="lq-playbooks-page__error" role="alert" data-testid="lq-playbook-action-error">
				{actionError}
			</div>
		{/if}
		{#if proposeSuccess}
			<div
				class="lq-playbooks-page__success"
				role="status"
				data-testid="lq-playbook-propose-success"
			>
				{proposeSuccess}
			</div>
		{/if}

		{#if loading}
			<div class="lq-playbooks-page__state" data-testid="lq-playbooks-loading">Loading…</div>
		{:else if listError}
			<div class="lq-playbooks-page__error" role="alert" data-testid="lq-playbooks-error">
				{listError}
			</div>
		{:else if playbooks.length === 0}
			<div class="lq-playbooks-page__state" data-testid="lq-playbooks-empty">
				No playbooks available yet.
			</div>
		{:else}
			<table class="lq-playbooks-table" data-testid="lq-playbooks-table">
				<thead>
					<tr>
						<th scope="col">Name</th>
						<th scope="col" class="lq-playbooks-table__compact">Contract type</th>
						<th scope="col" class="lq-playbooks-table__compact">Version</th>
						<th scope="col" class="lq-playbooks-table__actions">&nbsp;</th>
					</tr>
				</thead>
				<tbody>
					{#each playbooks as p (p.id)}
						<tr data-testid="lq-playbook-row" data-playbook-id={p.id}>
							<td class="lq-playbooks-table__name">
								<div class="lq-playbooks-table__name-text">
									{p.name}
									{#if proposalStatus.has(p.id)}
										{@const st = proposalStatus.get(p.id)}
										{#if st}
											<span
												class="lq-playbook-status lq-playbook-status--{st.state}"
												data-testid="lq-playbook-proposal-status"
											>
												{statusLabel(st.state)} · v{st.version_no}
											</span>
										{/if}
									{/if}
								</div>
								{#if p.description}
									<div class="lq-playbooks-table__desc">{p.description}</div>
								{/if}
							</td>
							<td class="lq-playbooks-table__compact">{p.contract_type}</td>
							<td class="lq-playbooks-table__compact">{formatVersion(p.version)}</td>
							<td class="lq-playbooks-table__actions">
								{#if canProposePlaybook(p, currentUserId)}
									<button
										type="button"
										class="lq-playbooks-table__propose"
										data-testid="lq-playbook-propose"
										on:click={() => propose(p)}
										disabled={proposingId === p.id || lockedRowIds.has(p.id)}
										title={lockedRowIds.has(p.id) ? lockedTooltips.get(p.id) : undefined}
									>
										{proposingId === p.id
											? 'Proposing…'
											: lockedRowIds.has(p.id)
												? 'Proposal open'
												: 'Propose to Library'}
									</button>
								{/if}
								<button
									type="button"
									class="lq-playbooks-table__apply"
									data-testid="lq-playbook-apply"
									on:click={() => openExecute(p)}
								>
									Apply
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}

		{#if selectedPlaybook}
			<PlaybookExecuteModal playbook={selectedPlaybook} on:close={closeExecute} />
		{/if}
	</div>
</PageShell>

<style>
	/* F2-M7a: width/margin/padding now come from <PageShell size="wide"
	   pad="compact">; this rule keeps only the inner vertical rhythm. */
	.lq-playbooks-page {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}
	.lq-playbooks-page__heading {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		margin-bottom: 0.5rem;
	}
	.lq-playbooks-page__header h1 {
		margin: 0;
		font-size: 1.5rem;
	}
	.lq-playbooks-page__cta {
		padding: 0.5rem 0.875rem;
		background: var(--primary);
		color: var(--primary-foreground);
		border: none;
		border-radius: 0.375rem;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
	}
	.lq-playbooks-page__cta:hover {
		opacity: 0.9;
	}
	.lq-playbooks-page__subtitle {
		margin: 0;
		color: var(--muted-foreground);
	}
	.lq-playbooks-page__state,
	.lq-playbooks-page__error {
		padding: 1.5rem;
		text-align: center;
		color: var(--muted-foreground);
		background: var(--muted);
		border-radius: 0.5rem;
	}
	.lq-playbooks-page__error {
		color: var(--destructive);
		background: var(--status-failed-wash);
		border: 1px solid var(--destructive);
	}
	.lq-playbooks-page__success {
		padding: 0.75rem 1rem;
		color: var(--foreground);
		background: var(--muted);
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		font-size: 0.875rem;
	}
	.lq-playbooks-table {
		width: 100%;
		border-collapse: collapse;
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		overflow: hidden;
	}
	.lq-playbooks-table th,
	.lq-playbooks-table td {
		padding: 0.75rem 1rem;
		text-align: left;
		border-bottom: 1px solid var(--border);
	}
	.lq-playbooks-table tbody tr:last-child td {
		border-bottom: none;
	}
	.lq-playbooks-table__name-text {
		font-weight: 600;
	}
	.lq-playbooks-table__desc {
		font-size: 0.8125rem;
		color: var(--muted-foreground);
		margin-top: 0.25rem;
		/* Cap the description so it doesn't crowd the compact columns
		   on long YAML descriptions (the seed playbooks have multi-
		   paragraph descriptions including the not-legal-advice line). */
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.lq-playbooks-table__compact {
		width: 1%;
		white-space: nowrap;
		vertical-align: top;
	}
	.lq-playbooks-table__actions {
		text-align: right;
		width: 1%;
		white-space: nowrap;
		vertical-align: top;
	}
	.lq-playbooks-table__apply {
		padding: 0.375rem 0.75rem;
		background: var(--primary);
		color: var(--primary-foreground);
		border: none;
		border-radius: 0.375rem;
		cursor: pointer;
		font-size: 0.875rem;
		font-weight: 500;
	}
	.lq-playbooks-table__apply:hover {
		opacity: 0.9;
	}
	.lq-playbooks-table__propose {
		padding: 0.375rem 0.75rem;
		margin-right: 0.375rem;
		background: transparent;
		color: var(--muted-foreground);
		border: 1px solid var(--border);
		border-radius: 0.375rem;
		cursor: pointer;
		font-size: 0.875rem;
		font-weight: 500;
	}
	.lq-playbooks-table__propose:hover {
		background: var(--muted);
	}
	.lq-playbooks-table__propose:disabled {
		cursor: not-allowed;
		opacity: 0.55;
	}
	.lq-playbook-status {
		display: inline-flex;
		align-items: center;
		margin-left: 0.5rem;
		padding: 1px 8px;
		border-radius: var(--lq-radius-pill, 999px);
		font-size: 0.6875rem;
		font-weight: 500;
		vertical-align: middle;
		background: var(--muted);
		color: var(--muted-foreground);
		border: 1px solid var(--border);
	}
	.lq-playbook-status--approved {
		color: var(--foreground);
	}
</style>
