/**
 * Practice-area API client — F1-S2 (ADR-F002).
 *
 * Read-only in S2: rows are seeded by migration 0053 and curated by the
 * operator; the config/admin API is S3. `configured` drives the cockpit's
 * inert-card semantics (unconfigured areas are not enterable); `unit_label`
 * is the unit-of-work noun the UI renders — data, not code (ADR-F004).
 */
import { apiRequest } from './client';

export interface PracticeArea {
	id: string;
	/** Stable machine key ('commercial', 'privacy', …) — cockpit URL state. */
	key: string;
	name: string;
	/** Unit-of-work noun: 'Matter' / 'Programme' / 'Deal'. */
	unit_label: string;
	/** F002 inert-card switch: only configured areas are enterable. */
	configured: boolean;
	position: number;
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
