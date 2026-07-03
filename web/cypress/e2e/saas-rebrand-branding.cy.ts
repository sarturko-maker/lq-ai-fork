/**
 * SAAS-rebrand — pins the "LQ.AI Oscar Edition" product-name surfaces
 * (ADR-F058 rebrand-execution addendum; plans/SAAS-REBRAND-oscar-edition.md).
 *
 * Asserts the three always-visible brand surfaces (shell <title>, cockpit
 * header wordmark, DualBrandingFooter) plus one per-page title as the
 * pattern representative. Deliberately does NOT assert running-prose
 * mentions — bare "LQ.AI" is the retained short mark there by policy.
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-smoke-test-Pw1!';

describe('SAAS-rebrand — LQ.AI Oscar Edition brand surfaces', () => {
	it('pre-auth: login page carries the shell title + footer brand line', () => {
		cy.visit('/lq-ai/login');
		// app.html fallback <title> (no svelte:head on the login page).
		cy.title().should('eq', 'LQ.AI Oscar Edition');
		cy.get('[data-testid="lq-ai-dual-branding-footer"]')
			.should('contain.text', 'LQ.AI Oscar Edition')
			.and('contain.text', 'Open-Source Legal AI');
		cy.screenshot('rebrand-login-footer', { capture: 'viewport' });
	});

	it('post-auth: cockpit header wordmark shows the Oscar Edition lockup', () => {
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
		// The brand anchor renders "LQ.AI Oscar Edition" across its spans.
		cy.contains('a', 'Oscar Edition').should('be.visible');
		cy.screenshot('rebrand-cockpit-header', { capture: 'viewport' });
	});

	it('per-page titles take the full product-name suffix (representative)', () => {
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
		cy.visit('/lq-ai/playbooks');
		cy.title().should('eq', 'Playbooks · LQ.AI Oscar Edition');
	});
});
