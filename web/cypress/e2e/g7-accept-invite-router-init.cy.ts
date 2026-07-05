/**
 * G7 — /lq-ai/accept-invite rendered a permanently blank page on a direct URL
 * load (found live in the ONBOARD-0 walkthrough; invite links are ONLY ever
 * opened by direct URL entry, so this hit every real invitee).
 *
 * Root cause: onMount called SvelteKit's `replaceState()` (from
 * `$app/navigation`) to scrub the single-use token from the address bar (the
 * "F7" scrub) before the router had finished initializing on a full/direct
 * page load. `replaceState` throws in that window ("Cannot call
 * replaceState(...) before router is initialized"), which aborted onMount
 * before `mounted = true` was reached — so `{#if !mounted}` rendered nothing,
 * forever. In-app navigation never hits this (router already initialized),
 * which is why it escaped review.
 *
 * This spec uses `cy.visit` — a real direct/full page load — rather than
 * client-side navigation, so it actually exercises the router-not-yet-ready
 * window the bug lived in. No live API stack required: the page does not
 * call the backend until submit.
 */

/// <reference types="cypress" />

describe('G7 — accept-invite direct load (router-init safety)', () => {
	it('renders the invite form on a direct URL load and scrubs the token from the address bar', () => {
		let capturedError: string | null = null;
		cy.on('uncaught:exception', (err) => {
			capturedError = err.message;
			// eslint-disable-next-line no-console
			console.log('G7 captured uncaught exception:', err.message);
			// Don't let a pre-fix throw abort the whole spec run — we want the
			// element-visibility assertion below to produce the failure evidence.
			return false;
		});

		cy.visit('/lq-ai/accept-invite?token=fake-repro-token-123');

		cy.get('[data-testid="lq-accept-invite-form"]', { timeout: 10000 })
			.should('be.visible')
			.then(() => {
				if (capturedError) {
					throw new Error(`Unexpected uncaught exception during mount: ${capturedError}`);
				}
			});

		// F7 — the single-use token must be scrubbed from the address bar shortly
		// after load; component state keeps it, browser history/autocomplete must not.
		cy.location('search').should('not.include', 'token=');
	});
});
