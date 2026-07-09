/**
 * Practice-area API client — F1-S2 reads + F1-S3 config + SETUP-4a/4b admin CRUD
 * (ADR-F002/F004/F010/F062).
 *
 * `configured` drives the cockpit's inert-card semantics (unconfigured areas
 * are not enterable) and is DERIVED server-side from real config in S3.
 * `unit_label` is the unit-of-work noun the UI renders — data, not code
 * (ADR-F004). `profile_md`/`agent_config` are readable for transparency (an
 * agent instruction must be readable in the UI or the source).
 */
import { apiRequest } from './client';

/** One playbook bound to an area — join summary (SETUP-4b), not the full detail. */
export interface BoundPlaybook {
	id: string;
	name: string;
}

/** One knowledge collection bound to an area — join summary (B-3, ADR-F067 D1),
 *  mirrors `BoundPlaybook`. */
export interface BoundKnowledgeBase {
	id: string;
	name: string;
}

export interface PracticeArea {
	id: string;
	/** Stable machine key ('commercial', 'privacy', …) — cockpit URL state. */
	key: string;
	name: string;
	/** Unit-of-work noun: 'Matter' / 'Programme' / 'Deal'. */
	unit_label: string;
	/** F002 inert-card switch: only configured areas are enterable (derived). */
	configured: boolean;
	position: number;
	/** Area profile — folded into the agent's system prompt (F1-S3). */
	profile_md: string | null;
	/** Default minimum inference tier (1..5), combined with the matter floor. */
	default_tier_floor: number | null;
	/** Area default budget profile for new runs (SETUP-5a, ADR-F063).
	 *  null = no area default — inherits the deployment default / balanced. */
	default_budget_profile: 'economy' | 'balanced' | 'generous' | null;
	/** Declarative agent config (subagents, by-reference playbooks/MCPs). */
	agent_config: Record<string, unknown>;
	/** HITL-3 (ADR-F071): the area's stop-and-ask policy — `{tool_name: true}`
	 *  for each granted tool that pauses for the lawyer's go-ahead. `{}` = nothing
	 *  gated (the zero-config default). */
	hitl_policy: Record<string, boolean>;
	/** HITL-3 (ADR-F071): the area's gate-able domain tools (sorted) — the
	 *  stop-and-ask checklist; a read-only projection of the area's bound tool
	 *  groups, not stored state. */
	hitl_eligible_tools: string[];
	/** Filesystem-canonical skill names bound to the area. */
	bound_skills: string[];
	/** Bound tool-group keys, REGISTRY-CANONICAL order (ADR-F062 D4) — never
	 *  attach/DB-row order. */
	bound_tool_groups: string[];
	/** Bound (non-deleted) playbooks. */
	bound_playbooks: BoundPlaybook[];
	/** Bound (non-archived) knowledge collections (B-3, ADR-F067 D1). */
	bound_knowledge_bases: BoundKnowledgeBase[];
	created_at: string;
	updated_at: string;
}

export interface PracticeAreaListResponse {
	practice_areas: PracticeArea[];
}

/** GET /api/v1/practice-areas — curated list, position order. */
export async function listPracticeAreas(): Promise<PracticeAreaListResponse> {
	return apiRequest<PracticeAreaListResponse>('/practice-areas');
}

/** POST /api/v1/practice-areas body (admin, SETUP-4a). `key` is an anchored slug
 *  (`^[a-z][a-z0-9-]{1,62}[a-z0-9]$`); `tool_groups` are registry keys — an
 *  unknown one 404s. */
export interface PracticeAreaCreateBody {
	key: string;
	name: string;
	unit_label: string;
	profile_md?: string | null;
	default_tier_floor?: number | null;
	agent_config?: Record<string, unknown> | null;
	tool_groups?: string[];
}

/** PATCH /api/v1/practice-areas/{key} body (admin) — partial update; only the
 *  fields present are applied (exclude_unset server-side). */
export interface PracticeAreaUpdateBody {
	name?: string;
	unit_label?: string;
	profile_md?: string | null;
	default_tier_floor?: number | null;
	/** SETUP-5a (ADR-F063): key present with explicit `null` CLEARS the area
	 *  default (the area inherits the deployment default); key ABSENT leaves it
	 *  unchanged. Send null only when the admin actually changed it to Inherit. */
	default_budget_profile?: 'economy' | 'balanced' | 'generous' | null;
	agent_config?: Record<string, unknown> | null;
}

/** POST /api/v1/practice-areas — create a practice area (admin). 201; dup key 409;
 *  unknown tool-group 404; a `model`-bearing subagent 400 (ADR-F010). */
export async function createPracticeArea(body: PracticeAreaCreateBody): Promise<PracticeArea> {
	return apiRequest<PracticeArea>('/practice-areas', { method: 'POST', body });
}

