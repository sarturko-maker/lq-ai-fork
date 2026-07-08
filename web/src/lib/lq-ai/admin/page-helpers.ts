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

/** Locale datetime for admin timestamps ("expires {date}", "Last updated {date}");
 *  raw string on parse failure. */
export function formatDateTime(iso: string): string {
	const d = new Date(iso);
	return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export interface CatalogOption {
	key: string;
	label: string;
	description: string | null;
	/** STORE-2 D-A: whether the org has adopted this capability into its
	 *  Library. Area-detail pickers filter to `in_library === true` (Store-
	 *  scoped bindings, ADR-F065) via {@link libraryOnly} before computing
	 *  `unboundOptions`. */
	in_library: boolean;
}

/**
 * SETUP-4b D7 — the attach catalogs come from `GET /admin/capabilities` (no
 * dedicated catalog endpoint). Project one kind's section into
 * `{key, label, description, in_library}` rows for attach controls and
 * binding labels.
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
		description: e.description,
		in_library: e.in_library
	}));
}

/**
 * STORE-2 — narrow a catalog projection to Library-adopted entries only
 * (ADR-F065: area bindings pick from the Library, never directly from the
 * Store). Applied BEFORE `unboundOptions` in every area-detail attach picker.
 */
export function libraryOnly(options: CatalogOption[]): CatalogOption[] {
	return options.filter((o) => o.in_library);
}
