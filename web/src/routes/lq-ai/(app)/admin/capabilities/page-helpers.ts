/**
 * Pure helpers for the /lq-ai/admin/capabilities page (SETUP-4b, ADR-F062 addendum).
 *
 * Extracted out of `+page.svelte` so vitest can exercise them without a
 * SvelteKit runtime (Users-page / matter-CapabilitiesPanel precedent — no
 * @testing-library/svelte).
 */

import { LQAIApiError } from '$lib/lq-ai/api/client';
import type {
	DeploymentCapabilityRead,
	DeploymentCapabilitySection,
	DeploymentToggleInput,
	ModelMenuAlias
} from '$lib/lq-ai/api/admin';

/** Stable key for an entry (kind+key) — the in-flight `saving` Set + #each key. */
export function entryId(kind: DeploymentCapabilityRead['capability_kind'], key: string): string {
	return `${kind}:${key}`;
}

/** "3 of 4 on" — every entry in a Level-0 section is toggleable (unlike the
 *  matter panel, there is no available/toggleable filter at this level). */
export function sectionSummary(section: Pick<DeploymentCapabilitySection, 'entries'>): string {
	const total = section.entries.length;
	if (total === 0) return '';
	const on = section.entries.filter((e) => e.enabled).length;
	return `${on} of ${total} on`;
}

/** The single-toggle PATCH body — one element only (D9). */
export function togglePayload(
	kind: DeploymentToggleInput['kind'],
	key: string,
	enabled: boolean
): DeploymentToggleInput[] {
	return [{ kind, key, enabled }];
}

/**
 * Optimistic local update (D9): return NEW sections with one entry's `enabled`
 * flipped, so the switch responds instantly (reverted on a failed PATCH).
 */
export function applyOptimisticToggle(
	sections: DeploymentCapabilitySection[],
	kind: DeploymentCapabilityRead['capability_kind'],
	key: string,
	enabled: boolean
): DeploymentCapabilitySection[] {
	return sections.map((section) => ({
		...section,
		entries: section.entries.map((e) =>
			e.capability_kind === kind && e.capability_key === key ? { ...e, enabled } : e
		)
	}));
}

/** "Tier N" for a resolved tier, "—" for null (fallback-only alias / unresolved). */
export function tierLabel(tier: ModelMenuAlias['tier']): string {
	return tier === null ? '—' : `Tier ${tier}`;
}

/** Human message for a failed mutation — surface the server's message verbatim. */
export function describeMutationError(err: unknown, fallback: string): string {
	if (err instanceof LQAIApiError) {
		return err.message || fallback;
	}
	return err instanceof Error ? err.message : fallback;
}
