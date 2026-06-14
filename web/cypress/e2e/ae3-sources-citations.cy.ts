/**
 * AE3 — Sources + Inline Citation (ADR-F011).
 *
 * Two surfaces:
 *
 *   1. The internal lab (`/lq-ai/_ae-lab`, auth-gated, no API of its own) drives
 *      the AE3 Sources card DETERMINISTICALLY: three documents with mixed
 *      verification states — two green (exact), one amber (paraphrase), one grey
 *      (unverified) → "Used 3 sources", each row a filename + passages·pages
 *      meta + a quote + a 5-state marker (badge-check / circle-alert).
 *
 *   2. The live chat workspace (`/lq-ai/chats`) with backend-free fixtures + a
 *      stubbed citations endpoint (rows carrying `source_filename`), to prove the
 *      Sources card binds to real per-message data + for the before/after shots.
 *
 * The functional `describe` asserts AE3-only behaviour and is skipped under
 * CAPTURE_ONLY=1 (the pre-AE3 bundle has no Sources card). The capture
 * `describe` is element-guarded so it can run on BOTH phases.
 *
 * Run (live stack, headed for honest dark capture):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ae3-sources-citations.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!,PHASE=after
 */
const PHASE = () => (Cypress.env('PHASE') as string) || 'after';
const CAPTURE_ONLY = String(Cypress.env('CAPTURE_ONLY')) === '1';

const NOW = '2026-06-14T10:00:00Z';
const PROJ_ID = '00000000-0000-4000-8000-0000000000c1';
const CHAT_ID_SHORT = '00000000-0000-4000-8000-0000000000c9';

// cy.session caches the token so we hit the auth backend ONCE per spec (the
// per-user session cap + bcrypt cost make rapid repeated logins flaky under
// load — see auth-refresh-scan-blank-fix).
function login() {
	cy.session('lq-admin', () => {
		cy.visit('/lq-ai/login');
		cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
		cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!');
		cy.get('button[type="submit"]').click();
		cy.url({ timeout: 30000 }).should('not.include', '/login');
	});
}

