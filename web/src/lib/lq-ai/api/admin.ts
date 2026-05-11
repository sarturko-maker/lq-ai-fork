/**
 * Admin API — gateway alias CRUD (D0.5).
 *
 * The backend's /api/v1/admin surface gates these on `is_admin`. Non-admin
 * users get 403 ``forbidden``; the route guard in /lq-ai/admin/* turns that
 * into a redirect to /lq-ai with a flash error.
 */
import { apiRequest } from './client';
import type { UsageResponse, UsageQuery } from '../types';

export interface AliasFallback {
	provider: string;
	model: string;
}

export interface Alias {
	name: string;
	provider: string;
	model: string;
	fallback: AliasFallback[];
	/** Tier 1-5 for the alias's primary target — populated on the
	 *  single-alias GET; absent on the list endpoint. */
	primary_inference_tier?: 1 | 2 | 3 | 4 | 5;
}

export interface AliasListResponse {
	object: 'list';
	data: Alias[];
}

export interface AliasCreateBody {
	name: string;
	provider: string;
	model: string;
	fallback?: AliasFallback[];
}

export interface AliasUpdateBody {
	provider: string;
	model: string;
	fallback?: AliasFallback[];
}

export async function listAliases(): Promise<AliasListResponse> {
	return apiRequest<AliasListResponse>('/admin/aliases');
}

export async function getAlias(name: string): Promise<Alias> {
	return apiRequest<Alias>(`/admin/aliases/${encodeURIComponent(name)}`);
}

export async function createAlias(body: AliasCreateBody): Promise<Alias> {
	return apiRequest<Alias>('/admin/aliases', { method: 'POST', body });
}

export async function updateAlias(name: string, body: AliasUpdateBody): Promise<Alias> {
	return apiRequest<Alias>(`/admin/aliases/${encodeURIComponent(name)}`, {
		method: 'PATCH',
		body
	});
}

export async function deleteAlias(name: string): Promise<void> {
	return apiRequest<void>(`/admin/aliases/${encodeURIComponent(name)}`, {
		method: 'DELETE'
	});
}

/**
 * Sanitized gateway config payload (D0.5). Used by the admin UI to
 * populate the provider dropdown when creating/editing aliases.
 *
 * Only the fields the editor consumes are typed; the gateway emits a
 * full ``GatewayConfig.model_dump`` so unknown fields ride along
 * unmodeled.
 */
export interface AdminConfigSnapshot {
	providers: Array<{
		name: string;
		type: string;
		tier: number;
		enabled?: boolean;
		models?: string[];
	}>;
	model_aliases: Record<string, unknown>;
	[k: string]: unknown;
}

export async function getAdminConfig(): Promise<AdminConfigSnapshot> {
	return apiRequest<AdminConfigSnapshot>('/admin/config');
}

/**
 * GET /api/v1/admin/usage — aggregated turn counts for trust + cost visibility.
 *
 * Admin-only; callers must handle `LQAIApiError` with status 403 (non-admin
 * users) by showing a graceful "admins only" message rather than an error.
 */
export async function getUsage(query: UsageQuery = {}): Promise<UsageResponse> {
	const params = new URLSearchParams();
	for (const [k, v] of Object.entries(query)) {
		if (v !== undefined && v !== null && v !== '') params.append(k, String(v));
	}
	const qs = params.toString();
	return apiRequest<UsageResponse>(`/admin/usage${qs ? '?' + qs : ''}`);
}
