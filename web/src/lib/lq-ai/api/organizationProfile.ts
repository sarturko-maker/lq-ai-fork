/**
 * Organization Profile API client — the House Brief memory tier (B-1,
 * ADR-F049). Thin wrapper over `api/app/api/organization_profile.py`.
 *
 * `GET` is readable by any authenticated user: the House Brief is one of
 * the four read-only DATA tiers injected into every agent run, and per the
 * transparency principle (CLAUDE.md) every user is entitled to see what's
 * shaping their output. `PUT` is admin-only server-side (`AdminUser`
 * dependency) — the client just issues the normal authenticated request and
 * lets a 403 surface via the standard error path.
 */
import { apiRequest } from './client';

/** Wire shape of GET/PUT responses (`OrganizationProfileResponse`). */
export interface OrganizationProfileResponse {
	/** Empty string ⇒ no House Brief set yet (fresh org). */
	content_md: string;
	updated_at: string | null;
	/** Stringified id of the admin who last saved it, or null if never set. */
	updated_by: string | null;
}

export interface OrganizationProfileUpdateBody {
	/** Full Markdown body. Server enforces 0..200,000 chars — over the cap
	 *  is a 422, matched client-side by {@link HOUSE_BRIEF_MAX_CHARS}. */
	content_md: string;
}

export async function getOrganizationProfile(): Promise<OrganizationProfileResponse> {
	return apiRequest<OrganizationProfileResponse>('/organization-profile');
}

export async function updateOrganizationProfile(
	body: OrganizationProfileUpdateBody
): Promise<OrganizationProfileResponse> {
	return apiRequest<OrganizationProfileResponse>('/organization-profile', {
		method: 'PUT',
		body
	});
}
