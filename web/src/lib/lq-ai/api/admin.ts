/**
 * Admin API — gateway alias CRUD (D0.5).
 *
 * The backend's /api/v1/admin surface gates these on `is_admin`. Non-admin
 * users get 403 ``forbidden``; the route guard in /lq-ai/admin/* turns that
 * into a redirect to /lq-ai with a flash error.
 */
import { apiRequest } from './client';
import type {
	FallbackTier,
	OrgSkillVersionState,
	PositionSeverity,
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
	return apiRequest<InviteResponse>(`/admin/users/invites/${encodeURIComponent(inviteId)}/resend`, {
		method: 'POST'
	});
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

// ----- Deployment-wide (Level 0) capability toggles (SETUP-4a/4b, ADR-F062) -----

/** One deployment capability + its effective Level-0 enabled state. Deliberately a
 *  narrower shape than the matter-panel `CapabilityEntry` (types.ts) — there is no
 *  `available`/`default_enabled`/`toggleable` at this level, only `enabled`.
 *
 *  STORE-2 (ADR-F065 D-A) additive fields for the Store/Library pages' provenance
 *  badges: `in_library` is the STORE-1 truth (`enabled` is its deprecated alias) —
 *  required, since it already governs Library-scoped picker filtering. The
 *  remaining fields are always present on the wire (the backend defaults
 *  `tags`/`recommended_for` to `[]` and `source`/`author`/`version` to `null`) but
 *  are typed OPTIONAL here — display-only provenance metadata that pre-STORE-2
 *  fixtures across the admin pages don't construct, so treating them as optional
 *  avoids churning every unrelated test's literal. Skill entries carry real
 *  `source`/`author`/`version`/`tags`; tool entries get `source: "built-in"` only;
 *  playbook entries get `source: null` (no provenance field exists for them yet).
 *  Knowledge entries (B-3, ADR-F067 D1) likewise get `source: null` — adoption +
 *  binding IS the control, not provenance review.
 *
 *  `approver` (B-2b, D3.5 wire gap): additive, optional — for `source === "org"`
 *  skill entries, the approving admin's email (the snapshot's `reviewed_by`
 *  resolved to an email, mirroring `author`'s resolution); `undefined`/`null` for
 *  every other entry. */
export interface DeploymentCapabilityRead {
	capability_kind: 'skill' | 'tool' | 'playbook' | 'knowledge';
	capability_key: string;
	label: string;
	description: string | null;
	in_library: boolean;
	enabled: boolean;
	source?: string | null;
	author?: string | null;
	version?: string | null;
	approver?: string | null;
	tags?: string[];
	recommended_for?: string[];
}

/** A kind-grouped section (Tools / Skills / Playbooks / Knowledge) of the deployment inventory. */
export interface DeploymentCapabilitySection {
	kind: 'skill' | 'tool' | 'playbook' | 'knowledge';
	label: string;
	entries: DeploymentCapabilityRead[];
}

/** GET/PATCH /api/v1/admin/capabilities body/response. */
export interface DeploymentCapabilitiesResponse {
	sections: DeploymentCapabilitySection[];
}

/** GET /api/v1/admin/capabilities — the whole-deployment inventory (admin). */
export async function getDeploymentCapabilities(): Promise<DeploymentCapabilitiesResponse> {
	return apiRequest<DeploymentCapabilitiesResponse>('/admin/capabilities');
}

// NOTE (STORE-2 review fix): the `patchDeploymentCapabilities` client (PATCH
// /admin/capabilities Level-0 toggles) lost its only caller when the old
// Capabilities page became a redirect stub, and was deleted with it. The
// SERVER keeps the PATCH endpoint as the STORE-1 compat shim over the Library
// (enabled=true ⇒ adopt / false ⇒ remove); the web writes through
// `adoptLibraryEntry`/`removeLibraryEntry` below instead.

// NOTE (SETUP-4b review fix 3): a `getModelMenu` client for GET /admin/model-menu
// briefly lived here and was DELETED along with the endpoint — the alias+tier pair
// is already member-visible via `modelsApi.listModels()` (GET /api/v1/models); the
// capabilities page derives it client-side.

// ----- Org Library — adopt/remove (STORE-1/2, ADR-F065) -----

/** POST /admin/library body — adopt one catalog capability. */
export interface LibraryEntryInput {
	kind: 'skill' | 'tool' | 'playbook' | 'knowledge';
	key: string;
}

/**
 * POST /api/v1/admin/library — adopt a catalog capability into the org's
 * Library (Store page's "Add to Library"). 422 for an unknown (kind, key);
 * 409 if already adopted (callers treat 409 as a benign no-op — the desired
 * end state already holds).
 */
export async function adoptLibraryEntry(body: LibraryEntryInput): Promise<void> {
	await apiRequest<void>('/admin/library', { method: 'POST', body });
}

/**
 * DELETE /api/v1/admin/library/{kind}/{key} — remove a capability from the
 * Library (Library page's Remove, after the D-F confirm). Idempotent (204
 * even if not adopted).
 */
export async function removeLibraryEntry(
	kind: 'skill' | 'tool' | 'playbook' | 'knowledge',
	key: string
): Promise<void> {
	await apiRequest<void>(`/admin/library/${encodeURIComponent(kind)}/${encodeURIComponent(key)}`, {
		method: 'DELETE'
	});
}

// ----- Org-skills review queue (B-2b, ADR-F067 D2/D3) -----

/**
 * One `org_skill_versions` row, FULL content — the admin review view
 * (`GET /admin/org-skills`, the approve/reject/revoke echo).
 *
 * `raw_yaml`/`body` are the review source of truth (the admin reads the exact
 * bytes before approving, D3.1) — never rendered as trusted markup, only shown
 * verbatim in a `<pre>` (or, for `body`, optionally ALSO through
 * `renderModelMarkdown` in a second view — the `<pre>` stays authoritative).
 */
export interface OrgSkillVersionAdminRead {
	id: string;
	slug: string;
	version_no: number;
	/** The shared ``OrgSkillVersionState`` union from ``$lib/lq-ai/types``
	 *  (also used by the author-side status view in ``userSkills.ts``). */
	state: OrgSkillVersionState;
	author_user_id: string | null;
	author_email: string | null;
	proposed_at: string;
	reviewed_by: string | null;
	/** B-2b, D3.5 wire gap — `reviewed_by` resolved to an email, mirroring
	 *  `author_email`. `null` until the row has been reviewed (approved OR
	 *  rejected both set it; revoke leaves it untouched). */
	approver_email: string | null;
	reviewed_at: string | null;
	review_note: string | null;
	revoked_at: string | null;
	content_hash: string;
	size_bytes: number;
	raw_yaml: string;
	body: string;
}

export interface OrgSkillVersionsListResponse {
	versions: OrgSkillVersionAdminRead[];
}

/**
 * GET /api/v1/admin/org-skills — the review queue, optionally state-filtered.
 * Newest-proposed first. AdminUser-gated; ADR-F064 excludes the platform
 * operator (tenant-authored content) — 403.
 */
export async function listOrgSkillVersions(
	state?: OrgSkillVersionState
): Promise<OrgSkillVersionsListResponse> {
	const qs = state ? `?state=${encodeURIComponent(state)}` : '';
	return apiRequest<OrgSkillVersionsListResponse>(`/admin/org-skills${qs}`);
}

/**
 * POST /api/v1/admin/org-skills/{id}/approve — pins the immutable snapshot.
 * 409 unless the row is `proposed`.
 */
export async function approveOrgSkillVersion(id: string): Promise<OrgSkillVersionAdminRead> {
	return apiRequest<OrgSkillVersionAdminRead>(
		`/admin/org-skills/${encodeURIComponent(id)}/approve`,
		{ method: 'POST' }
	);
}

/**
 * POST /api/v1/admin/org-skills/{id}/reject — `note` rides the response's
 * `review_note` (<=2000 chars); 409 unless the row is `proposed`.
 */
export async function rejectOrgSkillVersion(
	id: string,
	note?: string
): Promise<OrgSkillVersionAdminRead> {
	return apiRequest<OrgSkillVersionAdminRead>(
		`/admin/org-skills/${encodeURIComponent(id)}/reject`,
		{ method: 'POST', body: { note: note && note.trim() !== '' ? note : undefined } }
	);
}

/**
 * POST /api/v1/admin/org-skills/{id}/revoke — 409 unless the row is `approved`.
 * Does NOT remove a matching Library row (ADR-F067 D3.8 fail-close) — the
 * runtime and the member Library read both surface the dangling entry.
 */
export async function revokeOrgSkillVersion(id: string): Promise<OrgSkillVersionAdminRead> {
	return apiRequest<OrgSkillVersionAdminRead>(
		`/admin/org-skills/${encodeURIComponent(id)}/revoke`,
		{ method: 'POST' }
	);
}

// ----- Org-playbooks review queue (B-4, ADR-F067 D2/D3) -----

/**
 * One FROZEN position inside an `org_playbook_versions` snapshot — the review
 * surface's content payload (the playbook analogue of `raw_yaml`/`body`).
 *
 * These bytes come from untrusted JSONB (any authenticated author's playbook,
 * frozen at propose time), so the review renderer treats every free-text field
 * as escaped plain text — never trusted markup (CLAUDE.md injection rule). The
 * declared shape mirrors the backend's canonical position; the renderer still
 * guards defensively (missing/malformed arrays).
 */
export interface OrgPlaybookPositionRead {
	issue: string;
	description: string;
	standard_language: string;
	fallback_tiers: FallbackTier[];
	redline_strategy: string;
	severity_if_missing: PositionSeverity;
	detection_keywords: string[];
	detection_examples: string[];
	position_order: number;
}

/**
 * One `org_playbook_versions` row, FULL content — the admin review view
 * (`GET /admin/org-playbooks`, the approve/reject/revoke echo). The playbook
 * analogue of {@link OrgSkillVersionAdminRead}; `positions` (the frozen
 * snapshot) replaces `raw_yaml`/`body`.
 *
 * `playbook_id` is the stable adoption key (the Library keys org playbooks by
 * `str(playbook_id)`), independent of the live `playbooks` row. `playbook_version`
 * is the frozen capability label (distinct from `version_no`, the monotonic
 * proposal counter). The one deliberate content-exposing read — AdminUser-gated,
 * operator-excluded (ADR-F064), not audited.
 */
export interface OrgPlaybookVersionAdminRead {
	id: string;
	playbook_id: string;
	version_no: number;
	/** The shared ``OrgSkillVersionState`` union — identical closed set across
	 *  the skill and playbook harnesses. */
	state: OrgSkillVersionState;
	name: string;
	contract_type: string;
	description: string | null;
	playbook_version: string;
	author_user_id: string | null;
	author_email: string | null;
	proposed_at: string;
	reviewed_by: string | null;
	/** `reviewed_by` resolved to an email, mirroring `author_email`. `null`
	 *  until the row has been reviewed. */
	approver_email: string | null;
	reviewed_at: string | null;
	review_note: string | null;
	revoked_at: string | null;
	content_hash: string;
	size_bytes: number;
	position_count: number;
	positions: OrgPlaybookPositionRead[];
}

export interface OrgPlaybookVersionsListResponse {
	versions: OrgPlaybookVersionAdminRead[];
}

/**
 * GET /api/v1/admin/org-playbooks — the review queue, optionally state-filtered.
 * Newest-proposed first. AdminUser-gated; ADR-F064 excludes the platform
 * operator (tenant-authored content) — 403 (the queue section hides).
 */
export async function listOrgPlaybookVersions(
	state?: OrgSkillVersionState
): Promise<OrgPlaybookVersionsListResponse> {
	const qs = state ? `?state=${encodeURIComponent(state)}` : '';
	return apiRequest<OrgPlaybookVersionsListResponse>(`/admin/org-playbooks${qs}`);
}

/**
 * POST /api/v1/admin/org-playbooks/{id}/approve — pins the immutable snapshot.
 * 409 unless the row is `proposed`.
 */
export async function approveOrgPlaybookVersion(id: string): Promise<OrgPlaybookVersionAdminRead> {
	return apiRequest<OrgPlaybookVersionAdminRead>(
		`/admin/org-playbooks/${encodeURIComponent(id)}/approve`,
		{ method: 'POST' }
	);
}

/**
 * POST /api/v1/admin/org-playbooks/{id}/reject — `note` rides the response's
 * `review_note`; 409 unless the row is `proposed`.
 */
export async function rejectOrgPlaybookVersion(
	id: string,
	note?: string
): Promise<OrgPlaybookVersionAdminRead> {
	return apiRequest<OrgPlaybookVersionAdminRead>(
		`/admin/org-playbooks/${encodeURIComponent(id)}/reject`,
		{ method: 'POST', body: { note: note && note.trim() !== '' ? note : undefined } }
	);
}

/**
 * POST /api/v1/admin/org-playbooks/{id}/revoke — 409 unless the row is `approved`.
 * Does NOT remove the matching Library row or practice-area bindings (ADR-F067
 * D3.8 fail-close) — they surface as unavailable until removed/replaced.
 */
export async function revokeOrgPlaybookVersion(id: string): Promise<OrgPlaybookVersionAdminRead> {
	return apiRequest<OrgPlaybookVersionAdminRead>(
		`/admin/org-playbooks/${encodeURIComponent(id)}/revoke`,
		{ method: 'POST' }
	);
}
