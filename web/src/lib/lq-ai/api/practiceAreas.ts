/**
 * Practice-area API client — F1-S2 reads + F1-S3 config (ADR-F002/F004/F010).
 *
 * `configured` drives the cockpit's inert-card semantics (unconfigured areas
 * are not enterable) and is DERIVED server-side from real config in S3.
 * `unit_label` is the unit-of-work noun the UI renders — data, not code
 * (ADR-F004). `profile_md`/`agent_config` are readable for transparency (an
 * agent instruction must be readable in the UI or the source).
 */
import { apiRequest } from './client';

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
	/** Declarative agent config (subagents, by-reference playbooks/MCPs). */
	agent_config: Record<string, unknown>;
	/** Filesystem-canonical skill names bound to the area. */
	bound_skills: string[];
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
