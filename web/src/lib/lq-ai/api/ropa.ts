/**
 * /api/v1/ropa — the deployment-global ROPA register (read-only) — PRIV-3.
 *
 * The Privacy module's two-tier inventory: Processing Activities (Article 30
 * records) ↔ Systems (where personal data lives), linked M:N. The register is
 * the company's standing record (LQ.AI is single-tenant; ADR-F019), so these
 * read endpoints are global — no project/matter id in the path. The Privacy
 * Deep Agent is the only writer (guarded, code-validated tools); the UI reads.
 *
 * Wire shapes mirror api/app/schemas/ropa.py (the Read DTOs).
 */
import { apiRequest } from './client';

export type LawfulBasis =
	| 'consent'
	| 'contract'
	| 'legal_obligation'
	| 'vital_interests'
	| 'public_task'
	| 'legitimate_interests';

export type ControllerRole = 'controller' | 'joint_controller' | 'processor';

export type SystemType =
	| 'database'
	| 'analytics'
	| 'crm'
	| 'support'
	| 'email_marketing'
	| 'logs'
	| 'backup'
	| 'third_party_processor'
	| 'other';

/** A system as it appears linked under a processing activity. */
export interface SystemSummary {
	id: string;
	name: string;
	system_type: SystemType;
}

/** A processing activity as it appears linked under a system. */
export interface ProcessingActivitySummary {
	id: string;
	name: string;
	lawful_basis: LawfulBasis;
	special_category: boolean;
}

export interface ProcessingActivityRead {
	id: string;
	name: string;
	purpose: string;
	lawful_basis: LawfulBasis;
	controller_role: ControllerRole;
	retention: string;
	special_category: boolean;
	art9_condition: string | null;
	created_at: string;
	updated_at: string;
	systems: SystemSummary[];
}

export interface SystemRead {
	id: string;
	name: string;
	system_type: SystemType;
	description: string | null;
	owner: string | null;
	hosting_location: string | null;
	retention: string | null;
	security_measures: string | null;
	ai_usage: boolean;
	created_at: string;
	updated_at: string;
	processing_activities: ProcessingActivitySummary[];
}

export function listProcessingActivities(): Promise<ProcessingActivityRead[]> {
	return apiRequest<ProcessingActivityRead[]>('/ropa/processing-activities');
}

export function getProcessingActivity(id: string): Promise<ProcessingActivityRead> {
	return apiRequest<ProcessingActivityRead>(
		`/ropa/processing-activities/${encodeURIComponent(id)}`
	);
}

export function listSystems(): Promise<SystemRead[]> {
	return apiRequest<SystemRead[]>('/ropa/systems');
}

export function getSystem(id: string): Promise<SystemRead> {
	return apiRequest<SystemRead>(`/ropa/systems/${encodeURIComponent(id)}`);
}
