/**
 * Pure helpers for the `/lq-ai/playbooks` list page, extracted to a sibling
 * `.ts` file so vitest can exercise them without the svelte transformer
 * (matching the pattern in the M3-A4 plan, Task 5).
 */
import type { Playbook } from '$lib/lq-ai/types';
import type { OrgPlaybookProposalResponse } from '$lib/lq-ai/api/playbooks';

/**
 * Shared 409 body detection + mutation-error copy, re-exported so this module
 * is the page's single import surface (B-4 reuses the B-2b skill harness's
 * ONE `isOpenProposalConflict` rather than a second copy that could drift).
 */
export { describeMutationError, isOpenProposalConflict } from '../skills/page-helpers';

/** Returns a new array sorted case-insensitively by playbook name. */
export function sortPlaybooksByName(playbooks: Playbook[]): Playbook[] {
	return [...playbooks].sort((a, b) =>
		a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
	);
}

/** Prefix a version string with "v"; empty input passes through. */
export function formatVersion(version: string): string {
	if (!version) return '';
	return `v${version}`;
}

/**
 * Whether the "Propose to Library" row action should render for this row
 * (ADR-F067 D2/D3, B-4).
 *
 * Gates on `created_by === currentUserId` — the caller must OWN a non-built-in
 * playbook. A bare `created_by !== null` check is WRONG: admins see EVERY org
 * playbook in this list, so it would render the button on other authors' rows
 * and the propose call would 404 (owner-strict). Built-ins (`created_by ===
 * null`) never match a real user id, so they are correctly excluded.
 */
export function canProposePlaybook(
	p: Pick<Playbook, 'created_by'>,
	currentUserId: string | null | undefined
): boolean {
	return !!currentUserId && p.created_by === currentUserId;
}

/** Transient success copy naming the playbook + version — shown in place of a
 *  toast primitive (none exists in this codebase; mirrors the skill harness's
 *  `proposeSuccessMessage`). The proposal response carries no human name, so
 *  the caller passes the row's `name`. */
export function proposePlaybookSuccessMessage(
	name: string,
	res: Pick<OrgPlaybookProposalResponse, 'version_no'>
): string {
	return `Proposed "${name}" v${res.version_no} to the Library — an admin will review it.`;
}
