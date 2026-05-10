/**
 * Admin audit-log API (D3-coverage).
 *
 * The backend's ``GET /api/v1/admin/audit-log`` endpoint is gated on
 * ``is_admin`` and supports cursor-paginated reads with filters on
 * privilege flag, routed inference tier, action, user, and time range.
 * The route guard at /lq-ai/admin/audit-log redirects non-admins.
 */
import { apiRequest } from './client';

export interface AuditLogEntry {
	id: string;
	timestamp: string;
	user_id: string | null;
	action: string;
	resource_type: string;
	resource_id: string | null;
	privilege_marked: boolean;
	privilege_basis: string | null;
	routed_inference_tier: 1 | 2 | 3 | 4 | 5 | null;
	routed_provider: string | null;
	ip_address: string | null;
	user_agent: string | null;
	request_id: string | null;
	details: Record<string, unknown> | null;
}

export interface AuditLogPage {
	items: AuditLogEntry[];
	next_cursor: string | null;
}

export interface AuditLogFilters {
	privilege_marked?: boolean | null;
	routed_inference_tier?: 1 | 2 | 3 | 4 | 5 | null;
	action?: string | null;
	user_id?: string | null;
	since?: string | null;
	until?: string | null;
	limit?: number;
	cursor?: string | null;
}

function buildQuery(filters: AuditLogFilters): string {
	const params = new URLSearchParams();
	if (filters.privilege_marked != null) {
		params.set('privilege_marked', filters.privilege_marked ? 'true' : 'false');
	}
	if (filters.routed_inference_tier != null) {
		params.set('routed_inference_tier', String(filters.routed_inference_tier));
	}
	if (filters.action) params.set('action', filters.action);
	if (filters.user_id) params.set('user_id', filters.user_id);
	if (filters.since) params.set('since', filters.since);
	if (filters.until) params.set('until', filters.until);
	if (filters.limit != null) params.set('limit', String(filters.limit));
	if (filters.cursor) params.set('cursor', filters.cursor);
	const q = params.toString();
	return q ? `?${q}` : '';
}

export async function listAuditLog(filters: AuditLogFilters = {}): Promise<AuditLogPage> {
	return apiRequest<AuditLogPage>(`/admin/audit-log${buildQuery(filters)}`);
}
