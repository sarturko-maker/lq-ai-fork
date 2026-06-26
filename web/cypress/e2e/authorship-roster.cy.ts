/**
 * ADR-F048 — the authorship roster (who-is-who) human-amend UX.
 *
 * On the cockpit Memory panel, a new **Participants** section lets the supervising
 * lawyer ADD, EDIT and REMOVE who is who on the matter (each person → a side
 * ours/counterparty/unknown the agent uses to tell whose tracked changes are whose).
 * The composite GET and the roster POST/PATCH/retire are INTERCEPTED so the panel is
 * deterministic; the matter is real only so the cockpit renders ConversationHost
 * (mirrors c3-update-memory.cy.ts). The disabled-while-a-run-is-active gate is
 * host-driven and covered by the `canWrite` unit test, not forced here.
 *
 * Run (live stack, headed):
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/authorship-roster.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
const PRIVACY_MATTER = '47519e68-d764-4a3f-b96b-2d703c16229c';

const MEMORY = {
	project_id: PRIVACY_MATTER,
	wiki: { content_md: '## Working summary\n\nAcme MSA renewal.', char_count: 40, version_count: 0 },
	facts: [],
	corrections: [],
	roster: [
		{
			id: 'part-1',
			display_name: 'Mark Counsel',
			aliases: ['mcounsel@beta.example'],
			organization: 'Beta LLP',
			role_label: 'Their counsel',
			side: 'counterparty',
			trust: 'inferred',
			source_citation: 'From line of round-2.eml',
			created_at: '2026-05-03T00:00:00Z',
			updated_at: '2026-05-03T00:00:00Z'
		},
		{
			// ADR-F048 Slice 2: a known third party — its own 'other' (Third party) side.
			id: 'part-2',
			display_name: 'Iron Mountain',
			aliases: [],
			organization: 'Iron Mountain Inc.',
			role_label: 'Escrow agent',
			side: 'other',
			trust: 'confirmed',
			source_citation: 'Matter brief',
			created_at: '2026-05-04T00:00:00Z',
			updated_at: '2026-05-04T00:00:00Z'
		}
	],
	log: [],
	log_total: 1
};

const CREATED = {
	id: 'part-new',
	display_name: 'Jane Smith',
	aliases: [],
	organization: null,
	role_label: 'Lead counsel',
	side: 'ours',
	trust: 'confirmed',
	source_citation: null,
	created_at: '2026-06-26T00:00:00Z',
	updated_at: '2026-06-26T00:00:00Z'
};

const UPDATED = { ...MEMORY.roster[0], side: 'ours', trust: 'confirmed' };
const RETIRED = { id: 'part-1', retired_at: '2026-06-26T12:00:00Z' };

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
	'ADR-F048 — the authorship roster human-amend gestures',
	{ retries: { runMode: 2, openMode: 0 } },
	() => {
		beforeEach(() => {
			cy.intercept('GET', '/api/v1/matters/*/memory', { statusCode: 200, body: MEMORY }).as(
				'getMemory'
			);
			cy.intercept('POST', '**/roster', { statusCode: 201, body: CREATED }).as('createParticipant');
			cy.intercept('PATCH', '**/roster/*', { statusCode: 200, body: UPDATED }).as(
				'updateParticipant'
			);
			cy.intercept('POST', '**/roster/*/retire', { statusCode: 200, body: RETIRED }).as(
				'retireParticipant'
			);
		});

		it('adds, edits, and removes a participant', () => {
			cy.viewport(1440, 900);
			login(ADMIN_EMAIL(), ADMIN_PASSWORD());
			openMemory();

			// The seeded counterparty participant renders with its side badge.
			cy.get('[data-testid="lq-memory-roster"]').should('contain.text', 'Mark Counsel');
			cy.get('[data-testid="lq-memory-roster"]').should('contain.text', 'Counterparty');

			// 1) Add a participant (name + side ours + role).
			cy.get('[data-testid="lq-roster-add"]').should('be.enabled').click();
			cy.get('[data-testid="lq-roster-name"]').should('be.visible').type('Jane Smith');
			cy.get('[data-testid="lq-roster-side"]').select('ours');
			cy.get('[data-testid="lq-roster-role"]').type('Lead counsel');
			cy.get('[data-testid="lq-roster-aliases"]').type('jsmith@acme.example');
			cy.get('[data-testid="lq-roster-submit"]').should('be.enabled').click();
			cy.wait('@createParticipant')
				.its('request.body')
				.should((body) => {
					expect(body.display_name).to.equal('Jane Smith');
					expect(body.side).to.equal('ours');
					expect(body.role_label).to.equal('Lead counsel');
					expect(body.aliases).to.deep.equal(['jsmith@acme.example']);
				});
			cy.get('[data-testid="lq-roster-form"]').should('not.exist');
			cy.get('@getMemory.all').should('have.length.greaterThan', 1);

			// 2) Edit the seeded participant — the form pre-fills; change the side.
			cy.get('[data-testid="lq-roster-edit"]').first().click();
			cy.get('[data-testid="lq-roster-name"]').should('have.value', 'Mark Counsel');
			cy.get('[data-testid="lq-roster-side"]').select('ours');
			cy.get('[data-testid="lq-roster-submit"]').click();
			cy.wait('@updateParticipant')
				.its('request.body')
				.should((body) => {
					expect(body.side).to.equal('ours');
				});

			// 3) Remove a participant behind a confirm step.
			cy.get('[data-testid="lq-roster-remove"]').first().click();
			cy.get('[role="dialog"]')
				.should('be.visible')
				.and('contain.text', 'Remove this participant?');
			cy.get('[data-testid="lq-memory-retire-confirm"]').click();
			cy.wait('@retireParticipant');
			cy.get('[role="dialog"]').should('not.exist');
		});

		it('renders and offers the third-party (other) side', () => {
			cy.viewport(1440, 900);
			login(ADMIN_EMAIL(), ADMIN_PASSWORD());
			openMemory();

			// The seeded third party renders with the "Third party" badge (ADR-F048 Slice 2).
			cy.get('[data-testid="lq-memory-roster"]').should('contain.text', 'Iron Mountain');
			cy.get('[data-testid="lq-memory-roster"]').should('contain.text', 'Third party');

			// The add form's side <select> offers 'other' so the lawyer can classify a third party.
			cy.get('[data-testid="lq-roster-add"]').click();
			cy.get('[data-testid="lq-roster-side"]').find('option[value="other"]').should('exist');
			cy.get('[data-testid="lq-roster-side"]').select('other');
			cy.get('[data-testid="lq-roster-side"]').should('have.value', 'other');
			cy.contains('button', 'Cancel').click();
		});

		it('capture — the Participants section + add form: light/dark', () => {
			cy.viewport(1440, 900);
			login(ADMIN_EMAIL(), ADMIN_PASSWORD());
			openMemory();
			for (const theme of ['light', 'dark'] as const) {
				pinTheme(theme);
				// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
				cy.wait(300);
				cy.screenshot(`f048-roster-${theme}`, { capture: 'viewport' });
				cy.get('[data-testid="lq-roster-add"]').click();
				cy.get('[data-testid="lq-roster-name"]').type('Jane Smith');
				cy.get('[data-testid="lq-roster-side"]').select('ours');
				// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
				cy.wait(200);
				cy.screenshot(`f048-roster-form-${theme}`, { capture: 'viewport' });
				cy.contains('button', 'Cancel').click();
			}
			pinTheme('light');
		});
	}
);
