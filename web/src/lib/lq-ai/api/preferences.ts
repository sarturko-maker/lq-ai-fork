/**
 * /api/v1/users/me/preferences — server-synced personalization toggles.
 *
 * The 5 fields are spec'd in frontend design §4.3 + PRD §3.2.1. Backend
 * extended the schema in migration 0019; all 5 fields are required in
 * the GET response, optional in the PATCH body.
 */
import { apiRequest } from './client';
import type { Preferences, PreferencesUpdate } from '../types';

export async function getPreferences(): Promise<Preferences> {
	return apiRequest<Preferences>('/users/me/preferences');
}

export async function patchPreferences(patch: PreferencesUpdate): Promise<Preferences> {
	return apiRequest<Preferences>('/users/me/preferences', { method: 'PATCH', body: patch });
}
