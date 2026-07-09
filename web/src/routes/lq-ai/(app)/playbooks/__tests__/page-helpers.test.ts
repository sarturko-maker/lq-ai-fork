import { describe, it, expect } from 'vitest';

import { LQAIApiError } from '$lib/lq-ai/api/client';
import {
	canProposePlaybook,
	formatVersion,
	isOpenProposalConflict,
	proposePlaybookSuccessMessage,
	sortPlaybooksByName
} from '../page-helpers';
import type { Playbook } from '$lib/lq-ai/types';
import type { OrgPlaybookProposalResponse } from '$lib/lq-ai/api/playbooks';

const mkPlaybook = (overrides: Partial<Playbook>): Playbook => ({
	id: overrides.id ?? 'p',
	name: overrides.name ?? 'p',
	contract_type: overrides.contract_type ?? 'NDA',
	description: '',
	version: overrides.version ?? '1.0.0',
	created_by: overrides.created_by ?? null,
	created_at: '2026-05-18T00:00:00Z',
	updated_at: '2026-05-18T00:00:00Z',
	positions: []
});

describe('sortPlaybooksByName', () => {
	it('sorts case-insensitively', () => {
		const out = sortPlaybooksByName([
			mkPlaybook({ name: 'banana' }),
			mkPlaybook({ name: 'Apple' }),
			mkPlaybook({ name: 'cherry' })
		]);
		expect(out.map((p) => p.name)).toEqual(['Apple', 'banana', 'cherry']);
	});

	it('does not mutate the input array', () => {
		const input = [mkPlaybook({ name: 'b' }), mkPlaybook({ name: 'a' })];
		const out = sortPlaybooksByName(input);
		expect(input.map((p) => p.name)).toEqual(['b', 'a']);
		expect(out.map((p) => p.name)).toEqual(['a', 'b']);
	});
});

describe('formatVersion', () => {
	it('prefixes a v', () => {
		expect(formatVersion('1.0.0')).toBe('v1.0.0');
	});
	it('handles empty / null versions gracefully', () => {
		expect(formatVersion('')).toBe('');
	});
});

// ----- B-4 (ADR-F067 D2/D3) — "Propose to Library" row action -----

describe('canProposePlaybook', () => {
	it('is true when the caller owns the (non-built-in) playbook', () => {
		expect(canProposePlaybook(mkPlaybook({ created_by: 'user-1' }), 'user-1')).toBe(true);
	});

	it("is false for another author's playbook (admins see every org playbook)", () => {
		// The critical B-4 gate: created_by !== null alone would wrongly show the
		// button on someone else's row and the propose call would 404.
		expect(canProposePlaybook(mkPlaybook({ created_by: 'user-2' }), 'user-1')).toBe(false);
	});

	it('is false for a built-in playbook (created_by === null)', () => {
		expect(canProposePlaybook(mkPlaybook({ created_by: null }), 'user-1')).toBe(false);
	});

	it('is false when there is no current user', () => {
		expect(canProposePlaybook(mkPlaybook({ created_by: 'user-1' }), null)).toBe(false);
		expect(canProposePlaybook(mkPlaybook({ created_by: 'user-1' }), undefined)).toBe(false);
	});
});

describe('isOpenProposalConflict (reused from the skill harness)', () => {
	it('is true for the open-proposal 409', () => {
		const err = new LQAIApiError(
			409,
			'http_409',
			'an open proposal already exists for this playbook'
		);
		expect(isOpenProposalConflict(err)).toBe(true);
	});

	it('is false for a non-conflict error', () => {
		expect(isOpenProposalConflict(new LQAIApiError(422, 'http_422', 'too big'))).toBe(false);
		expect(isOpenProposalConflict(new Error('network'))).toBe(false);
	});
});

describe('proposePlaybookSuccessMessage', () => {
	it('names the playbook and version', () => {
		const res: Pick<OrgPlaybookProposalResponse, 'version_no'> = { version_no: 3 };
		expect(proposePlaybookSuccessMessage('NDA Playbook', res)).toBe(
			'Proposed "NDA Playbook" v3 to the Library — an admin will review it.'
		);
	});
});
