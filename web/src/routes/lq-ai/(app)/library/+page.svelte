<script lang="ts">
	/**
	 * /lq-ai/library — the org's adopted Library, member-readable (STORE-2 D-G,
	 * ADR-F065). Transparency: every skill/tool/playbook shaping an agent's
	 * behaviour must be inspectable by any authenticated user, not just an
	 * admin (mirrors the tier-config dual-exposure precedent). Read-only —
	 * shares its rendering (grouping/where-used/provenance-badge) with the
	 * admin Library page via `$lib/lq-ai/library/page-helpers`, so the two
	 * surfaces can never disagree about the same adopted capability. No
	 * Remove action here; guarded only on being authenticated (no admin gate).
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { titleFor } from '$lib/lq-ai/branding/store';
	import { libraryApi, practiceAreasApi } from '$lib/lq-ai/api';
	import { auth } from '$lib/lq-ai/auth/store';
	import type { LibraryEntry } from '$lib/lq-ai/api/library';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';

	import Alert from '$lib/lq-ai/components/primitives/Alert.svelte';
	import Card from '$lib/lq-ai/components/primitives/Card.svelte';
	import CardGrid from '$lib/lq-ai/components/primitives/CardGrid.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';

	import { describeMutationError } from '$lib/lq-ai/admin/page-helpers';
	import {
		buildWhereUsedMap,
		groupLibraryEntries,
		provenanceBadge,
		whereUsedFor,
		whereUsedLabel
	} from '$lib/lq-ai/library/page-helpers';

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
			loadError = describeMutationError(e, 'Failed to load the Library.');
		} finally {
			loading = false;
		}
	}

	onMount(async () => {
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		await load();
	});
</script>

<svelte:head>
	<title>{$titleFor('Library')}</title>
</svelte:head>

<PageShell size="wide" data-testid="lq-library-page">
	<SectionHeader
		title="Library"
		subtitle="Your organisation's Library — what your company has adopted for its agents. Read-only."
	/>

	{#if loading}
		<p class="mt-6 text-sm text-muted-foreground">Loading…</p>
	{:else if loadError}
		<div class="mt-6"><Alert intent="error">{loadError}</Alert></div>
	{:else if entries.length === 0}
		<p class="mt-6 text-sm text-muted-foreground">Your company hasn't added anything yet.</p>
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
									<div class="flex flex-col gap-2">
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
