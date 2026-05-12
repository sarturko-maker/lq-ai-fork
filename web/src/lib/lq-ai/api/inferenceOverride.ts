/**
 * /api/v1/inference/override-tier-floor — admin tier-floor override helper.
 *
 * Wraps the T4 backend endpoint. Caller passes the id of a `kind='refusal'`
 * message and a free-text reason; backend re-runs the immediately preceding
 * `kind='user'` message with `tier_floor=None`, persists a new `kind='ai'`
 * `Message`, and writes an `audit_log` row. Admin-only at M1 (per-user
 * `override_tier_floor` capability deferred to v1.1+).
 *
 * Uses the shared `apiRequest` helper for auth header attachment, refresh-
 * on-401, and structured error translation. Mirrors the house pattern from
 * `projectKnowledgeBases.ts`.
 */
import { apiRequest } from './client';
import type { Message } from '../types';

/**
 * Response shape for the override endpoint.
 *
 * `routing_log_id` is nullable: the gateway-mocked code paths in T4's
 * integration tests do not write an `inference_routing_log` row, so the
 * backend hands back `null` in those cases. Real provider traffic always
 * populates it.
 */
export interface OverrideResponse {
	ai_message: Message;
	routing_log_id: string | null;
}

/**
 * POST /api/v1/inference/override-tier-floor — admin re-run of a refused
 * inference with the tier floor lifted. `reason` must be 10–500 chars
 * (enforced server-side; this client doesn't pre-validate).
 *
 * Throws `LQAIApiError` on non-2xx (e.g. 403 if caller is not an admin,
 * 404 if `messageId` doesn't resolve to a refusal row, 422/400 if
 * `reason` fails server-side validation).
 */
export async function overrideTierFloor(
	messageId: string,
	reason: string
): Promise<OverrideResponse> {
	return apiRequest<OverrideResponse>('/inference/override-tier-floor', {
		method: 'POST',
		body: { message_id: messageId, reason }
	});
}
