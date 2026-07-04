/**
 * Pure helpers for the /lq-ai/admin/users page (SETUP-3b, ADR-F061).
 *
 * Extracted out of `+page.svelte` so vitest can exercise them without a
 * SvelteKit runtime (intake-bridges precedent — no @testing-library/svelte).
 * The helpers cover:
 *
 *   - user status labelling (active / disabled / deletion-scheduled)
 *   - the operator/self action lock (ADR-F061 addendum D6 — operator rows
 *     stay visible, badged, locked; the server 403s regardless)
 *   - invite status labels + badge tones
 *   - list-query building for GET /admin/users
 *   - date formatting (formatRelativeDate lifted from DevRoleManagementCard)
 *   - client-side invite validation + mutation-error messages
 */

import type {
	AdminUserListQuery,
	AdminUserRow,
	InviteStatus,
	UserRole
} from '$lib/lq-ai/types';

/** Subset of the shadcn Badge variants the status badges use. */
export type BadgeTone = 'secondary' | 'destructive' | 'outline';

export interface StatusView {
	label: string;
	tone: BadgeTone;
}

/** Account status for the Status column (disabled wins over pending deletion). */
export function userStatus(
	row: Pick<AdminUserRow, 'disabled_at' | 'deletion_scheduled_at'>
): StatusView {
	if (row.disabled_at) return { label: 'Disabled', tone: 'destructive' };
	if (row.deletion_scheduled_at) return { label: 'Deletion scheduled', tone: 'outline' };
	return { label: 'Active', tone: 'secondary' };
}

/** D6 — platform-operator rows render a badge instead of the role select. */
export function isOperatorRow(row: Pick<AdminUserRow, 'role'>): boolean {
	return row.role === 'operator';
}

/**
 * D6 — rows whose actions are locked in the UI: the platform operator (the
 * server refuses every org-admin mutation on it) and the caller's own row
 * (self-disable is refused server-side; self-demotion is an easy lockout).
 */
export function isRowActionLocked(
	row: Pick<AdminUserRow, 'id' | 'role'>,
	selfId: string | null
): boolean {
	return row.role === 'operator' || (selfId !== null && row.id === selfId);
}

/** Badge label + tone for an invite's derived status. */
export function inviteStatusView(status: InviteStatus): StatusView {
	switch (status) {
		case 'pending':
			return { label: 'Pending', tone: 'secondary' };
		case 'accepted':
			return { label: 'Accepted', tone: 'outline' };
		case 'revoked':
			return { label: 'Revoked', tone: 'destructive' };
		case 'expired':
			return { label: 'Expired', tone: 'outline' };
	}
}

/** Resend/revoke actions only make sense on a pending invite. */
export function isPendingInvite(invite: { status: InviteStatus }): boolean {
	return invite.status === 'pending';
}

/** Compose the GET /admin/users query from the filter controls. */
export function buildListQuery(
	roleFilter: UserRole | '',
	emailQuery: string,
	limit: number,
	offset: number
): AdminUserListQuery {
	const query: AdminUserListQuery = { limit, offset };
	if (roleFilter) query.role = roleFilter;
	const trimmed = emailQuery.trim();
	if (trimmed) query.email_q = trimmed;
	return query;
}

/** "today" / "3d ago" / "2mo ago" — lifted from DevRoleManagementCard (D5). */
export function formatRelativeDate(isoDate: string | null | undefined): string {
	if (!isoDate) return 'never';
	const d = new Date(isoDate);
	const diffMs = Date.now() - d.getTime();
	const diffDays = Math.floor(diffMs / 86400000);
	if (diffDays === 0) return 'today';
	if (diffDays === 1) return 'yesterday';
	if (diffDays < 30) return `${diffDays}d ago`;
	const diffMonths = Math.floor(diffDays / 30);
	if (diffMonths < 12) return `${diffMonths}mo ago`;
	return `${Math.floor(diffMonths / 12)}y ago`;
}

/** Locale datetime for invite expiry ("expires {date}"); raw string on parse failure. */
export function formatDateTime(iso: string): string {
	const d = new Date(iso);
	return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

/**
 * Client-side invite email check — a cheap pre-flight only (the server's
 * EmailStr is authoritative). Requires a dot in the domain, matching
 * pydantic's validator, so the common typo fails before the request.
 */
export function validateInviteEmail(email: string): string | null {
	const trimmed = email.trim();
	if (!trimmed) return 'Email is required.';
	if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) return 'Enter a valid email address.';
	return null;
}

/**
 * Human message for a failed mutation, keyed on the REAL backend contract
 * (SETUP-3b review fix F4 — no 'last_admin' code exists anywhere in api/):
 * the guard rejections (last-admin demote/disable, self-disable, operator
 * target) are 403 with envelope code 'forbidden' and an already-actionable
 * message; duplicate user/invite is 409 'conflict'. Both carry user-facing
 * copy — surface the server's message verbatim. Re-exported from the shared
 * admin helper module (SETUP-4b review fix 4) so the contract has one home;
 * this path stays stable for the page and its tests.
 */
export { describeMutationError } from '$lib/lq-ai/admin/page-helpers';
