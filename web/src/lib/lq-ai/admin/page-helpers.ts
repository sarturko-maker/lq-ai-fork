/**
 * Shared pure helpers for the /lq-ai/admin/* pages (SETUP-4b review fix 4).
 *
 * These were duplicated verbatim across the admin page-helpers modules
 * (users, areas, areas/[key], capabilities) — one shared copy now, so a
 * change to the mutation-error contract or the catalog projection has a
 * single home and a single test suite. Per-page helpers keep only
 * page-specific logic.
 */

import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { DeploymentCapabilitiesResponse } from '$lib/lq-ai/api/admin';

/**
 * Human message for a failed mutation — surface the server's message verbatim
 * (SETUP-3b review fix F4 established the contract: the backend's guard
 * rejections and conflicts all carry user-facing copy; never synthesize a
 * client-side variant for a shape the server doesn't emit).
 */
export function describeMutationError(err: unknown, fallback: string): string {
	if (err instanceof LQAIApiError) {
		return err.message || fallback;
	}
	return err instanceof Error ? err.message : fallback;
}

export interface CatalogOption {
	key: string;
	label: string;
	description: string | null;
}

/**
 * SETUP-4b D7 — the attach catalogs come from `GET /admin/capabilities` (no
 * dedicated catalog endpoint). Project one kind's section into
 * `{key, label, description}` rows for attach controls and binding labels.
 */
export function catalogEntriesForKind(
	catalog: DeploymentCapabilitiesResponse | null,
	kind: 'skill' | 'tool' | 'playbook'
): CatalogOption[] {
	if (!catalog) return [];
	const section = catalog.sections.find((s) => s.kind === kind);
	if (!section) return [];
	return section.entries.map((e) => ({
		key: e.capability_key,
		label: e.label,
		description: e.description
	}));
}
