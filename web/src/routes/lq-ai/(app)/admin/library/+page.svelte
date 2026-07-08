<script lang="ts">
	/**
	 * /lq-ai/admin/library — the org's adopted Library (STORE-2, ADR-F065)
	 * PLUS the org-skills review queue (B-2b, ADR-F067 D2/D3, contract
	 * decision 2 — the queue lives on this page, no new route/nav change).
	 *
	 * Admin-gated. Data: `GET /library` (member-readable read model — reused
	 * here for the admin view too, since it's the same "what did we adopt"
	 * data) + `GET /practice-areas` (where-used) + `GET /admin/org-skills`
	 * (the review queue, state-filtered). Write actions: Remove (D-F confirm
	 * modal), Approve/Reject-with-note/Revoke on the queue — never silent
	 * ("system proposes, user owns").
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { titleFor } from '$lib/lq-ai/branding/store';
	import { adminApi, libraryApi, practiceAreasApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import { auth } from '$lib/lq-ai/auth/store';
	import type { LibraryEntry } from '$lib/lq-ai/api/library';
	import type { OrgSkillVersionAdminRead } from '$lib/lq-ai/api/admin';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { OrgSkillVersionState } from '$lib/lq-ai/types';

	import { Button } from '$lib/components/ui/button/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import Alert from '$lib/lq-ai/components/primitives/Alert.svelte';
	import Card from '$lib/lq-ai/components/primitives/Card.svelte';
	import CardGrid from '$lib/lq-ai/components/primitives/CardGrid.svelte';
	import FormControl from '$lib/lq-ai/components/primitives/FormControl.svelte';
	import ModalShell from '$lib/lq-ai/components/primitives/ModalShell.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';

	import { describeMutationError, formatDateTime } from '$lib/lq-ai/admin/page-helpers';
	import {
		buildWhereUsedMap,
		groupLibraryEntries,
		provenanceBadge,
		removeConfirmWarning,
		whereUsedFor,
		whereUsedLabel
	} from '$lib/lq-ai/library/page-helpers';
	import { renderModelMarkdown } from '$lib/lq-ai/sanitize-markdown';
	import {
		DEFAULT_QUEUE_STATE,
		STATE_FILTER_PILLS,
		formatSizeBytes,
		queueEmptyMessage,
		truncateHash
	} from './page-helpers';

	const SECTIONS = [
		{ kind: 'tool' as const, label: 'Tools' },
		{ kind: 'skill' as const, label: 'Skills' },
		{ kind: 'playbook' as const, label: 'Playbooks' },
		{ kind: 'knowledge' as const, label: 'Knowledge' }
	];

	let entries = $state<LibraryEntry[]>([]);
	let areas = $state<PracticeArea[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	const grouped = $derived(groupLibraryEntries(entries));
	const whereUsedMap = $derived(buildWhereUsedMap(areas));

	let removeTarget = $state<LibraryEntry | null>(null);
	let removeModalOpen = $state(false);
	let removeBusy = $state(false);
	let removeError = $state<string | null>(null);

	async function load() {
		loading = true;
		loadError = null;
		try {
			const [lib, list] = await Promise.all([
				libraryApi.getLibrary(),
				practiceAreasApi.listPracticeAreas()
			]);
			entries = lib.entries;
			areas = list.practice_areas;
		} catch (e) {
			loadError = describeMutationError(e, 'Failed to load your Library.');
		} finally {
			loading = false;
		}
	}

	function openRemove(entry: LibraryEntry) {
		removeTarget = entry;
		removeError = null;
		removeModalOpen = true;
	}

	async function confirmRemove() {
		if (!removeTarget) return;
		removeBusy = true;
		removeError = null;
		try {
			await adminApi.removeLibraryEntry(removeTarget.kind, removeTarget.key);
			removeModalOpen = false;
			removeTarget = null;
			await load();
		} catch (e) {
			removeError = describeMutationError(e, 'Could not remove that. Please retry.');
		} finally {
			removeBusy = false;
		}
	}

	// ----- Review queue (B-2b) -----

	let queueState = $state<OrgSkillVersionState>(DEFAULT_QUEUE_STATE);
	let queueVersions = $state<OrgSkillVersionAdminRead[]>([]);
	let queueLoading = $state(true);
	let queueError = $state<string | null>(null);
	let queueActionError = $state<string | null>(null);
	/** ADR-F064 tenant-data exclusion: the platform operator is 403'd off
	 *  /admin/org-skills BY DESIGN (tenant-authored content). On a 403 the
	 *  whole review-queue section silently disappears — no error banner, no
	 *  empty state — while the rest of the Library page renders normally. */
	let queueForbidden = $state(false);
	/** Stays false until the FIRST loadQueue() settles — the section is not
	 *  rendered at all before that, so an operator never sees it flash in
	 *  and vanish while the ADR-F064 403 is in flight. */
	let queueEverLoaded = $state(false);
	// Monotonic request token (the SlashPopover idiom): rapid state-pill
	// clicks can leave multiple loadQueue() calls in flight and resolving
	// out of order; only the newest call may write queue state.
	let queueRequestId = 0;
	/** id of the version currently expanded to its full raw_yaml/body — one at a time. */
	let expandedId = $state<string | null>(null);
	/** '`raw`' is the review source of truth (raw_yaml + body verbatim in a `<pre>`);
	 *  '`rendered`' additionally shows body through the same markdown renderer the
	 *  agent's own prompt uses — never the only view. */
	let expandedView = $state<'raw' | 'rendered'>('raw');
	/** id of the version an approve request is in flight for (reject and
	 *  revoke ride their own confirm modals' busy flags). */
	let actionBusyId = $state<string | null>(null);

	async function loadQueue() {
		const myId = ++queueRequestId;
		queueLoading = true;
		queueError = null;
		try {
			const resp = await adminApi.listOrgSkillVersions(queueState);
			if (myId !== queueRequestId) return; // superseded by a newer call
			queueVersions = resp.versions;
		} catch (e) {
			if (myId !== queueRequestId) return;
			if (e instanceof LQAIApiError && e.status === 403) {
				// ADR-F064: operator exclusion — hide the section, no error UI.
				queueForbidden = true;
			} else {
				queueError = describeMutationError(e, 'Failed to load the review queue.');
			}
		} finally {
			if (myId === queueRequestId) {
				queueLoading = false;
				queueEverLoaded = true;
			}
		}
	}

	function selectQueueState(state: OrgSkillVersionState) {
		if (state === queueState) return;
		queueState = state;
		expandedId = null;
		queueActionError = null;
		void loadQueue();
	}

	function toggleExpanded(id: string) {
		expandedId = expandedId === id ? null : id;
		expandedView = 'raw';
	}

	async function approve(version: OrgSkillVersionAdminRead) {
		actionBusyId = version.id;
		queueActionError = null;
		try {
			await adminApi.approveOrgSkillVersion(version.id);
			await loadQueue();
		} catch (e) {
			queueActionError = describeMutationError(e, 'Could not approve that proposal.');
		} finally {
			actionBusyId = null;
		}
	}

	// ----- Revoke confirm modal (org-wide destructive — never one-click) -----

	let revokeTarget = $state<OrgSkillVersionAdminRead | null>(null);
	let revokeModalOpen = $state(false);
	let revokeBusy = $state(false);
	let revokeError = $state<string | null>(null);

	function openRevoke(version: OrgSkillVersionAdminRead) {
		revokeTarget = version;
		revokeError = null;
		revokeModalOpen = true;
	}

	async function confirmRevoke() {
		if (!revokeTarget) return;
		revokeBusy = true;
		revokeError = null;
		try {
			await adminApi.revokeOrgSkillVersion(revokeTarget.id);
			revokeModalOpen = false;
			revokeTarget = null;
			await loadQueue();
		} catch (e) {
			revokeError = describeMutationError(e, 'Could not revoke that version. Please retry.');
		} finally {
			revokeBusy = false;
		}
	}

	// ----- Reject-with-note modal -----

	let rejectTarget = $state<OrgSkillVersionAdminRead | null>(null);
	let rejectModalOpen = $state(false);
	let rejectNote = $state('');
	let rejectBusy = $state(false);
	let rejectError = $state<string | null>(null);

	function openReject(version: OrgSkillVersionAdminRead) {
		rejectTarget = version;
		rejectNote = '';
		rejectError = null;
		rejectModalOpen = true;
	}

	async function confirmReject() {
		if (!rejectTarget) return;
		rejectBusy = true;
		rejectError = null;
		try {
			await adminApi.rejectOrgSkillVersion(rejectTarget.id, rejectNote);
			rejectModalOpen = false;
			rejectTarget = null;
			await loadQueue();
		} catch (e) {
			rejectError = describeMutationError(e, 'Could not reject that proposal. Please retry.');
		} finally {
			rejectBusy = false;
		}
	}

	onMount(async () => {
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		if (!$auth.user.is_admin) {
			console.warn('non-admin attempted /lq-ai/admin/library; redirecting');
			goto('/lq-ai');
			return;
		}
		await Promise.all([load(), loadQueue()]);
	});
