/**
 * /api/v1/saved-prompts — per-user saved prompt CRUD (D7 / DE-013).
 *
 * Per PRD §9 DE-013, saved prompts are a lighter-weight alternative
 * to skills for personal text reuse. The backend scopes everything to
 * the calling user; cross-user reads/updates/deletes 404, so this
 * client doesn't accept a user id parameter.
 */
import { apiRequest } from './client';
import type { SavedPrompt, SavedPromptCreate, SavedPromptUpdate } from '../types';

/** GET /api/v1/saved-prompts — caller's own prompts, newest first. */
export async function listSavedPrompts(): Promise<SavedPrompt[]> {
	return apiRequest<SavedPrompt[]>('/saved-prompts');
}

/** POST /api/v1/saved-prompts — create + return the new row. */
export async function createSavedPrompt(body: SavedPromptCreate): Promise<SavedPrompt> {
	return apiRequest<SavedPrompt>('/saved-prompts', { method: 'POST', body });
}

/** GET /api/v1/saved-prompts/{id} — owner-only fetch. */
export async function getSavedPrompt(id: string): Promise<SavedPrompt> {
	return apiRequest<SavedPrompt>(`/saved-prompts/${encodeURIComponent(id)}`);
}

/** PATCH /api/v1/saved-prompts/{id} — partial update; only supplied keys touch the row. */
export async function updateSavedPrompt(id: string, body: SavedPromptUpdate): Promise<SavedPrompt> {
	return apiRequest<SavedPrompt>(`/saved-prompts/${encodeURIComponent(id)}`, {
		method: 'PATCH',
		body
	});
}

/** DELETE /api/v1/saved-prompts/{id} — owner-only delete (204). */
export async function deleteSavedPrompt(id: string): Promise<void> {
	await apiRequest<void>(`/saved-prompts/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
