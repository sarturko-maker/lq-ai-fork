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
	EMPTY_ASSESSMENTS,
	EMPTY_SYSTEMS,
	EMPTY_VENDORS,
	REGISTER_TABS,
	art9ConditionLabel,
	assessmentStatusLabel,
	assessmentTypeLabel,
	controllerRoleLabel,
	dpaStatusLabel,
	dpiaOnFile,
	humanize,
	lawfulBasisLabel,
	riskLevelLabel,
	riskStatusLabel,
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

describe('assessmentTypeLabel', () => {
	it('maps PIA/DPIA/LIA/TIA to upper-case acronyms', () => {
		expect(assessmentTypeLabel('pia')).toBe('PIA');
		expect(assessmentTypeLabel('dpia')).toBe('DPIA');
		expect(assessmentTypeLabel('lia')).toBe('LIA');
		expect(assessmentTypeLabel('tia')).toBe('TIA');
	});
	it('shows an em dash for null/undefined', () => {
		expect(assessmentTypeLabel(null)).toBe('—');
	});
});

describe('assessmentStatusLabel', () => {
	it('maps assessment statuses, with the multi-word one', () => {
		expect(assessmentStatusLabel('draft')).toBe('Draft');
		expect(assessmentStatusLabel('in_progress')).toBe('In progress');
		expect(assessmentStatusLabel('completed')).toBe('Completed');
	});
});

describe('riskLevelLabel / riskStatusLabel', () => {
	it('maps the low/medium/high band', () => {
		expect(riskLevelLabel('low')).toBe('Low');
		expect(riskLevelLabel('medium')).toBe('Medium');
		expect(riskLevelLabel('high')).toBe('High');
	});
	it('maps risk dispositions', () => {
		expect(riskStatusLabel('open')).toBe('Open');
		expect(riskStatusLabel('mitigated')).toBe('Mitigated');
		expect(riskStatusLabel('accepted')).toBe('Accepted');
	});
});

describe('dpiaOnFile', () => {
	it('is true only when a completed DPIA covers the activity', () => {
		expect(dpiaOnFile([{ type: 'dpia', status: 'completed' }])).toBe(true);
		expect(
			dpiaOnFile([
				{ type: 'pia', status: 'completed' },
				{ type: 'dpia', status: 'completed' }
			])
		).toBe(true);
	});
	it('is false for a draft/in-progress DPIA, a non-DPIA, or no assessments', () => {
		expect(dpiaOnFile([{ type: 'dpia', status: 'draft' }])).toBe(false);
		expect(dpiaOnFile([{ type: 'dpia', status: 'in_progress' }])).toBe(false);
		expect(dpiaOnFile([{ type: 'pia', status: 'completed' }])).toBe(false);
		expect(dpiaOnFile([])).toBe(false);
		expect(dpiaOnFile(null)).toBe(false);
		expect(dpiaOnFile(undefined)).toBe(false);
	});
});

describe('register tabs + empty states', () => {
	it('exposes the register tabs in order', () => {
		expect(REGISTER_TABS.map((t) => t.id)).toEqual([
			'overview',
			'data-flow',
			'activities',
			'systems',
			'vendors',
			'data-subjects',
			'data-categories',
			'assessments'
		]);
		expect(REGISTER_TABS.map((t) => t.label)).toEqual([
			'Overview',
			'Data flow',
			'Processing activities',
			'Systems',
			'Vendors',
			'Data subjects',
			'Data categories',
			'Assessments'
		]);
	});
	it('has honest, agent-attributed empty-state copy', () => {
		expect(EMPTY_ACTIVITIES).toContain('Privacy agent');
		expect(EMPTY_ACTIVITIES.toLowerCase()).toContain('no processing activities');
		expect(EMPTY_SYSTEMS).toContain('Privacy agent');
		expect(EMPTY_SYSTEMS.toLowerCase()).toContain('no systems');
		expect(EMPTY_VENDORS).toContain('Privacy agent');
		expect(EMPTY_VENDORS.toLowerCase()).toContain('no vendors');
		expect(EMPTY_ASSESSMENTS).toContain('Privacy agent');
		expect(EMPTY_ASSESSMENTS.toLowerCase()).toContain('no privacy assessments');
	});
});
