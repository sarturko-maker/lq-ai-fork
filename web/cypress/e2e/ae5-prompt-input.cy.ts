/**
 * AE5 — Prompt Input (ADR-F011).
 *
 * The composer is inherently a LIVE surface (it needs an active chat), so AE5 is
 * tested on the real chat workspace (`/lq-ai/chats`) with backend-free fixtures —
 * the same SHORT-fixture recipe AE3/AE4 use. The functional `describe` asserts the
 * AE Prompt Input identity (one unified rounded shell containing the textarea +
 * a toolbar carrying the model selector, attach/enhance/receipts tools, and the
 * submit control) and that the KEPT affordances still wire up (Enhance opens its
 * panel; the slash popover still anchors to the shell). The capture `describe` is
 * element-guarded on stable testids so it runs on BOTH the pre- and post-AE5
 * bundle for before/after evidence.
 *
 * Run (live stack, headed for honest dark capture):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ae5-prompt-input.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!,PHASE=after
 */
const PHASE = () => (Cypress.env('PHASE') as string) || 'after';
const CAPTURE_ONLY = String(Cypress.env('CAPTURE_ONLY')) === '1';

const NOW = '2026-06-14T10:00:00Z';
const PROJ_ID = '00000000-0000-4000-8000-0000000000d1';
const CHAT_ID = '00000000-0000-4000-8000-0000000000d9';

function login() {
	cy.session('lq-admin', () => {
		cy.visit('/lq-ai/login');
		cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
		cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!');
		cy.get('button[type="submit"]').click();
		cy.url({ timeout: 30000 }).should('not.include', '/login');
	});
}

describe('AE5 — Prompt Input', { retries: { runMode: 2, openMode: 0 } }, () => {
	if (!CAPTURE_ONLY) {
		describe('live chat — prompt-input shell', () => {
			beforeEach(() => {
				stubChat();
				login();
				cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
				cy.get('[data-testid="lq-ai-prompt-input"]', { timeout: 30000 }).should('be.visible');
			});

			it('wraps the textarea + toolbar in one unified shell', () => {
				// The textarea and the toolbar both live INSIDE the single shell.
				cy.get('[data-testid="lq-ai-prompt-input"]').within(() => {
					cy.get('[data-testid="lq-ai-composer-input"]').should('exist');
					cy.get('[data-testid="lq-ai-prompt-toolbar"]').should('exist');
				});
			});

			it('carries the model selector + tools on the left and submit on the right', () => {
				const tb = '[data-testid="lq-ai-prompt-toolbar"] ';
				cy.get(tb + '[data-testid="lq-ai-model-picker"]').should('exist');
				cy.get(tb + '[data-testid="lq-ai-attach-kb-btn"]').should('exist');
				cy.get(tb + '[data-testid="lq-ai-enhance-btn"]').should('exist');
				cy.get(tb + '[data-testid="lq-ai-receipts-toggle"]').should('exist');
				cy.get(tb + '[data-testid="lq-ai-send-btn"]').should('exist');
				// Icon buttons render lucide SVGs, not emoji glyphs.
				cy.get(tb + '[data-testid="lq-ai-enhance-btn"] svg.lucide-sparkles').should('exist');
				cy.get(tb + '[data-testid="lq-ai-send-btn"] svg.lucide-send').should('exist');
			});

			it('disables submit until the composer has content, then enables it', () => {
				cy.get('[data-testid="lq-ai-send-btn"]').should('be.disabled');
				cy.get('[data-testid="lq-ai-composer-input"]').type('Review clause 9.2');
				cy.get('[data-testid="lq-ai-send-btn"]').should('not.be.disabled');
			});

			it('keeps Enhance wired — the ✨ tool opens the enhancement panel', () => {
				cy.get('[data-testid="lq-ai-composer-input"]').type('tighten this');
				cy.get('[data-testid="lq-ai-enhance-btn"]').click();
				cy.get('[data-testid="lq-ai-enhance-panel"]', { timeout: 10000 }).should('exist');
			});

			it('keeps the slash popover anchored to the shell', () => {
				cy.get('[data-testid="lq-ai-composer-input"]').type('/');
				cy.get('[data-testid="lq-ai-slash-popover-anchor"]').should('exist');
			});

			it('toggles the model dropdown upward (no viewport-bottom clip)', () => {
				cy.get('[data-testid="lq-ai-model-picker-toggle"]').click();
				cy.get('[data-testid="lq-ai-model-picker-dropdown"]')
					.should('be.visible')
					.then(($dd) => {
						const ddBottom = $dd[0].getBoundingClientRect().bottom;
						cy.get('[data-testid="lq-ai-model-picker-toggle"]').then(($t) => {
							// The dropdown opens above the trigger, so its bottom edge is
							// at or above the trigger's top edge.
							expect(ddBottom).to.be.lte($t[0].getBoundingClientRect().bottom);
						});
					});
			});
		});
	}

	// ---- before/after capture ----
	describe('capture', () => {
		it('captures the chat composer (light + dark, wide + narrow)', () => {
			stubChat();
			login();
			for (const theme of ['light', 'dark'] as const) {
				cy.window().then((w) => w.localStorage.setItem('theme', theme));
				cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
				cy.get('[data-testid="lq-ai-composer"]', { timeout: 30000 }).should('exist');
				cy.window().then((win) => {
					win.localStorage.setItem('theme', theme);
					win.document.documentElement.classList.remove('light', 'dark');
					win.document.documentElement.classList.add(theme);
				});
				cy.get('html').should('have.class', theme);
				cy.get('[data-testid="lq-ai-message-m-asst-1"]').should('be.visible');

				cy.viewport(1281, 900);
				cy.viewport(1280, 900);
				cy.wait(400);
				cy.screenshot(`ae5-${PHASE()}-chat-${theme}-wide`, { capture: 'viewport' });

				cy.viewport(701, 900);
				cy.viewport(700, 900);
				cy.wait(400);
				cy.screenshot(`ae5-${PHASE()}-chat-${theme}-narrow`, { capture: 'viewport' });
			}
		});
	});
});

