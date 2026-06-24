/**
 * C7a — cockpit matter Documents tab + redline download (ADR-F046).
 *
 * The cockpit now shows a "Documents" tab on EVERY matter (area-agnostic) listing
 * the matter's files (`GET /api/v1/matters/{id}/files`) — uploads plus the agent's
 * redline outputs — each with a Download button that streams the bytes from the
 * existing `GET /api/v1/files/{id}/content`.
 *
 * We drive the REAL seeded Privacy matter (so the cockpit renders ConversationHost,
 * mirrors c3c2-matter-memory.cy.ts); the files listing + content are INTERCEPTED so
 * the panel is deterministic regardless of the matter's actual stored files.
 *
 * Run (live stack, headed for an honest light+dark capture):
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/c7a-documents.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
const PRIVACY_MATTER = '47519e68-d764-4a3f-b96b-2d703c16229c';
const REDLINE_FILE = 'bbbbbbbb-0000-0000-0000-000000000002';

const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

const FILES = {
	project_id: PRIVACY_MATTER,
	files: [
		{
			id: REDLINE_FILE,
			filename: 'Acme MSA (redlined).docx',
			mime_type: DOCX_MIME,
			size_bytes: 53_400,
			ingestion_status: 'ready',
			created_at: '2026-05-04T09:00:00Z',
			created_by_run_id: 'run-deadbeef-0001'
		},
		{
			id: 'aaaaaaaa-0000-0000-0000-000000000001',
			filename: 'Acme MSA.docx',
			mime_type: DOCX_MIME,
			size_bytes: 51_200,
			ingestion_status: 'ready',
			created_at: '2026-05-01T09:00:00Z',
			created_by_run_id: null
		}
	]
};

function pinTheme(theme: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', theme);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(theme);
	});
	cy.get('html').should('have.class', theme);
}

function openDocuments() {
	cy.visit(`/lq-ai?area=privacy&matter=${PRIVACY_MATTER}`);
	cy.get('[data-testid="lq-cockpit-conversation"]', { timeout: 30000 }).should('exist');
	// In stacked/narrow mode a fresh deep-link (no thread) shows the thread LIST,
	// not the panel where the matter tab strip lives — enter the panel first.
	cy.get('body').then(($b) => {
		if ($b.find('[data-testid="lq-cockpit-matter-tab-documents"]').length === 0) {
			cy.get('[data-testid="lq-cockpit-new-conversation"]').first().click();
		}
	});
	cy.get('[data-testid="lq-cockpit-matter-tab-documents"]', { timeout: 30000 })
		.should('be.visible')
		.click();
	cy.wait('@listFiles');
	cy.get('[data-testid="lq-matter-documents"]', { timeout: 30000 }).should('be.visible');
}

describe('C7a — cockpit Documents tab', { retries: { runMode: 2, openMode: 0 } }, () => {
	beforeEach(() => {
		cy.intercept('GET', '/api/v1/matters/*/files', { statusCode: 200, body: FILES }).as(
			'listFiles'
		);
		// The download fetch (apiBlobRequest → GET /files/{id}/content). A tiny body +
		// attachment disposition is enough to drive the blob → <a download> path.
		cy.intercept('GET', '/api/v1/files/*/content', {
			statusCode: 200,
			headers: {
				'content-type': DOCX_MIME,
				'content-disposition': 'attachment; filename="Acme MSA (redlined).docx"'
			},
			body: 'PK fake docx bytes'
		}).as('downloadContent');
	});

	it('lists the matter files and downloads one', () => {
		cy.viewport(1440, 900);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
		openDocuments();

		// Both files render; the redline output carries the "Redline" badge.
		cy.get('[data-testid="lq-documents-row"]').should('have.length', 2);
		cy.get('[data-testid="lq-documents-list"]').should('contain.text', 'Acme MSA (redlined).docx');
		cy.get('[data-testid="lq-documents-list"]').should('contain.text', 'Redline');
		cy.get('[data-testid="lq-documents-list"]').should('contain.text', 'Acme MSA.docx');

		// Download the redline output → hits GET /files/{id}/content.
		cy.get('[data-testid="lq-documents-download"]').first().click();
		cy.wait('@downloadContent')
			.its('request.url')
			.should('include', `/files/${REDLINE_FILE}/content`);
	});

	it('capture — Documents tab: light/dark × wide/narrow', () => {
		const sizes = [
			{ name: 'wide', w: 1440, h: 900 },
			{ name: 'narrow', w: 700, h: 900 }
		] as const;
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
		for (const s of sizes) {
			cy.viewport(s.w, s.h);
			openDocuments();
			for (const theme of ['light', 'dark'] as const) {
				pinTheme(theme);
				// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
				cy.wait(300);
				cy.screenshot(`c7a-documents-${s.name}-${theme}`, { capture: 'viewport' });
			}
			pinTheme('light');
		}
	});
});
