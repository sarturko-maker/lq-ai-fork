/**
 * Unit tests for the RefusalMessageBubble logic helpers.
 *
 * Mirrors the AttachKBModal / NewMatterModal pattern: helpers are exported
 * from `<script context="module">` and exercised here. The Svelte template
 * itself is glue — it composes these helpers and wires the three action
 * callbacks. DOM-rendering integration of the refusal bubble is covered
 * via Cypress in T21.
 */
import { describe, expect, it } from 'vitest';
import {
	refusalHeading,
	refusalBody,
	showOverrideButton
} from '../components/RefusalMessageBubble.svelte';

describe('RefusalMessageBubble helpers', () => {
	it('refusalHeading substitutes the enforced tier', () => {
		expect(refusalHeading('privileged')).toBe('Refused at privileged-floor');
		expect(refusalHeading('strict')).toBe('Refused at strict-floor');
	});

	it('refusalBody substitutes both requested and enforced tiers', () => {
		const body = refusalBody('standard', 'privileged');
		expect(body).toContain('standard tier provider');
		expect(body).toContain('privileged-floor');
		// Spec §7.4 framing — "refused to keep your work in privileged-only providers"
		expect(body).toContain('privileged-only providers');
	});

	it('showOverrideButton returns true only for the operator (SETUP-3b fence)', () => {
		// POST /inference/override-tier-floor is operator-fenced (ADR-F061 D4);
		// an org-admin's click would only earn a 403, so the button hides.
		expect(showOverrideButton('operator')).toBe(true);
		expect(showOverrideButton('admin')).toBe(false);
		expect(showOverrideButton('member')).toBe(false);
		expect(showOverrideButton('viewer')).toBe(false);
	});
});