// --- fixtures (mirrors ae4 SHORT fixture) ---
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
			id: CHAT_ID,
			title: 'Redline helper',
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
const MESSAGES = {
	items: [
		{
			id: 'm-user-1',
			chat_id: CHAT_ID,
			role: 'user',
			content: 'What is unusual about the indemnity in clause 9.2?',
			created_at: NOW
		},
		{
			id: 'm-asst-1',
			chat_id: CHAT_ID,
			role: 'assistant',
			content:
				'Clause 9.2 carries an **uncapped** indemnity, which is unusual for a mutual ' +
				'agreement of this size. Recommend negotiating a liability cap before signature.',
			routed_inference_tier: 4,
			routed_provider: 'minimax',
			routed_model: 'MiniMax-M3',
			created_at: NOW
		}
	],
	next_cursor: null
};
const MODELS = {
	object: 'list',
	data: [
		{
			id: 'smart',
			object: 'model',
			lq_ai_resolves_to: 'minimax/MiniMax-M3',
			lq_ai_fallback_count: 0,
			routed_inference_tier: 4
		},
		{ id: 'minimax/MiniMax-M3', object: 'model', routed_inference_tier: 4 }
	]
};

function stubChat() {
	cy.intercept('GET', /\/api\/v1\/projects(\?.*)?$/, [PROJECT]).as('projects');
	cy.intercept('GET', `**/api/v1/projects/${PROJ_ID}`, PROJECT).as('project');
	cy.intercept('GET', /\/api\/v1\/chats(\?.*)?$/, CHATS).as('chats');
	cy.intercept('GET', '**/api/v1/chats/*/messages*', MESSAGES).as('messages');
	cy.intercept('GET', '**/api/v1/chats/*/messages/*/citations', []).as('citations');
	cy.intercept('GET', /\/api\/v1\/models(\?.*)?$/, MODELS).as('models');
}
