/**
 * /api/v1/enhance-prompt — Enhance Prompt skill client.
 *
 * POST /enhance-prompt  → expand a raw prompt via the skill.
 * PATCH /enhance-prompt/{id}  → record the user's outcome action for telemetry.
 *
 * Per the OpenAPI sketch and Task T6 spec, the PATCH takes a boolean pair
 * { used, edited_before_use } rather than a string enum.
 */
import { apiRequest } from './client';
import type {
	EnhancePromptRequest,
	EnhancePromptResponse,
	EnhancePromptOutcomeUpdate
} from '../types';

/** POST /api/v1/enhance-prompt — invoke the skill and return the expansion preview. */
export async function enhance(req: EnhancePromptRequest): Promise<EnhancePromptResponse> {
	return apiRequest<EnhancePromptResponse>('/enhance-prompt', {
		method: 'POST',
		body: req
	});
}

/**
 * PATCH /api/v1/enhance-prompt/{interactionId} — record what the user did with
 * the expansion preview. Idempotent; a no-op PATCH returns 200 without writing.
 *
 * UX action → outcome mapping:
 *   Use enhanced   → { used: true,  edited_before_use: false }
 *   Edit enhanced  → { used: true,  edited_before_use: true  }
 *   Keep original  → { used: false }
 *   Dismiss (X)    → { used: false }
 */
export async function recordOutcome(
	interactionId: string,
	outcome: EnhancePromptOutcomeUpdate
): Promise<void> {
	await apiRequest<EnhancePromptResponse>(
		`/enhance-prompt/${encodeURIComponent(interactionId)}`,
		{ method: 'PATCH', body: outcome }
	);
}
