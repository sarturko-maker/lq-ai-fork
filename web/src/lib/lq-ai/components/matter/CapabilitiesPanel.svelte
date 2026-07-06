<script module lang="ts">
	/**
	 * Capability panel (ADR-F054) — the practice AREA curates which capabilities are
	 * available; the LAWYER toggles a subset on/off PER MATTER (persisted). The run
	 * composition reads the same toggles, so this panel reflects exactly what the
	 * agent gets. MCP is a disabled "coming soon" placeholder until the MCP milestone.
	 *
	 * Pure helpers live here (no @testing-library/svelte in the codebase — behaviour
	 * is tested at the helper layer; the template is glue).
	 */
	import type {
		CapabilityEntry,
		CapabilityInventory,
		CapabilitySection,
		CapabilityToggleInput
	} from '$lib/lq-ai/types';

	/** A locked row: the disabled MCP placeholder, or anything unavailable. */
	export function isLocked(entry: CapabilityEntry): boolean {
		return !entry.available || !entry.toggleable;
	}

	/** "3 of 4 on" style summary for a section's toggleable entries (empty → ''). */
	export function sectionSummary(section: CapabilitySection): string {
		const toggleable = section.entries.filter((e) => e.available && e.toggleable);
		if (toggleable.length === 0) return '';
		const on = toggleable.filter((e) => e.enabled).length;
		return `${on} of ${toggleable.length} on`;
	}

	/** The caption under an empty/locked section (so it's never just a bare header). */
	export function emptyCaption(section: CapabilitySection): string | null {
		if (section.kind === 'mcp') return 'Coming soon — external tool servers.';
		if (section.entries.length === 0) {
			switch (section.kind) {
				case 'playbook':
					return 'No playbooks bound to this practice area yet.';
				case 'skill':
					return 'No skills bound to this practice area yet.';
				case 'tool':
					return 'No tools available for this practice area.';
			}
		}
		return null;
	}

	/** The single-toggle PUT body — the panel sends only the changed capability. */
	export function togglePayload(
		entry: CapabilityEntry,
		enabled: boolean
	): CapabilityToggleInput[] {
		return [
			{
				kind: entry.capability_kind as CapabilityToggleInput['kind'],
				key: entry.capability_key,
				enabled
			}
		];
	}

	/**
	 * Optimistic local update: return a NEW inventory with one entry's `enabled`
	 * flipped, so the switch responds instantly (reverted on a failed PUT). Only
	 * toggleable+available entries change; the placeholder is never touched.
	 */
	export function applyOptimisticToggle(
		inventory: CapabilityInventory,
		entry: CapabilityEntry,
		enabled: boolean
	): CapabilityInventory {
		return {
			...inventory,
			sections: inventory.sections.map((section) => ({
				...section,
				entries: section.entries.map((e) =>
					e.capability_kind === entry.capability_kind &&
					e.capability_key === entry.capability_key &&
					e.available &&
					e.toggleable
						? { ...e, enabled }
						: e
				)
			}))
		};
	}

	/** Stable key for an entry (kind+key) — used for the in-flight saving set + #each. */
	export function entryId(entry: CapabilityEntry): string {
		return `${entry.capability_kind}:${entry.capability_key}`;
	}
</script>