describe('AE3 — Sources + Inline Citation', { retries: { runMode: 2, openMode: 0 } }, () => {
	if (!CAPTURE_ONLY) {
		describe('lab — sources card', () => {
			beforeEach(() => {
				login();
				cy.visit('/lq-ai/_ae-lab');
				cy.get('[data-testid="ae-lab-sources"]', { timeout: 30000 }).should('be.visible');
			});

			it('summarises the distinct documents and is collapsed by default', () => {
				cy.get('[data-testid="ae-lab-sources"] [data-testid="lq-ai-sources"]').should('exist');
				cy.get('[data-testid="ae-lab-sources"] [data-testid="lq-ai-sources"] summary span')
					.first()
					.should('have.text', 'Used 3 sources');
				cy.get('[data-testid="ae-lab-sources"] [data-testid="lq-ai-sources"]').should(
					'not.have.attr',
					'open'
				);
			});

			it('expands to one entry per document with names, meta, and 5-state markers', () => {
				cy.get('[data-testid="ae-lab-sources"] [data-testid="lq-ai-sources"] summary').click();
				const root = '[data-testid="ae-lab-sources"] ';
				cy.get(root + '[data-testid="lq-ai-source"]').should('have.length', 3);

				// Names (auto-escaped text bindings).
				cy.get(root + '[data-testid="lq-ai-source"]')
					.first()
					.should('contain.text', 'Master Services Agreement.pdf')
					.and('contain.text', '2 passages · pp. 12, 13');

				// Verification rollup: 2 verified (green/amber badge-check) + 1
				// unverified (grey circle-alert).
				cy.get(root + '[data-testid="lq-ai-source"] svg.lucide-badge-check').should(
					'have.length',
					2
				);
				cy.get(root + '[data-testid="lq-ai-source"] svg.lucide-circle-alert').should(
					'have.length',
					1
				);
				cy.get(root + '[data-testid="lq-ai-source"][data-state="unverified"]')
					.should('contain.text', 'Side Letter (unsigned).pdf')
					.find('svg.lucide-circle-alert')
					.should('exist');
			});
		});

		describe('live chat — sources on a real assistant message', () => {
			beforeEach(() => {
				stubChat(CITATIONS);
				login();
			});

			it('renders the Sources card with the joined filename, under the assistant turn only', () => {
				cy.visit(`/lq-ai/chats?id=${CHAT_ID_SHORT}`);
				cy.get('[data-testid="lq-ai-message-m-asst-1"]', { timeout: 30000 }).should('exist');
				cy.get('[data-testid="lq-ai-message-m-asst-1"] [data-testid="lq-ai-sources"]', {
					timeout: 30000
				}).should('exist');
				cy.get(
					'[data-testid="lq-ai-message-m-asst-1"] [data-testid="lq-ai-sources"] summary'
				).should('contain.text', 'Used 3 sources');
				cy.get('[data-testid="lq-ai-message-m-asst-1"] [data-testid="lq-ai-sources"] summary').click();
				cy.get('[data-testid="lq-ai-message-m-asst-1"] [data-testid="lq-ai-source"]')
					.first()
					.should('contain.text', 'Master Services Agreement.pdf');
				// The user turn carries NO sources card.
				cy.get(
					'[data-testid="lq-ai-message-m-user-1"] [data-testid="lq-ai-sources"]'
				).should('not.exist');
			});
		});
	}

	// ---- before/after capture ----
	describe('capture', () => {
		it('captures the lab Sources card (light + dark)', () => {
			login();
			for (const theme of ['light', 'dark'] as const) {
				cy.window().then((w) => w.localStorage.setItem('theme', theme));
				cy.visit('/lq-ai/_ae-lab');
				cy.get('[data-testid="ae-lab-sources"]', { timeout: 30000 }).should('be.visible');
				cy.window().then((win) => {
					win.localStorage.setItem('theme', theme);
					win.document.documentElement.classList.remove('light', 'dark');
					win.document.documentElement.classList.add(theme);
				});
				cy.get('html').should('have.class', theme);
				// Expand the card so the rows + markers are in frame, then nudge.
				cy.get('[data-testid="ae-lab-sources"] [data-testid="lq-ai-sources"]').then(($d) => {
					if (!$d.attr('open')) {
						cy.wrap($d).find('summary').click();
					}
				});
				cy.viewport(1281, 900);
				cy.viewport(1280, 900);
				cy.wait(300);
				cy.get('[data-testid="ae-lab-sources"]').scrollIntoView();
				cy.screenshot(`ae3-${PHASE()}-lab-sources-${theme}`, { capture: 'viewport' });
			}
		});

		it('captures the chat surface with the Sources card (light + dark, wide + narrow)', () => {
			stubChat(CITATIONS);
			login();
			for (const theme of ['light', 'dark'] as const) {
				cy.window().then((w) => w.localStorage.setItem('theme', theme));
				cy.visit(`/lq-ai/chats?id=${CHAT_ID_SHORT}`);
				cy.get('[data-testid="lq-ai-message-list"]', { timeout: 30000 }).should('exist');
				cy.window().then((win) => {
					win.localStorage.setItem('theme', theme);
					win.document.documentElement.classList.remove('light', 'dark');
					win.document.documentElement.classList.add(theme);
				});
				cy.get('html').should('have.class', theme);
				cy.get('[data-testid="lq-ai-message-m-asst-1"]').should('be.visible');
				// Open the card if present (absent on the pre-AE3 "before" bundle).
				cy.get('[data-testid="lq-ai-message-m-asst-1"]').then(($m) => {
					const $s = $m.find('[data-testid="lq-ai-sources"] summary');
					if ($s.length) cy.wrap($s).click();
				});

				cy.viewport(1281, 900);
				cy.viewport(1280, 900);
				cy.wait(300);
				cy.screenshot(`ae3-${PHASE()}-chat-${theme}-wide`, { capture: 'viewport' });

				cy.viewport(701, 900);
				cy.viewport(700, 900);
				cy.wait(300);
				cy.screenshot(`ae3-${PHASE()}-chat-${theme}-narrow`, { capture: 'viewport' });
			}
		});
	});
});

