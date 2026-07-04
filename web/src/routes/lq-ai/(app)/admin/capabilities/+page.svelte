<script lang="ts">
	/**
	 * /lq-ai/admin/capabilities — deployment-wide (Level 0) capability toggles
	 * (SETUP-4b, ADR-F062 addendum).
	 *
	 * Tools / Skills / Playbooks sections from `GET /admin/capabilities`, each
	 * with a hand-rolled on/off switch (deployment surface — no run-lock, unlike
	 * the matter CapabilitiesPanel this markup is modeled on but does NOT
	 * import). MCP is a visible-but-disabled placeholder (no backend section —
	 * real MCP wiring is its own approval-gated milestone). Models is a
	 * read-only alias+tier list from `GET /admin/model-menu`.
	 *
	 * Generation-B surface (plan D1): semantic tokens + SectionHeader/Alert
	 * primitives only — no --lq-* on this page.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { adminApi } from '$lib/lq-ai/api';
	import { auth } from '$lib/lq-ai/auth/store';
	import type { DeploymentCapabilitySection, ModelMenuAlias } from '$lib/lq-ai/api/admin';

	import Alert from '$lib/lq-ai/components/primitives/Alert.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';

	import {
		applyOptimisticToggle,
		describeMutationError,
		entryId,
		sectionSummary,
		tierLabel,
		togglePayload
	} from './page-helpers';

	let sections = $state<DeploymentCapabilitySection[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);
	let saving = $state<Set<string>>(new Set());
	let saveError = $state<string | null>(null);

	let modelMenu = $state<ModelMenuAlias[] | null>(null);
	let modelMenuUnavailable = $state(false);

	async function load() {
		loading = true;
		loadError = null;
		try {
			const resp = await adminApi.getDeploymentCapabilities();
			sections = resp.sections;
		} catch (e) {
			loadError = describeMutationError(e, 'Failed to load capabilities.');
		} finally {
			loading = false;
		}
	}

	async function loadModelMenu() {
		modelMenuUnavailable = false;
		try {
			const resp = await adminApi.getModelMenu();
			modelMenu = resp.aliases;
		} catch {
			// Muted note, not an error Alert — the models section is a courtesy
			// visibility surface, not something the admin needs to act on.
			modelMenu = null;
			modelMenuUnavailable = true;
		}
	}

	function setSaving(id: string, on: boolean) {
		const next = new Set(saving);
		if (on) next.add(id);
		else next.delete(id);
		saving = next;
	}

	async function onToggle(
		kind: DeploymentCapabilitySection['entries'][number]['capability_kind'],
		key: string,
		next: boolean
	) {
		const id = entryId(kind, key);
		if (saving.has(id)) return;
		const previous = sections;
		sections = applyOptimisticToggle(sections, kind, key, next);
		setSaving(id, true);
		saveError = null;
		try {
			const resp = await adminApi.patchDeploymentCapabilities(togglePayload(kind, key, next));
			sections = resp.sections;
		} catch (e) {
			sections = previous;
			saveError = describeMutationError(e, 'Could not save that change. Please retry.');
		} finally {
			setSaving(id, false);
		}
	}

	onMount(async () => {
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		if (!$auth.user.is_admin) {
			console.warn('non-admin attempted /lq-ai/admin/capabilities; redirecting');
			goto('/lq-ai');
			return;
		}
		await Promise.all([load(), loadModelMenu()]);
	});
</script>

<svelte:head>
	<title>Capabilities — LQ.AI Oscar Edition admin</title>
</svelte:head>

<PageShell size="wide" data-testid="lq-admin-caps-page">
	<SectionHeader
		title="Capabilities"
		subtitle="Disabling a capability here removes it from every matter's capability panel."
	/>

	{#if saveError}
		<div class="mt-4">
			<Alert intent="error">{saveError}</Alert>
		</div>
	{/if}

	{#if loading}
		<p class="mt-6 text-sm text-muted-foreground">Loading…</p>
	{:else if loadError}
		<div class="mt-6">
			<Alert intent="error">{loadError}</Alert>
		</div>
	{:else}
		<div class="mt-6 flex flex-col gap-6">
			{#each sections as section (section.kind)}
				<section class="rounded-lg border border-border p-4" aria-label={section.label}>
					<div class="mb-3 flex items-baseline justify-between">
						<SectionHeader size="section" title={section.label} />
						{#if sectionSummary(section)}
							<span class="text-xs text-muted-foreground">{sectionSummary(section)}</span>
						{/if}
					</div>
					{#if section.entries.length === 0}
						<p class="text-xs text-muted-foreground">Nothing in this section yet.</p>
					{/if}
					<ul class="flex flex-col gap-1.5" data-testid={`lq-admin-caps-section-${section.kind}`}>
						{#each section.entries as entry (entryId(entry.capability_kind, entry.capability_key))}
							{@const id = entryId(entry.capability_kind, entry.capability_key)}
							{@const busy = saving.has(id)}
							<li
								class="flex items-start justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2.5"
							>
								<div class="min-w-0">
									<p class="truncate text-sm font-medium text-foreground">{entry.label}</p>
									{#if entry.description}
										<p class="mt-0.5 text-xs text-muted-foreground">{entry.description}</p>
									{/if}
								</div>
								<button
									type="button"
									role="switch"
									aria-checked={entry.enabled}
									aria-label="Toggle {entry.label}"
									disabled={busy}
									data-testid={`lq-admin-caps-toggle-${id}`}
									onclick={() => onToggle(entry.capability_kind, entry.capability_key, !entry.enabled)}
									class="relative mt-0.5 inline-flex h-5 w-9 flex-none items-center rounded-full transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed {entry.enabled
										? 'bg-primary'
										: 'bg-muted'}"
								>
									<span
										class="inline-block h-4 w-4 transform rounded-full bg-background shadow transition-transform duration-150 {entry.enabled
											? 'translate-x-4'
											: 'translate-x-0.5'}"
									></span>
								</button>
							</li>
						{/each}
					</ul>
				</section>
			{/each}

			<!-- MCP — visible-but-disabled placeholder (no backend section; the
			     matter panel's caption/copy is reused verbatim). -->
			<section class="rounded-lg border border-border p-4 opacity-60" aria-label="MCP servers">
				<SectionHeader size="section" title="MCP servers" class="mb-3" />
				<div class="flex items-start justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2.5">
					<div class="min-w-0">
						<p class="truncate text-sm font-medium text-foreground">
							MCP servers <span class="ml-1 text-xs font-normal text-muted-foreground">(coming soon)</span>
						</p>
						<p class="mt-0.5 text-xs text-muted-foreground">
							Connect external tool servers (e.g. case-law research). Coming soon.
						</p>
					</div>
					<button
						type="button"
						role="switch"
						aria-checked="false"
						aria-label="Toggle MCP servers"
						disabled
						data-testid="lq-admin-caps-toggle-mcp"
						class="relative mt-0.5 inline-flex h-5 w-9 flex-none items-center rounded-full bg-muted disabled:cursor-not-allowed"
					>
						<span class="inline-block h-4 w-4 translate-x-0.5 transform rounded-full bg-background shadow"
						></span>
					</button>
				</div>
				<p class="mt-2 text-xs text-muted-foreground">Coming soon — external tool servers.</p>
			</section>

			<!-- Models — read-only alias+tier visibility (plan §7 row 6). -->
			<section class="rounded-lg border border-border p-4" aria-label="Models">
				<SectionHeader size="section" title="Models" class="mb-3" />
				{#if modelMenuUnavailable}
					<p class="text-xs text-muted-foreground" data-testid="lq-admin-caps-models-unavailable">
						Model menu unavailable.
					</p>
				{:else if modelMenu === null}
					<p class="text-xs text-muted-foreground">Loading…</p>
				{:else if modelMenu.length === 0}
					<p class="text-xs text-muted-foreground">No model aliases configured.</p>
				{:else}
					<ul class="flex flex-col gap-1.5" data-testid="lq-admin-caps-models-list">
						{#each modelMenu as m (m.alias)}
							<li class="flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2.5">
								<span class="text-sm font-medium text-foreground">{m.alias}</span>
								<span class="text-xs text-muted-foreground">{tierLabel(m.tier)}</span>
							</li>
						{/each}
					</ul>
				{/if}
				<p class="mt-2 text-xs text-muted-foreground">Managed by your platform operator.</p>
			</section>
		</div>
	{/if}
</PageShell>
