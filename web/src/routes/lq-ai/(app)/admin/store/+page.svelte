<script lang="ts">
	/**
	 * /lq-ai/admin/store — browse everything LQ.AI Oscar Edition ships
	 * (STORE-2, ADR-F065). Read side of the Store/Library split: the Store is
	 * the shipped catalog (skills/tools/playbooks), provenance-labelled,
	 * read-only. The one write action here is "Add to Library" — removal
	 * lives on the Library page (D-F confirm), never here.
	 *
	 * Admin-gated (same two-tier guard the old Capabilities page used). Data:
	 * `GET /admin/capabilities` (now carrying STORE-2's provenance/
	 * recommended_for fields) + `GET /practice-areas` (area labels for the
	 * Recommended rail only).
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { titleFor } from '$lib/lq-ai/branding/store';
	import { adminApi, practiceAreasApi } from '$lib/lq-ai/api';
	import { auth } from '$lib/lq-ai/auth/store';
	import type { DeploymentCapabilitiesResponse, DeploymentCapabilityRead } from '$lib/lq-ai/api/admin';
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';

	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import Alert from '$lib/lq-ai/components/primitives/Alert.svelte';
	import Card from '$lib/lq-ai/components/primitives/Card.svelte';
	import CardGrid from '$lib/lq-ai/components/primitives/CardGrid.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';

	import { describeMutationError } from '$lib/lq-ai/admin/page-helpers';
	import {
		buildRecommendedRails,
		flattenCapabilities,
		matchesSearch,
		missingEntries,
		provenanceBadge,
		type FlatCapability
	} from './page-helpers';

	let catalog = $state<DeploymentCapabilitiesResponse | null>(null);
	let areas = $state<PracticeArea[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);
	let searchTerm = $state('');

	let busy = $state<Set<string>>(new Set());
	let adoptError = $state<string | null>(null);
	let railBusy = $state<Set<string>>(new Set());
	let railError = $state<string | null>(null);

	const rails = $derived(catalog ? buildRecommendedRails(catalog, areas) : []);
	const flat = $derived(catalog ? flattenCapabilities(catalog) : []);
	const toolEntries = $derived(
		flat.filter((e) => e.capability_kind === 'tool' && matchesSearch(e, searchTerm))
	);
	const skillEntries = $derived(
		flat.filter((e) => e.capability_kind === 'skill' && matchesSearch(e, searchTerm))
	);
	const playbookEntries = $derived(
		flat.filter((e) => e.capability_kind === 'playbook' && matchesSearch(e, searchTerm))
	);

	function entryId(entry: DeploymentCapabilityRead): string {
		return `${entry.capability_kind}:${entry.capability_key}`;
	}

	async function load() {
		loading = true;
		loadError = null;
		try {
			const [caps, list] = await Promise.all([
				adminApi.getDeploymentCapabilities(),
				practiceAreasApi.listPracticeAreas()
			]);
			catalog = caps;
			areas = list.practice_areas;
		} catch (e) {
			loadError = describeMutationError(e, 'Failed to load the Store.');
		} finally {
			loading = false;
		}
	}

	async function onAdopt(entry: FlatCapability) {
		const id = entryId(entry);
		if (busy.has(id)) return;
		const next = new Set(busy);
		next.add(id);
		busy = next;
		adoptError = null;
		try {
			await adminApi.adoptLibraryEntry({ kind: entry.capability_kind, key: entry.capability_key });
			await load();
		} catch (e) {
			adoptError = describeMutationError(e, 'Could not add that to your Library. Please retry.');
		} finally {
			const done = new Set(busy);
			done.delete(id);
			busy = done;
		}
	}

	async function onAddAll(rail: ReturnType<typeof buildRecommendedRails>[number]) {
		if (railBusy.has(rail.areaKey)) return;
		const toAdd = missingEntries(rail);
		if (toAdd.length === 0) return;
		const nextBusy = new Set(railBusy);
		nextBusy.add(rail.areaKey);
		railBusy = nextBusy;
		railError = null;
		for (const { kind, key } of toAdd) {
			try {
				await adminApi.adoptLibraryEntry({ kind, key });
			} catch (e) {
				// Continue past failures — surface the last error, still add the rest.
				railError = describeMutationError(e, 'Could not add everything. Please retry.');
			}
		}
		await load();
		const done = new Set(railBusy);
		done.delete(rail.areaKey);
		railBusy = done;
	}

	onMount(async () => {
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		if (!$auth.user.is_admin) {
			console.warn('non-admin attempted /lq-ai/admin/store; redirecting');
			goto('/lq-ai');
			return;
		}
		await load();
	});
</script>

<svelte:head>
	<title>{$titleFor('Store', 'admin')}</title>
</svelte:head>

<PageShell size="wide" data-testid="lq-admin-store-page">
	<SectionHeader
		title="Store"
		subtitle="Everything that ships with LQ.AI Oscar Edition. Add what your company uses to your Library."
	/>
	<p class="mt-1 text-sm">
		<a href="/lq-ai/admin/library" class="underline">Go to your Library</a>
	</p>

	{#if adoptError}
		<div class="mt-4"><Alert intent="error">{adoptError}</Alert></div>
	{/if}

	{#if loading}
		<p class="mt-6 text-sm text-muted-foreground">Loading…</p>
	{:else if loadError}
		<div class="mt-6"><Alert intent="error">{loadError}</Alert></div>
	{:else}
		<div class="mt-6 flex flex-col gap-8">
			{#if rails.length > 0}
				<section class="flex flex-col gap-3" aria-label="Recommended">
					{#if railError}
						<Alert intent="error">{railError}</Alert>
					{/if}
					<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
						{#each rails as rail (rail.areaKey)}
							<Card bordered pad="compact" data-testid={`lq-store-rail-${rail.areaKey}`}>
								<p class="text-sm font-semibold text-foreground">
									Recommended for {rail.areaLabel}
								</p>
								<div class="mt-2 flex flex-wrap gap-1.5">
									{#each rail.entries as chip (chip.kind + ':' + chip.key)}
										<span
											class="rounded-full border border-border px-2 py-0.5 text-xs {chip.inLibrary
												? 'text-muted-foreground'
												: 'text-foreground'}"
										>
											{chip.inLibrary ? '✓ ' : ''}{chip.label}
										</span>
									{/each}
								</div>
								<div class="mt-3">
									{#if rail.missingCount === 0}
										<Button type="button" size="sm" variant="outline" disabled>
											All in your Library ✓
										</Button>
									{:else}
										<Button
											type="button"
											size="sm"
											disabled={railBusy.has(rail.areaKey)}
											onclick={() => onAddAll(rail)}
											data-testid={`lq-store-rail-add-all-${rail.areaKey}`}
										>
											{railBusy.has(rail.areaKey)
												? 'Adding…'
												: `Add all (${rail.missingCount} remaining)`}
										</Button>
									{/if}
								</div>
							</Card>
						{/each}
					</div>
				</section>
			{/if}

			<label class="flex max-w-sm flex-col gap-1">
				<span class="text-[13px] font-medium text-foreground">Search</span>
				<Input
					type="text"
					placeholder="Search the Store…"
					bind:value={searchTerm}
					data-testid="lq-store-search"
				/>
			</label>

			{#each [{ kind: 'tool', label: 'Tools', entries: toolEntries }, { kind: 'skill', label: 'Skills', entries: skillEntries }, { kind: 'playbook', label: 'Playbooks', entries: playbookEntries }] as section (section.kind)}
				<section aria-label={section.label} data-testid={`lq-store-section-${section.kind}`}>
					<SectionHeader size="section" title={section.label} class="mb-3" />
					{#if section.entries.length === 0}
						<!-- A search miss must not read as an empty catalog (review fix). -->
						<p class="text-xs text-muted-foreground">
							{searchTerm ? `No matches for “${searchTerm}”.` : 'Nothing here yet.'}
						</p>
					{:else}
						<CardGrid cols={3}>
							{#each section.entries as entry (entryId(entry))}
								<Card pad="compact" data-testid={`lq-store-card-${entryId(entry)}`}>
									<div class="flex min-h-full flex-col gap-2">
										<div>
											{#if entry.capability_kind === 'skill'}
												<a
													href="/lq-ai/skills/{encodeURIComponent(entry.capability_key)}"
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
										</div>
										{#if provenanceBadge(entry)}
											<span class="text-xs text-muted-foreground">{provenanceBadge(entry)}</span>
										{/if}
										<div class="mt-auto pt-1">
											{#if entry.in_library}
												<Button type="button" size="sm" variant="outline" disabled>
													In Library ✓
												</Button>
											{:else}
												<Button
													type="button"
													size="sm"
													disabled={busy.has(entryId(entry))}
													onclick={() => onAdopt(entry)}
													data-testid={`lq-store-add-${entryId(entry)}`}
												>
													{busy.has(entryId(entry)) ? 'Adding…' : 'Add to Library'}
												</Button>
											{/if}
										</div>
									</div>
								</Card>
							{/each}
						</CardGrid>
					{/if}
				</section>
			{/each}

			<!-- MCP — relocated from the old Capabilities page (D-D): catalog-shaped
			     "coming soon" placeholder, not a real Library entry. -->
			<section aria-label="MCP servers">
				<SectionHeader size="section" title="MCP servers" class="mb-3" />
				<Card bordered pad="compact" class="opacity-60">
					<p class="text-sm font-medium text-foreground">
						MCP servers
						<span class="ml-1 text-xs font-normal text-muted-foreground">(coming soon)</span>
					</p>
					<p class="mt-0.5 text-xs text-muted-foreground">
						Connect external tool servers (e.g. case-law research). Coming soon.
					</p>
				</Card>
			</section>
		</div>
	{/if}
</PageShell>
