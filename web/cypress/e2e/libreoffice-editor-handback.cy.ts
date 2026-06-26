/**
 * In-app Word editor — Slice 5 hand-back (ADR-F047). LIVE check against the real
 * stack: opens a real agent redline in the cockpit editor, proves the new "Done —
 * hand back" affordance, then exercises the hand-back — the editor closes and the
 * conversation composer is PRIMED with an editable instruction naming the document
 * (the lawyer sends it; the existing createRun({prompt, thread_id}) resumes the run
 * and the agent calls review_edited_document). Captures the button + the primed
 * composer light+dark.
 *
 * NOT a CI gate (CI runs svelte-check + Vitest only) — needs the live stack +
 * Collabora. Run headed for an honest capture:
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/libreoffice-editor-handback.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
const MATTER = '905720d1-5d17-43cd-a8f0-3a76d095de34'; // Atlas (Commercial)

function pinTheme(theme: 'light' | 'dark') {
	cy.window().then((win) => {
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(theme);
		win.localStorage.setItem('lq-theme', theme);
	});
}

function openEditorFromDocuments() {
	cy.visit(`/lq-ai?area=commercial&matter=${MATTER}`);
	cy.get('[data-testid="lq-cockpit-matter-tab-documents"]', { timeout: 20000 }).click();
	cy.get('[data-testid="lq-documents-edit"]', { timeout: 20000 }).first().click();
	cy.get('[data-testid="lq-document-editor"]', { timeout: 20000 }).should('be.visible');
}

describe('editor hand-back (ADR-F047, Slice 5)', () => {
	it('hands back to the agent: closes the editor and primes the composer', () => {
		cy.viewport(1440, 900);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
		openEditorFromDocuments();

		// The new chrome: both "Done — hand back" and Close are present.
		cy.get('[data-testid="lq-document-editor"]').within(() => {
			cy.get('[data-testid="lq-editor-handback"]').should('exist');
			cy.get('[data-testid="lq-editor-close"]').should('exist');
		});

		// Prove the live editor actually loads the document (CheckFileInfo + GetFile +
		// the editing websocket) — the document canvas appears inside the same-origin
		// iframe. The hand-back button is enabled once the editor is ready; it does NOT
		// wait on Collabora's flaky Document_Loaded postMessage.
		cy.get('[data-testid="lq-editor-frame"]', { timeout: 30000 }).should('exist');
		cy.get('[data-testid="lq-editor-frame"]', { timeout: 90000 }).should(($f) => {
			const doc = ($f[0] as HTMLIFrameElement).contentDocument;
			expect(doc, 'iframe document').to.exist;
			expect(doc!.querySelector('canvas'), 'editor canvas').to.exist;
		});
		cy.wait(12000); // settle Collabora's tiles for the capture
		cy.get('[data-testid="lq-editor-handback"]').should('not.be.disabled');

		// Capture the editor WITH the hand-back affordance, both themes.
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			cy.wait(400);
			cy.screenshot(`slice5-editor-handback-${theme}`, { capture: 'viewport' });
		}
		pinTheme('light');

		// Drive Collabora's "document loaded" lifecycle signal deterministically — it is
		// reliable on a real human open but flaky under headless automation — so the doc
		// reads as clean and the hand-back takes the immediate path. This is the SAME
		// message Collabora posts in production; we are exercising OUR hand-back wiring.
		cy.window().then((win) => {
			win.postMessage(
				JSON.stringify({ MessageId: 'App_LoadingStatus', Values: { Status: 'Document_Loaded' } }),
				win.location.origin
			);
		});
		cy.wait(300);

		// The document name shown in the chrome — it must be echoed into the primed
		// composer instruction.
		cy.get('[data-testid="lq-document-editor"]')
			.find('span[title]')
			.first()
			.invoke('attr', 'title')
			.then((fname) => {
				const filename = String(fname);

				// Hand back: the editor tears down and returns to the conversation.
				cy.get('[data-testid="lq-editor-handback"]').click();
				cy.get('[data-testid="lq-document-editor"]', { timeout: 20000 }).should('not.exist');

				// The composer is primed with an editable instruction that NAMES the document
				// and asks the agent to re-read + incorporate (drives review_edited_document).
				cy.get('#ag-prompt', { timeout: 10000 }).should(($t) => {
					const v = ($t[0] as HTMLTextAreaElement).value;
					expect(v, 'composer primed with the document name').to.contain(filename);
					expect(v.toLowerCase(), 'asks the agent to re-read').to.contain('re-read');
					expect(v.toLowerCase(), 'asks the agent to incorporate').to.contain('incorporate');
				});
				cy.get('#ag-prompt').should('be.focused');
				cy.screenshot('slice5-composer-primed', { capture: 'viewport' });
			});
	});
});