/** PATCH /api/v1/practice-areas/{key} — configure an area (admin). */
export async function updatePracticeArea(
	key: string,
	body: PracticeAreaUpdateBody
): Promise<PracticeArea> {
	return apiRequest<PracticeArea>(`/practice-areas/${encodeURIComponent(key)}`, {
		method: 'PATCH',
		body
	});
}

/** PUT /api/v1/practice-areas/{key}/hitl-policy — replace the area's stop-and-ask
 *  policy (admin, HITL-3 / ADR-F071). `policy` is the COMPLETE desired map of gated
 *  tools; an unknown tool name → 400. Returns the updated area. */
export async function setHitlPolicy(
	key: string,
	policy: Record<string, boolean>
): Promise<PracticeArea> {
	return apiRequest<PracticeArea>(`/practice-areas/${encodeURIComponent(key)}/hitl-policy`, {
		method: 'PUT',
		body: { policy }
	});
}

/** DELETE /api/v1/practice-areas/{key} — 204; 409 (with `active_matter_count` in
 *  `details`) while a non-archived matter is filed under the area. */
export async function deletePracticeArea(key: string): Promise<void> {
	return apiRequest<void>(`/practice-areas/${encodeURIComponent(key)}`, { method: 'DELETE' });
}

/**
 * POST /api/v1/practice-areas/reorder — bulk reposition (admin, SETUP-4b). `keys`
 * must be EXACTLY a permutation of every existing area key (missing/extra/duplicate
 * → 422 — the caller should refetch on that error, since it means a stale client).
 */
export async function reorderPracticeAreas(keys: string[]): Promise<PracticeAreaListResponse> {
	return apiRequest<PracticeAreaListResponse>('/practice-areas/reorder', {
		method: 'POST',
		body: { keys }
	});
}

/** POST /api/v1/practice-areas/{key}/skills — attach a registry skill (admin).
 *  Unknown skill 404; re-attach 409. */
export async function attachSkill(key: string, skillName: string): Promise<void> {
	return apiRequest<void>(`/practice-areas/${encodeURIComponent(key)}/skills`, {
		method: 'POST',
		body: { skill_name: skillName }
	});
}

/** DELETE /api/v1/practice-areas/{key}/skills/{skill_name} — idempotent detach. */
export async function detachSkill(key: string, skillName: string): Promise<void> {
	return apiRequest<void>(
		`/practice-areas/${encodeURIComponent(key)}/skills/${encodeURIComponent(skillName)}`,
		{ method: 'DELETE' }
	);
}

/** POST /api/v1/practice-areas/{key}/playbooks — attach a playbook (admin, ADR-F054).
 *  Unknown/soft-deleted playbook 404; re-attach 409. */
export async function attachPlaybook(key: string, playbookId: string): Promise<void> {
	return apiRequest<void>(`/practice-areas/${encodeURIComponent(key)}/playbooks`, {
		method: 'POST',
		body: { playbook_id: playbookId }
	});
}

/** DELETE /api/v1/practice-areas/{key}/playbooks/{playbook_id} — idempotent detach. */
export async function detachPlaybook(key: string, playbookId: string): Promise<void> {
	return apiRequest<void>(
		`/practice-areas/${encodeURIComponent(key)}/playbooks/${encodeURIComponent(playbookId)}`,
		{ method: 'DELETE' }
	);
}

/** POST /api/v1/practice-areas/{key}/tool-groups — attach a registry tool group
 *  (admin, ADR-F062). Unknown group 404; re-attach 409. */
export async function attachToolGroup(key: string, groupKey: string): Promise<void> {
	return apiRequest<void>(`/practice-areas/${encodeURIComponent(key)}/tool-groups`, {
		method: 'POST',
		body: { group_key: groupKey }
	});
}

/** DELETE /api/v1/practice-areas/{key}/tool-groups/{group_key} — idempotent detach. */
export async function detachToolGroup(key: string, groupKey: string): Promise<void> {
	return apiRequest<void>(
		`/practice-areas/${encodeURIComponent(key)}/tool-groups/${encodeURIComponent(groupKey)}`,
		{ method: 'DELETE' }
	);
}

/** POST /api/v1/practice-areas/{key}/knowledge-bases — attach a knowledge collection
 *  (admin, B-3, ADR-F067 D1). Unknown/archived collection 404; not yet adopted into
 *  the Library 422 (ADR-F065 D4); re-attach 409. */
export async function attachKnowledgeBase(key: string, knowledgeBaseId: string): Promise<void> {
	return apiRequest<void>(`/practice-areas/${encodeURIComponent(key)}/knowledge-bases`, {
		method: 'POST',
		body: { knowledge_base_id: knowledgeBaseId }
	});
}

/** DELETE /api/v1/practice-areas/{key}/knowledge-bases/{kb_id} — idempotent detach. */
export async function detachKnowledgeBase(key: string, knowledgeBaseId: string): Promise<void> {
	return apiRequest<void>(
		`/practice-areas/${encodeURIComponent(key)}/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}`,
		{ method: 'DELETE' }
	);
}
