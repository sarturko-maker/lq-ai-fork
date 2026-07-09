/**
 * Pure helpers for the /lq-ai/admin/areas/[key] detail page (SETUP-4b, ADR-F062
 * addendum).
 *
 * Extracted out of `+page.svelte` so vitest can exercise them without a
 * SvelteKit runtime (Users-page precedent — no @testing-library/svelte).
 */

import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { DeploymentCapabilitiesResponse } from '$lib/lq-ai/api/admin';
import type { PracticeArea, PracticeAreaUpdateBody } from '$lib/lq-ai/api/practiceAreas';
import type { CatalogOption } from '$lib/lq-ai/admin/page-helpers';

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
	/** '' = "Inherit deployment default", else one of the three profiles —
	 *  mirroring the `<select>`'s string value (SETUP-5a, ADR-F063). */
	default_budget_profile: string;
}

/**
 * PATCH body containing ONLY the fields that differ from `original`
 * (exclude_unset semantics) — never a no-op PATCH with every field repeated.
 * For `default_budget_profile`, "changed to Inherit" sends an EXPLICIT null
 * (the server clears the column); an unchanged field is omitted entirely
 * (ADR-F063 — key-present-null clears, key-absent leaves unchanged).
 */
export function diffPatch(
	original: Pick<
		PracticeArea,
		'name' | 'unit_label' | 'profile_md' | 'default_tier_floor' | 'default_budget_profile'
	>,
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

	const budgetProfile =
		draft.default_budget_profile === ''
			? null
			: (draft.default_budget_profile as 'economy' | 'balanced' | 'generous');
	if (budgetProfile !== original.default_budget_profile) {
		patch.default_budget_profile = budgetProfile;
	}

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

/** Label for a bound key (skill name / tool-group key) — the catalog's label
 *  when resolvable, else the raw key (registry drift is possible but should
 *  never blank the row). Catalog rows come from the shared
 *  `catalogEntriesForKind` (`$lib/lq-ai/admin/page-helpers`, review fix 4). */
export function bindingLabel(options: CatalogOption[], key: string): string {
	return options.find((o) => o.key === key)?.label ?? key;
}

/** Catalog entries not yet bound — the attach `<select>`'s option set. */
export function unboundOptions(options: CatalogOption[], boundKeys: string[]): CatalogOption[] {
	const bound = new Set(boundKeys);
	return options.filter((o) => !bound.has(o.key));
}

/**
 * HITL-3 (ADR-F071) — the enabled (gated) tool names in a draft stop-and-ask
 * policy, sorted. The admin card's checkbox draft carries eligible tools as a
 * boolean map; only the `true` ones are the policy. Sorted so the dirty check
 * and the PUT body are order-stable.
 */
export function hitlEnabledTools(draft: Record<string, boolean>): string[] {
	return Object.keys(draft)
		.filter((name) => draft[name])
		.sort();
}

/**
 * True when a draft policy's enabled set differs from the area's saved
 * `hitl_policy` — gates the Save button so no no-op PUT is sent.
 */
export function hitlPolicyDirty(
	saved: Record<string, boolean>,
	draft: Record<string, boolean>
): boolean {
	const a = hitlEnabledTools(saved);
	const b = hitlEnabledTools(draft);
	return a.length !== b.length || a.some((name, i) => name !== b[i]);
}

/** The shape `provenanceBadge` ($lib/lq-ai/library/page-helpers) needs for an
 *  org-authored skill's provenance chip. */
export interface OrgSkillBadge {
	source: 'org';
	author: string | null;
	approver: string | null;
}

/**
 * B-2b (ADR-F067 D2/D3, decision 5) — org-authored skill provenance, keyed by
 * skill key. Reads straight off the FULL catalog response — `DeploymentCapabilityRead`
 * already carries `source`/`author`/`approver` for an approved org-skill snapshot,
 * but the narrower `CatalogOption` projection this page's other pickers use strips
 * them — so this is a small standalone derivation rather than widening the shared
 * `CatalogOption` shape every other admin page consumes. `catalog` may be `null`
 * while loading; a key with no `source === 'org'` entry (built-in, dangling, or no
 * catalog yet) is simply absent from the returned map.
 */
export function orgSkillBadges(
	catalog: DeploymentCapabilitiesResponse | null
): Map<string, OrgSkillBadge> {
	const section = catalog?.sections.find((s) => s.kind === 'skill');
	const map = new Map<string, OrgSkillBadge>();
	for (const e of section?.entries ?? []) {
		if (e.source === 'org') {
			map.set(e.capability_key, {
				source: 'org',
				author: e.author ?? null,
				approver: e.approver ?? null
			});
		}
	}
	return map;
}

/**
 * G13(a) — bound keys the agent will NOT actually receive at run time.
 * `build_area_inventory` fail-closes on any bound key whose catalog entry
 * isn't Library-adopted ("configured for redlining" yet the agent silently
 * never gets it), so the area page has to surface the same fail-closed
 * check the server applies. Two cases collapse into "degraded":
 *
 * * the catalog entry exists but `in_library` is `false` (bound, not adopted).
 * * no catalog entry exists at all (registry drift — deleted/renamed capability).
 *
 * Callers pass the FULL per-kind catalog (`catalogEntriesForKind(...)`, e.g.
 * `skillCatalogAll`) — never `libraryOnly(...)`, which would make every
 * unadopted entry disappear before this check ever sees it. Passing one
 * kind's catalog + that kind's bound keys keeps kinds isolated by
 * construction (a skill key and a tool-group key never cross-pollute).
 */
export function degradedBindingKeys(catalog: CatalogOption[], boundKeys: string[]): Set<string> {
	const byKey = new Map(catalog.map((o) => [o.key, o]));
	const degraded = new Set<string>();
	for (const key of boundKeys) {
		if (!(byKey.get(key)?.in_library ?? false)) degraded.add(key);
	}
	return degraded;
}

/**
 * STORE-2 — which empty-state copy an attach picker shows when its `<select>`
 * has nothing to offer, distinguishing two honestly different reasons:
 *
 * * `'library-empty'` — the org's Library has NO entries of this kind at all
 *   (the picker's Library-scoped catalog, i.e. `libraryOnly(...)`, is empty) —
 *   the fix is to visit the Store.
 * * `'all-attached'` — the Library has entries of this kind, but every one is
 *   already bound to this area — nothing left to attach.
 *
 * `null` when the picker has options to show (no empty state needed).
 */
export type PickerEmptyState = 'library-empty' | 'all-attached' | null;

export function pickerEmptyState(
	libraryScopedCatalog: CatalogOption[],
	unbound: CatalogOption[]
): PickerEmptyState {
	if (unbound.length > 0) return null;
	return libraryScopedCatalog.length === 0 ? 'library-empty' : 'all-attached';
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
	return (
		boundGroups.filter((g) => (LEDGER_BEARING_GROUPS as readonly string[]).includes(g)).length >= 2
	);
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
