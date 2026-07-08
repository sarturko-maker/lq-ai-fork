/**
 * Pure-helper tests for the /lq-ai/skills/[id]/edit "Proposals" section
 * (B-2b, ADR-F067 D2/D3).
 */
import { describe, expect, it } from 'vitest';

import type { OrgSkillProposalResponse } from '$lib/lq-ai/api/userSkills';
import type { OrgSkillVersionState } from '$lib/lq-ai/types';
import {
	proposalStateLabel,
	proposalStateTone,
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
