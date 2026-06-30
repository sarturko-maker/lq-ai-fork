/**
 * /api/v1/matters/{id}/capabilities — the capability panel (ADR-F054).
 *
 * GET returns the matter's available capabilities (Playbooks / Skills / Tools, +
 * the disabled MCP placeholder) with each one's resolved on/off state; PUT writes
 * the lawyer's sparse toggles. Owner-scoped on the server (404, never 403, on a
 * missing / cross-user / archived matter). The run composition reads the same
 * toggles, so the panel reflects exactly what the agent gets.
 */
import type { CapabilityInventory, CapabilityToggleInput } from '../types';
import { apiRequest } from './client';

/** GET /api/v1/matters/{id}/capabilities — the inventory + resolved enabled state. */
export async function getMatterCapabilities(projectId: string): Promise<CapabilityInventory> {
	return apiRequest<CapabilityInventory>(
		`/matters/${encodeURIComponent(projectId)}/capabilities`
	);
}

/**
 * PATCH /api/v1/matters/{id}/capabilities — set per-matter capability toggles.
 * Sends only the changed toggles (sparse); the server rejects (422) any toggle for
 * an unknown / non-toggleable / unbound capability. Returns the resolved inventory.
 * (PATCH, not PUT — the codebase convention; the api CORS allow-list has no PUT.)
 */
export async function updateMatterCapabilities(
	projectId: string,
	toggles: CapabilityToggleInput[]
): Promise<CapabilityInventory> {
	return apiRequest<CapabilityInventory>(
		`/matters/${encodeURIComponent(projectId)}/capabilities`,
		{ method: 'PATCH', body: { toggles } }
	);
}
