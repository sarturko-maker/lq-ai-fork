/**
 * In-app Word editor — Slice 4 (ADR-F047). LIVE visual check against the real
 * stack: opens a real agent-redlined .docx in the cockpit editor, proves the
 * Collabora iframe loads the document through the new root-path nginx proxy
 * (CheckFileInfo + GetFile + the editing websocket), and captures the
 * conversation-left / editor-right layout light+dark × wide+narrow.
 *
 * This is NOT a CI gate (CI runs svelte-check + Vitest only) — it needs the live
 * stack + the Collabora container. Run headed for an honest capture:
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/libreoffice-editor.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 *
 * The matter + file are real rows in the dev DB (admin-owned Atlas, Commercial);
 * the redline is the agent's `created_by_run_id` output, so the first save would
 * exercise the Slice-3 snapshot-then-mutate path.
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
const MATTER = '905720d1-5d17-43cd-a8f0-3a76d095de34'; // Atlas (Commercial)
const COMPLETED_THREAD = '0dd52a2b-a0af-4075-9c9a-10a72e911555'; // Atlas, has a completed run
const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

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

// Wait for Collabora to actually paint the document inside the same-origin
// iframe (cold-start boots a jailed LOK + the websocket). We poll the iframe's
// own document for the editor canvas.
function waitForDocumentRender() {
	cy.get('[data-testid="lq-editor-frame"]', { timeout: 30000 }).should('exist');
	// Collabora renders the document onto a <canvas> inside the same-origin
	// iframe; its presence proves CheckFileInfo + GetFile + the websocket worked.
	cy.get('[data-testid="lq-editor-frame"]', { timeout: 90000 }).should(($f) => {
		const doc = ($f[0] as HTMLIFrameElement).contentDocument;
		expect(doc, 'iframe document').to.exist;
		expect(doc!.querySelector('canvas'), 'editor canvas').to.exist;
	});
	// Generous settle so the document tiles are painted in the capture (Collabora
	// cold-start boots a jailed LOK + websocket before the first tiles arrive).
	cy.wait(16000);
	// The save-state pill appears once Collabora's postMessage lifecycle reaches us
	// (Document_Loaded). Observed, not gated, so a capture is never blocked on it.
	cy.get('[data-testid="lq-document-editor"]').then(($panel) => {
		const pill = $panel.find('[data-testid="lq-editor-savestate"]');
		cy.log(`editor save-state: ${pill.length ? pill.text().trim() : '(no postMessage yet)'}`);
	});
}

// The fitted document must fill the pane width without overflowing. Collabora's
// zoom steps are ~1.2×/level so the guaranteed no-overflow fill is >0.99/1.2 ≈
// 0.83 (≈0.98 at the 1920 pane); 0.8 catches the ~0.68 undershoot regression. We
// also assert <1.0 so an overflow (which would clip text at the right edge) fails.
function assertDocFillsPane(label: string) {
	cy.get('[data-testid="lq-editor-frame"]').should(($f) => {
		const map = (
			($f[0] as HTMLIFrameElement).contentWindow as unknown as {
				app?: {
					map?: { getSize?: () => { x: number }; _docLayer?: { _docPixelSize?: { x: number } } };
				};
			} | null
		)?.app?.map;
		const docPx = map?._docLayer?._docPixelSize?.x;
		const paneX = map?.getSize?.().x;
		const ratio = docPx && paneX ? docPx / paneX : 0;
		expect(
			ratio,
			`document fills the pane width @ ${label} (no whitespace, no overflow)`
		).to.be.within(0.8, 1.0);
	});
}

describe('in-app Word editor (ADR-F047, Slice 4)', () => {
	it('opens an agent redline and renders it in the cockpit editor', () => {
		cy.viewport(1440, 900);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
		openEditorFromDocuments();

		// Our chrome: the file name + the close affordance + the save-state pill.
		cy.get('[data-testid="lq-document-editor"]').within(() => {
			cy.contains('Cirrus-Analytics-MSA-Draft');
			cy.get('[data-testid="lq-editor-close"]').should('exist');
		});

		waitForDocumentRender();

		// 4b regression A: the editor section must FILL its 2/3 card slot. The bug was
		// the <section> lacked w-full, so it shrank to ~iframe intrinsic width (~544px)
		// and left whitespace to the right of the document inside the 2/3 pane.
		cy.get('[data-testid="lq-cockpit-editor"]').then(($card) => {
			const cardW = ($card[0] as HTMLElement).offsetWidth;
			cy.get('[data-testid="lq-document-editor"]').should(($sec) => {
				const secW = ($sec[0] as HTMLElement).offsetWidth;
				expect(secW / cardW, 'editor section fills its card slot').to.be.greaterThan(0.98);
			});
		});

		// 4b regression B: prove the iterative fit-to-width filled the pane.
		assertDocFillsPane('1440');

		// Capture the conversation-left / editor-right layout in both themes + sizes.
		// 1920 matches a real wide monitor (where the un-filled-section bug was stark).
		const sizes = [
			{ name: 'ultrawide', w: 1920, h: 1080 },
			{ name: 'wide', w: 1440, h: 900 },
			{ name: 'narrow', w: 1024, h: 768 }
		];
		for (const s of sizes) {
			cy.viewport(s.w, s.h);
			// Let the resize-driven re-fit re-converge to the new pane width, then assert
			// the fit holds at THIS width before capturing.
			cy.wait(4000);
			assertDocFillsPane(s.name);
			for (const theme of ['light', 'dark'] as const) {
				pinTheme(theme);
				cy.wait(500);
				cy.screenshot(`slice4-editor-${s.name}-${theme}`, { capture: 'viewport' });
			}
		}

		// Close slides the editor away and restores the single-pane conversation.
		cy.viewport(1440, 900);
		pinTheme('light');
		cy.get('[data-testid="lq-editor-close"]').click();
		cy.get('[data-testid="lq-document-editor"]').should('not.exist');
		cy.screenshot('slice4-editor-closed', { capture: 'viewport' });
	});

	// Deterministic regression for the maintainer's HEADLINE flow: when the agent
	// produces a redline while the conversation is open, the editor must AUTO-open
	// (no manual Edit click). The matter-files endpoint is intercepted to go
	// empty → +redline (a redline appearing AFTER thread-open); editor-session +
	// discovery are stubbed so the panel opens without a live Collabora doc. This
	// fails on the pre-fix code (which seeded the freshly-produced redline as
	// "already seen" and never opened it).
	it('auto-opens the editor when a redline appears after the conversation opens', () => {
		cy.viewport(1440, 900);
		const REDLINE = {
			id: 'feeed000-0000-0000-0000-0000000000a1',
			filename: 'Auto Cirrus MSA (redlined).docx',
			mime_type: DOCX_MIME,
			size_bytes: 4242,
			ingestion_status: 'ready',
			created_at: '2026-06-25T12:00:00Z',
			created_by_run_id: 'feeed000-0000-0000-0000-0000000000b2'
		};
		let filesCalls = 0;
		cy.intercept('GET', '/api/v1/matters/*/files', (req) => {
			filesCalls += 1;
			// 1st call = the baseline (existing-at-open) → empty; later = the redline appeared.
			req.reply({ body: { project_id: MATTER, files: filesCalls <= 1 ? [] : [REDLINE] } });
		}).as('files');
		cy.intercept('POST', '/api/v1/files/*/editor-session', {
			body: {
				access_token: 'stub-token',
				access_token_ttl: 9999999999999,
				wopi_src: 'http://api:8000/api/v1/wopi/files/stub'
			}
		});
		cy.intercept('GET', '/hosting/discovery', {
			headers: { 'content-type': 'application/xml' },
			body: '<wopi-discovery><net-zone><app name="application/vnd.openxmlformats-officedocument.wordprocessingml.document"><action name="edit" ext="docx" urlsrc="http://localhost:3000/browser/stub/cool.html?"/></app></net-zone></wopi-discovery>'
		});

		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
		cy.visit(`/lq-ai?area=commercial&matter=${MATTER}&thread=${COMPLETED_THREAD}`);

		// No manual Edit click — the editor slides in on its own.
		cy.get('[data-testid="lq-document-editor"]', { timeout: 20000 }).should('be.visible');
		cy.get('[data-testid="lq-document-editor"]').contains('Auto Cirrus MSA (redlined).docx');
		cy.screenshot('slice4-auto-open', { capture: 'viewport' });
	});
});
