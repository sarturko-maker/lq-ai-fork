<script lang="ts">
	/**
	 * /lq-ai/admin/house-brief — the House Brief memory tier (B-1, ADR-F049).
	 *
	 * Single-form admin page over `GET/PUT /api/v1/organization-profile`
	 * (already shipped, admin-gated — ZERO backend for this slice). A markdown
	 * textarea plus a live preview rendered through the same sanitising sink
	 * as model output (`renderModelMarkdown` — CLAUDE.md: injected content is
	 * untrusted, one media-forbid policy, no drift).
	 *
	 * The House Brief is one of the four read-only DATA memory tiers
	 * (`TierMemoryMiddleware`, ADR-F049) — it is injected into EVERY agent
	 * run for every practice area, and the agent can only read it, never
	 * write it. A fresh org seeds no row, so this text is blank until an
	 * admin sets it here — the teaching empty state below explains why that
	 * matters before the admin writes anything.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { organizationProfileApi } from '$lib/lq-ai/api';
	import { auth } from '$lib/lq-ai/auth/store';
	import { titleFor } from '$lib/lq-ai/branding/store';
	import { renderModelMarkdown } from '$lib/lq-ai/sanitize-markdown';

	import { Button } from '$lib/components/ui/button/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import Alert from '$lib/lq-ai/components/primitives/Alert.svelte';
	import FormControl from '$lib/lq-ai/components/primitives/FormControl.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';

	import { describeMutationError } from '$lib/lq-ai/admin/page-helpers';
	import {
		HOUSE_BRIEF_MAX_CHARS,
		formatLastUpdated,
		isContentEmpty,
		validateContentLength
	} from './page-helpers';

	let loading = $state(true);
	let loadError = $state<string | null>(null);

	let content = $state('');
	let updatedAt = $state<string | null>(null);
	let updatedBy = $state<string | null>(null);

	let saving = $state(false);
	let saveError = $state<string | null>(null);
	let saveDone = $state(false);

	const lengthError = $derived(validateContentLength(content));
	const empty = $derived(isContentEmpty(content));
	const previewHtml = $derived(empty ? '' : renderModelMarkdown(content));
	const lastUpdatedLine = $derived(formatLastUpdated(updatedAt, updatedBy));

	async function load() {
		loading = true;
		loadError = null;
		try {
			const resp = await organizationProfileApi.getOrganizationProfile();
			content = resp.content_md;
			updatedAt = resp.updated_at;
			updatedBy = resp.updated_by;
		} catch (e) {
			loadError = describeMutationError(e, 'Failed to load the House Brief.');
		} finally {
			loading = false;
		}
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (lengthError || saving) return;
		saving = true;
		saveError = null;
		saveDone = false;
		try {
			const resp = await organizationProfileApi.updateOrganizationProfile({
				content_md: content
			});
			content = resp.content_md;
			updatedAt = resp.updated_at;
			updatedBy = resp.updated_by;
			saveDone = true;
		} catch (e) {
			saveError = describeMutationError(e, 'Failed to save the House Brief.');
		} finally {
			saving = false;
		}
	}

	onMount(async () => {
		// Per-page admin guard (branding-page precedent — no admin-layout guard
		// exists; the server's AdminUser dependency gates the PUT anyway).
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		if (!$auth.user.is_admin) {
			console.warn('non-admin attempted /lq-ai/admin/house-brief; redirecting');
			goto('/lq-ai');
			return;
		}
		await load();
	});
</script>

<svelte:head>
	<title>{$titleFor('House Brief', 'admin')}</title>
</svelte:head>

<PageShell size="wide" data-testid="lq-admin-house-brief-page">
	<SectionHeader
		title="House Brief"
		subtitle="Who the company is and who its legal team acts for — injected read-only into every agent run."
	/>

	{#if loadError}
		<div class="mt-6"><Alert intent="error">{loadError}</Alert></div>
	{:else if loading}
		<p class="mt-6 text-sm text-muted-foreground">Loading the House Brief…</p>
	{:else}
		{#if empty}
			<div class="mt-6" data-testid="lq-admin-house-brief-empty-state">
				<Alert intent="info">
					<p class="font-medium">The House Brief is empty.</p>
					<p class="mt-1">
						This is the company's standing context — who it is, its business, its group
						structure, the commercial postures it takes with counterparties, and any house
						drafting conventions. It is injected read-only into <strong
							>every agent run, in every practice area</strong
						>
						(the House Brief memory tier, ADR-F049) — the agent can weigh it, but never edit it.
						Until it is set, every practice area's agent works with no company context at all.
					</p>
					<p class="mt-1">
						Worth including: the company's name and what it does, its corporate/group
						structure, the commercial risk posture it wants agents to take with
						counterparties, and any house conventions (e.g. preferred defined terms, standard
						notice periods, escalation triggers).
					</p>
				</Alert>
			</div>
		{/if}

		<form class="mt-6 flex flex-col gap-3" novalidate onsubmit={save}>
			<FormControl
				id="lq-house-brief-content"
				label="House Brief"
				optional
				error={lengthError}
				help={`${content.length} / ${HOUSE_BRIEF_MAX_CHARS} characters — Markdown supported.`}
			>
				<Textarea
					id="lq-house-brief-content"
					bind:value={content}
					rows={16}
					class="font-mono text-sm"
					disabled={saving}
					aria-invalid={!!lengthError}
					data-testid="lq-admin-house-brief-textarea"
				/>
			</FormControl>

			{#if saveError}
				<Alert intent="error">{saveError}</Alert>
			{/if}
			{#if saveDone}
				<Alert intent="info">House Brief saved.</Alert>
			{/if}
			{#if lastUpdatedLine}
				<p class="text-xs text-muted-foreground" data-testid="lq-admin-house-brief-updated">
					{lastUpdatedLine}
				</p>
			{/if}

			<div>
				<Button
					type="submit"
					disabled={saving || !!lengthError}
					data-testid="lq-admin-house-brief-save"
				>
					{saving ? 'Saving…' : 'Save House Brief'}
				</Button>
			</div>
		</form>

		{#if !empty}
			<section class="mt-8 max-w-3xl">
				<h2 class="text-sm font-semibold text-foreground">Preview</h2>
				<p class="mt-1 text-xs text-muted-foreground">
					How this reads to the agent — the same markdown rendering used for the fenced
					memory-tier block in every run's system prompt.
				</p>
				<div
					class="mt-3 rounded-lg border border-border bg-card p-4 prose prose-sm dark:prose-invert max-w-none"
					data-testid="lq-admin-house-brief-preview"
				>
					<!-- eslint-disable-next-line svelte/no-at-html-tags — renderModelMarkdown-sanitized -->
					{@html previewHtml}
				</div>
			</section>
		{/if}
	{/if}
</PageShell>
