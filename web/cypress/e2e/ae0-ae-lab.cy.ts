/**
 * AE0 — AI Elements vendoring foundation (ADR-F011).
 *
 * Smoke-proves the vendored AI Elements components (Loader, Suggestion/
 * Suggestions) compile + render + behave in the REAL prod bundle, via the
 * internal lab at `/lq-ai/_ae-lab` (unadvertised, auth-gated, links nowhere —
 * changes no live surface). This is the AE0 proof artifact (the slice is
 * screenshot-exempt; the lab is dev scratch, not a user surface).
 *
 * The lab makes no API calls of its own — only the auth gate hits the backend,
 * which `login()` satisfies.
 *
 * Run (live stack, headed to match the R-series convention):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ae0-ae-lab.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
function login() {
	cy.visit('/lq-ai/login');
	cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
	cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!');
	cy.get('button[type="submit"]').click();
	cy.url({ timeout: 15000 }).should('not.include', '/login');
}

describe('AE0 — vendored AI Elements lab', () => {
	beforeEach(() => {
		login();
		cy.visit('/lq-ai/_ae-lab');
		cy.get('[data-testid="ae-lab-banner"]', { timeout: 15000 }).should('be.visible');
	});

	it('renders the Loader (vendored inline SVG spinner) at every size', () => {
		// Three <Loader> instances → three spinner SVGs, each animate-spin.
		cy.get('[data-testid="ae-lab-loader"] svg').should('have.length', 3);
		cy.get('[data-testid="ae-lab-loader"] .animate-spin').should('have.length', 3);
	});

	it('renders Suggestion chips and fires onclick with the suggestion text', () => {
		cy.get('[data-testid="ae-lab-suggestions"] button').should('have.length.greaterThan', 1);
		cy.get('[data-testid="ae-lab-pick-count"]').should('have.text', '0');

		cy.get('[data-testid="ae-lab-suggestions"] button').contains('Flag unusual indemnities').click();

		cy.get('[data-testid="ae-lab-pick-count"]').should('have.text', '1');
		cy.get('[data-testid="ae-lab-last-pick"]').should('have.text', 'Flag unusual indemnities');

		// Second pick increments and updates the last value.
		cy.get('[data-testid="ae-lab-suggestions"] button').contains('What are the key dates?').click();
		cy.get('[data-testid="ae-lab-pick-count"]').should('have.text', '2');
		cy.get('[data-testid="ae-lab-last-pick"]').should('have.text', 'What are the key dates?');
	});

	it('toggles the theme class so the components are exercised in dark + light', () => {
		cy.get('html').then(($html) => {
			const startedDark = $html.hasClass('dark');
			cy.get('[data-testid="ae-lab-theme-toggle"]').click();
			cy.get('html').should($el => {
				expect($el.hasClass('dark')).to.equal(!startedDark);
			});
			// Components still rendered after the theme flip.
			cy.get('[data-testid="ae-lab-loader"] svg').should('have.length', 3);
		});
	});
});
