/**
 * UX-A-4 — sub-nav surfaces in the cockpit canvas (ADR-F014).
 *
 * Moves the last `(tools)` surfaces — admin, autonomous, settings, trust — into
 * `(app)`, so they render inside the cockpit shell. Three of the four carry
 * their OWN sub-nav `+layout.svelte` (admin/autonomous = horizontal tab strip;
 * settings = vertical rail), which now render INSIDE the canvas — nested chrome,
 * accepted for UX-A. Proves:
 *   1. opening admin from the rail Tools group renders it IN the canvas, the
 *      cockpit rail stays, the tool highlights, and the admin sub-nav paints;
 *   2. settings + trust deep-link inside the shell (reached via the cockpit
 *      header gear + Tools-dropdown trust link, both still present);
 *   3. a sub-nav child (settings/account, admin/models) deep-links and the
 *      surface's own sub-nav renders beside the cockpit rail.
 *
 * After this slice NO surface carries the legacy TopTabBar chrome — the
 * `(tools)/+layout.svelte` shell is orphaned (retired in UX-A-5).
 *
 * Runs against the live dev backend (real data, no stubs). Headed for an honest
 * dark capture (headless lies about dark mode).
 *
 * Run:
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ux-a-4-subnav-surfaces.cy.ts' \
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

// Migrated sub-nav surfaces: URL → a stable surface selector. (admin requires an
// admin user — the dev admin login covers it; autonomous is opt-in-gated so it's
// excluded from the deep-link sweep here.)
const MIGRATED = [
	{ url: '/lq-ai/admin/audit-log', surface: '[data-testid="lq-ai-admin-audit-log"]' },
	{ url: '/lq-ai/admin/models', surface: '[data-testid="lq-ai-admin-models"]' },
	{ url: '/lq-ai/settings/appearance', surface: '[data-testid="lq-ai-auto-enhance-toggle"]' },
	{ url: '/lq-ai/trust', surface: '.trust-page' }
] as const;

describe(
	'UX-A-4 sub-nav surfaces in canvas',
	{ retries: { runMode: 2, openMode: 0 } },
	() => {
		it('opens admin from the rail INTO the canvas (rail stays, tool highlights, sub-nav paints)', () => {
			login();
			cy.viewport(1280, 950);
			cy.visit('/lq-ai');
			cy.get('[data-testid="lq-cockpit"]', { timeout: 30000 }).should('be.visible');
			cy.get('[data-testid="lq-cockpit-tool-admin"]', { timeout: 30000 })
				.should('be.visible')
				.click();

			cy.url().should('include', '/lq-ai/admin');
			cy.get('[data-testid="lq-cockpit-rail"]').should('be.visible');
			// The admin sub-nav (its own +layout) renders inside the canvas.
			cy.get('nav[aria-label="Admin navigation"]', { timeout: 20000 }).should('be.visible');
			cy.get('[data-testid="lq-ai-admin-audit-log"]', { timeout: 20000 }).should('be.visible');
			cy.get('[data-testid="lq-cockpit-tool-admin"]').should('have.attr', 'aria-current', 'page');

			for (const theme of ['light', 'dark'] as const) {
				pinTheme(theme);
				cy.wait(400);
				cy.screenshot(`ux-a-4-admin-in-canvas-${theme}-wide`, { capture: 'viewport' });
			}
		});

		it('deep-links every migrated sub-nav surface inside the shell', () => {
			login();
			cy.viewport(1280, 950);
			for (const { url, surface } of MIGRATED) {
				cy.visit(url);
				cy.get('[data-testid="lq-cockpit-rail"]', { timeout: 30000 }).should('be.visible');
				cy.get(surface, { timeout: 20000 }).should('exist');
			}
		});

		it('settings composes its vertical sub-nav beside the cockpit rail; trust renders in canvas', () => {
			login();
			cy.viewport(1280, 950);

			// Settings: the cockpit rail + the settings sub-nav (its own +layout) + content.
			cy.visit('/lq-ai/settings/account');
			cy.get('[data-testid="lq-cockpit-rail"]', { timeout: 30000 }).should('be.visible');
			cy.get('nav[aria-label="Settings navigation"]', { timeout: 20000 }).should('be.visible');

			// Trust: a plain page in the canvas, reachable from the header Tools dropdown.
			cy.visit('/lq-ai/trust');
			cy.get('[data-testid="lq-cockpit-rail"]').should('be.visible');
			cy.get('.trust-page', { timeout: 20000 }).should('be.visible');

			for (const theme of ['light', 'dark'] as const) {
				pinTheme(theme);
				cy.wait(400);
				cy.screenshot(`ux-a-4-trust-in-canvas-${theme}-wide`, { capture: 'viewport' });
			}
		});
	}
);
