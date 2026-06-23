/**
 * C3c-2 — cockpit matter-memory panel (ADR-F042 / F044).
 *
 * The cockpit now shows a "Memory" tab on EVERY matter (area-agnostic) rendering
 * the C3c-1 composite (`GET /api/v1/matters/{id}/memory`) and offering a
 * human-authenticated wiki revert (`POST .../memory/wiki/revert`) behind a
 * confirm step, disabled while a run is active.
 *
 * We drive the REAL seeded Privacy matter — the strongest proof of the
 * "all matters, any area" decision: a Privacy matter gets a Memory tab ALONGSIDE
 * its ROPA register. The memory composite + revert are INTERCEPTED so the panel
 * content is deterministic regardless of the matter's actual stored memory; the
 * matter is real only so the cockpit renders ConversationHost (mirrors
 * priv-9a-covisible.cy.ts).
 *
 * Run (live stack, headed for an honest light+dark capture):
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/c3c2-matter-memory.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
const PRIVACY_MATTER = '47519e68-d764-4a3f-b96b-2d703c16229c';
const SNAPSHOT_ID = 'aaaaaaaa-0000-0000-0000-000000000001';

const MEMORY = {
	project_id: PRIVACY_MATTER,
	wiki: {
		content_md:
			'## Working summary\n\nAcme MSA renewal. Governing law **England & Wales**. ' +
			'Counterparty is *Acme UK Ltd*.\n\n- Liability cap under negotiation.\n- DPA outstanding.',
		char_count: 142,
		version_count: 2
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
		},
		{
			id: 'fact-2',
			body_md: 'Liability cap proposed at 12 months’ fees.',
			fact_type: 'position',
			source_citation: null,
			author: 'agent',
			valid_at: null,
			created_at: '2026-05-03T00:00:00Z'
		}
	],
	corrections: [
		{
			id: 'corr-1',
			body_md: 'The counterparty entity is **Acme UK Ltd**, not Acme Inc.',
			trust: 'pinned',
			created_at: '2026-05-03T12:00:00Z'
		}
	],
	log: [
		{
			id: SNAPSHOT_ID,
			kind: 'wiki_snapshot',
			created_at: '2026-05-04T09:00:00Z',
			run_id: 'run-deadbeef-0001',
			author: 'agent',
			fact_type: null,
			source_citation: null,
			superseded: false,
			body_preview: 'Prior summary — before the liability-cap position landed.'
		},
		{
			id: 'log-2',
			kind: 'fact',
			created_at: '2026-05-03T00:00:00Z',
			run_id: 'run-deadbeef-0002',
			author: 'agent',
			fact_type: 'position',
			source_citation: null,
			superseded: true,
			body_preview: 'Earlier liability-cap position (since superseded).'
		}
	],
	log_total: 7
};

const REVERT_RESPONSE = {
	reverted_to_snapshot_id: SNAPSHOT_ID,
	snapshotted_prior: true,
	wiki: { content_md: 'Prior summary', char_count: 13, version_count: 3 }
};

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
	// In stacked/narrow mode a fresh deep-link (no thread) shows the thread LIST,
	// not the panel where the matter tab strip lives — enter the panel first.
	cy.get('body').then(($b) => {
		if ($b.find('[data-testid="lq-cockpit-matter-tab-memory"]').length === 0) {
			cy.get('[data-testid="lq-cockpit-new-conversation"]').first().click();
		}
	});
	// The Memory tab is present on every matter (here, beside the ROPA register).
	cy.get('[data-testid="lq-cockpit-matter-tab-memory"]', { timeout: 30000 })
		.should('be.visible')
		.click();
	cy.wait('@getMemory');
	cy.get('[data-testid="lq-matter-memory"]', { timeout: 30000 }).should('be.visible');
}

describe('C3c-2 — cockpit matter-memory panel', { retries: { runMode: 2, openMode: 0 } }, () => {
	beforeEach(() => {
		cy.intercept('GET', '/api/v1/matters/*/memory', { statusCode: 200, body: MEMORY }).as(
			'getMemory'
		);
		cy.intercept('POST', '/api/v1/matters/*/memory/wiki/revert', {
			statusCode: 200,
			body: REVERT_RESPONSE
		}).as('revert');
	});

	it('renders the four sections and reverts a wiki version behind a confirm step', () => {
		cy.viewport(1440, 900);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
		openMemory();

		// The four sections render, fed by the composite GET.
		cy.get('[data-testid="lq-memory-wiki"]').should('contain.text', 'Working summary');
		cy.get('[data-testid="lq-memory-facts"]').should('contain.text', 'Facts (2)');
		cy.get('[data-testid="lq-memory-corrections"]').should(
			'contain.text',
			'Pinned corrections (1)'
		);
		cy.get('[data-testid="lq-memory-log"]').should('contain.text', 'Activity (7)');
		// Tail note (log_total 7 > 2 shown).
		cy.get('[data-testid="lq-memory-log"]').should('contain.text', 'most recent of 7');

		// Revert: a wiki_snapshot row offers "Restore this version" → confirm dialog.
		cy.get('[data-testid="lq-memory-restore"]').first().should('be.enabled').click();
		cy.get('[role="dialog"]').should('be.visible').and('contain.text', 'Restore this version?');
		cy.get('[data-testid="lq-memory-revert-confirm"]').click();

		cy.wait('@revert').its('request.body').should('deep.equal', { snapshot_id: SNAPSHOT_ID });
		// On success the dialog dismisses and the panel refetches the composite.
		cy.get('[role="dialog"]').should('not.exist');
		cy.get('@getMemory.all').should('have.length.greaterThan', 1);
	});

	it('capture — memory panel: light/dark × wide/narrow', () => {
		const sizes = [
			{ name: 'wide', w: 1440, h: 900 },
			{ name: 'narrow', w: 700, h: 900 }
		] as const;
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
		for (const s of sizes) {
			cy.viewport(s.w, s.h);
			openMemory();
			for (const theme of ['light', 'dark'] as const) {
				pinTheme(theme);
				// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
				cy.wait(300);
				cy.screenshot(`c3c2-memory-${s.name}-${theme}`, { capture: 'viewport' });
			}
			pinTheme('light');
		}
	});
});
