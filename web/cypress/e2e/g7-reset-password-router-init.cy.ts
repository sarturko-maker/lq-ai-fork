/**
 * G7 — /lq-ai/reset-password shares the identical direct-load router-init
 * hazard as accept-invite (same onMount → replaceState → scrub pattern; see
 * g7-accept-invite-router-init.cy.ts for the full root-cause writeup). Reset
 * links are also only ever opened by direct URL entry, so this page hit the
 * same permanently-blank-page bug.
 *
 * No live API stack required: the confirm form renders from the `?token=`
 * query param alone, no backend call until submit.
 */

/// <reference types="cypress" />

describe('G7 — reset-password direct load (router-init safety)', () => {
	it('renders the confirm form on a direct URL load and scrubs the token from the address bar', () => {
		let capturedError: string | null = null;
		cy.on('uncaught:exception', (err) => {
			capturedError = err.message;
			// eslint-disable-next-line no-console
			console.log('G7 captured uncaught exception:', err.message);
			return false;
		});

		cy.visit('/lq-ai/reset-password?token=fake-repro-token-456');

		cy.get('[data-testid="lq-reset-password-confirm-form"]', { timeout: 10000 })
			.should('be.visible')
			.then(() => {
				if (capturedError) {
					throw new Error(`Unexpected uncaught exception during mount: ${capturedError}`);
				}
			});

		cy.location('search').should('not.include', 'token=');
	});
});
