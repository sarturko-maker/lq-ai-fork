<script lang="ts">
	/**
	 * /lq-ai/admin/library — the org's adopted Library (STORE-2, ADR-F065).
	 *
	 * Admin-gated. Data: `GET /library` (member-readable read model — reused
	 * here for the admin view too, since it's the same "what did we adopt"
	 * data) + `GET /practice-areas` (where-used). The only write action is
	 * Remove, behind the D-F confirm modal (always shown, never a silent
	 * delete — "system proposes, user owns").
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { titleFor } from '$lib/lq-ai/branding/store';
	import { adminApi, libraryApi, practiceAreasApi } from '$lib/lq-ai/api';
	import { auth } from '$lib/lq-ai/auth/store';
	import type { LibraryEntry } from '$lib/lq-ai/api/library';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';

	import { Button } from '$lib/components/ui/button/index.js';
	import Alert from '$lib/lq-ai/components/primitives/Alert.svelte';
	import Card from '$lib/lq-ai/components/primitives/Card.svelte';
	import CardGrid from '$lib/lq-ai/components/primitives/CardGrid.svelte';
	import ModalShell from '$lib/lq-ai/components/primitives/ModalShell.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';

	import { describeMutationError } from '$lib/lq-ai/admin/page-helpers';
	import {
		buildWhereUsedMap,
		groupLibraryEntries,
		provenanceBadge,
		removeConfirmWarning,
		whereUsedFor,
		whereUsedLabel
	} from '$lib/lq-ai/library/page-helpers';

	const SECTIONS = [
		{ kind: 'tool' as const, label: 'Tools' },
		{ kind: 'skill' as const, label: 'Skills' },
		{ kind: 'playbook' as const, label: 'Playbooks' }
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
		await load();
	});
</script>

<svelte:head>
	<title>{$titleFor('Library', 'admin')}</title>
</svelte:head>

<PageShell size="wide" data-testid="lq-admin-library-page">
	<SectionHeader
		title="Library"
		subtitle="Your organisation's Library — what your firm has adopted for its agents."
	/>

	{#if loading}
		<p class="mt-6 text-sm text-muted-foreground">Loading…</p>
	{:else if loadError}
		<div class="mt-6"><Alert intent="error">{loadError}</Alert></div>
	{:else if entries.length === 0}
		<div class="mt-6 flex flex-col items-start gap-3">
			<p class="text-sm text-muted-foreground">
				Your library is empty — browse the Store to add what your firm uses.
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
													No longer in the shipped catalog.
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
