/**
 * UX-A-5 — retire the legacy `(tools)` shell + the header Tools dropdown (ADR-F014).
 *
 * The final UX-A slice. The `(tools)/+layout.svelte` shell (legacy `TopTabBar` +
 * footer) is deleted, and the `CockpitHeader` Tools dropdown is removed — tools
 * are reached ONLY from the rail's Tools section now. Proves:
 *   1. NO legacy `TopTabBar` (`nav[aria-label="Primary"]`) on any surface;
 *   2. the header carries NO "Tools" dropdown trigger any more;
 *   3. tools open from the rail Tools section into the canvas (the sole path);
 *   4. trust stays reachable from the header (dedicated trust button), now that
 *      it no longer lives in the retired Tools dropdown.
 *
 * Runs against the live dev backend (real data, no stubs). Headed for an honest
 * dark capture (headless lies about dark mode).
 *
 * Run:
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ux-a-5-retire-legacy-shell.cy.ts' \
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

describe('UX-A-5 legacy shell retired', { retries: { runMode: 2, openMode: 0 } }, () => {
	it('no legacy TopTabBar / Tools dropdown remains; the header is the calm cockpit chrome', () => {
		login();
		cy.viewport(1280, 950);

		// The cockpit landing + a representative migrated tool surface: neither
		// carries the legacy TopTabBar, and the header has no Tools dropdown.
		for (const url of ['/lq-ai', '/lq-ai/skills', '/lq-ai/admin/audit-log']) {
			cy.visit(url);
			cy.get('[data-testid="lq-cockpit"]', { timeout: 30000 }).should('be.visible');
			cy.get('nav[aria-label="Primary"]').should('not.exist');
			// The header Tools dropdown trigger is gone (tools live in the rail).
			cy.get('[data-testid="lq-cockpit-header"]').within(() => {
				cy.contains('button', 'Tools').should('not.exist');
			});
		}

		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			cy.wait(400);
			cy.screenshot(`ux-a-5-cockpit-header-${theme}-wide`, { capture: 'viewport' });
		}
	});

	it('tools open ONLY from the rail Tools section into the canvas', () => {
		login();
		cy.viewport(1280, 950);
		cy.visit('/lq-ai');
		cy.get('[data-testid="lq-cockpit-tools"]', { timeout: 30000 }).should('be.visible');
		cy.get('[data-testid="lq-cockpit-tool-tabular"]').click();
		cy.url().should('include', '/lq-ai/tabular');
		cy.get('[data-testid="lq-cockpit-rail"]').should('be.visible');
		cy.get('[data-testid="lq-cockpit-tool-tabular"]').should('have.attr', 'aria-current', 'page');
	});

	it('trust stays reachable from the dedicated header trust button', () => {
		login();
		cy.viewport(1280, 950);
		cy.visit('/lq-ai');
		cy.get('[data-testid="lq-cockpit"]', { timeout: 30000 }).should('be.visible');
		cy.get('[data-testid="lq-cockpit-header"] button[aria-label="Trust & transparency"]').click();
		cy.url().should('include', '/lq-ai/trust');
		cy.get('.trust-page', { timeout: 20000 }).should('be.visible');
	});
});
