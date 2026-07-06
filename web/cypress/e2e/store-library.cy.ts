/**
 * Store + Library admin pages — STORE-2 (ADR-F065).
 *
 * Covers the end-to-end Store -> Library -> area-detail loop:
 *
 *   1. Login (admin) -> /lq-ai/admin/store renders the Recommended rail +
 *      the Tools/Skills/Playbooks sections.
 *   2. Adopt ONE currently-unadopted entry ("Add to Library").
 *   3. /lq-ai/admin/library shows the newly-adopted entry, with a
 *      "Not attached to any practice area." where-used line.
 *   4. The Remove-confirm modal (D-F) on a BOUND entry (already attached to
 *      an area from the deployment seed) lists the area name(s) + the
 *      plain-language warning — then CANCEL (the seeded binding survives).
 *   5. Remove the entry adopted in step 2 (fully confirmed this time) —
 *      restores the org's Library to its pre-test state (NET-ZERO on data).
 *   6. An area-detail picker (Playbooks — no playbook is adopted by default
 *      per the STORE-1 seed) shows the Store empty-state link when the
 *      Library has no entries of that kind.
 *
 * Cypress command-queue trap: every assertion that depends on a value
 * captured off the DOM (the adopted entry's testid/label) is nested INSIDE
 * the `.then()` callback that captured it — reading the outer `let` at
 * enqueue time (rather than at run time) is a classic Cypress bug this spec
 * deliberately avoids.
 *
 * Run requires a live stack:
 *   docker compose up -d
 *   docker compose exec api python -m app.cli reset-admin-password
 *   (note the printed password; export LQ_PASSWORD or update the fallback)
 *   cd web && npx cypress run --spec 'cypress/e2e/store-library.cy.ts'
 */
import { login } from '../support/lq-ai-helpers';

const EMAIL = (Cypress.env('LQ_EMAIL') as string) || 'admin@lq.ai';
const PASSWORD = (Cypress.env('LQ_PASSWORD') as string) || 'LQ-AI-local-Pw1!';

describe('Store + Library (STORE-2)', () => {
	beforeEach(() => {
		login(EMAIL, PASSWORD);
	});

	it('adopts an entry from the Store, sees it in the Library, cancels a bound Remove, then removes it (net-zero)', () => {
		// ── 1. Store renders the rail + sections ──────────────────────────────
		cy.visit('/lq-ai/admin/store');
		cy.get('[data-testid="lq-admin-store-page"]', { timeout: 15000 }).should('exist');
		cy.get('[data-testid="lq-store-section-tool"]').should('exist');
		cy.get('[data-testid="lq-store-section-skill"]').should('exist');
		cy.get('[data-testid="lq-store-section-playbook"]').should('exist');

		// ── 2. Adopt the first currently-unadopted entry we find ──────────────
		cy.get('button[data-testid^="lq-store-add-"]')
			.first()
			.then(($btn) => {
				const adoptedTestId = ($btn.attr('data-testid') || '').replace('lq-store-add-', '');
				// The Store page's testids use the entryId `kind:key` grammar; the
				// Library page's use `kind-key` — translate when crossing pages
				// (caught live in the STORE-2 gate browser pass).
				const libraryTestId = adoptedTestId.replace(':', '-');
				const adoptedLabel = $btn
					.closest('[data-testid^="lq-store-card-"]')
					.find('p, a')
					.first()
					.text()
					.trim();

				cy.wrap($btn).click();

				// Optimistic-then-refetch flip to "In Library ✓" (disabled).
				cy.get(`[data-testid="lq-store-card-${adoptedTestId}"]`, { timeout: 10000 }).within(
					() => {
						cy.contains('button', 'In Library ✓').should('exist');
					}
				);

				// ── 3. Library shows it, unattached ────────────────────────────────
				cy.visit('/lq-ai/admin/library');
				cy.get('[data-testid="lq-admin-library-page"]', { timeout: 15000 }).should('exist');
				cy.contains('[data-testid^="lq-library-card-"]', adoptedLabel)
					.contains('Not attached to any practice area.')
					.should('exist');

				// ── 4. Remove-confirm modal on a BOUND entry -> lists the area(s), CANCEL ──
				// Any card whose where-used line starts with "Attached to:" is bound —
				// the deployment seed guarantees at least one (Redlining/Tabular on
				// Commercial, ROPA/Assessments on Privacy).
				cy.contains('[data-testid^="lq-library-card-"]', 'Attached to:')
					.first()
					.within(() => {
						cy.contains('button', 'Remove').click();
					});
				cy.get('[role="dialog"]').should('be.visible');
				cy.get('[role="dialog"]')
					.contains(/attached to:/i)
					.should('exist');
				cy.get('[data-testid="lq-library-remove-warning"]').should('exist');
				cy.get('[data-testid="lq-library-remove-cancel"]').click();
				cy.get('[role="dialog"]').should('not.exist');

				// ── 5. Remove the entry WE adopted (unattached -> no warning line) ──
				cy.get(`[data-testid="lq-library-remove-${libraryTestId}"]`).click();
				cy.get('[role="dialog"]').should('be.visible');
				cy.get('[role="dialog"]').contains('Not attached to any practice area.').should('exist');
				cy.get('[data-testid="lq-library-remove-warning"]').should('not.exist');
				cy.get('[data-testid="lq-library-remove-confirm"]').click();
				cy.get('[role="dialog"]').should('not.exist');
				cy.get(`[data-testid="lq-library-card-${libraryTestId}"]`).should('not.exist');
			});

		// ── 6. Area-detail: Playbooks picker shows the Store empty-state link ──
		// (no playbook is adopted into the Library by default — STORE-1 seed).
		cy.visit('/lq-ai/admin/areas/commercial');
		cy.get('[data-testid="lq-admin-area-playbooks-empty"]', { timeout: 15000 })
			.contains('browse the Store')
			.should('have.attr', 'href', '/lq-ai/admin/store');
	});
});