// --- fixtures (mirrors ae2-reasoning-actions.cy.ts SHORT fixture) ---
const PROJECT = {
	id: PROJ_ID,
	name: 'Acme ⇄ Globex Merger',
	slug: 'acme-globex',
	description: null,
	context_md: null,
	owner_id: 'admin',
	privileged: false,
	minimum_inference_tier: null,
	attached_skill_names: [],
	attached_file_ids: [],
	attached_knowledge_base_ids: [],
	archived_at: null,
	is_sandbox: false,
	created_at: NOW,
	updated_at: NOW
};
const CHATS = {
	items: [
		{
			id: CHAT_ID_SHORT,
			title: 'Indemnity (short)',
			owner_id: 'admin',
			project_id: PROJ_ID,
			archived_at: null,
			message_count: 0,
			created_at: NOW,
			updated_at: NOW
		}
	],
	next_cursor: null
};
const MESSAGES_SHORT = {
	items: [
		{
			id: 'm-user-1',
			chat_id: CHAT_ID_SHORT,
			role: 'user',
			content: 'Summarise the indemnity cap and survival periods in the disclosure schedule.',
			created_at: NOW
		},
		{
			id: 'm-asst-1',
			chat_id: CHAT_ID_SHORT,
			role: 'assistant',
			content:
				'<think>Check the cap clause, then the survival table.</think>' +
				'Here is the **indemnity position**:\n\n' +
				'- **Cap:** 15% of the purchase price\n' +
				'- **General reps:** 12-month survival\n\n' +
				'See the *cap clause* for the de-minimis basket.',
			routed_inference_tier: 4,
			routed_provider: 'minimax',
			routed_model: 'MiniMax-M3',
			created_at: NOW
		}
	],
	next_cursor: null
};

// Persisted MessageCitation rows (AE3: each carries the LEFT-joined
// `source_filename`). Two passages in one document (green/exact), one paraphrase
// (amber), one failed (grey) → the card rolls up to "Used 3 sources".
const CITATIONS = [
	{
		id: 'cite-1',
		source_file_id: 'f1',
		source_filename: 'Master Services Agreement.pdf',
		source_offset_start: 0,
		source_offset_end: 10,
		source_page: 12,
		source_text: 'The Supplier shall indemnify and hold harmless the Customer',
		verified: true,
		verification_method: 'exact_match',
		verification_confidence: 1.0,
		partial: false,
		created_at: NOW
	},
	{
		id: 'cite-2',
		source_file_id: 'f1',
		source_filename: 'Master Services Agreement.pdf',
		source_offset_start: 20,
		source_offset_end: 40,
		source_page: 13,
		source_text: 'such indemnity to apply without limit of liability',
		verified: true,
		verification_method: 'exact_match',
		verification_confidence: 1.0,
		partial: false,
		created_at: NOW
	},
	{
		id: 'cite-3',
		source_file_id: 'f2',
		source_filename: 'Data Processing Addendum.pdf',
		source_offset_start: 0,
		source_offset_end: 10,
		source_page: 4,
		source_text: 'the processor notifies the controller within 24 hours of a breach',
		verified: true,
		verification_method: 'paraphrase_judge',
		verification_confidence: 0.8,
		partial: false,
		created_at: NOW
	},
	{
		id: 'cite-4',
		source_file_id: 'f3',
		source_filename: 'Side Letter (unsigned).pdf',
		source_offset_start: 0,
		source_offset_end: 10,
		source_page: null,
		source_text: 'the parties intend to negotiate a cap in good faith',
		verified: false,
		verification_method: 'failed',
		verification_confidence: null,
		partial: false,
		created_at: NOW
	}
];

function stubChat(citations: unknown[] = []) {
	cy.intercept('GET', /\/api\/v1\/projects(\?.*)?$/, [PROJECT]).as('projects');
	cy.intercept('GET', `**/api/v1/projects/${PROJ_ID}`, PROJECT).as('project');
	cy.intercept('GET', /\/api\/v1\/chats(\?.*)?$/, CHATS).as('chats');
	cy.intercept('GET', '**/api/v1/chats/*/messages*', MESSAGES_SHORT).as('messages');
	// Correct path: /chats/{id}/messages/{mid}/citations (AE2's glob missed this).
	cy.intercept('GET', '**/api/v1/chats/*/messages/*/citations', citations).as('citations');
}
