/**
 * Capture-affordance preference — controls where the inline
 * "📝 Capture as skill" button appears on AI messages.
 *
 * When `true` (default), the button shows next to thumbs on every AI
 * message. When `false`, it is demoted to the message's overflow (⋯)
 * menu so users who don't capture frequently get a quieter footer.
 *
 * Stored client-side in localStorage (not in the server-synced
 * Preferences contract) for the same reasons documented in
 * `autoEnhance.ts`:
 *   - The server `Preferences` schema is a strict 5-field contract
 *     (reasoning_visibility, featured_tools, workspace_layout,
 *     trust_pills, provenance_pills); arbitrary keys are not
 *     supported and adding a column requires an OpenAPI update +
 *     migration, which is out of scope for this UX-only toggle.
 *   - This is a per-device display preference; no audit/policy
 *     implications justify server-side storage.
 */

export const CAPTURE_AFFORDANCE_STORAGE_KEY = 'lq_ai_capture_affordance_inline';
const DEFAULT_VALUE = true;

export function readCaptureAffordanceInline(): boolean {
	try {
		const raw = localStorage.getItem(CAPTURE_AFFORDANCE_STORAGE_KEY);
		if (raw === null) return DEFAULT_VALUE;
		return raw === 'true';
	} catch {
		return DEFAULT_VALUE;
	}
}

export function writeCaptureAffordanceInline(value: boolean): void {
	try {
		localStorage.setItem(CAPTURE_AFFORDANCE_STORAGE_KEY, value ? 'true' : 'false');
	} catch {
		// best-effort; non-persistent fallback acceptable
	}
}
