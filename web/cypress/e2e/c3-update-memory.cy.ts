/**
 * C3-UM — the human "update memory" UX (ADR-F042 / F044 §4B).
 *
 * Layered on the read-only C3c-2 Memory panel, the supervising lawyer can now:
 *   1. PIN a correction (composer in the Corrections header),
 *   2. CORRECT a specific fact (a quiet action that pre-fills the composer with a
 *      "Re: '…' →" stub — still stored as an ordinary pinned correction),
 *   3. RETIRE a pinned correction or a fact (soft, append-only, behind a confirm step).
 *
 * The composite GET and the three POSTs are INTERCEPTED so the panel is deterministic
 * regardless of stored memory; the matter is real only so the cockpit renders
 * ConversationHost (mirrors c3c2-matter-memory.cy.ts). The disabled-while-a-run-is-active
 * gate is host-driven (`runActive` prop) and is covered by the `canWrite` unit test, not
 * forced here.
 *
 * Run (live stack, headed):
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/c3-update-memory.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
const PRIVACY_MATTER = '47519e68-d764-4a3f-b96b-2d703c16229c';

const MEMORY = {
	project_id: PRIVACY_MATTER,
	wiki: {
		content_md:
			'## Working summary\n\nAcme MSA renewal. Governing law **England & Wales**. ' +
			'Counterparty is *Acme UK Ltd*.',
		char_count: 110,
		version_count: 1
	},
	facts: [
		{
			id: 'fact-1',
			body_md: 'Governing law is England & Wales.',
			fact_type: 'term',
			source_citation: 'MSA §18.2',
			author: 'agent',
			valid_at: '2026-05-01T00:00:00Z',
			created_at: '2026-05-02T00:00:00Z'
		}
	],
	corrections: [
		{
			id: 'corr-1',
			body_md: 'The counterparty entity is **Acme UK Ltd**, not Acme Inc.',
			trust: 'human-pinned',
			created_at: '2026-05-03T12:00:00Z'
		}
	],
	log: [
		{
			id: 'log-1',
			kind: 'correction',
			created_at: '2026-05-03T12:00:00Z',
			run_id: null,
			author: 'lawyer',
			fact_type: null,
			source_citation: null,
			superseded: false,
			body_preview: 'The counterparty entity is Acme UK Ltd, not Acme Inc.'
		}
	],
	log_total: 3
};

const PIN_RESPONSE = {
	id: 'corr-new',
	project_id: PRIVACY_MATTER,
	body_md: 'We act for the seller.',
	trust: 'human-pinned',
	created_at: '2026-06-23T00:00:00Z'
};

const RETIRE_RESPONSE = { id: 'entry-x', retired_at: '2026-06-23T12:00:00Z' };

function pinTheme(theme: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', theme);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(theme);
	});
	cy.get('html').should('have.class', theme);
}

function openMemory() {
	cy.visit(`/lq-ai?area=privacy&matter=${PRIVACY_MATTER}`);
	cy.get('[data-testid="lq-cockpit-conversation"]', { timeout: 30000 }).should('exist');
	cy.get('body').then(($b) => {
		if ($b.find('[data-testid="lq-cockpit-matter-tab-memory"]').length === 0) {
			cy.get('[data-testid="lq-cockpit-new-conversation"]').first().click();
		}
	});
	cy.get('[data-testid="lq-cockpit-matter-tab-memory"]', { timeout: 30000 })
		.should('be.visible')
		.click();
	cy.wait('@getMemory');
	cy.get('[data-testid="lq-matter-memory"]', { timeout: 30000 }).should('be.visible');
}

describe(
	'C3-UM — the human update-memory gestures',
	{ retries: { runMode: 2, openMode: 0 } },
	() => {
		beforeEach(() => {
			cy.intercept('GET', '/api/v1/matters/*/memory', { statusCode: 200, body: MEMORY }).as(
				'getMemory'
			);
			cy.intercept('POST', '**/memory/corrections', { statusCode: 201, body: PIN_RESPONSE }).as(
				'pin'
			);
			cy.intercept('POST', '**/memory/corrections/*/retire', {
				statusCode: 200,
				body: RETIRE_RESPONSE
			}).as('retireCorrection');
			cy.intercept('POST', '**/memory/facts/*/retire', {
				statusCode: 200,
				body: RETIRE_RESPONSE
			}).as('retireFact');
		});

		it('pins a correction, pre-fills the composer from a fact, and retires a correction + a fact', () => {
			cy.viewport(1440, 900);
			login(ADMIN_EMAIL(), ADMIN_PASSWORD());
			openMemory();

			// 1) Pin a correction via the Corrections-header composer.
			cy.get('[data-testid="lq-memory-pin-open"]').should('be.enabled').click();
			cy.get('[data-testid="lq-memory-composer-input"]')
				.should('be.visible')
				.type('We act for the seller.');
			cy.get('[data-testid="lq-memory-pin-submit"]').should('be.enabled').click();
			cy.wait('@pin')
				.its('request.body')
				.should('deep.equal', { body_md: 'We act for the seller.' });
			// The composer closes and the panel refetches the composite.
			cy.get('[data-testid="lq-memory-composer-input"]').should('not.exist');
			cy.get('@getMemory.all').should('have.length.greaterThan', 1);

			// 2) Correct a fact → the SAME composer opens, pre-filled with a "Re: '…' →" stub.
			cy.get('[data-testid="lq-memory-fact-correct"]').first().click();
			cy.get('[data-testid="lq-memory-composer-input"]')
				.should('be.visible')
				.should('have.value', 'Re: "Governing law is England & Wales." → ');
			// Close the composer so it doesn't overlay the next gesture.
			cy.contains('button', 'Cancel').click();

			// 3) Retire a pinned correction behind a confirm step.
			cy.get('[data-testid="lq-memory-correction-retire"]').first().click();
			cy.get('[role="dialog"]').should('be.visible').and('contain.text', 'Retire this correction?');
			cy.get('[data-testid="lq-memory-retire-confirm"]').click();
			cy.wait('@retireCorrection');
			cy.get('[role="dialog"]').should('not.exist');

			// 4) Retire a fact behind a confirm step (distinct copy).
			cy.get('[data-testid="lq-memory-fact-retire"]').first().click();
			cy.get('[role="dialog"]').should('be.visible').and('contain.text', 'Retire this fact?');
			cy.get('[data-testid="lq-memory-retire-confirm"]').click();
			cy.wait('@retireFact');
			cy.get('[role="dialog"]').should('not.exist');
		});

		it('capture — update-memory affordances + composer: light/dark', () => {
			cy.viewport(1440, 900);
			login(ADMIN_EMAIL(), ADMIN_PASSWORD());
			openMemory();
			for (const theme of ['light', 'dark'] as const) {
				pinTheme(theme);
				// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
				cy.wait(300);
				cy.screenshot(`c3-um-affordances-${theme}`, { capture: 'viewport' });
				// Open the composer to capture the pin surface.
				cy.get('[data-testid="lq-memory-pin-open"]').click();
				cy.get('[data-testid="lq-memory-composer-input"]').type('We act for the seller.');
				// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
				cy.wait(200);
				cy.screenshot(`c3-um-composer-${theme}`, { capture: 'viewport' });
				cy.contains('button', 'Cancel').click();
			}
			pinTheme('light');
		});
	}
);
