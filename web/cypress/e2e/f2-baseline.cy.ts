/**
 * F2 — minimalist pass: before/after capture (ADR-F012).
 *
 * Captures the two surface families F2 changes most: the cockpit landing
 * (`/lq-ai` — the centered-entry + AreaGrid target) and a legacy `(tools)`
 * surface (`/lq-ai/skills` — shows the TopTabBar + AmbientTrustChrome + footer
 * chrome that F2-M2/M3 calm). Runs against the live dev backend (real data, no
 * stubs) so the baseline is honest. PHASE selects the filename (before|after);
 * M0 captures PHASE=before on the pre-F2 bundle.
 *
 * Run (live stack, headed for honest dark capture):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/f2-baseline.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!,PHASE=before
 */
const PHASE = () => (Cypress.env('PHASE') as string) || 'before';

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
	cy.viewport(1281, 900);
	cy.viewport(1280, 900);
	cy.wait(400);
	cy.screenshot(`f2-${PHASE()}-${name}-wide`, { capture: 'viewport' });
	cy.viewport(821, 900);
	cy.viewport(820, 900);
	cy.wait(400);
	cy.screenshot(`f2-${PHASE()}-${name}-narrow`, { capture: 'viewport' });
}

describe('F2 baseline capture', { retries: { runMode: 2, openMode: 0 } }, () => {
	it('captures the cockpit landing (light + dark, wide + narrow)', () => {
		login();
		cy.visit('/lq-ai');
		cy.get('[data-testid="lq-cockpit"]', { timeout: 30000 }).should('be.visible');
		cy.get('[data-testid="lq-cockpit-area-grid"]', { timeout: 30000 }).should('exist');
		// F2-M4: the centered intent launcher leads the landing now — wait for it
		// so the after-capture is guaranteed to include it.
		cy.get('[data-testid="lq-cockpit-centered-entry"]', { timeout: 30000 }).should('be.visible');
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`cockpit-${theme}`);
		}
	});

	it('captures a legacy (tools) chrome surface (light + dark, wide + narrow)', () => {
		login();
		cy.visit('/lq-ai/skills');
		// Wait for the chrome F2 actually changes (the TopTabBar nav) to paint,
		// not just `body` — a bare `body` assertion passes before the SPA renders
		// and yields a blank capture (seen on F2-M3 light-wide).
		cy.get('nav[aria-label="Primary"]', { timeout: 30000 }).should('be.visible');
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`tools-skills-${theme}`);
		}
	});
});
