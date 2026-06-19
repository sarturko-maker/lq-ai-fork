/**
 * PRIV-9a — co-visible chat + ROPA register capture (LIVE, read-only).
 *
 * A Privacy matter with enough width now shows the conversation and the
 * deployment-global ROPA register SIDE BY SIDE (resizable) instead of the
 * one-at-a-time "Conversation | ROPA register" toggle; below the width budget
 * it falls back to that toggle. This spec drives the REAL seeded Privacy matter
 * and triggers NO agent run (read-only) — the run-lock + live-refresh + the
 * measured time-to-visible live in priv-9a-runlock.cy.ts.
 *
 * Headless Electron is 1280 wide, which (rail expanded) lands in the toggle
 * fallback; collapsing the rail clears the co-visible width budget — so the two
 * states are captured at the same viewport by toggling the rail.
 *
 * Run (live stack, headed for an honest light+dark capture):
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/priv-9a-covisible.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
const PRIVACY_MATTER = '47519e68-d764-4a3f-b96b-2d703c16229c';

function pinTheme(theme: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', theme);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(theme);
	});
	cy.get('html').should('have.class', theme);
}

describe('PRIV-9a — co-visible chat + register', { retries: { runMode: 2, openMode: 0 } }, () => {
	it('falls back to the toggle when narrow, shows both side by side when wide', () => {
		cy.viewport(1280, 850);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
		cy.visit(`/lq-ai?area=privacy&matter=${PRIVACY_MATTER}`);
		cy.get('[data-testid="lq-cockpit-conversation"]', { timeout: 30000 }).should('exist');

		// Rail expanded → the panel area is under the co-visible budget, so the
		// one-at-a-time toggle is the surface. Both the composer and the "ROPA
		// register" tab exist, but only one body shows at a time.
		cy.get('[data-testid="lq-ai-agents-composer"]', { timeout: 30000 }).should('be.visible');
		cy.contains('button', 'ROPA register').should('be.visible');
		// The register's programme dashboard is NOT co-shown in toggle mode.
		cy.get('[data-testid="lq-ropa-dashboard"]').should('not.exist');
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
			cy.wait(300);
			cy.screenshot(`priv-9a-toggle-${theme}`, { capture: 'viewport' });
		}
		pinTheme('light');

		// Collapse the rail → the panel clears the co-visible budget → chat AND
		// the register render at the same time, and the toggle tab is gone.
		cy.get('[data-testid="lq-cockpit-rail-toggle"]').click();
		cy.get('[data-testid="lq-ai-agents-composer"]', { timeout: 30000 }).should('be.visible');
		cy.get('[data-testid="lq-ropa-dashboard"]', { timeout: 30000 }).should('be.visible');
		cy.contains('button', 'ROPA register').should('not.exist'); // toggle tab retired
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
			cy.wait(300);
			cy.screenshot(`priv-9a-covisible-${theme}`, { capture: 'viewport' });
		}
	});
});
