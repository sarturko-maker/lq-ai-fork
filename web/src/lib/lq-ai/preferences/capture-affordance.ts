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

import { writable } from 'svelte/store';

export const CAPTURE_AFFORDANCE_STORAGE_KEY = 'lq_ai_capture_affordance_inline';
const DEFAULT_VALUE = true;

export function readCaptureAffordanceInline(): boolean {
	try {
		const raw = localStorage.getItem(CAPTURE_AFFORDANCE_STORAGE_KEY);
		if (raw === null) return DEFAULT_VALUE;
		// Strict parse: only the canonical 'true' / 'false' strings round-trip.
		// Any other value (corruption, manual edits, legacy keys) falls back to
		// the documented default (true) rather than silently coercing to false.
		if (raw === 'true') return true;
		if (raw === 'false') return false;
		return DEFAULT_VALUE;
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

// Reactive Svelte store wrapper. Initial value is hydrated from localStorage at
// module load so a fresh subscriber sees the persisted preference, not the raw
// default. Cross-tab `storage` events are NOT wired (out of scope; would
// require a window listener and lifecycle teardown).
const _store = writable<boolean>(readCaptureAffordanceInline());

export const captureAffordanceInline = {
	subscribe: _store.subscribe,
	/** Re-read from localStorage and broadcast. Call from a top-level layout if needed. */
	load(): void {
		_store.set(readCaptureAffordanceInline());
	},
	/** Persist + broadcast in one call. */
	setValue(v: boolean): void {
		writeCaptureAffordanceInline(v);
		_store.set(v);
	}
};
