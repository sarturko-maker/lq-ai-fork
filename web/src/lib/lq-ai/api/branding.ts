/**
 * Deployment-branding API — BRAND-1b (fork, ADR-F068).
 *
 * `GET /branding` is UNAUTHENTICATED by design: the login / accept-invite /
 * reset-password pages are branded surfaces consulted before any credentials
 * exist, so the read follows the bootstrap-status precedent
 * (`skipAuth: true, skipRefresh: true`). The write endpoints (PUT name +
 * palette, POST/DELETE logo) are admin-only server-side and use the normal
 * authenticated client path.
 */
import { apiRequest, LQ_AI_API_BASE_URL } from './client';

/** Wire shape of GET/PUT/POST responses (`api/app/api/branding.py`). */
export interface BrandingResponse {
	/** Empty string ⇒ the default brand. */
	product_name: string;
	/** `{"light": {token: "#RRGGBB"}, "dark": {...}}` over the closed
	 *  7-token allowlist; `{}` ⇒ no custom palette. */
	palette: Record<string, Record<string, string>>;
	/** Opaque cache-buster when a logo is set, else null. Never parsed —
	 *  only appended as `?v=` to the logo URL. */
	logo_version: number | null;
	updated_at: string | null;
}

export interface BrandingUpdateBody {
	product_name: string;
	palette: Record<string, Record<string, string>>;
}

/** Client-side pre-check mirror of the server's hard logo cap (413). */
export const LOGO_MAX_BYTES = 512 * 1024;

export async function getBranding(): Promise<BrandingResponse> {
	return apiRequest<BrandingResponse>('/branding', {
		skipAuth: true,
		skipRefresh: true
	});
}

export async function updateBranding(body: BrandingUpdateBody): Promise<BrandingResponse> {
	return apiRequest<BrandingResponse>('/branding', { method: 'PUT', body });
}

export async function uploadLogo(file: File): Promise<BrandingResponse> {
	const formData = new FormData();
	formData.append('file', file);
	return apiRequest<BrandingResponse>('/branding/logo', { method: 'POST', formData });
}

export async function deleteLogo(): Promise<void> {
	await apiRequest<void>('/branding/logo', { method: 'DELETE' });
}

/** Version-busted unauth logo URL (the endpoint serves the sniffed raster
 *  type with `immutable` caching — the `?v=` is what makes that safe). */
export function logoUrl(version: number): string {
	return `${LQ_AI_API_BASE_URL}/branding/logo?v=${encodeURIComponent(String(version))}`;
}
