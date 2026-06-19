/**
 * PRIV-6b — privacy programme dashboard capture.
 *
 * The ROPA surface of a Privacy matter now opens on the Overview tab: a
 * read-only programme dashboard (totals, lawful-basis / controller-role /
 * DPA-status breakdowns, special-category & restricted-transfer counts, and
 * "needs attention" gaps) over the deployment-global register. Runs against the
 * LIVE dev backend (the seeded "Programme — GDPR / ROPA" matter), so the numbers
 * are the real register aggregate. Headed for an honest light+dark capture.
 *
 * Run:
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/priv-6b-programme-dashboard.cy.ts' \
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

describe('PRIV-6b programme dashboard', { retries: { runMode: 2, openMode: 0 } }, () => {
	it('the ROPA Overview tab renders the live programme dashboard', () => {
		login();
		cy.visit(`/lq-ai?area=privacy&matter=${PRIVACY_MATTER}`);

		// A Privacy matter exposes the Conversation | ROPA register toggle.
		cy.contains('button', 'ROPA register', { timeout: 30000 }).should('be.visible').click();

		// Overview is the default tab → the programme dashboard renders, live.
		cy.get('[data-testid="lq-ropa-dashboard"]', { timeout: 30000 }).should('be.visible');
		cy.contains('[data-testid="lq-ropa-dashboard"]', 'Processing activities').should('be.visible');
		cy.contains('[data-testid="lq-ropa-dashboard"]', 'Needs attention').should('be.visible');
		cy.wait(500);

		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			cy.viewport(1281, 950);
			cy.viewport(1280, 950);
			cy.wait(300);
			cy.screenshot(`priv-6b-overview-${theme}-wide`, { capture: 'viewport' });
			cy.viewport(821, 950);
			cy.viewport(820, 950);
			cy.wait(300);
			cy.screenshot(`priv-6b-overview-${theme}-narrow`, { capture: 'viewport' });
		}
	});
});
