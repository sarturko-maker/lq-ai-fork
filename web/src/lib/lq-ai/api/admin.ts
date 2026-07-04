/**
 * Admin API — gateway alias CRUD (D0.5).
 *
 * The backend's /api/v1/admin surface gates these on `is_admin`. Non-admin
 * users get 403 ``forbidden``; the route guard in /lq-ai/admin/* turns that
 * into a redirect to /lq-ai with a flash error.
 */
import { apiRequest } from './client';
import type {
	UsageResponse,
	UsageQuery,
	AdminUserListResponse,
	AdminUserListQuery,
	InviteCreateRequest,
	InviteListResponse,
	InviteResponse,
	UserDisableResponse,
	UserRoleResponse
} from '../types';

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

/**
 * GET /api/v1/admin/users — list platform users with optional role/email filters.
 *
 * Admin-only. Callers must handle LQAIApiError status 403.
 */
export async function listUsers(query: AdminUserListQuery = {}): Promise<AdminUserListResponse> {
	const params = new URLSearchParams();
	for (const [k, v] of Object.entries(query)) {
		if (v !== undefined && v !== null && v !== '') params.append(k, String(v));
	}
	const qs = params.toString();
	return apiRequest<AdminUserListResponse>(`/admin/users${qs ? '?' + qs : ''}`);
}

/**
 * PATCH /api/v1/admin/users/{user_id}/role — update a user's platform role.
 *
 * Demoting the last admin is refused with 403 code "forbidden" and an
 * actionable message (SETUP-3b review fix F4/F6 — the endpoint returns a
 * UserRoleResponse, not an AdminUserRow, and no 'last_admin' code exists).
 */
export async function patchUserRole(
	userId: string,
	role: 'admin' | 'member' | 'viewer'
): Promise<UserRoleResponse> {
	return apiRequest<UserRoleResponse>(`/admin/users/${encodeURIComponent(userId)}/role`, {
		method: 'PATCH',
		body: { role }
	});
}

// ----- User lifecycle: invites + disable/enable (SETUP-3b, ADR-F061 D8) -----

/**
 * POST /api/v1/admin/users/invites — invite a new user.
 *
 * 409 when an active user or a pending invite already owns the email. When
 * SMTP is off the response carries `accept_url` for out-of-band handover —
 * display it, never log or persist it.
 */
export async function createInvite(body: InviteCreateRequest): Promise<InviteResponse> {
	return apiRequest<InviteResponse>('/admin/users/invites', { method: 'POST', body });
}

/** GET /api/v1/admin/users/invites — all invites, newest first. */
export async function listInvites(): Promise<InviteListResponse> {
	return apiRequest<InviteListResponse>('/admin/users/invites');
}

/** POST /api/v1/admin/users/invites/{id}/resend — revoke + reissue (409 if accepted). */
export async function resendInvite(inviteId: string): Promise<InviteResponse> {
	return apiRequest<InviteResponse>(
		`/admin/users/invites/${encodeURIComponent(inviteId)}/resend`,
		{ method: 'POST' }
	);
}

/** DELETE /api/v1/admin/users/invites/{id} — revoke a pending invite (204). */
export async function revokeInvite(inviteId: string): Promise<void> {
	return apiRequest<void>(`/admin/users/invites/${encodeURIComponent(inviteId)}`, {
		method: 'DELETE'
	});
}

/**
 * POST /api/v1/admin/users/{id}/disable — disable an account (ADR-F061 D5).
 *
 * Server guards: 403 for self, the last active admin, and operator targets.
 */
export async function disableUser(userId: string): Promise<UserDisableResponse> {
	return apiRequest<UserDisableResponse>(`/admin/users/${encodeURIComponent(userId)}/disable`, {
		method: 'POST'
	});
}

/** POST /api/v1/admin/users/{id}/enable — re-enable a disabled account. */
export async function enableUser(userId: string): Promise<UserDisableResponse> {
	return apiRequest<UserDisableResponse>(`/admin/users/${encodeURIComponent(userId)}/enable`, {
		method: 'POST'
	});
}
