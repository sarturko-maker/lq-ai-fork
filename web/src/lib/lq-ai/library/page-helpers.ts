/**
 * Shared Library-view logic (STORE-2, ADR-F065) — the ONE home for the
 * grouping/where-used/provenance-badge derivations both Library surfaces need:
 *
 * * `/lq-ai/admin/library` — admin view, adds Remove + the D-F confirm modal.
 * * `/lq-ai/library` — member read-only view (transparency, D-G).
 *
 * Living here (not duplicated per-route) means the two surfaces cannot render
 * a different label/badge/where-used answer for the same adopted capability.
 * `provenanceBadge` is also reused by the Store page's page-helpers (same
 * card format across Store and Library, per the parent plan) — it accepts a
 * small structural shape so it works for both `LibraryEntry` and the admin
 * catalog's `DeploymentCapabilityRead`.
 */
import type { LibraryEntry } from '$lib/lq-ai/api/library';
import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';

export type LibraryKind = 'tool' | 'skill' | 'playbook';

const SOURCE_LABELS: Record<string, string> = {
	'built-in': 'LQ built-in',
	community: 'Community',
	user: 'Your team',
	team: 'Your team'
};

/**
 * A provenance badge string, e.g. "LQ built-in", "Community · Jamie Tso ·
 * v1.0.0" — `null` when there's nothing to show (no `source`, which is the
 * dangling-entry case AND the "playbooks carry no provenance field" case,
 * D-A). Author/version are appended only when present.
 */
export function provenanceBadge(entry: {
	source?: string | null;
	author?: string | null;
	version?: string | null;
}): string | null {
	if (!entry.source) return null;
	const bits = [SOURCE_LABELS[entry.source] ?? entry.source];
	if (entry.author) bits.push(entry.author);
	// derive_summary never sends null for a resolvable skill — a versionless one
	// arrives as the sentinel "unversioned" (D-E), which must not render as
	// "vunversioned" (review fix, STORE-2).
	if (entry.version && entry.version !== 'unversioned') bits.push(`v${entry.version}`);
	return bits.join(' · ');
}

/** Split a flat (already server-sorted) entry list into per-kind buckets,
 *  preserving each bucket's incoming order. */
export function groupLibraryEntries(entries: LibraryEntry[]): Record<LibraryKind, LibraryEntry[]> {
	return {
		tool: entries.filter((e) => e.kind === 'tool'),
		skill: entries.filter((e) => e.kind === 'skill'),
		playbook: entries.filter((e) => e.kind === 'playbook')
	};
}

export type WhereUsedMap = Record<LibraryKind, Record<string, string[]>>;

/**
 * Build the (kind, key) -> [area names...] map from `GET /practice-areas`
 * (already ActiveUser, already returns `bound_skills` + `bound_tool_groups` +
 * `bound_playbooks` per area — no backend read model needed for where-used,
 * STORE-2 recon). Playbook keys match `bound_playbooks[].id` AS A STRING (the
 * Library keys playbooks by `str(playbook_id)`).
 */
export function buildWhereUsedMap(areas: PracticeArea[]): WhereUsedMap {
	const map: WhereUsedMap = { tool: {}, skill: {}, playbook: {} };
	for (const area of areas) {
		for (const skillName of area.bound_skills) {
			(map.skill[skillName] ??= []).push(area.name);
		}
		for (const groupKey of area.bound_tool_groups) {
			(map.tool[groupKey] ??= []).push(area.name);
		}
		for (const pb of area.bound_playbooks) {
			(map.playbook[pb.id] ??= []).push(area.name);
		}
	}
	return map;
}

/** The area names a given Library entry is bound in (empty when unbound). */
export function whereUsedFor(map: WhereUsedMap, entry: { kind: LibraryKind; key: string }): string[] {
	return map[entry.kind][entry.key] ?? [];
}

/** The card's where-used line — "Attached to: X, Y" or the honest negative. */
export function whereUsedLabel(areaNames: string[]): string {
	return areaNames.length > 0
		? `Attached to: ${areaNames.join(', ')}`
		: 'Not attached to any practice area.';
}

/**
 * D-F remove-confirm warning — plain language, no "binding"/"capability"
 * jargon. `null` when the entry isn't bound anywhere (the modal then shows
 * only the negative `whereUsedLabel`, no extra warning line).
 */
export function removeConfirmWarning(areaNames: string[]): string | null {
	if (areaNames.length === 0) return null;
	const subject = areaNames.length === 1 ? `The ${areaNames[0]} agent` : `The ${areaNames.join(', ')} agents`;
	return `${subject} will lose this — it stays attached but stops resolving until you add it back.`;
}
