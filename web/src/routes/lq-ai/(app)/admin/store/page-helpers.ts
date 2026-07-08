/**
 * Pure helpers for the /lq-ai/admin/store page (STORE-2, ADR-F065).
 *
 * Extracted so vitest can exercise them without a SvelteKit runtime (the
 * house pattern — no @testing-library/svelte). `provenanceBadge` is imported
 * from the shared Library helpers module so the Store and Library pages
 * render the identical badge format (parent plan: "provenance badge …" is
 * one spec for both surfaces).
 */
import type { DeploymentCapabilitiesResponse, DeploymentCapabilityRead } from '$lib/lq-ai/api/admin';
import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';

export { provenanceBadge } from '$lib/lq-ai/library/page-helpers';

/** One catalog entry, flattened out of its section (carries its kind). */
export interface FlatCapability extends DeploymentCapabilityRead {
	capability_kind: 'skill' | 'tool' | 'playbook' | 'knowledge';
}

/** Flatten the four sections into one list — used by search + the rail. */
export function flattenCapabilities(catalog: DeploymentCapabilitiesResponse): FlatCapability[] {
	return catalog.sections.flatMap((s) =>
		s.entries.map((e) => ({ ...e, capability_kind: s.kind as FlatCapability['capability_kind'] }))
	);
}

/**
 * Client-side search predicate — label/key/description/tags, case-insensitive
 * (the `SkillPicker.svelte` house pattern). An empty/whitespace term matches
 * everything.
 */
export function matchesSearch(entry: DeploymentCapabilityRead, term: string): boolean {
	const t = term.trim().toLowerCase();
	if (t === '') return true;
	if (entry.label.toLowerCase().includes(t)) return true;
	if (entry.capability_key.toLowerCase().includes(t)) return true;
	if (entry.description && entry.description.toLowerCase().includes(t)) return true;
	return (entry.tags ?? []).some((tag) => tag.toLowerCase().includes(t));
}

/** One chip in a "Recommended for {area}" rail. */
export interface RecommendedChip {
	kind: 'skill' | 'tool' | 'playbook' | 'knowledge';
	key: string;
	label: string;
	inLibrary: boolean;
}

export interface RecommendedRail {
	areaKey: string;
	/** The org's configured area name when one exists, else a humanised key. */
	areaLabel: string;
	entries: RecommendedChip[];
	missingCount: number;
}

/** `"m-and-a"` -> `"M And A"` — last-resort label when no configured area
 *  matches the recommended area key (shouldn't happen once an org has its
 *  standard areas, but keeps the rail honest rather than blank). */
function humaniseAreaKey(key: string): string {
	return key
		.split('-')
		.map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w))
		.join(' ');
}

/**
 * Build one rail per area key present in ANY entry's `recommended_for`, in
 * the org's own configured area order (`listPracticeAreas()`'s position
 * order) — a recommended key with no matching configured area sorts last,
 * alphabetically, so the rail is still complete on a deployment missing a
 * standard area.
 */
export function buildRecommendedRails(
	catalog: DeploymentCapabilitiesResponse,
	areas: PracticeArea[]
): RecommendedRail[] {
	const flat = flattenCapabilities(catalog);
	const areaKeysPresent = new Set<string>();
	for (const e of flat) {
		for (const areaKey of e.recommended_for ?? []) areaKeysPresent.add(areaKey);
	}

	const areaByKey = new Map(areas.map((a) => [a.key, a]));
	const known = areas.filter((a) => areaKeysPresent.has(a.key)).map((a) => a.key);
	const unknown = [...areaKeysPresent].filter((k) => !areaByKey.has(k)).sort();
	const orderedKeys = [...known, ...unknown];

	return orderedKeys.map((areaKey) => {
		const entries: RecommendedChip[] = flat
			.filter((e) => (e.recommended_for ?? []).includes(areaKey))
			.map((e) => ({
				kind: e.capability_kind,
				key: e.capability_key,
				label: e.label,
				inLibrary: e.in_library
			}));
		return {
			areaKey,
			areaLabel: areaByKey.get(areaKey)?.name ?? humaniseAreaKey(areaKey),
			entries,
			missingCount: entries.filter((e) => !e.inLibrary).length
		};
	});
}

/** The `(kind, key)` pairs "Add all" must POST — the rail's not-yet-adopted entries. */
export function missingEntries(
	rail: RecommendedRail
): { kind: 'skill' | 'tool' | 'playbook' | 'knowledge'; key: string }[] {
	return rail.entries.filter((e) => !e.inLibrary).map((e) => ({ kind: e.kind, key: e.key }));
}
