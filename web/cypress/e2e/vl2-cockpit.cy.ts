/**
 * F2-VL2 — cockpit re-skin capture (ADR-F013 §6/§7).
 *
 * The flagship re-skin: the cockpit landing (Hero launcher + bordered area
 * Card grid + StatusDot rollups + Recent-matters dot-status list) and the
 * re-skinned `--sidebar` rail (New-matter ink button + account footer),
 * captured against the direction-vercel target. Runs against the live dev
 * backend (real data, no stubs) so the evidence is honest. Headed for an
 * honest dark capture (headless lies about dark mode).
 *
 * Run:
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/vl2-cockpit.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
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

describe('F2-VL2 cockpit re-skin', { retries: { runMode: 2, openMode: 0 } }, () => {
	it('captures the re-skinned landing (light + dark, wide + narrow)', () => {
		login();
		cy.visit('/lq-ai');
		cy.get('[data-testid="lq-cockpit"]', { timeout: 30000 }).should('be.visible');
		cy.get('[data-testid="lq-cockpit-area-grid"]', { timeout: 30000 }).should('exist');
		cy.get('[data-testid="lq-cockpit-centered-entry"]', { timeout: 30000 }).should('be.visible');
		// The Hero materialises the text-display token — prove it rendered.
		cy.contains('h1', 'What are you working on?').should('be.visible');
		cy.wait(800);

		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			// Wide: rail pane + landing both visible.
			cy.viewport(1281, 950);
			cy.viewport(1280, 950);
			cy.wait(400);
			cy.screenshot(`vl2-cockpit-${theme}-wide`, { capture: 'viewport' });
			// Narrow: rail collapses to the drawer, landing goes full-width.
			cy.viewport(821, 950);
			cy.viewport(820, 950);
			cy.wait(400);
			cy.screenshot(`vl2-cockpit-${theme}-narrow`, { capture: 'viewport' });
		}
	});

	it('captures the re-skinned rail drawer at narrow (light + dark)', () => {
		login();
		cy.visit('/lq-ai');
		cy.get('[data-testid="lq-cockpit"]', { timeout: 30000 }).should('be.visible');
		cy.wait(600);

		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			cy.viewport(821, 950);
			cy.viewport(820, 950);
			cy.wait(300);
			// Open the off-canvas rail (the header toggle); capture the Vercel rail
			// — New-matter button, practice areas, unfiled bucket, account footer.
			cy.get('[data-testid="lq-cockpit-rail-toggle"]').click();
			cy.get('[data-testid="lq-cockpit-drawer"]', { timeout: 10000 }).should('be.visible');
			cy.get('[data-testid="lq-cockpit-new-matter"]').should('be.visible');
			cy.wait(400);
			cy.screenshot(`vl2-rail-drawer-${theme}-narrow`, { capture: 'viewport' });
			// Close it so the next theme iteration starts clean.
			cy.get('body').type('{esc}');
			cy.wait(200);
		}
	});
});
