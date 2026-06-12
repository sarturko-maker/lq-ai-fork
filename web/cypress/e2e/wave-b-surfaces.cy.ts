/**
 * Wave B v2 surface smoke tests.
 *
 * Covers the seven new surfaces that shipped in Wave B v2:
 *
 *   1. Post-login lands on the Guided Dashboard at /lq-ai (not the chat shell)
 *   2. Chats tab routes to /lq-ai/chats — no ComingSoonModal; chat shell renders
 *   3. /lq-ai/settings/appearance toggle persists across reload (real backend PATCH)
 *   4. /lq-ai/trust renders all four trust cards
 *   5. /lq-ai/admin/developer renders the four developer-support cards
 *   6. ✨ Enhance Prompt button opens the expansion panel (or error state)
 *   7. /lq-ai/skills/[id] detail page renders SkillDetailTabs; tab switching works
 *
 * Run requires a live stack:
 *   docker compose up -d
 *   docker compose exec api python -m app.cli reset-admin-password
 *   (note the printed password; export LQAI_ADMIN_PASSWORD or update env)
 *   cd web && npx cypress run --spec 'cypress/e2e/wave-b-surfaces.cy.ts'
 */
describe('Wave B v2 — new surfaces', () => {
	beforeEach(() => {
		cy.visit('/lq-ai/login');
		cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
		cy.get('input[type="password"]').type(
			Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-smoke-test-Pw1!'
		);
		cy.get('button[type="submit"]').click();
		// If must-change-password gate fires (fresh password reset), log and continue.
		// CI smoke environments are expected to have a stable post-change password.
		cy.url().then((url) => {
			if (url.includes('/change-password')) {
				cy.log(
					'must-change-password gate triggered; ensure the smoke password is the post-change one'
				);
			}
		});
		cy.url({ timeout: 15000 }).should('not.include', '/login');
	});

	// ── Test 1 ───────────────────────────────────────────────────────────────────
	// Post-login lands in the cockpit (F1-S2 — the guided dashboard retired).
	it('post-login lands in the cockpit at /lq-ai', () => {
		cy.url().should('match', /\/lq-ai\/?$/);
		cy.get('[data-testid="lq-cockpit"]').should('exist');
		cy.get('[data-testid="lq-cockpit-rail"]')
			.contains(/practice areas/i)
			.should('be.visible');
	});

	// ── Test 2 ───────────────────────────────────────────────────────────────────
	// Chats tab is now available=true; clicking it routes to /lq-ai/chats and
	// the chat shell renders instead of ComingSoonModal.
	it('Chats opens from the cockpit Tools menu with no ComingSoonModal', () => {
		cy.get('[data-testid="lq-cockpit"]').should('exist');
		cy.contains('button', 'Tools').click();
		cy.contains('[role="menuitem"]', 'Chats').click();
		cy.url().should('include', '/lq-ai/chats');
		// No dialog should be present (was the ComingSoonModal path).
		cy.get('[role="dialog"]').should('not.exist');
		// The chat shell root element must be in the DOM.
		cy.get('[data-testid="lq-ai-chat-shell"]').should('exist');
	});

	// ── Test 3 ───────────────────────────────────────────────────────────────────
	// /lq-ai/settings/appearance: toggling "Featured tools" to "Inline" persists
	// across a full page reload (real backend PATCH via the T2 preferences store).
	it('Featured tools toggle persists across reload', () => {
		cy.visit('/lq-ai/settings/appearance');

		// The SettingsToggleGroup for "Featured tools" renders a <fieldset> with
		// <legend> text "Featured tools". Inside, each option is a <label> wrapping
		// an <input type="radio">. We click the label whose text is "Inline toolbar only".
		cy.contains('fieldset', 'Featured tools').within(() => {
			cy.contains('label', 'Inline toolbar only').click();
		});

		cy.reload();

		// After reload the radio for "Inline toolbar only" should be checked.
		// (15s: the gate layout re-boots through /users/me + a possible token
		// refresh after reload — the bare 4s default flakes under load.)
		cy.contains('fieldset', 'Featured tools', { timeout: 15000 }).within(() => {
			cy.contains('label', 'Inline toolbar only').find('input[type="radio"]').should('be.checked');
		});

		// Restore default (Prominent) so this test is idempotent.
		cy.contains('fieldset', 'Featured tools').within(() => {
			cy.contains('label', 'Prominent cards on dashboard').click();
		});
	});

	// ── Test 4 ───────────────────────────────────────────────────────────────────
	// /lq-ai/trust renders all four trust cards using their actual h3 titles.
	it('/lq-ai/trust renders all four trust cards', () => {
		cy.visit('/lq-ai/trust');
		// TrustDataResidencyCard: h3 = "Where your data lives"
		cy.contains('h3', 'Where your data lives').should('be.visible');
		// TrustProvidersCard: h3 = "Configured providers"
		cy.contains('h3', 'Configured providers').should('be.visible');
		// TrustExternalTurnsCard: h3 = "External-turn usage"
		cy.contains('h3', 'External-turn usage').should('be.visible');
		// TrustArtifactsCard: h3 = "Trust artifacts"
		cy.contains('h3', 'Trust artifacts').should('be.visible');
	});

	// ── Test 5 ───────────────────────────────────────────────────────────────────
	// /lq-ai/admin/developer renders all four developer-support cards.
	// Card titles are h2 elements inside each DevXxx component.
	it('/lq-ai/admin/developer renders all four developer cards', () => {
		cy.visit('/lq-ai/admin/developer');
		// DevApiDocsCard: h2 = "API documentation"
		cy.contains('h2', 'API documentation').should('be.visible');
		// DevApiPlaygroundCard: h2 = "API playground"
		cy.contains('h2', 'API playground').should('be.visible');
		// DevRoleManagementCard: h2 = "Role management"
		cy.contains('h2', 'Role management').should('be.visible');
		// DevForkCallout: h2 = "Build your own frontend"
		cy.contains('h2', 'Build your own frontend').should('be.visible');
	});

	// ── Test 6 ───────────────────────────────────────────────────────────────────
	// ✨ Enhance Prompt button on the chat composer opens the expansion panel.
	// Accepts the success state (Original + Enhanced cards) OR the error state
	// (Enhance Prompt failed message) — the backend enhance-prompt service may
	// not be reachable in all smoke environments.
	it('✨ Enhance Prompt button opens the expansion panel', () => {
		cy.visit('/lq-ai/chats');
		// Type a prompt so the ✨ button becomes enabled.
		cy.get('[data-testid="lq-ai-composer-input"]').type('review this NDA for unusual provisions');
		// The enhance button is enabled only when composerText is non-empty.
		cy.get('[data-testid="lq-ai-enhance-btn"]').should('not.be.disabled').click();
		// The panel root must appear (covers all non-closed states).
		cy.get('[data-testid="lq-ai-enhance-panel"]', { timeout: 30000 }).should('exist');
		// Accept either the success path (Original card) or the error path.
		cy.get('[data-testid="lq-ai-enhance-panel"]').then(($panel) => {
			const text = $panel.text();
			const successPath =
				$panel.find('[data-testid="lq-ai-enhance-original"]').length > 0 ||
				$panel.find('[data-testid="lq-ai-enhance-enhanced"]').length > 0 ||
				$panel.find('[data-testid="lq-ai-enhance-skipped"]').length > 0;
			const errorPath = text.includes('Enhance Prompt failed');
			expect(successPath || errorPath, 'enhancement panel shows a result or error').to.be.true;
		});
	});

	// ── Test 7 ───────────────────────────────────────────────────────────────────
	// /lq-ai/skills/[id] detail page: SkillDetailTabs renders with "Use it" active
	// by default; clicking "View source" switches the tab and SkillSourceView renders
	// "Frontmatter" as the section heading.
	it('skill detail page renders SkillDetailTabs and tab switching works', () => {
		cy.visit('/lq-ai/skills');
		// Click the first skill name link — these are anchors with href="/lq-ai/skills/<slug>"
		// (not /edit or /new). The skills list page uses data-testid="lq-ai-user-skill-row"
		// rows; each title cell has an <a href="/lq-ai/skills/{slug}">.
		cy.get('a[href^="/lq-ai/skills/"]')
			.not('[href*="/edit"]')
			.not('[href*="/new"]')
			.first()
			.click();
		cy.url().should('match', /\/lq-ai\/skills\/[^/]+$/);

		// SkillDetailTabs: the tablist container
		cy.get('nav[role="tablist"][aria-label="Skill detail tabs"]').should('exist');

		// "Use it" tab is active by default (aria-selected="true")
		cy.contains('button[role="tab"]', 'Use it').should('have.attr', 'aria-selected', 'true');

		// Click "View source" — switches the active tab
		cy.contains('button[role="tab"]', 'View source').click();
		cy.contains('button[role="tab"]', 'View source').should('have.attr', 'aria-selected', 'true');

		// SkillSourceView renders a "Frontmatter" section heading (h2.lq-text-label)
		cy.contains('h2', 'Frontmatter').should('be.visible');
	});
});
