/**
 * Pure-helper tests for the /lq-ai/skills page (B-2b, ADR-F067 D2/D3).
 */
import { describe, expect, it } from 'vitest';

import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { UserSkill } from '$lib/lq-ai/types';
import type { OrgSkillProposalResponse } from '$lib/lq-ai/api/userSkills';
import {
	canProposeSkill,
	isOpenProposalConflict,
	proposeSuccessMessage
} from '../page-helpers';

function userSkill(over: Partial<UserSkill> = {}): UserSkill {
	return {
		id: 'skill-1',
		scope: 'user',
		owner_user_id: 'user-1',
		owner_team_id: null,
		slug: 'nda-review',
		display_name: 'NDA Review',
		description: 'Review an NDA.',
		version: '1.0.0',
		tags: [],
		frontmatter_extra: {},
		body: 'Body text.',
		slash_alias: null,
		forked_from: null,
		archived_at: null,
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...over
	};
}

describe('canProposeSkill', () => {
	it('is true for a user-scope row', () => {
		expect(canProposeSkill(userSkill({ scope: 'user' }))).toBe(true);
	});

	it('is false for a team-scope row', () => {
		expect(canProposeSkill(userSkill({ scope: 'team', owner_user_id: null, owner_team_id: 'team-1' }))).toBe(
			false
		);
	});
});

describe('isOpenProposalConflict', () => {
	it('is true for the open-proposal 409', () => {
		const err = new LQAIApiError(409, 'http_409', "an open proposal already exists for slug 'nda-review'");
		expect(isOpenProposalConflict(err)).toBe(true);
	});

	it('is false for the shipped-slug-collision 409 (doctrine problem, stays clickable)', () => {
		const err = new LQAIApiError(409, 'http_409', "skill slug 'nda-review' collides with a shipped skill");
		expect(isOpenProposalConflict(err)).toBe(false);
	});

	it('is false for the concurrent-race 409 (message says retry)', () => {
		const err = new LQAIApiError(
			409,
			'http_409',
			"a concurrent proposal for slug 'nda-review' was just recorded — retry"
		);
		expect(isOpenProposalConflict(err)).toBe(false);
	});

	it('is false for a 422 (allowlist / size cap)', () => {
		const err = new LQAIApiError(422, 'http_422', 'org skill content exceeds the byte cap');
		expect(isOpenProposalConflict(err)).toBe(false);
	});

	it('is false for a non-LQAIApiError', () => {
		expect(isOpenProposalConflict(new Error('network error'))).toBe(false);
		expect(isOpenProposalConflict(null)).toBe(false);
	});
});

describe('proposeSuccessMessage', () => {
	it('names the slug and version', () => {
		const res: Pick<OrgSkillProposalResponse, 'slug' | 'version_no'> = {
			slug: 'nda-review',
			version_no: 3
		};
		expect(proposeSuccessMessage(res)).toBe(
			'Proposed "nda-review" v3 to the Library — an admin will review it.'
		);
	});
});
