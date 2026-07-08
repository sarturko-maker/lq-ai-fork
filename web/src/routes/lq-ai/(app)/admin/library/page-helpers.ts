/**
 * Pure helpers for the /lq-ai/admin/library page's review-queue section
 * (B-2b, ADR-F067 D2/D3, contract decision 2).
 *
 * Extracted so vitest can exercise them without a SvelteKit runtime (the
 * house pattern — no @testing-library/svelte). The queue itself lives ON
 * this page (no new route) above the existing adopted-entries sections.
 */
import type { OrgSkillVersionState } from '$lib/lq-ai/types';

/** One filter pill in the review-queue's state row. `proposed` is the
 *  landing default (contract decision 2); the rest are history/audit views —
 *  `approved` is also where Revoke lives. */
export const STATE_FILTER_PILLS: ReadonlyArray<{ value: OrgSkillVersionState; label: string }> = [
	{ value: 'proposed', label: 'Proposed' },
	{ value: 'approved', label: 'Approved' },
	{ value: 'rejected', label: 'Rejected' },
	{ value: 'superseded', label: 'Superseded' },
	{ value: 'revoked', label: 'Revoked' }
];

export const DEFAULT_QUEUE_STATE: OrgSkillVersionState = 'proposed';

/** Honest empty-state copy per filter — never a bare "No results". */
export function queueEmptyMessage(state: OrgSkillVersionState): string {
	return `Nothing ${state} right now.`;
}

/** Truncated content_hash for the collapsed row line — enough to
 *  eyeball-compare across two loads without wrapping the row. The FULL hash
 *  (the D2 immutability receipt) renders in the row's expanded review panel
 *  next to the raw content. */
export function truncateHash(hash: string, visibleChars = 12): string {
	return hash.length <= visibleChars ? hash : `${hash.slice(0, visibleChars)}…`;
}

/** Human-readable size (1024-based), e.g. 2048 -> "2.0 KB", 0 -> "0 B".
 *  A small local copy rather than importing DocumentsPanel's — that one lives
 *  inside a Svelte component's module block for a different surface (uploaded
 *  file sizes); this is the review queue's own tiny formatter. */
export function formatSizeBytes(bytes: number): string {
	if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
	const units = ['B', 'KB', 'MB', 'GB'];
	const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
	const value = bytes / 1024 ** i;
	return `${i === 0 ? value : value.toFixed(1)} ${units[i]}`;
}
