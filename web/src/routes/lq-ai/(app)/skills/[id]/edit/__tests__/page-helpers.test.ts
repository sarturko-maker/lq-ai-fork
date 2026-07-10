/**
 * Pure-helper tests for the /lq-ai/skills/[id]/edit "Proposals" section
 * (B-2b, ADR-F067 D2/D3).
 */
import { describe, expect, it } from 'vitest';

import type { OrgSkillProposalResponse } from '$lib/lq-ai/api/userSkills';
import type { OrgSkillVersionState, PlatformRole, User } from '$lib/lq-ai/types';
import {
	canPropose,
	canPublish,
	proposalStateLabel,
	proposalStateTone,
	showOrgLibrarySection,
	showProposalsSection,
	sortProposalsNewestFirst
} from '../page-helpers';

function proposal(over: Partial<OrgSkillProposalResponse> = {}): OrgSkillProposalResponse {
	return {
		id: 'v-1',
		slug: 'nda-review',
		version_no: 1,
		state: 'proposed',
		content_hash: 'abc123',
		size_bytes: 1234,
		proposed_at: '2026-07-01T00:00:00Z',
		reviewed_at: null,
		review_note: null,
		revoked_at: null,
		...over
	};
}

/** A minimal user shape for the role gates — only the two fields they read. */
function user(is_admin: boolean, role?: PlatformRole): Pick<User, 'is_admin' | 'role'> {
	return { is_admin, role };
}

describe('canPublish / canPropose (ADR-F067 org-adoption gates)', () => {
	it('an org admin (non-operator) sees Publish only', () => {
		const admin = user(true, 'admin');
		expect(canPublish(admin)).toBe(true);
		expect(canPropose(admin)).toBe(false);
	});

	it('a plain member sees Propose only', () => {
		const member = user(false, 'member');
		expect(canPropose(member)).toBe(true);
		expect(canPublish(member)).toBe(false);
	});

	it('a viewer sees NEITHER — propose is MutatingUser-gated, viewers are read-only (ADR-F064 D1)', () => {
		const viewer = user(false, 'viewer');
		expect(canPropose(viewer)).toBe(false);
		expect(canPublish(viewer)).toBe(false);
	});

	it('the platform operator sees NEITHER (ADR-F064 fences tenant content)', () => {
		// Operator passes the AdminUser gate (org-admin ⊂ operator), so is_admin
		// may be true — the role guard is what excludes it from BOTH buttons.
		const operatorAdmin = user(true, 'operator');
		expect(canPublish(operatorAdmin)).toBe(false);
		expect(canPropose(operatorAdmin)).toBe(false);

		const operatorPlain = user(false, 'operator');
		expect(canPublish(operatorPlain)).toBe(false);
		expect(canPropose(operatorPlain)).toBe(false);
	});

	it('is safe for a null / undefined user (logged-out) — neither shows', () => {
		expect(canPublish(null)).toBe(false);
		expect(canPropose(null)).toBe(false);
		expect(canPublish(undefined)).toBe(false);
		expect(canPropose(undefined)).toBe(false);
	});

	it('the two gates are MUTUALLY EXCLUSIVE across every is_admin × role combo', () => {
		const roles: (PlatformRole | undefined)[] = [
			'admin',
			'member',
			'viewer',
			'operator',
			undefined
		];
		for (const is_admin of [true, false]) {
			for (const role of roles) {
				const u = user(is_admin, role);
				expect(canPublish(u) && canPropose(u)).toBe(false);
			}
		}
	});
});

describe('showOrgLibrarySection (scope × role gate)', () => {
	it('shows for a user-scope skill when the viewer can publish or propose', () => {
		expect(showOrgLibrarySection('user', user(true, 'admin'))).toBe(true);
		expect(showOrgLibrarySection('user', user(false, 'member'))).toBe(true);
	});

	it('NEVER shows for a team-scope skill — publish/propose 404 team rows (ADR-F067 D2)', () => {
		expect(showOrgLibrarySection('team', user(true, 'admin'))).toBe(false);
		expect(showOrgLibrarySection('team', user(false, 'member'))).toBe(false);
	});

	it('hides for the operator and for a logged-out viewer regardless of scope', () => {
		expect(showOrgLibrarySection('user', user(true, 'operator'))).toBe(false);
		expect(showOrgLibrarySection('user', null)).toBe(false);
		expect(showOrgLibrarySection('user', undefined)).toBe(false);
	});
});

describe('proposalStateTone', () => {
	it('maps every state to a tone', () => {
		const states: OrgSkillVersionState[] = ['proposed', 'approved', 'rejected', 'superseded', 'revoked'];
		for (const s of states) {
			expect(typeof proposalStateTone(s)).toBe('string');
		}
	});

	it('gives approved the sage (success) tone and rejected/revoked red', () => {
		expect(proposalStateTone('approved')).toBe('sage');
		expect(proposalStateTone('rejected')).toBe('red');
		expect(proposalStateTone('revoked')).toBe('red');
	});

	it('gives proposed the amber (pending) tone', () => {
		expect(proposalStateTone('proposed')).toBe('amber');
	});
});

describe('proposalStateLabel', () => {
	it('title-cases every state', () => {
		expect(proposalStateLabel('proposed')).toBe('Proposed');
		expect(proposalStateLabel('approved')).toBe('Approved');
		expect(proposalStateLabel('rejected')).toBe('Rejected');
		expect(proposalStateLabel('superseded')).toBe('Superseded');
		expect(proposalStateLabel('revoked')).toBe('Revoked');
	});
});

describe('showProposalsSection', () => {
	it('shows the section only for user-scope skills (ADR-F067 D2)', () => {
		expect(showProposalsSection('user')).toBe(true);
	});

	it('hides the section entirely for team-scope skills (endpoint would 404)', () => {
		expect(showProposalsSection('team')).toBe(false);
	});
});

describe('sortProposalsNewestFirst', () => {
	it('sorts by version_no descending regardless of input order', () => {
		const unsorted = [
			proposal({ id: 'v-1', version_no: 1 }),
			proposal({ id: 'v-3', version_no: 3 }),
			proposal({ id: 'v-2', version_no: 2 })
		];
		expect(sortProposalsNewestFirst(unsorted).map((p) => p.version_no)).toEqual([3, 2, 1]);
	});

	it('does not mutate the input array', () => {
		const input = [proposal({ version_no: 1 }), proposal({ version_no: 2 })];
		const copy = [...input];
		sortProposalsNewestFirst(input);
		expect(input).toEqual(copy);
	});

	it('returns [] for an empty list', () => {
		expect(sortProposalsNewestFirst([])).toEqual([]);
	});
});
