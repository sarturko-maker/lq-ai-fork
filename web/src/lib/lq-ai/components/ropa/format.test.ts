/**
 * ROPA register format/label helpers (PRIV-3).
 *
 * The codebase has no @testing-library/svelte (CLAUDE.md: don't add libs without
 * justification), so — like AttachKBModal/ComingSoonModal — we cover the register
 * at the pure-helper layer: the enum→label mapping the table cells and badges
 * render, the empty-state copy, and the tab list. The Svelte templates are glue
 * that compose these.
 */
import { describe, expect, it } from 'vitest';
import {
	EMPTY_ACTIVITIES,
	EMPTY_SYSTEMS,
	EMPTY_VENDORS,
	REGISTER_TABS,
	art9ConditionLabel,
	controllerRoleLabel,
	dpaStatusLabel,
	humanize,
	lawfulBasisLabel,
	systemTypeLabel,
	transferMechanismLabel,
	vendorRoleLabel
} from './format';

describe('humanize', () => {
	it('title-cases snake_case tokens', () => {
		expect(humanize('legal_obligation')).toBe('Legal Obligation');
		expect(humanize('third_party_processor')).toBe('Third Party Processor');
	});
	it('returns empty string for empty input', () => {
		expect(humanize('')).toBe('');
	});
});

describe('lawfulBasisLabel', () => {
	it('maps known bases to friendly labels', () => {
		expect(lawfulBasisLabel('legal_obligation')).toBe('Legal obligation');
		expect(lawfulBasisLabel('legitimate_interests')).toBe('Legitimate interests');
		expect(lawfulBasisLabel('consent')).toBe('Consent');
	});
	it('falls back to humanize for an unknown value', () => {
		expect(lawfulBasisLabel('some_future_basis')).toBe('Some Future Basis');
	});
	it('shows an em dash for null/undefined', () => {
		expect(lawfulBasisLabel(null)).toBe('—');
		expect(lawfulBasisLabel(undefined)).toBe('—');
	});
});

describe('controllerRoleLabel', () => {
	it('maps roles', () => {
		expect(controllerRoleLabel('controller')).toBe('Controller');
		expect(controllerRoleLabel('joint_controller')).toBe('Joint controller');
		expect(controllerRoleLabel('processor')).toBe('Processor');
	});
});

describe('systemTypeLabel', () => {
	it('maps system types, including the multi-word one', () => {
		expect(systemTypeLabel('third_party_processor')).toBe('Third-party processor');
		expect(systemTypeLabel('crm')).toBe('CRM');
		expect(systemTypeLabel('email_marketing')).toBe('Email marketing');
	});
});

describe('vendorRoleLabel', () => {
	it('maps vendor roles, with the hyphenated sub-processor', () => {
		expect(vendorRoleLabel('processor')).toBe('Processor');
		expect(vendorRoleLabel('sub_processor')).toBe('Sub-processor');
		expect(vendorRoleLabel('joint_controller')).toBe('Joint controller');
		expect(vendorRoleLabel('separate_controller')).toBe('Separate controller');
		expect(vendorRoleLabel('recipient')).toBe('Recipient');
	});
});

describe('dpaStatusLabel', () => {
	it('maps DPA statuses', () => {
		expect(dpaStatusLabel('in_place')).toBe('In place');
		expect(dpaStatusLabel('not_required')).toBe('Not required');
		expect(dpaStatusLabel('pending')).toBe('Pending');
		expect(dpaStatusLabel('none')).toBe('None');
	});
});

describe('transferMechanismLabel', () => {
	it('maps Chapter V transfer mechanisms, with acronyms/Article refs preserved', () => {
		expect(transferMechanismLabel('standard_contractual_clauses')).toBe(
			'Standard contractual clauses (SCCs)'
		);
		expect(transferMechanismLabel('uk_idta')).toBe('UK IDTA');
		expect(transferMechanismLabel('binding_corporate_rules')).toBe(
			'Binding corporate rules (BCRs)'
		);
		expect(transferMechanismLabel('derogation')).toBe('Derogation (Art 49)');
		expect(transferMechanismLabel('adequacy_regulations')).toBe('Adequacy regulations');
	});
	it('shows an em dash when absent (a non-restricted transfer carries no mechanism)', () => {
		expect(transferMechanismLabel(null)).toBe('—');
	});
});

describe('art9ConditionLabel', () => {
	it('maps Article 9 conditions', () => {
		expect(art9ConditionLabel('health_or_social_care')).toBe('Health or social care');
		expect(art9ConditionLabel('explicit_consent')).toBe('Explicit consent');
	});
	it('shows an em dash when absent (non-special-category record)', () => {
		expect(art9ConditionLabel(null)).toBe('—');
	});
});

describe('register tabs + empty states', () => {
	it('exposes the three tiers in order', () => {
		expect(REGISTER_TABS.map((t) => t.id)).toEqual(['activities', 'systems', 'vendors']);
		expect(REGISTER_TABS.map((t) => t.label)).toEqual([
			'Processing activities',
			'Systems',
			'Vendors'
		]);
	});
	it('has honest, agent-attributed empty-state copy', () => {
		expect(EMPTY_ACTIVITIES).toContain('Privacy agent');
		expect(EMPTY_ACTIVITIES.toLowerCase()).toContain('no processing activities');
		expect(EMPTY_SYSTEMS).toContain('Privacy agent');
		expect(EMPTY_SYSTEMS.toLowerCase()).toContain('no systems');
		expect(EMPTY_VENDORS).toContain('Privacy agent');
		expect(EMPTY_VENDORS.toLowerCase()).toContain('no vendors');
	});
});
