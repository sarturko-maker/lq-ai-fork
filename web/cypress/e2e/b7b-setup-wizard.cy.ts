/**
 * B-7b — guided admin setup wizard (ADR-F067 D4).
 *
 * LIVE-AUTH screenshot walk of the wizard shell over the real profiles API
 * (like b4-org-playbooks, this needs the dev stack up; it is NOT part of the
 * deterministic CI suite, which is svelte-check + Vitest). It drives the
 * maintainer-facing flow far enough to capture each screen — it deliberately
 * does NOT click "Activate" (the full apply → member-runs-agent journey is the
 * maintainer's browser/real-model UAT).
 *
 * Run (live stack for auth):
 *   cd web && npx cypress run --browser chromium \
 *     --spec 'cypress/e2e/b7b-setup-wizard.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=<dev-admin-pw>
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';

describe('B-7b setup wizard', () => {
	it('walks profile picker → House Brief → review & activate', () => {
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());

		cy.visit('/lq-ai/admin/setup');
		cy.get('[data-testid="lq-admin-setup-page"]', { timeout: 20000 }).should('exist');
		cy.get('[data-testid="lq-setup-steprail"]').should('exist');
		cy.get('[data-testid="lq-setup-profile-commercial"]', { timeout: 20000 }).should('exist');
		cy.screenshot('b7b-01-profile-picker', { capture: 'viewport' });

		// pick Commercial → Next (House Brief) → Next (review)
		cy.get('[data-testid="lq-setup-profile-commercial"]').click();
		cy.get('[data-testid="lq-setup-next"]').click();
		cy.get('[data-testid="lq-setup-step-brief"]', { timeout: 15000 }).should('exist');
		cy.screenshot('b7b-02-house-brief', { capture: 'viewport' });

		cy.get('[data-testid="lq-setup-next"]').click();
		cy.get('[data-testid="lq-setup-step-review"]', { timeout: 15000 }).should('exist');
		// the activation summary only renders once the manifest detail has loaded
		cy.get('[data-testid="lq-setup-activation-summary"]', { timeout: 20000 }).should('exist');
		cy.get('[data-testid="lq-setup-activate"]').should('exist');
		cy.screenshot('b7b-03-review-activate', { capture: 'viewport' });
	});
});
