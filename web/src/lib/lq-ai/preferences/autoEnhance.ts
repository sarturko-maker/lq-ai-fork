/**
 * Auto-enhance preference — §7.1 Settings: "Auto-enhance prompts on send".
 *
 * Stored client-side in localStorage (not in the server-synced Preferences
 * contract) because:
 *   - Adding a column to the backend Preferences schema requires an OpenAPI
 *     update + migration; this toggle is a UX preference that can live
 *     per-device without affecting server-side audit/policy.
 *   - The send-side wiring (preview-and-confirm before send when enabled)
 *     is queued for v1.1+; this module exposes the read/write surface so
 *     the toggle UI ships now and the consumer can adopt it without churn.
 */

export const AUTO_ENHANCE_STORAGE_KEY = 'lq_ai_composer_auto_enhance';

export function readAutoEnhance(): boolean {
	try {
		return localStorage.getItem(AUTO_ENHANCE_STORAGE_KEY) === 'true';
	} catch {
		return false;
	}
}

export function writeAutoEnhance(value: boolean): void {
	try {
		localStorage.setItem(AUTO_ENHANCE_STORAGE_KEY, value ? 'true' : 'false');
	} catch {
		// best-effort; non-persistent fallback acceptable
	}
}
