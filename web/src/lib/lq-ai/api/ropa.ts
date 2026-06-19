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
import { apiBlobRequest, apiRequest } from './client';

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

export type VendorRole =
	| 'processor'
	| 'sub_processor'
	| 'joint_controller'
	| 'separate_controller'
	| 'recipient';

export type DpaStatus = 'in_place' | 'pending' | 'not_required' | 'none';

export type TransferMechanism =
	| 'adequacy_regulations'
	| 'standard_contractual_clauses'
	| 'uk_idta'
	| 'binding_corporate_rules'
	| 'derogation';

/** A system as it appears linked under a processing activity. */
export interface SystemSummary {
	id: string;
	name: string;
	system_type: SystemType;
}

/** A vendor/recipient as it appears linked under a processing activity. */
export interface VendorSummary {
	id: string;
	name: string;
	vendor_role: VendorRole;
}

/**
 * A third-country transfer as it appears under its parent processing activity
 * (PRIV-5b). A transfer is a child of one activity, with an optional recipient
 * vendor; `mechanism` is the Chapter V safeguard, present iff `restricted`.
 */
export interface TransferSummary {
	id: string;
	destination: string;
	restricted: boolean;
	mechanism: TransferMechanism | null;
	details: string | null;
	vendor: VendorSummary | null;
}

/**
 * A category of data subjects / personal data as it appears tagged on a
 * processing activity (Article 30(1)(c); PRIV-6a). A pure controlled-vocabulary
 * label.
 */
export interface DataSubjectCategorySummary {
	id: string;
	name: string;
}

export interface DataCategorySummary {
	id: string;
	name: string;
}

/** A processing activity as it appears linked under a system or vendor. */
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
	vendors: VendorSummary[];
	transfers: TransferSummary[];
	data_subject_categories: DataSubjectCategorySummary[];
	data_categories: DataCategorySummary[];
}

export interface VendorRead {
	id: string;
	name: string;
	vendor_role: VendorRole;
	description: string | null;
	country: string | null;
	dpa_status: DpaStatus;
	created_at: string;
	updated_at: string;
	processing_activities: ProcessingActivitySummary[];
}

/**
 * A category of data subjects / personal data + the activities tagged with it
 * (Article 30(1)(c); PRIV-6a). Immutable label — no `updated_at`.
 */
export interface DataSubjectCategoryRead {
	id: string;
	name: string;
	created_at: string;
	processing_activities: ProcessingActivitySummary[];
}

export interface DataCategoryRead {
	id: string;
	name: string;
	created_at: string;
	processing_activities: ProcessingActivitySummary[];
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

/**
 * Programme summary (PRIV-6b) — a read-only aggregate over the whole register:
 * totals, categorical breakdowns (canonical enum order, incl. zero buckets) and
 * "needs attention" gaps. Counts only — no free-text. Mirrors
 * api/app/schemas/ropa.py ProgrammeSummary.
 */
export interface CountByValue {
	value: string;
	count: number;
}

export interface ProgrammeGaps {
	activities_without_systems: number;
	activities_without_recipients: number;
	activities_without_data_categories: number;
	activities_without_data_subjects: number;
	vendors_without_dpa: number;
}

export interface ProgrammeSummary {
	activities_total: number;
	systems_total: number;
	vendors_total: number;
	transfers_total: number;
	transfers_restricted: number;
	special_category_activities: number;
	systems_using_ai: number;
	lawful_basis: CountByValue[];
	controller_role: CountByValue[];
	dpa_status: CountByValue[];
	gaps: ProgrammeGaps;
}

/**
 * Data-flow / lineage graph (PRIV-6c) — a read-only node-link projection of the
 * register: systems feed the activities that process their data, which disclose
 * to recipients and transfer to third-country destinations (the Chapter V
 * safeguard rides each transfer edge). Labels + categorical badges only — no
 * free-text. Mirrors api/app/schemas/ropa.py DataFlow{Node,Edge,Graph}.
 */
export type DataFlowNodeKind = 'system' | 'activity' | 'recipient' | 'destination';
export type DataFlowEdgeKind = 'processed_by' | 'disclosed_to' | 'transferred_to';

export interface DataFlowNode {
	id: string;
	kind: DataFlowNodeKind;
	label: string;
	// System badges.
	system_type?: string | null;
	ai_usage?: boolean | null;
	// Activity badges.
	lawful_basis?: string | null;
	controller_role?: string | null;
	special_category?: boolean | null;
	// Recipient (vendor) badges.
	vendor_role?: string | null;
	dpa_status?: string | null;
}

export interface DataFlowEdge {
	source: string;
	target: string;
	kind: DataFlowEdgeKind;
	restricted?: boolean | null;
	mechanism?: string | null;
	recipient?: string | null;
}

export interface DataFlowGraph {
	nodes: DataFlowNode[];
	edges: DataFlowEdge[];
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

export function listVendors(): Promise<VendorRead[]> {
	return apiRequest<VendorRead[]>('/ropa/vendors');
}

export function getVendor(id: string): Promise<VendorRead> {
	return apiRequest<VendorRead>(`/ropa/vendors/${encodeURIComponent(id)}`);
}

export function listDataSubjectCategories(): Promise<DataSubjectCategoryRead[]> {
	return apiRequest<DataSubjectCategoryRead[]>('/ropa/data-subject-categories');
}

export function listDataCategories(): Promise<DataCategoryRead[]> {
	return apiRequest<DataCategoryRead[]>('/ropa/data-categories');
}

export function getProgrammeSummary(): Promise<ProgrammeSummary> {
	return apiRequest<ProgrammeSummary>('/ropa/programme-summary');
}

export function getDataFlow(): Promise<DataFlowGraph> {
	return apiRequest<DataFlowGraph>('/ropa/data-flow');
}

// --- Article 30 export (PRIV-4a) ---------------------------------------------

/** Export formats the backend serves (api/app/api/ropa.py ExportFormat). */
export type ExportFormat = 'json' | 'csv' | 'xlsx';

/**
 * Read the download filename the server set in `Content-Disposition`, falling
 * back to a sensible default when the header is absent (e.g. under a proxy that
 * strips it). Pure — unit-tested separately from the DOM download.
 */
export function filenameFromDisposition(disposition: string | null, format: ExportFormat): string {
	const match = disposition?.match(/filename="([^"]+)"/);
	return match ? match[1] : `article-30-ropa.${format}`;
}

/**
 * Download the company ROPA as an Article 30 deliverable. Fetches the file with
 * auth (refresh-on-401), then triggers a browser download via an object URL.
 * Browser-only — the DOM bits no-op under SSR/tests without a document.
 */
export async function downloadArticle30(format: ExportFormat = 'xlsx'): Promise<void> {
	const res = await apiBlobRequest(`/ropa/export?format=${encodeURIComponent(format)}`);
	const blob = await res.blob();
	const filename = filenameFromDisposition(res.headers.get('content-disposition'), format);

	if (typeof document === 'undefined') {
		return;
	}
	const url = URL.createObjectURL(blob);
	try {
		const a = document.createElement('a');
		a.href = url;
		a.download = filename;
		document.body.appendChild(a);
		a.click();
		a.remove();
	} finally {
		URL.revokeObjectURL(url);
	}
}
