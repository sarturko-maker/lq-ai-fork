/**
 * UX-A-2 — rail "Tools" section + flat surfaces in the cockpit canvas (ADR-F014).
 *
 * Proves the navigational-convergence contract for the migrated flat surfaces:
 *   1. the rail carries an expandable "Tools" group (Lucide glyphs);
 *   2. opening a tool from the rail renders it IN the cockpit canvas — the rail
 *      stays present (no dead-end) and the active tool highlights;
 *   3. every migrated surface deep-links directly (URL unchanged by the route
 *      group) and still renders inside the shell, incl. an `[id]`-style child.
 *
 * Runs against the live dev backend (real data, no stubs). Headed for an honest
 * dark capture (headless lies about dark mode).
 *
 * Run:
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ux-a-2-rail-tools.cy.ts' \
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

// Migrated flat surfaces: rail tool id → URL + a stable testid on the surface.
const MIGRATED = [
	{ id: 'tabular', url: '/lq-ai/tabular', surface: 'lq-tabular-new-cta' },
	{ id: 'playbooks', url: '/lq-ai/playbooks', surface: 'lq-playbooks-generate-cta' },
	{ id: 'skills', url: '/lq-ai/skills', surface: 'lq-ai-user-skills' },
	{ id: 'knowledge', url: '/lq-ai/knowledge', surface: 'lq-ai-knowledge-page' },
	{ id: 'learn', url: '/lq-ai/learn', surface: 'lq-ai-learn-page' },
	{ id: 'saved-prompts', url: '/lq-ai/saved-prompts', surface: 'lq-ai-saved-prompts-page' }
] as const;

describe('UX-A-2 rail Tools + flat surfaces in canvas', { retries: { runMode: 2, openMode: 0 } }, () => {
	it('opens a tool from the rail INTO the canvas (rail stays, tool highlights)', () => {
		login();
		cy.viewport(1280, 950);
		cy.visit('/lq-ai');
		cy.get('[data-testid="lq-cockpit"]', { timeout: 30000 }).should('be.visible');

		// The expandable Tools group is present (open by default).
		cy.get('[data-testid="lq-cockpit-tools-toggle"]', { timeout: 30000 }).should('be.visible');
		cy.get('[data-testid="lq-cockpit-tool-tabular"]').should('be.visible').click();

		// URL is the canonical one (route group is URL-invisible)…
		cy.url().should('include', '/lq-ai/tabular');
		// …the shell rail is STILL present (no dead-end)…
		cy.get('[data-testid="lq-cockpit-rail"]').should('be.visible');
		// …the tool rendered in the canvas…
		cy.get('[data-testid="lq-tabular-new-cta"]', { timeout: 20000 }).should('be.visible');
		// …and the open tool is highlighted in the rail.
		cy.get('[data-testid="lq-cockpit-tool-tabular"]').should('have.attr', 'aria-current', 'page');

		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			cy.wait(400);
			cy.screenshot(`ux-a-2-tabular-in-canvas-${theme}-wide`, { capture: 'viewport' });
		}
	});

	it('collapses + expands the Tools group', () => {
		login();
		cy.viewport(1280, 950);
		cy.visit('/lq-ai');
		cy.get('[data-testid="lq-cockpit-tools"]', { timeout: 30000 }).should('be.visible');
		cy.get('[data-testid="lq-cockpit-tools-toggle"]')
			.should('have.attr', 'aria-expanded', 'true')
			.click()
			.should('have.attr', 'aria-expanded', 'false');
		cy.get('[data-testid="lq-cockpit-tools"]').should('not.exist');
		cy.get('[data-testid="lq-cockpit-tools-toggle"]').click();
		cy.get('[data-testid="lq-cockpit-tools"]').should('be.visible');
	});

	it('deep-links every migrated surface inside the shell (light + dark)', () => {
		login();
		cy.viewport(1280, 950);
		for (const { url, surface } of MIGRATED) {
			cy.visit(url);
			// Shell present + the surface rendered in the canvas.
			cy.get('[data-testid="lq-cockpit-rail"]', { timeout: 30000 }).should('be.visible');
			cy.get(`[data-testid="${surface}"]`, { timeout: 20000 }).should('exist');
		}
		// Capture one representative surface in both themes.
		cy.visit('/lq-ai/skills');
		cy.get('[data-testid="lq-ai-user-skills"]', { timeout: 20000 }).should('be.visible');
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			cy.wait(400);
			cy.screenshot(`ux-a-2-skills-deeplink-${theme}-wide`, { capture: 'viewport' });
		}
	});

	it('deep-links an [id]-style child surface inside the shell', () => {
		login();
		cy.viewport(1280, 950);
		cy.visit('/lq-ai/tabular/new');
		cy.get('[data-testid="lq-cockpit-rail"]', { timeout: 30000 }).should('be.visible');
		cy.get('[data-testid="lq-tabwiz-steps"]', { timeout: 20000 }).should('be.visible');
	});
});
