/**
 * ROPA register label/format helpers (PRIV-3).
 *
 * Pure functions only — the register's enum values arrive as machine tokens
 * (`legal_obligation`, `third_party_processor`, `health_or_social_care`) and the
 * UI shows humanised labels. Kept in a standalone module (not inline in the
 * Svelte component) so they are unit-testable without @testing-library/svelte
 * (the codebase tests decision/format helpers, not rendered templates).
 *
 * Rendered in LQ.AI's own F013 style — the labels are ours, not OneTrust's/
 * Oscar's chrome.
 */

const LAWFUL_BASIS_LABELS: Record<string, string> = {
	consent: 'Consent',
	contract: 'Contract',
	legal_obligation: 'Legal obligation',
	vital_interests: 'Vital interests',
	public_task: 'Public task',
	legitimate_interests: 'Legitimate interests'
};

const CONTROLLER_ROLE_LABELS: Record<string, string> = {
	controller: 'Controller',
	joint_controller: 'Joint controller',
	processor: 'Processor'
};

const SYSTEM_TYPE_LABELS: Record<string, string> = {
	database: 'Database',
	analytics: 'Analytics',
	crm: 'CRM',
	support: 'Support',
	email_marketing: 'Email marketing',
	logs: 'Logs',
	backup: 'Backup',
	third_party_processor: 'Third-party processor',
	other: 'Other'
};

const VENDOR_ROLE_LABELS: Record<string, string> = {
	processor: 'Processor',
	sub_processor: 'Sub-processor',
	joint_controller: 'Joint controller',
	separate_controller: 'Separate controller',
	recipient: 'Recipient'
};

const DPA_STATUS_LABELS: Record<string, string> = {
	in_place: 'In place',
	pending: 'Pending',
	not_required: 'Not required',
	none: 'None'
};

const TRANSFER_MECHANISM_LABELS: Record<string, string> = {
	adequacy_regulations: 'Adequacy regulations',
	standard_contractual_clauses: 'Standard contractual clauses (SCCs)',
	uk_idta: 'UK IDTA',
	binding_corporate_rules: 'Binding corporate rules (BCRs)',
	derogation: 'Derogation (Art 49)'
};

const ART9_CONDITION_LABELS: Record<string, string> = {
	explicit_consent: 'Explicit consent',
	employment_social_security: 'Employment / social security',
	vital_interests: 'Vital interests',
	not_for_profit_body: 'Not-for-profit body',
	made_public_by_data_subject: 'Made public by data subject',
	legal_claims: 'Legal claims',
	substantial_public_interest: 'Substantial public interest',
	health_or_social_care: 'Health or social care',
	public_health: 'Public health',
	archiving_research_statistics: 'Archiving, research & statistics'
};

/** Title-case a snake_case token as a last resort (e.g. a future enum value). */
export function humanize(token: string): string {
	if (!token) return '';
	return token
		.split('_')
		.map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
		.join(' ');
}

function labelFrom(map: Record<string, string>, token: string | null | undefined): string {
	if (!token) return '—';
	return map[token] ?? humanize(token);
}

export const lawfulBasisLabel = (t: string | null | undefined): string =>
	labelFrom(LAWFUL_BASIS_LABELS, t);
export const controllerRoleLabel = (t: string | null | undefined): string =>
	labelFrom(CONTROLLER_ROLE_LABELS, t);
export const systemTypeLabel = (t: string | null | undefined): string =>
	labelFrom(SYSTEM_TYPE_LABELS, t);
export const vendorRoleLabel = (t: string | null | undefined): string =>
	labelFrom(VENDOR_ROLE_LABELS, t);
export const dpaStatusLabel = (t: string | null | undefined): string =>
	labelFrom(DPA_STATUS_LABELS, t);
export const transferMechanismLabel = (t: string | null | undefined): string =>
	labelFrom(TRANSFER_MECHANISM_LABELS, t);
export const art9ConditionLabel = (t: string | null | undefined): string =>
	labelFrom(ART9_CONDITION_LABELS, t);

/** Honest empty-state copy — the register shows only what the agent has written. */
export const EMPTY_ACTIVITIES =
	'No processing activities recorded yet — the Privacy agent adds these to the company ROPA as it works.';
export const EMPTY_SYSTEMS =
	'No systems recorded yet — the Privacy agent adds these to the company inventory as it works.';
export const EMPTY_VENDORS =
	'No vendors recorded yet — the Privacy agent adds recipients to the company register as it works.';

export type RegisterTab = 'activities' | 'systems' | 'vendors';

/** The two-tier register's tabs, in display order. */
export const REGISTER_TABS: { id: RegisterTab; label: string }[] = [
	{ id: 'activities', label: 'Processing activities' },
	{ id: 'systems', label: 'Systems' },
	{ id: 'vendors', label: 'Vendors' }
];
