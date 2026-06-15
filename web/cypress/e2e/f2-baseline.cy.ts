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

	it('captures the matters + conversation surfaces (light + dark, wide + narrow)', () => {
		// F2-M6: the matters list + conversation column adopt the PageShell idiom
		// (compact / tight pads). Deep-link into the one configured area, capture
		// the matters list, then open a matter to capture the conversation view.
		login();
		cy.visit('/lq-ai?area=commercial');
		cy.get('[data-testid="lq-cockpit-matters"]', { timeout: 30000 }).should('be.visible');
		cy.get('[data-testid="lq-cockpit-matter-row"]', { timeout: 30000 }).should(
			'have.length.gte',
			1
		);
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`matters-${theme}`);
		}
		cy.get('[data-testid="lq-cockpit-matter-row"]').first().click();
		cy.get('[data-testid="lq-cockpit-conversation"]', { timeout: 30000 }).should('be.visible');
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`conversation-${theme}`);
		}
	});

	it('captures the table-list surfaces — playbooks + tabular (light + dark, wide + narrow)', () => {
		// F2-M7a: the executor/skills table-list pages adopt PageShell + migrate
		// their color --lq-* tokens to semantic (status pills onto the status-*
		// tone family). Capture playbooks + tabular page bodies; skills is already
		// captured by the (tools)-chrome test below.
		login();
		cy.visit('/lq-ai/playbooks');
		cy.get('[data-testid="lq-playbooks-generate-cta"]', { timeout: 30000 }).should('be.visible');
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`playbooks-${theme}`);
		}
		cy.visit('/lq-ai/tabular');
		cy.get('[data-testid="lq-tabular-new-cta"]', { timeout: 30000 }).should('be.visible');
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`tabular-${theme}`);
		}
	});

	it('captures a legacy (tools) chrome surface (light + dark, wide + narrow)', () => {
		login();
		// UX-A-2 moved skills into the cockpit shell; `chats` is still a legacy
		// `(tools)` surface (its UX-A-3 slice hasn't landed), so it still carries
		// the TopTabBar chrome F2-M2/M3 calm.
		cy.visit('/lq-ai/chats');
		// Wait for the chrome F2 actually changes (the TopTabBar nav) to paint,
		// not just `body` — a bare `body` assertion passes before the SPA renders
		// and yields a blank capture (seen on F2-M3 light-wide).
		cy.get('nav[aria-label="Primary"]', { timeout: 30000 }).should('be.visible');
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`tools-chats-${theme}`);
		}
	});
});
