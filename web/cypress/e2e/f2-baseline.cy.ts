/**
 * F2 — minimalist pass: before/after capture (ADR-F012).
 *
 * Captures the surface families F2 changes most: the cockpit landing
 * (`/lq-ai` — the centered-entry + AreaGrid target), the matters/conversation
 * surfaces, and the table-list surfaces. Runs against the live dev backend
 * (real data, no stubs) so the baseline is honest. PHASE selects the filename
 * (before|after); M0 captures PHASE=before on the pre-F2 bundle.
 *
 * UX-A-4 removed the "legacy (tools) chrome" capture: admin/autonomous/settings/
 * trust migrated into the cockpit shell, so NO surface carries the legacy
 * TopTabBar chrome any more (the orphaned `(tools)/+layout.svelte` is unreachable,
 * retired in UX-A-5). There is nothing legacy left to capture.
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
		// tone family). Capture playbooks + tabular page bodies.
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

	it('captures the library card surfaces — knowledge + learn (light + dark, wide + narrow)', () => {
		// F2-M7b: the card/wrapper library pages adopt PageShell (snapped onto the
		// system reading widths) + migrate their color --lq-* tokens to semantic
		// (KB status pills onto the status-* tone family) + the F013 calm card
		// idiom (flat, border-led, hover-washes-to-muted, scarce-blue focus).
		login();
		cy.visit('/lq-ai/knowledge');
		cy.get('[data-testid="lq-ai-knowledge-page"]', { timeout: 30000 }).should('be.visible');
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`knowledge-${theme}`);
		}
		cy.visit('/lq-ai/learn');
		cy.get('[data-testid="lq-ai-learn-page"]', { timeout: 30000 }).should('be.visible');
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`learn-${theme}`);
		}
		cy.visit('/lq-ai/saved-prompts');
		cy.get('[data-testid="lq-ai-saved-prompts-page"]', { timeout: 30000 }).should('be.visible');
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`saved-prompts-${theme}`);
		}
	});

	it('captures the nav-shell surfaces — settings + admin + trust (light + dark, wide + narrow)', () => {
		// F2-M8: the settings (vertical rail) / admin (horizontal tab strip) / trust
		// nav shells migrate their color --lq-* tokens to semantic + adopt the F013
		// calm idiom — the active marker is inked (--card pill / --foreground
		// underline), no longer the old teal --lq-accent; scarce blue is focus-only.
		login();
		cy.visit('/lq-ai/settings/account');
		cy.get('nav[aria-label="Settings navigation"]', { timeout: 30000 }).should('be.visible');
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`settings-${theme}`);
		}
		cy.visit('/lq-ai/admin/audit-log');
		cy.get('nav[aria-label="Admin navigation"]', { timeout: 30000 }).should('be.visible');
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`admin-${theme}`);
		}
		cy.visit('/lq-ai/trust');
		cy.get('[data-testid="lq-ai-trust-page"]', { timeout: 30000 }).should('be.visible');
		cy.wait(800);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			shoot(`trust-${theme}`);
		}
	});
});
