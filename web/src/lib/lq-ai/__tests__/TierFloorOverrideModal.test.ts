/**
 * Unit tests for the TierFloorOverrideModal logic helpers.
 *
 * Mirrors the RefusalMessageBubble / AttachKBModal pattern: helpers are
 * exported from `<script context="module">` and exercised here. The Svelte
 * template itself is glue — it wires the reason textarea to validateReason,
 * the live counter to reasonCounterText, and submission to T9's
 * inferenceOverride.ts. DOM-rendering integration is covered via Cypress
 * in T21.
 */
import { describe, expect, it } from 'vitest';
import {
	validateReason,
	reasonCounterText
} from '../components/TierFloorOverrideModal.svelte';

describe('TierFloorOverrideModal helpers', () => {
	it('validateReason rejects strings shorter than 10 chars', () => {
		const r = validateReason('short');
		expect(r.valid).toBe(false);
		expect(r.error).toMatch(/at least 10/);
	});

	it('validateReason rejects strings longer than 500 chars', () => {
		const tooLong = 'x'.repeat(501);
		const r = validateReason(tooLong);
		expect(r.valid).toBe(false);
		expect(r.error).toMatch(/at most 500/);
	});

	it('validateReason accepts strings of valid length (10..500 inclusive)', () => {
		expect(validateReason('Urgent client request — partner risk-accepted').valid).toBe(true);
		// Boundary: exactly 500 chars passes
		expect(validateReason('x'.repeat(500)).valid).toBe(true);
		// Boundary: exactly 10 chars passes
		expect(validateReason('x'.repeat(10)).valid).toBe(true);
	});

	it('reasonCounterText formats as N/500', () => {
		expect(reasonCounterText('')).toBe('0/500');
		expect(reasonCounterText('hello')).toBe('5/500');
		expect(reasonCounterText('x'.repeat(500))).toBe('500/500');
	});
});
