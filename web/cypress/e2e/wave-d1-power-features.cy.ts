/**
 * Wave D.1 — In-chat power features (T21 E2E suite).
 *
 * Covers the four in-chat power features that shipped through Wave D.1 (T0–T20):
 *
 *   1. Enhance Prompt (T20)            — ⌘E expansion → "Use enhanced" → send
 *   2. KB attach modal (T11/T12)       — composer 📎 → multi-select → matter rail reflects
 *   3. Tier-floor refusal + admin
 *      override (T13/T14/T15)          — amber refusal block → Override → reason → confirm
 *   4. Receipts drawer (T16/T17/T18/
 *      T19)                            — composer 📜 → drawer → filter chip → JSONL export
 *   5. Member sees refusal but no
 *      Override button                 — admin-only gate on RefusalMessageBubble
 *
 * Run requires a live stack (mirrors wave-c-matters.cy.ts contract):
 *   docker compose up -d
 *   docker compose exec api python -m app.cli reset-admin-password
 *   cd web && npx cypress run --spec 'cypress/e2e/wave-d1-power-features.cy.ts'
 *
 * Scenarios 3 and 5 require fixture work — a privileged matter wired so that
 * a standard-tier prompt deterministically trips the tier-floor refusal — and
 * a member-role user for scenario 5. These are marked `.skip` and deferred to
 * a Wave F follow-on Cypress-fixtures task. The remaining three scenarios
 * (1, 2, 4) exercise the surfaces directly against a fresh matter created
 * inline by the test (same pattern Wave C established).
 */

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-smoke-test-Pw1!';
const MEMBER_EMAIL = () => Cypress.env('LQAI_MEMBER_EMAIL') || 'member@lq.ai';
const MEMBER_PASSWORD = () => Cypress.env('LQAI_MEMBER_PASSWORD') || 'LQ-AI-smoke-test-Pw1!';

/**
 * Inline login — mirrors wave-c-matters.cy.ts beforeEach pattern.
 * Wave C did not extract a custom command for this; we follow the same shape
 * so anyone reading the suite sees a single consistent login flow.
 */
function login(email: string, password: string) {
	cy.visit('/lq-ai/login');
	cy.get('input[type="email"]').type(email);
	cy.get('input[type="password"]').type(password);
	cy.get('button[type="submit"]').click();
	cy.url().should('not.include', '/login');
}

/**
 * Create a fresh non-privileged matter and land in its workspace.
 * Returns the matter name via Cypress alias `@matterName` so tests can assert
 * on it later. Mirrors wave-c-matters.cy.ts test 3.
 */
function createSampleMatter(prefix = 'Cypress Wave D.1') {
	const matterName = `${prefix} ${Date.now()}`;
	cy.visit('/lq-ai/matters');
	cy.contains('button', '+ New matter').first().click();
	cy.get('[role="dialog"]').should('exist');
	cy.get('[role="dialog"]').find('input[type="text"]').first().clear().type(matterName);
	cy.contains('button', 'Create matter').click();
	cy.url({ timeout: 10000 }).should('match', /\/lq-ai\/matters\/[a-f0-9-]+$/);
	cy.get('[data-testid="lq-ai-chat-shell"]', { timeout: 10000 }).should('exist');
	cy.wrap(matterName).as('matterName');
}

