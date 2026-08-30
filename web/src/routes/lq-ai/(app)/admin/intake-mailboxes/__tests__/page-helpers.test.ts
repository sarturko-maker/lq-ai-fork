/**
 * Pure-helper tests for the /lq-ai/admin/intake-mailboxes page (INTAKE-5a,
 * ADR-F086). Helpers live in a sibling `page-helpers.ts` so vitest can
 * exercise them without the svelte transformer (Users/Areas-page precedent).
 */
import { describe, expect, it } from 'vitest';

import type { AdminUserRow } from '$lib/lq-ai/types';
import type { IntakeMailbox } from '$lib/lq-ai/api/intakeMailboxes';
import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';

import {
	areaNameFor,
	budgetProfileLabel,
	buildAreaNameMap,
	buildUserEmailMap,
	mailboxStatusView,
	ownerEmailFor,
	parseBudgetProfile,
	parseMaxSteps,
	validateAddress,
	validateInboxId,
	validateMaxSteps,
	validateOwner,
	validatePracticeArea
} from '../page-helpers';

function mailbox(over: Partial<IntakeMailbox> = {}): IntakeMailbox {
	return {
		id: 'mbx-1',
		provider: 'agentmail',
		inbox_id: 'inbox-1',
		address: 'intake@example.com',
		practice_area_id: 'area-1',
		owner_user_id: 'user-1',
		default_budget_profile: null,
		max_steps: null,
		active: true,
		created_at: '2026-08-01T00:00:00Z',
		updated_at: '2026-08-01T00:00:00Z',
		...over
	};
}

function area(over: Partial<PracticeArea> = {}): PracticeArea {
	return {
		id: 'area-1',
		key: 'commercial',
		name: 'Commercial',
		area_code: 'COM',
		unit_label: 'Matter',
		configured: true,
		position: 0,
		profile_md: null,
		default_tier_floor: null,
		default_budget_profile: null,
		agent_config: {},
		hitl_policy: {},
		hitl_eligible_tools: [],
		bound_skills: [],
		bound_tool_groups: [],
		bound_playbooks: [],
		bound_knowledge_bases: [],
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...over
	};
}

function user(over: Partial<AdminUserRow> = {}): AdminUserRow {
	return {
		id: 'user-1',
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

describe('mailboxStatusView', () => {
	it('labels an active mailbox', () => {
		expect(mailboxStatusView(mailbox({ active: true }))).toEqual({
			label: 'Active',
			tone: 'secondary'
		});
	});

	it('labels an inactive mailbox', () => {
		expect(mailboxStatusView(mailbox({ active: false }))).toEqual({
			label: 'Inactive',
			tone: 'outline'
		});
	});
});

describe('budgetProfileLabel', () => {
	it('reads null as Inherit', () => {
		expect(budgetProfileLabel(null)).toBe('Inherit');
	});

	it.each([
		['economy', 'Economy'],
		['balanced', 'Balanced'],
		['generous', 'Generous']
	] as const)('labels %s', (value, expected) => {
		expect(budgetProfileLabel(value)).toBe(expected);
	});
});

describe('buildAreaNameMap / areaNameFor', () => {
	it('resolves a known area to its name', () => {
		const map = buildAreaNameMap([area({ id: 'area-1', name: 'Commercial' })]);
		expect(areaNameFor(map, 'area-1')).toBe('Commercial');
	});

	it('falls back for an area not in the map (deleted out from under the binding)', () => {
		const map = buildAreaNameMap([]);
		expect(areaNameFor(map, 'area-9')).toBe('Unknown area (area-9)');
	});
});

describe('buildUserEmailMap / ownerEmailFor', () => {
	it('resolves a known user to their email', () => {
		const map = buildUserEmailMap([user({ id: 'user-1', email: 'alice@example.com' })]);
		expect(ownerEmailFor(map, 'user-1')).toBe('alice@example.com');
	});

	it('falls back for a user not in the map (soft-deleted out from under the binding)', () => {
		const map = buildUserEmailMap([]);
		expect(ownerEmailFor(map, 'user-9')).toBe('Unknown user (user-9)');
	});
});

describe('validateInboxId', () => {
	it('rejects empty', () => {
		expect(validateInboxId('  ')).toBe('Inbox id is required.');
	});

	it('accepts a non-empty id', () => {
		expect(validateInboxId('inbox-123')).toBeNull();
	});
});

describe('validateAddress', () => {
	it('rejects empty', () => {
		expect(validateAddress('')).toBe('Address is required.');
	});

	it('rejects a non-email string', () => {
		expect(validateAddress('not-an-email')).toBe('Enter a valid email address.');
	});

	it('accepts a well-formed address', () => {
		expect(validateAddress('intake@example.com')).toBeNull();
	});
});

describe('validatePracticeArea / validateOwner', () => {
	it('rejects an empty selection', () => {
		expect(validatePracticeArea('')).toBe('Choose a practice area.');
		expect(validateOwner('')).toBe('Choose an owner.');
	});

	it('accepts a chosen id', () => {
		expect(validatePracticeArea('area-1')).toBeNull();
		expect(validateOwner('user-1')).toBeNull();
	});
});

describe('validateMaxSteps', () => {
	it('accepts an empty value (leave unset)', () => {
		expect(validateMaxSteps('')).toBeNull();
		expect(validateMaxSteps('   ')).toBeNull();
	});

	it('accepts values inside 1..600', () => {
		expect(validateMaxSteps('1')).toBeNull();
		expect(validateMaxSteps('600')).toBeNull();
		expect(validateMaxSteps('42')).toBeNull();
	});

	it('rejects out-of-range and non-integer values', () => {
		expect(validateMaxSteps('0')).toBe('Max steps must be a whole number between 1 and 600.');
		expect(validateMaxSteps('601')).toBe('Max steps must be a whole number between 1 and 600.');
		expect(validateMaxSteps('4.5')).toBe('Max steps must be a whole number between 1 and 600.');
		expect(validateMaxSteps('abc')).toBe('Max steps must be a whole number between 1 and 600.');
	});
});

describe('parseBudgetProfile', () => {
	it('parses the unset option to null', () => {
		expect(parseBudgetProfile('')).toBeNull();
	});

	it('passes a chosen value through', () => {
		expect(parseBudgetProfile('economy')).toBe('economy');
	});
});

describe('parseMaxSteps', () => {
	it('parses empty to null', () => {
		expect(parseMaxSteps('')).toBeNull();
		expect(parseMaxSteps('  ')).toBeNull();
	});

	it('parses a digit string to its number', () => {
		expect(parseMaxSteps('42')).toBe(42);
	});
});