<script lang="ts">
	import { matterCapabilitiesApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';

	let {
		projectId,
		runActive = false,
		reloadKey = 0
	}: { projectId: string; runActive?: boolean; reloadKey?: number } = $props();

	let inventory = $state<CapabilityInventory | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let saving = $state<Set<string>>(new Set());
	let saveError = $state<string | null>(null);

	let loadGeneration = 0;
	// Sentinel (not a prop) so the first reconcile effect run is a no-op — the
	// mount effect below already loads; only a CHANGE to reloadKey re-fetches.
	let lastReloadKey = -1;

	async function load(quiet = false) {
		const gen = ++loadGeneration;
		if (!quiet) {
			loading = true;
			error = null;
		}
		try {
			const data = await matterCapabilitiesApi.getMatterCapabilities(projectId);
			if (gen !== loadGeneration) return;
			inventory = data;
			if (!quiet) error = null;
		} catch (e) {
			if (gen !== loadGeneration) return;
			if (!quiet) {
				error =
					e instanceof LQAIApiError ? e.message : 'Failed to load this matter’s capabilities.';
			}
		} finally {
			if (!quiet) loading = false;
		}
	}

	// Load on mount + when the matter changes.
	$effect(() => {
		void projectId;
		void load();
	});

	// Reconcile on a host reloadKey bump (e.g. after a run settles). Reads reloadKey
	// inside the effect (reactive); the first run only records the baseline.
	$effect(() => {
		const rk = reloadKey;
		if (rk === lastReloadKey) return;
		const first = lastReloadKey === -1;
		lastReloadKey = rk;
		if (!first) void load(true);
	});

	function setSaving(id: string, on: boolean) {
		const next = new Set(saving);
		if (on) next.add(id);
		else next.delete(id);
		saving = next;
	}

	async function onToggle(entry: CapabilityEntry) {
		if (isLocked(entry) || runActive) return;
		const id = entryId(entry);
		if (saving.has(id)) return;
		const next = !entry.enabled;
		const previous = inventory;
		// Optimistic flip.
		if (inventory) inventory = applyOptimisticToggle(inventory, entry, next);
		setSaving(id, true);
		saveError = null;
		try {
			inventory = await matterCapabilitiesApi.updateMatterCapabilities(
				projectId,
				togglePayload(entry, next)
			);
		} catch (e) {
			// Revert the optimistic change and surface the error.
			inventory = previous;
			saveError =
				e instanceof LQAIApiError ? e.message : 'Could not save that change. Please retry.';
		} finally {
			setSaving(id, false);
		}
	}
</script>

<div class="mx-auto w-full max-w-3xl p-4 sm:p-6" data-testid="lq-cockpit-capabilities">
	<header class="mb-4">
		<h2 class="text-base font-semibold text-foreground">Capabilities</h2>
		<p class="mt-1 text-sm text-muted-foreground">
			What this {inventory?.unit_label?.toLowerCase() ?? 'matter'}’s agent can use. The practice
			area sets what’s available; turn pieces off here for this {inventory?.unit_label?.toLowerCase() ??
				'matter'}. Changes apply to the next run.
		</p>
	</header>

	{#if loading}
		<p class="text-sm text-muted-foreground">Loading…</p>
	{:else if error}
		<p class="text-sm text-destructive" data-testid="lq-cap-error">{error}</p>
	{:else if inventory}
		{#if runActive}
			<p
				class="mb-3 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
				data-testid="lq-cap-runlock"
			>
				The agent is working — capability changes are paused until the run finishes.
			</p>
		{/if}
		{#if saveError}
			<p class="mb-3 text-sm text-destructive" data-testid="lq-cap-save-error">{saveError}</p>
		{/if}

		<div class="flex flex-col gap-5">
			{#each inventory.sections as section (section.kind)}
				<section>
					<div class="mb-2 flex items-baseline justify-between">
						<h3 class="text-sm font-semibold text-foreground">{section.label}</h3>
						{#if sectionSummary(section)}
							<span class="text-xs text-muted-foreground">{sectionSummary(section)}</span>
						{/if}
					</div>

					{#if section.entries.length === 0 || section.kind === 'mcp'}
						<p class="text-xs text-muted-foreground">{emptyCaption(section)}</p>
					{/if}

					<ul class="flex flex-col gap-1.5">
						{#each section.entries as entry (entryId(entry))}
							{@const locked = isLocked(entry)}
							{@const busy = saving.has(entryId(entry))}
							<li
								class="flex items-start justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2.5 {locked
									? 'opacity-60'
									: ''}"
							>
								<div class="min-w-0">
									<p class="truncate text-sm font-medium text-foreground">
										{#if entry.capability_kind === 'skill'}
											<a
												href="/lq-ai/skills/{encodeURIComponent(entry.capability_key)}"
												class="hover:underline"
											>
												{entry.label}
											</a>
										{:else}
											{entry.label}
										{/if}
										{#if locked && entry.capability_kind === 'mcp'}
											<span class="ml-1 text-xs font-normal text-muted-foreground">(coming soon)</span>
										{/if}
									</p>
									{#if entry.description}
										<p class="mt-0.5 text-xs text-muted-foreground">{entry.description}</p>
									{/if}
								</div>
								<button
									type="button"
									role="switch"
									aria-checked={entry.enabled}
									aria-label="Toggle {entry.label}"
									disabled={locked || runActive || busy}
									data-testid="lq-cap-toggle-{entryId(entry)}"
									onclick={() => onToggle(entry)}
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
		</div>
	{/if}
</div>
