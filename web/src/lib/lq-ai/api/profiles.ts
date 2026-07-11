/**
 * Agent-profile API client — the guided setup wizard's data layer (B-7b,
 * ADR-F067 D4). Thin wrapper over `api/app/api/profiles.py` (shipped in B-7a).
 *
 * A **profile** is a shipped, declarative bundle describing what a practice
 * area is by default (doctrine, unit vocabulary, tier/budget defaults, skill +
 * tool-group bindings, sub-agent roster, HITL defaults). The admin materialises
 * one onto a real area via `applyProfile` — a single all-or-nothing transaction
 * that create/patches the area AND adopts the matching Library entries (the G13
 * fix: bindings alone are inert until adopted).
 *
 * All three endpoints are AdminUser-gated server-side; `apply` additionally
 * fences the platform operator (403, ADR-F064). The client issues the normal
 * authenticated request and lets those statuses surface via the standard error
 * path (`describeMutationError`).
 */
import { apiRequest } from './client';

/** One profile in the wizard picker (`GET /profiles`). Mirrors `ProfileSummary`. */
export interface ProfileSummary {
	name: string;
	kind: 'area' | 'blank';
	display_name: string;
	description: string;
	/** The area key an `area` profile targets; null for `blank`. */
	area_key: string | null;
	/** The unit-of-work noun ('Matter' / 'Programme' / …); null for `blank`. */
	unit_label: string | null;
	skill_count: number;
	tool_group_count: number;
	subagent_count: number;
}

export interface ProfileListResponse {
	profiles: ProfileSummary[];
}

/** A profile's full manifest for the review screen (`GET /profiles/{name}`). Mirrors `ProfileDetail`. */
export interface ProfileDetail extends ProfileSummary {
	/** The area doctrine (`profile_md`); null for `blank`. */
	doctrine: string | null;
	default_tier_floor: number | null;
	default_budget_profile: string | null;
	skills: string[];
	tool_groups: string[];
	/** Declarative sub-agent roster (`{ subagents: [...] }`). */
	agent_config: Record<string, unknown>;
	/** HITL defaults (`{ tool_name: true }`). */
	hitl: Record<string, boolean>;
}

/**
 * Body for `POST /profiles/{name}/apply`.
 *
 * For an `area` profile the identity comes from the manifest, so all three
 * fields must be OMITTED (send `{}`) — sending any is a 422. For the `blank`
 * profile all three are REQUIRED (the admin names the new area).
 */
export interface ProfileApplyRequest {
	target_key?: string;
	name?: string;
	unit_label?: string;
}

/** What apply materialised — counts/keys only (audit-contract shape). Mirrors `ProfileApplyResult`. */
export interface ProfileApplyResult {
	profile_name: string;
	target_key: string;
	/** True when a new area row was inserted (a blank area, or an area profile
	 *  onto a missing area); false when an existing area was activated/overwritten
	 *  — the fresh-org norm, since the seeded areas already exist. */
	area_created: boolean;
	/** Newly-adopted Library keys, by kind (`{ skill: [...], tool: [...] }`). */
	adopted: Record<string, string[]>;
	/** Newly-written area bindings, by kind (`{ skill: n, tool: n }`). */
	bindings_written: Record<string, number>;
	roster_subagents: number;
	hitl_tools: number;
	/** Manifest-owned scalar fields the overwrite changed on an existing area —
	 *  field NAMES only. `[]` on a fresh create. */
	changed_fields: string[];
}

/** GET /api/v1/profiles — the shipped profile catalog (admin, wizard picker). */
export async function listProfiles(): Promise<ProfileListResponse> {
	return apiRequest<ProfileListResponse>('/profiles');
}

/** GET /api/v1/profiles/{name} — one profile's full manifest (admin, review screen). 404 if unknown. */
export async function getProfile(name: string): Promise<ProfileDetail> {
	return apiRequest<ProfileDetail>(`/profiles/${encodeURIComponent(name)}`);
}

/**
 * POST /api/v1/profiles/{name}/apply — materialise a profile onto a real area
 * (admin; operator-fenced). ONE all-or-nothing transaction: create/patch area +
 * adopt Library + bind skills/tools. Idempotent (re-apply adds nothing new).
 *
 * Errors surface via the standard path: 403 (operator), 404 (unknown profile /
 * drifted tool group), 409 (blank onto an existing key), 422 (an area profile
 * sent identity fields, or a blank missing them, or a drifted skill binding).
 */
export async function applyProfile(
	name: string,
	body: ProfileApplyRequest = {}
): Promise<ProfileApplyResult> {
	return apiRequest<ProfileApplyResult>(`/profiles/${encodeURIComponent(name)}/apply`, {
		method: 'POST',
		body
	});
}