</script>

<svelte:head>
	<title>{$titleFor('Library', 'admin')}</title>
</svelte:head>

<PageShell size="wide" data-testid="lq-admin-library-page">
	<SectionHeader
		title="Library"
		subtitle="Your organisation's Library — what your company has adopted for its agents."
	/>

	<!-- ----- Review queue (B-2b, ADR-F067 D2/D3, decision 2) — above the adopted sections.
	     Hidden entirely (no error, no empty state) when the queue fetch 403s: the platform
	     operator is excluded from tenant-authored content by design (ADR-F064). ----- -->
	{#if queueEverLoaded && !queueForbidden}
	<section class="mt-6" aria-label="Review queue" data-testid="lq-admin-review-queue">
		<SectionHeader
			size="section"
			title="Review queue"
			subtitle="Org-authored skills your team proposed for wider adoption."
			class="mb-3"
		/>

		<div class="mb-3 flex flex-wrap gap-2" role="group" aria-label="Filter by state">
			{#each STATE_FILTER_PILLS as pill (pill.value)}
				<Button
					type="button"
					size="sm"
					variant={pill.value === queueState ? 'default' : 'outline'}
					aria-pressed={pill.value === queueState}
					onclick={() => selectQueueState(pill.value)}
					data-testid={`lq-admin-review-queue-filter-${pill.value}`}
				>
					{pill.label}
				</Button>
			{/each}
		</div>

		{#if queueActionError}
			<div class="mb-3"><Alert intent="error">{queueActionError}</Alert></div>
		{/if}

		{#if queueLoading}
			<p class="text-sm text-muted-foreground">Loading…</p>
		{:else if queueError}
			<Alert intent="error">{queueError}</Alert>
		{:else if queueVersions.length === 0}
			<p class="text-sm text-muted-foreground" data-testid="lq-admin-review-queue-empty">
				{queueEmptyMessage(queueState)}
			</p>
		{:else}
			<div class="flex flex-col gap-3">
				{#each queueVersions as version (version.id)}
					<div
						class="rounded-lg border border-border p-3"
						data-testid={`lq-admin-org-skill-${version.id}`}
					>
						<div class="flex flex-wrap items-start justify-between gap-3">
							<div class="min-w-0">
								<button
									type="button"
									class="text-sm font-medium text-foreground hover:underline"
									onclick={() => toggleExpanded(version.id)}
									data-testid={`lq-admin-org-skill-${version.id}-toggle`}
								>
									{version.slug} · v{version.version_no}
								</button>
								<p class="mt-0.5 text-xs text-muted-foreground">
									{version.author_email ?? 'Unknown author'} · proposed {formatDateTime(
										version.proposed_at
									)} · {formatSizeBytes(version.size_bytes)} · {truncateHash(version.content_hash)}
								</p>
								{#if version.approver_email}
									<p class="mt-0.5 text-xs text-muted-foreground">
										{#if version.reviewed_at}
											Reviewed by {version.approver_email} on {formatDateTime(version.reviewed_at)}
										{:else}
											Reviewed by {version.approver_email}
										{/if}
									</p>
								{/if}
								{#if version.state === 'rejected' && version.review_note}
									<p class="mt-1 text-xs text-muted-foreground">Note: {version.review_note}</p>
								{/if}
							</div>
							<div class="flex shrink-0 items-center gap-2">
								{#if version.state === 'proposed'}
									<Button
										type="button"
										size="sm"
										disabled={actionBusyId === version.id}
										onclick={() => approve(version)}
										data-testid={`lq-admin-org-skill-${version.id}-approve`}
									>
										{actionBusyId === version.id ? 'Approving…' : 'Approve'}
									</Button>
									<Button
										type="button"
										size="sm"
										variant="outline"
										disabled={actionBusyId === version.id}
										onclick={() => openReject(version)}
										data-testid={`lq-admin-org-skill-${version.id}-reject`}
									>
										Reject
									</Button>
								{:else if version.state === 'approved'}
									<Button
										type="button"
										size="sm"
										variant="destructive"
										onclick={() => openRevoke(version)}
										data-testid={`lq-admin-org-skill-${version.id}-revoke`}
									>
										Revoke
									</Button>
								{/if}
							</div>
						</div>

						{#if expandedId === version.id}
							<div class="mt-3 border-t border-border pt-3">
								<div class="mb-2 flex gap-2">
									<Button
										type="button"
										size="sm"
										variant={expandedView === 'raw' ? 'default' : 'outline'}
										onclick={() => (expandedView = 'raw')}
										data-testid={`lq-admin-org-skill-${version.id}-view-raw`}
									>
										Raw
									</Button>
									<Button
										type="button"
										size="sm"
										variant={expandedView === 'rendered' ? 'default' : 'outline'}
										onclick={() => (expandedView = 'rendered')}
										data-testid={`lq-admin-org-skill-${version.id}-view-rendered`}
									>
										Rendered
									</Button>
								</div>
								<!-- Full content_hash — the D2 immutability receipt: what the admin
								     approves is exactly this hash's bytes, so it belongs on the
								     review surface (the row shows the truncated form). -->
								<p class="mb-2 text-xs text-muted-foreground">
									Content hash:
									<span
										class="font-mono break-all select-all"
										data-testid={`lq-admin-org-skill-${version.id}-hash`}>{version.content_hash}</span
									>
								</p>
								{#if expandedView === 'raw'}
									<p class="mb-1 text-xs text-muted-foreground">
										The review source of truth — exact bytes, frontmatter then body.
									</p>
									<pre
										class="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap"
										data-testid={`lq-admin-org-skill-${version.id}-source`}>{version.raw_yaml}

{version.body}</pre>
								{:else}
									<p class="mb-1 text-xs text-muted-foreground">
										Frontmatter (raw) + body rendered as the agent would read it.
									</p>
									<pre
										class="mb-2 max-h-40 overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap">{version.raw_yaml}</pre>
									<div
										class="prose prose-sm dark:prose-invert max-w-none rounded-md border border-border p-3"
										data-testid={`lq-admin-org-skill-${version.id}-rendered`}
									>
										<!-- eslint-disable-next-line svelte/no-at-html-tags — renderModelMarkdown-sanitized -->
										{@html renderModelMarkdown(version.body)}
									</div>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</section>
	{/if}

	{#if loading}
		<p class="mt-6 text-sm text-muted-foreground">Loading…</p>
	{:else if loadError}
		<div class="mt-6"><Alert intent="error">{loadError}</Alert></div>
	{:else if entries.length === 0}
		<div class="mt-6 flex flex-col items-start gap-3">
			<p class="text-sm text-muted-foreground">
				Your library is empty — browse the Store to add what your company uses.
			</p>
			<Button type="button" onclick={() => goto('/lq-ai/admin/store')}>Browse the Store</Button>
		</div>
	{:else}
		<div class="mt-6 flex flex-col gap-8">
			{#each SECTIONS as section (section.kind)}
				{@const sectionEntries = grouped[section.kind]}
				{#if sectionEntries.length > 0}
					<section aria-label={section.label} data-testid={`lq-library-section-${section.kind}`}>
						<SectionHeader size="section" title={section.label} class="mb-3" />
						<CardGrid cols={3}>
							{#each sectionEntries as entry (entry.kind + ':' + entry.key)}
								{@const areaNames = whereUsedFor(whereUsedMap, entry)}
								<Card pad="compact" data-testid={`lq-library-card-${entry.kind}-${entry.key}`}>
									<div class="flex min-h-full flex-col gap-2">
										<div>
											{#if entry.label === null}
												<p class="text-sm font-medium text-foreground">{entry.key}</p>
												<p class="mt-0.5 text-xs text-muted-foreground">
													{entry.kind === 'knowledge'
														? 'This collection was archived by its owner — agents no longer search it.'
														: 'No longer in the shipped catalog.'}
												</p>
											{:else}
												{#if entry.kind === 'skill'}
													<a
														href="/lq-ai/skills/{encodeURIComponent(entry.key)}"
														class="text-sm font-medium text-foreground hover:underline"
													>
														{entry.label}
													</a>
												{:else}
													<p class="text-sm font-medium text-foreground">{entry.label}</p>
												{/if}
												{#if entry.description}
													<p class="mt-0.5 text-xs text-muted-foreground">{entry.description}</p>
												{/if}
											{/if}
										</div>
										{#if provenanceBadge(entry)}
											<span class="text-xs text-muted-foreground">{provenanceBadge(entry)}</span>
										{/if}
										<p class="text-xs text-muted-foreground">{whereUsedLabel(areaNames)}</p>
										<div class="mt-auto pt-1">
											<Button
												type="button"
												size="sm"
												variant="outline"
												onclick={() => openRemove(entry)}
												data-testid={`lq-library-remove-${entry.kind}-${entry.key}`}
											>
												Remove
											</Button>
										</div>
									</div>
								</Card>
							{/each}
						</CardGrid>
					</section>
				{/if}
			{/each}
		</div>
	{/if}
</PageShell>

<ModalShell bind:open={removeModalOpen} title="Remove from your Library?" contentClass="sm:max-w-md">
	{#if removeTarget}
		{@const areaNames = whereUsedFor(whereUsedMap, removeTarget)}
		<div class="flex flex-col gap-2 text-sm">
			<p class="text-foreground">{whereUsedLabel(areaNames)}</p>
			{#if removeConfirmWarning(areaNames)}
				<p class="text-muted-foreground" data-testid="lq-library-remove-warning">
					{removeConfirmWarning(areaNames)}
				</p>
			{/if}
			{#if removeError}
				<Alert intent="error">{removeError}</Alert>
			{/if}
		</div>
	{/if}
	{#snippet footer()}
		<Button
			type="button"
			variant="ghost"
			disabled={removeBusy}
			onclick={() => (removeModalOpen = false)}
			data-testid="lq-library-remove-cancel"
		>
			Cancel
		</Button>
		<Button
			type="button"
			variant="destructive"
			disabled={removeBusy}
			onclick={confirmRemove}
			data-testid="lq-library-remove-confirm"
		>
			{removeBusy ? 'Removing…' : 'Remove'}
		</Button>
	{/snippet}
</ModalShell>

<ModalShell bind:open={rejectModalOpen} title="Reject this proposal?" contentClass="sm:max-w-md">
	{#if rejectTarget}
		<div class="flex flex-col gap-3 text-sm">
			<p class="text-foreground">
				{rejectTarget.slug} · v{rejectTarget.version_no}, proposed by {rejectTarget.author_email ??
					'an unknown author'}.
			</p>
			<FormControl id="lq-admin-review-queue-reject-note" label="Note to the author" optional>
				<Textarea
					id="lq-admin-review-queue-reject-note"
					bind:value={rejectNote}
					rows={4}
					maxlength={2000}
					placeholder="Why this isn't ready yet…"
					disabled={rejectBusy}
					data-testid="lq-admin-review-queue-reject-note"
				/>
			</FormControl>
			{#if rejectError}
				<Alert intent="error">{rejectError}</Alert>
			{/if}
		</div>
	{/if}
	{#snippet footer()}
		<Button
			type="button"
			variant="ghost"
			disabled={rejectBusy}
			onclick={() => (rejectModalOpen = false)}
			data-testid="lq-admin-review-queue-reject-cancel"
		>
			Cancel
		</Button>
		<Button
			type="button"
			variant="destructive"
			disabled={rejectBusy}
			onclick={confirmReject}
			data-testid="lq-admin-review-queue-reject-confirm"
		>
			{rejectBusy ? 'Rejecting…' : 'Reject'}
		</Button>
	{/snippet}
</ModalShell>

<ModalShell
	bind:open={revokeModalOpen}
	title={revokeTarget ? `Revoke ${revokeTarget.slug}?` : 'Revoke this version?'}
	contentClass="sm:max-w-md"
>
	{#if revokeTarget}
		<div class="flex flex-col gap-2 text-sm">
			<p class="text-foreground">
				{revokeTarget.slug} · v{revokeTarget.version_no}, approved for org-wide use.
			</p>
			<p class="text-muted-foreground">
				Agents across your company stop loading this skill immediately — it fails closed at the
				next run. The Library entry and any practice-area bindings stay visible but show as
				unavailable until you remove or replace them. The author keeps their personal copy.
			</p>
			{#if revokeError}
				<Alert intent="error">{revokeError}</Alert>
			{/if}
		</div>
	{/if}
	{#snippet footer()}
		<Button
			type="button"
			variant="ghost"
			disabled={revokeBusy}
			onclick={() => (revokeModalOpen = false)}
			data-testid="lq-admin-org-skill-revoke-cancel"
		>
			Cancel
		</Button>
		<Button
			type="button"
			variant="destructive"
			disabled={revokeBusy}
			onclick={confirmRevoke}
			data-testid="lq-admin-org-skill-revoke-confirm"
		>
			{revokeBusy ? 'Revoking…' : 'Revoke'}
		</Button>
	{/snippet}
</ModalShell>
