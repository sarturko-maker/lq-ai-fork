/**
 * UX-A-3 — conversation surfaces in the cockpit canvas (ADR-F014).
 *
 * Moves the heavier surfaces — agents, chats, matters (+ matters/[id]) — from
 * the `(tools)` route group into `(app)`, so they render inside the cockpit
 * shell. Proves:
 *   1. opening one from the rail Tools group renders it IN the canvas, rail
 *      stays present, the tool highlights;
 *   2. they deep-link directly (URLs unchanged by the route group);
 *   3. matters/[id] composes its OWN `MatterRail` + `ChatPanel` inside the
 *      canvas WITHOUT clobbering the cockpit rail (the two-rail composition
 *      this slice deliberately keeps — recorded in HANDOFF).
 *
 * Runs against the live dev backend (real data, no stubs). Headed for an honest
 * dark capture (headless lies about dark mode).
 *
 * Run:
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ux-a-3-conversation-surfaces.cy.ts' \
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

// Migrated conversation surfaces: rail tool id → URL + a stable surface selector.
const MIGRATED = [
	{ id: 'agents', url: '/lq-ai/agents', surface: '[data-testid="lq-ai-agents-page"]' },
	{ id: 'chats', url: '/lq-ai/chats', surface: '[data-testid="lq-ai-chat-shell"]' },
	{ id: 'matters', url: '/lq-ai/matters', surface: '.mtr-page' }
] as const;

describe(
	'UX-A-3 conversation surfaces in canvas',
	{ retries: { runMode: 2, openMode: 0 } },
	() => {
		it('opens a conversation surface from the rail INTO the canvas (rail stays, tool highlights)', () => {
			login();
			cy.viewport(1280, 950);
			cy.visit('/lq-ai');
			cy.get('[data-testid="lq-cockpit"]', { timeout: 30000 }).should('be.visible');
			cy.get('[data-testid="lq-cockpit-tool-agents"]', { timeout: 30000 })
				.should('be.visible')
				.click();

			cy.url().should('include', '/lq-ai/agents');
			cy.get('[data-testid="lq-cockpit-rail"]').should('be.visible');
			cy.get('[data-testid="lq-ai-agents-page"]', { timeout: 20000 }).should('be.visible');
			cy.get('[data-testid="lq-cockpit-tool-agents"]').should('have.attr', 'aria-current', 'page');

			for (const theme of ['light', 'dark'] as const) {
				pinTheme(theme);
				cy.wait(400);
				cy.screenshot(`ux-a-3-agents-in-canvas-${theme}-wide`, { capture: 'viewport' });
			}
		});

		it('deep-links every migrated conversation surface inside the shell', () => {
			login();
			cy.viewport(1280, 950);
			for (const { url, surface } of MIGRATED) {
				cy.visit(url);
				cy.get('[data-testid="lq-cockpit-rail"]', { timeout: 30000 }).should('be.visible');
				cy.get(surface, { timeout: 20000 }).should('exist');
			}
		});

		it('matters/[id] composes its MatterRail + ChatPanel beside the cockpit rail', () => {
			login();
			cy.viewport(1280, 950);
			cy.visit('/lq-ai/matters');
			cy.get('.mtr-page', { timeout: 30000 }).should('be.visible');
			// Open the first matter (dev stack has Commercial matters).
			cy.get('a.matter-card', { timeout: 20000 }).first().click();
			cy.url().should('match', /\/lq-ai\/matters\/[0-9a-f-]+/);

			// Two-rail composition: cockpit rail (app nav) + the matter's own
			// MatterRail (within-matter nav) + the chat pane, all in the canvas.
			cy.get('[data-testid="lq-cockpit-rail"]').should('be.visible');
			cy.get('aside.matter-rail', { timeout: 20000 }).should('be.visible');
			cy.get('.matter-workspace').should('be.visible');

			for (const theme of ['light', 'dark'] as const) {
				pinTheme(theme);
				cy.wait(400);
				cy.screenshot(`ux-a-3-matter-detail-${theme}-wide`, { capture: 'viewport' });
			}
		});
	}
);