describe('Wave D.1 — in-chat power features', () => {
	beforeEach(() => {
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
	});

	// ── Test 1 ───────────────────────────────────────────────────────────────────
	// Enhance Prompt full cycle: open composer → type prompt → ⌘E (hotkey) →
	// expansion panel renders → click "Use enhanced" → the enhanced text replaces
	// the composer contents (T20 audit ships explicit data-testids on the panel
	// and the use-enhanced button).
	it('enhance prompt: ⌘E expands and Use enhanced replaces composer text', () => {
		createSampleMatter('Cypress Enhance');
		const prompt = 'Draft an NDA for a vendor';
		cy.get('[data-testid="lq-ai-composer-input"]').first().type(prompt);

		// Hotkey trigger — Composer.svelte binds Cmd/Ctrl+E to onEnhance().
		// We dispatch the key against the composer textarea (not body) so the
		// focused element receives the keydown.
		cy.get('[data-testid="lq-ai-composer-input"]').first().type('{cmd}e');

		// Enhance panel renders. Either the loading state or the JIT/result card
		// must appear; we accept either, then wait for the result card with the
		// "Use enhanced" button visible (full live-LLM round-trip).
		cy.get('[data-testid="lq-ai-enhance-panel"]', { timeout: 60000 }).should('be.visible');
		cy.get('[data-testid="lq-ai-enhance-use"]', { timeout: 60000 }).should('be.visible').click();

		// After Use enhanced, the panel collapses and the composer holds the
		// enhanced text. We don't assert on the exact enhanced wording (provider-
		// dependent), but the composer must no longer be empty and the panel
		// should be gone or in its post-accept state.
		cy.get('[data-testid="lq-ai-composer-input"]').first().should(($el) => {
			expect(($el.val() as string).length).to.be.greaterThan(prompt.length);
		});
	});

	// ── Test 2 ───────────────────────────────────────────────────────────────────
	// KB attach modal: composer 📎 button opens AttachKBModal → multi-select
	// checkbox UI → "Attach N selected" submits and dismisses → matter rail
	// Knowledge section (data-testid="matter-rail-knowledge") reflects the
	// newly-attached KBs. Test tolerates the empty-KB-fixture case by skipping
	// the assertion if no checkboxes render (no KBs in this org).
	it('KB attach modal: composer 📎 → multi-select → matter rail reflects', () => {
		createSampleMatter('Cypress KB Attach');

		cy.get('[data-testid="lq-ai-attach-kb-btn"]').click();
		cy.get('[role="dialog"]').should('exist');
		cy.contains(/attach knowledge/i).should('be.visible');

		// If no KBs exist in this org, the modal renders an empty state.
		// In that case the rest of the test is informational; we close the
		// modal and assert the rail Knowledge section exists (T12 always-render).
		cy.get('body').then(($body) => {
			const checkboxes = $body.find('[role="dialog"] input[type="checkbox"]');
			if (checkboxes.length === 0) {
				cy.log('No KBs in fixture — skipping attach assertion');
				cy.get('[role="dialog"]').contains('button', /cancel|close/i).click();
				return;
			}
			// Select up to 2 KBs (or 1 if only one exists).
			cy.get('[role="dialog"] input[type="checkbox"]').first().check({ force: true });
			if (checkboxes.length >= 2) {
				cy.get('[role="dialog"] input[type="checkbox"]').eq(1).check({ force: true });
			}
			cy.contains('button', /^attach \d+ selected$/i).click();
			cy.get('[role="dialog"]').should('not.exist');
		});

		// MatterRailKnowledge section is mounted in the rail (T12 wiring).
		cy.get('[data-testid="matter-rail-knowledge"]').should('exist');
	});

	// ── Test 3 ───────────────────────────────────────────────────────────────────
	// Tier-floor refusal + admin override.
	//
	// SKIPPED — requires a privileged matter pre-wired so that a standard-tier
	// prompt deterministically trips the gateway's tier-floor refusal. The
	// current fixture story does not seed such a matter, and the gateway
	// behavior depends on a configured tier-floor + a provider routing rule.
	// Deferred to Wave F Cypress-fixtures task.
	it.skip('tier-floor refusal + admin override', () => {
		// Open the pre-seeded privileged matter (placeholder — fixture work pending).
		cy.visit('/lq-ai/matters');
		cy.contains(/privileged/i).first().click();
		cy.url({ timeout: 10000 }).should('match', /\/lq-ai\/matters\/[a-f0-9-]+$/);

		cy.get('[data-testid="lq-ai-composer-input"]')
			.first()
			.type('Quick rough draft — should hit standard tier (intentional tier mismatch)');
		cy.get('[data-testid="lq-ai-composer"] button[type="submit"]').first().click();

		// Amber refusal block renders (RefusalMessageBubble — T13).
		cy.get('[data-testid="refusal-bubble"]', { timeout: 60000 }).should('be.visible');
		cy.contains(/refused at .*-floor/i).should('be.visible');

		// Admin sees Override button (T13 gate on user.role === 'admin').
		cy.get('[data-testid="override-button"]').click();

		// TierFloorOverrideModal opens — fill reason (10..500 chars) and confirm.
		cy.get('[role="dialog"]').should('exist');
		cy.get('#override-reason').type(
			'Urgent client request — partner has risk-accepted (Cypress E2E test reason)'
		);
		cy.get('[data-testid="confirm-button"]').click();

		// Refusal block replaced with AI response (re-run at higher tier).
		cy.get('[data-testid="refusal-bubble"]', { timeout: 60000 }).should('not.exist');
	});

	// ── Test 4 ───────────────────────────────────────────────────────────────────
	// Receipts drawer toggle + filter + JSONL export (T16/T17/T18/T19).
	// We don't send a real message here — the receipts drawer mounts as long
	// as a chat is selected. Filter chip click + export click are the surfaces
	// under test. (Sending a message would require a configured provider; the
	// drawer's empty state still exercises filter + export UI affordances.)
	it('receipts drawer toggle + filter + export', () => {
		createSampleMatter('Cypress Receipts');

		// Open drawer via composer 📜 toggle (T19).
		cy.get('[data-testid="lq-ai-receipts-toggle"]').click();
		cy.contains(/receipts/i).should('be.visible');

		// Filter chips render (T17 ReceiptsList). The list will likely show
		// the empty-state ("No receipts yet…") on a brand-new matter; that's
		// expected and validates the empty-state path.
		cy.get('body').then(($body) => {
			const chips = $body.find('[data-testid^="filter-chip-"]');
			if (chips.length > 0) {
				cy.get('[data-testid^="filter-chip-"]').first().click();
			} else {
				cy.log('No receipts yet — filter chips not rendered (empty state expected)');
			}
		});

		// Export button is always rendered in the drawer header (T18 ReceiptsExport).
		cy.get('[data-testid="export-jsonl"]').should('be.visible');

		// We don't actually click export — that triggers a real file download
		// against a likely-empty receipts log and pollutes cypress/downloads.
		// The presence of the export button + the drawer rendering is the
		// T16+T18 contract. Real download verification is deferred to a Wave F
		// fixture-backed receipts test that seeds at least one receipts row.
	});

	// ── Test 5 ───────────────────────────────────────────────────────────────────
	// Member sees refusal but no Override button.
	//
	// SKIPPED — requires (a) a member-role test user and (b) the same
	// privileged-matter fixture as Test 3. Deferred to Wave F Cypress-fixtures.
	it.skip('member sees refusal but no Override button', () => {
		// Re-auth as member.
		cy.clearCookies();
		cy.clearLocalStorage();
		login(MEMBER_EMAIL(), MEMBER_PASSWORD());

		cy.visit('/lq-ai/matters');
		cy.contains(/privileged/i).first().click();
		cy.url({ timeout: 10000 }).should('match', /\/lq-ai\/matters\/[a-f0-9-]+$/);

		cy.get('[data-testid="lq-ai-composer-input"]').first().type('rough draft please');
		cy.get('[data-testid="lq-ai-composer"] button[type="submit"]').first().click();

		// Refusal renders…
		cy.get('[data-testid="refusal-bubble"]', { timeout: 60000 }).should('be.visible');
		cy.contains(/refused at .*-floor/i).should('be.visible');

		// …but no Override button (admin-only gate in RefusalMessageBubble).
		cy.get('[data-testid="override-button"]').should('not.exist');
	});
});
