/**
 * PRIV-6c — privacy data-flow / lineage view capture.
 *
 * The ROPA surface of a Privacy matter has a "Data flow" tab: an interactive
 * node-link map of the deployment-global register (systems feed activities,
 * which disclose to recipients and transfer to third countries — restricted
 * transfers flagged). Runs against the LIVE dev backend (the seeded
 * "Programme — GDPR / ROPA" matter), so the graph is the real register
 * projection. Headed for an honest light+dark capture.
 *
 * Run:
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/priv-6c-data-flow.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
const PRIVACY_MATTER = '47519e68-d764-4a3f-b96b-2d703c16229c';

function login() {
	cy.session('lq-admin', () => {
		cy.visit('/lq-ai/login');
		cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
		cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!');
		cy.get('button[type="submit"]').click();
		cy.url({ timeout: 30000 }).should('not.include', '/login');
	});
}

function pinTheme(theme: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', theme);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(theme);
	});
	cy.get('html').should('have.class', theme);
}

// Re-select the Data flow tab + wait for the canvas to draw. The cockpit's
// responsive layout remounts the register when the viewport crosses a
// breakpoint (resetting the tab to its 'overview' default), so every capture at
// a new viewport/theme re-selects the tab first.
function showDataFlow() {
	cy.contains('[role="tab"]', 'Data flow', { timeout: 30000 }).should('be.visible').click();
	cy.get('[data-testid="lq-ropa-dataflow"] .lqf-node', { timeout: 30000 }).should('exist');
}

describe('PRIV-6c data-flow view', { retries: { runMode: 2, openMode: 0 } }, () => {
	it('the ROPA Data flow tab renders the live lineage graph', () => {
		login();
		cy.visit(`/lq-ai?area=privacy&matter=${PRIVACY_MATTER}`);

		// A Privacy matter exposes the Conversation | ROPA register toggle.
		cy.contains('button', 'ROPA register', { timeout: 30000 }).should('be.visible').click();

		// Switch to the Data flow tab → the interactive graph renders, live.
		showDataFlow();
		cy.contains('[data-testid="lq-ropa-dataflow"]', 'Restricted transfer').should('be.visible');

		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			cy.viewport(1281, 950);
			cy.viewport(1280, 950);
			cy.wait(300);
			showDataFlow();
			cy.wait(500);
			cy.screenshot(`priv-6c-dataflow-${theme}-wide`, { capture: 'viewport' });
			cy.viewport(821, 950);
			cy.viewport(820, 950);
			cy.wait(300);
			showDataFlow();
			cy.wait(500);
			cy.screenshot(`priv-6c-dataflow-${theme}-narrow`, { capture: 'viewport' });
		}
	});
});
