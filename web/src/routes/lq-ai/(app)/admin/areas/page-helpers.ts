/**
 * Pure helpers for the /lq-ai/admin/areas list+create page (SETUP-4b, ADR-F062
 * addendum).
 *
 * Extracted out of `+page.svelte` so vitest can exercise them without a
 * SvelteKit runtime (Users-page precedent — no @testing-library/svelte).
 */

import type { DeploymentCapabilitiesResponse } from '$lib/lq-ai/api/admin';
import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
import { catalogEntriesForKind, type CatalogOption } from '$lib/lq-ai/admin/page-helpers';

/** Anchored slug pattern the backend's `PracticeAreaCreate.key` field enforces
 *  (`api/app/schemas/practice_areas.py`) — mirrored here for instant feedback;
 *  the server 422 is authoritative. */
const AREA_KEY_PATTERN = /^[a-z][a-z0-9-]{1,62}[a-z0-9]$/;

/** Client-side pre-flight only. Requires lowercase letters/digits/hyphens, no
 *  leading/trailing hyphen, at least 3 characters. */
export function validateAreaKey(key: string): string | null {
	const trimmed = key.trim();
	if (!trimmed) return 'Key is required.';
	if (!AREA_KEY_PATTERN.test(trimmed)) {
		return 'Lowercase letters, digits, and hyphens only — must start and end with a letter or digit (at least 3 characters).';
	}
	return null;
}

/**
 * Build the new full key order after moving `key` one step `up`/`down` in
 * `keys`. Returns the SAME array reference (no-op) at an edge, so callers can
 * cheaply detect "nothing to do" via reference equality.
 */
export function moveKey(keys: string[], key: string, direction: 'up' | 'down'): string[] {
	const index = keys.indexOf(key);
	if (index === -1) return keys;
	const swapWith = direction === 'up' ? index - 1 : index + 1;
	if (swapWith < 0 || swapWith >= keys.length) return keys;
	const next = [...keys];
	[next[index], next[swapWith]] = [next[swapWith], next[index]];
	return next;
}

function pluralize(count: number, noun: string): string {
	return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

/** "3 skills · 1 playbook · 2 groups" — a scannable bound-capability summary. */
export function boundCountsLabel(
	area: Pick<PracticeArea, 'bound_skills' | 'bound_playbooks' | 'bound_tool_groups'>
): string {
	return [
		pluralize(area.bound_skills.length, 'skill'),
		pluralize(area.bound_playbooks.length, 'playbook'),
		pluralize(area.bound_tool_groups.length, 'group')
	].join(' · ');
}

export interface StatusView {
	label: string;
	tone: 'secondary' | 'outline';
	/** Hint shown as the badge's `title` when not configured (D5). */
	title?: string;
}

/** D5 — "Enable" is the existing `configured` derivation (non-empty profile_md).
 *  No fake toggle: an unconfigured area gets a hint instead. */
export function areaStatusView(area: Pick<PracticeArea, 'configured'>): StatusView {
	if (area.configured) return { label: 'Active', tone: 'secondary' };
	return { label: 'Not configured', tone: 'outline', title: 'Add doctrine to activate' };
}

/** The tool-group catalog for the "New practice area" modal — a brand-new area
 *  has no bindings yet, so every registry tool group is offered.
 *  (`catalogEntriesForKind`/`describeMutationError` live in the shared
 *  `$lib/lq-ai/admin/page-helpers` module — review fix 4.) */
export function availableGroupOptions(
	catalog: DeploymentCapabilitiesResponse | null
): CatalogOption[] {
	return catalogEntriesForKind(catalog, 'tool');
}
