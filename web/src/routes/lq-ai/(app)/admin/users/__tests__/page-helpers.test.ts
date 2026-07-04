/**
 * Pure-helper tests for the /lq-ai/admin/users page (SETUP-3b, ADR-F061).
 *
 * The helpers live in a sibling `page-helpers.ts` so vitest can exercise them
 * without the svelte transformer (intake-bridges precedent).
 */
import { describe, expect, it } from 'vitest';

import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { AdminUserRow, InviteStatus } from '$lib/lq-ai/types';
import {
	buildListQuery,
	describeMutationError,
	formatDateTime,
	formatRelativeDate,
	inviteStatusView,
	isOperatorRow,
	isPendingInvite,
	isRowActionLocked,
	userStatus,
	validateInviteEmail
} from '../page-helpers';

function userRow(over: Partial<AdminUserRow> = {}): AdminUserRow {
	return {
		id: '00000000-0000-0000-0000-000000000001',
		email: 'alice@example.com',
		display_name: 'Alice',
		role: 'member',
		is_admin: false,
		mfa_enabled: false,
		must_change_password: false,
		created_at: '2026-01-01T00:00:00Z',
		last_login_at: null,
		deletion_scheduled_at: null,
		disabled_at: null,
		...over
	};
}

describe('userStatus', () => {
	it('labels an ordinary account Active', () => {
		expect(userStatus(userRow())).toEqual({ label: 'Active', tone: 'secondary' });
	});

	it('labels a disabled account', () => {
		expect(userStatus(userRow({ disabled_at: '2026-07-01T00:00:00Z' }))).toEqual({
			label: 'Disabled',
			tone: 'destructive'
		});
	});

	it('labels a pending-deletion account', () => {
		expect(userStatus(userRow({ deletion_scheduled_at: '2026-07-10T00:00:00Z' }))).toEqual({
			label: 'Deletion scheduled',
			tone: 'outline'
		});
	});

	it('disabled wins over pending deletion', () => {
		const row = userRow({
			disabled_at: '2026-07-01T00:00:00Z',
			deletion_scheduled_at: '2026-07-10T00:00:00Z'
		});
		expect(userStatus(row).label).toBe('Disabled');
	});
});

describe('isOperatorRow / isRowActionLocked (D6)', () => {
	it('flags operator rows', () => {
		expect(isOperatorRow(userRow({ role: 'operator' }))).toBe(true);
		expect(isOperatorRow(userRow({ role: 'admin' }))).toBe(false);
	});

	it('locks operator rows regardless of who is looking', () => {
		expect(isRowActionLocked(userRow({ role: 'operator' }), 'someone-else')).toBe(true);
		expect(isRowActionLocked(userRow({ role: 'operator' }), null)).toBe(true);
	});

	it('locks the caller’s own row', () => {
		const row = userRow();
		expect(isRowActionLocked(row, row.id)).toBe(true);
	});

	it('leaves other org rows unlocked', () => {
		expect(isRowActionLocked(userRow(), 'someone-else')).toBe(false);
		expect(isRowActionLocked(userRow({ role: 'admin' }), 'someone-else')).toBe(false);
	});
});

describe('inviteStatusView / isPendingInvite', () => {
	it('maps each derived status to a label + tone', () => {
		expect(inviteStatusView('pending')).toEqual({ label: 'Pending', tone: 'secondary' });
		expect(inviteStatusView('accepted')).toEqual({ label: 'Accepted', tone: 'outline' });
		expect(inviteStatusView('revoked')).toEqual({ label: 'Revoked', tone: 'destructive' });
		expect(inviteStatusView('expired')).toEqual({ label: 'Expired', tone: 'outline' });
	});

	it('only pending invites offer resend/revoke', () => {
		const statuses: InviteStatus[] = ['pending', 'accepted', 'revoked', 'expired'];
		expect(statuses.filter((s) => isPendingInvite({ status: s }))).toEqual(['pending']);
	});
});

