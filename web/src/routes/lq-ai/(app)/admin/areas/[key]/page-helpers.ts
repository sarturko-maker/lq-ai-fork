/**
 * Pure helpers for the /lq-ai/admin/areas/[key] detail page (SETUP-4b, ADR-F062
 * addendum).
 *
 * Extracted out of `+page.svelte` so vitest can exercise them without a
 * SvelteKit runtime (Users-page precedent — no @testing-library/svelte).
 */

import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { PracticeArea, PracticeAreaUpdateBody } from '$lib/lq-ai/api/practiceAreas';

/** Pick an area by its route-param key; `undefined` when unknown (inline
 *  not-found state, never a thrown error page). */
export function findAreaByKey(areas: PracticeArea[], key: string): PracticeArea | undefined {
	return areas.find((a) => a.key === key);
}

export interface AreaEditDraft {
	name: string;
	unit_label: string;
	/** '' means "no doctrine" in the UI; normalized to `null` on diff. */
	profile_md: string;
	/** '' or a numeric string, mirroring the `<select>`'s string value. */
	default_tier_floor: string;
}

/**
 * PATCH body containing ONLY the fields that differ from `original`
 * (exclude_unset semantics) — never a no-op PATCH with every field repeated.
 */
export function diffPatch(
	original: Pick<PracticeArea, 'name' | 'unit_label' | 'profile_md' | 'default_tier_floor'>,
	draft: AreaEditDraft
): PracticeAreaUpdateBody {
	const patch: PracticeAreaUpdateBody = {};

	const name = draft.name.trim();
	if (name !== original.name) patch.name = name;

	const unitLabel = draft.unit_label.trim();
	if (unitLabel !== original.unit_label) patch.unit_label = unitLabel;

	const profileMd = draft.profile_md.trim() === '' ? null : draft.profile_md;
	if (profileMd !== (original.profile_md ?? null)) patch.profile_md = profileMd;

	const tierFloor = draft.default_tier_floor === '' ? null : Number(draft.default_tier_floor);
	if (tierFloor !== original.default_tier_floor) patch.default_tier_floor = tierFloor;

	return patch;
}

export interface RosterParseResult {
	/** Parsed object on success; `null` when the textarea fails the parse gate. */
	value: Record<string, unknown> | null;
	error: string | null;
}

/**
 * D6 — client-side JSON.parse gate for the roster textarea. An empty textarea
 * is treated as `{}` (no subagents); anything that doesn't parse to a plain
 * JSON object is a client-side error (Save stays disabled) — the server's own
 * shape/ADR-F010 validation (400) is authoritative and surfaced verbatim on save.
 */
export function parseRosterDraft(text: string): RosterParseResult {
	const trimmed = text.trim();
	if (trimmed === '') return { value: {}, error: null };
	let parsed: unknown;
	try {
		parsed = JSON.parse(trimmed);
	} catch {
		return { value: null, error: 'Invalid JSON.' };
	}
	if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
		return { value: null, error: 'Must be a JSON object.' };
	}
	return { value: parsed as Record<string, unknown>, error: null };
}

export interface CatalogOption {
	key: string;
	label: string;
	description: string | null;
}

/** Label for a bound key (skill name / tool-group key) — the catalog's label
 *  when resolvable, else the raw key (registry drift is possible but should
 *  never blank the row). */
export function bindingLabel(options: CatalogOption[], key: string): string {
	return options.find((o) => o.key === key)?.label ?? key;
}

/** Catalog entries not yet bound — the attach `<select>`'s option set. */
export function unboundOptions(options: CatalogOption[], boundKeys: string[]): CatalogOption[] {
	const bound = new Set(boundKeys);
	return options.filter((o) => !bound.has(o.key));
}

/**
 * Ledger-bearing tool groups (SETUP-4b) — source of truth is
 * `TOOL_GROUP_REGISTRY` in `api/app/agents/capabilities.py` (`ledger_factory`
 * set on `redlining` → `DealChangeLedger`, `ropa` → `RopaChangeLedger`). The
 * composition loop keeps only the FIRST enabled ledger-bearing group's ledger
 * (ADR-F062 D5) — this caption exists so an admin who attaches both to one
 * area understands only one streams live changes.
 */
export const LEDGER_BEARING_GROUPS = ['redlining', 'ropa'] as const;

/** True when 2+ ledger-bearing groups are bound to the area (D5 caption gate). */
export function hasMultipleLedgerBearingGroups(boundGroups: string[]): boolean {
	return boundGroups.filter((g) => (LEDGER_BEARING_GROUPS as readonly string[]).includes(g)).length >= 2;
}

/** Human message for a failed mutation — surface the server's message verbatim
 *  (Users-page `describeMutationError` precedent). */
export function describeMutationError(err: unknown, fallback: string): string {
	if (err instanceof LQAIApiError) {
		return err.message || fallback;
	}
	return err instanceof Error ? err.message : fallback;
}

/**
 * DELETE 409 message — the server's message plus the live-matter count from
 * `error.details.active_matter_count` (the plan's "409 renders the server
 * message + active_matter_count from error.details").
 */
export function formatDeleteConflict(err: unknown): string {
	if (err instanceof LQAIApiError) {
		const count = err.details?.active_matter_count;
		if (typeof count === 'number') {
			return `${err.message} (${count} active matter${count === 1 ? '' : 's'})`;
		}
		return err.message || 'Failed to delete the practice area.';
	}
	return err instanceof Error ? err.message : 'Failed to delete the practice area.';
}
