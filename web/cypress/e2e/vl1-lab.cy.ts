/**
 * F2-VL1 (ADR-F013) — capture the _vl-lab proof surface.
 *
 * The lab (`/lq-ai/_vl-lab`) composes every VL1 primitive (AppShell + Hero +
 * CardGrid/Card + StatusDot + Inline + the recoloured Button) into the
 * `direction-vercel` cockpit target + an isolated gallery. Auth-gated, served
 * by the prod bundle on :3000 → proves the primitives render on the VL0 tokens.
 * Headed (electron) for honest dark capture.
 *
 * Run:
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/vl1-lab.cy.ts' \
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

function shoot(name: string) {
	cy.viewport(1281, 980);
	cy.viewport(1280, 980);
	cy.wait(400);
	cy.screenshot(`vl1-${name}-wide`, { capture: 'viewport' });
	cy.viewport(821, 980);
	cy.viewport(820, 980);
	cy.wait(400);
	cy.screenshot(`vl1-${name}-narrow`, { capture: 'viewport' });
}

describe('F2-VL1 lab capture', { retries: { runMode: 2, openMode: 0 } }, () => {
	it('captures the primitives proof (light + dark, wide + narrow)', () => {
		login();
		cy.visit('/lq-ai/_vl-lab');
		cy.get('[data-testid="vl-lab"]', { timeout: 30000 }).should('be.visible');
		// The Hero's text-display title must render (proves the VL0 type token).
		cy.contains('h1', 'What are you working on?', { timeout: 30000 }).should('be.visible');
		cy.wait(600);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`lab-${theme}`);
		}
	});
});