describe('buildListQuery', () => {
	it('always carries pagination', () => {
		expect(buildListQuery('', '', 50, 0)).toEqual({ limit: 50, offset: 0 });
	});

	it('adds role + trimmed email filters when set', () => {
		expect(buildListQuery('admin', '  bob  ', 10, 20)).toEqual({
			limit: 10,
			offset: 20,
			role: 'admin',
			email_q: 'bob'
		});
	});

	it('drops a whitespace-only email query', () => {
		expect(buildListQuery('viewer', '   ', 50, 0)).toEqual({ limit: 50, offset: 0, role: 'viewer' });
	});
});

describe('date formatting', () => {
	it('formatRelativeDate: never / today / days / months / years', () => {
		expect(formatRelativeDate(null)).toBe('never');
		expect(formatRelativeDate(undefined)).toBe('never');
		expect(formatRelativeDate(new Date().toISOString())).toBe('today');
		const threeDays = new Date(Date.now() - 3 * 86400000).toISOString();
		expect(formatRelativeDate(threeDays)).toBe('3d ago');
		const twoMonths = new Date(Date.now() - 65 * 86400000).toISOString();
		expect(formatRelativeDate(twoMonths)).toBe('2mo ago');
		const twoYears = new Date(Date.now() - 800 * 86400000).toISOString();
		expect(formatRelativeDate(twoYears)).toBe('2y ago');
	});

	it('formatDateTime returns the raw string on parse failure', () => {
		expect(formatDateTime('not-a-date')).toBe('not-a-date');
		expect(formatDateTime('2026-07-01T12:00:00Z')).not.toBe('2026-07-01T12:00:00Z');
	});
});

describe('validateInviteEmail', () => {
	it('requires a non-empty value', () => {
		expect(validateInviteEmail('')).toBe('Email is required.');
		expect(validateInviteEmail('   ')).toBe('Email is required.');
	});

	it('requires an @ and a dotted domain (pydantic EmailStr parity)', () => {
		expect(validateInviteEmail('nope')).toBe('Enter a valid email address.');
		expect(validateInviteEmail('a@b')).toBe('Enter a valid email address.');
		expect(validateInviteEmail('a b@example.com')).toBe('Enter a valid email address.');
	});

	it('accepts a plausible address (trimmed)', () => {
		expect(validateInviteEmail(' colleague@example.com ')).toBeNull();
	});
});

describe('describeMutationError (real backend contract — review fix F4)', () => {
	it('surfaces the last-admin guard as the server emits it: 403 code=forbidden', () => {
		// api/app/api/admin.py raises Forbidden (403, envelope code 'forbidden')
		// with an already-actionable message — no 'last_admin' code exists in api/.
		const lastAdmin = new LQAIApiError(
			403,
			'forbidden',
			'Cannot demote the last admin. Promote another user to admin first, then retry the demotion.'
		);
		expect(describeMutationError(lastAdmin, 'fallback')).toBe(
			'Cannot demote the last admin. Promote another user to admin first, then retry the demotion.'
		);
	});

	it('surfaces the other 403 guard messages and 409 conflicts verbatim', () => {
		const forbidden = new LQAIApiError(403, 'forbidden', 'You cannot disable your own account.');
		expect(describeMutationError(forbidden, 'fallback')).toBe(
			'You cannot disable your own account.'
		);
		const conflict = new LQAIApiError(409, 'conflict', 'A user with this email already exists.');
		expect(describeMutationError(conflict, 'fallback')).toBe(
			'A user with this email already exists.'
		);
	});

	it("never special-cases the fictional 409/'last_admin' shape the server does not emit", () => {
		// Regression guard: if someone re-keys the friendly copy on
		// 409+'last_admin' (the pre-F4 fiction), this asserts the raw message
		// passes through untouched — it FAILS on any synthesized variant.
		const fictional = new LQAIApiError(409, 'last_admin', 'server text');
		expect(describeMutationError(fictional, 'fallback')).toBe('server text');
	});

	it('falls back for non-Error throws', () => {
		expect(describeMutationError('boom', 'fallback')).toBe('fallback');
		expect(describeMutationError(new Error('net down'), 'fallback')).toBe('net down');
	});
});
