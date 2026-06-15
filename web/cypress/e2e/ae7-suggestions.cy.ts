/**
 * AE7 — Suggestions (ADR-F011). The AE-series closer.
 *
 * AE Suggestion chips, surfaced above the composer as one-click STARTERS on an
 * empty conversation. They are backed by the user's OWN SavedPrompts — an
 * honest, user-owned data source — NOT model-invented follow-ups (for which no
 * honest source exists; inventing them is explicitly out of scope). So the
 * chips appear only when (a) the conversation is empty AND (b) the user has
 * saved prompts; an empty saved-prompts list shows NO chips (no invention).
 *
 * Tested on the live chat workspace (`/lq-ai/chats`) with backend-free
 * fixtures — the SHORT-fixture recipe AE3/AE4/AE5 use. The capture `describe`
 * is element-guarded so it runs on BOTH the pre- and post-AE7 bundle for
 * before/after evidence.
 *
 * Run (live stack, headed for honest dark capture):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ae7-suggestions.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!,PHASE=after
 */
const PHASE = () => (Cypress.env('PHASE') as string) || 'after';
const CAPTURE_ONLY = String(Cypress.env('CAPTURE_ONLY')) === '1';

const NOW = '2026-06-14T10:00:00Z';
const PROJ_ID = '00000000-0000-4000-8000-0000000000f1';
const CHAT_ID = '00000000-0000-4000-8000-0000000000f9';

function login() {
	cy.session('lq-admin', () => {
		cy.visit('/lq-ai/login');
		cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
		cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!');
		cy.get('button[type="submit"]').click();
		cy.url({ timeout: 30000 }).should('not.include', '/login');
	});
}

describe('AE7 — Suggestions', { retries: { runMode: 2, openMode: 0 } }, () => {
	if (!CAPTURE_ONLY) {
		describe('empty conversation — saved-prompt starter chips', () => {
			it('renders one AE Suggestion chip per saved prompt', () => {
				stubChat(EMPTY_MESSAGES, SAVED_PROMPTS);
				login();
				cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
				cy.get('[data-testid="lq-ai-suggestions"]', { timeout: 30000 }).should('be.visible');
				cy.get('[data-testid="lq-ai-suggestion"]').should('have.length', SAVED_PROMPTS.length);
				cy.get('[data-testid="lq-ai-suggestion"]')
					.first()
					.should('contain.text', SAVED_PROMPTS[0].name);
			});

			it('fills the composer with the prompt body when a chip is clicked', () => {
				stubChat(EMPTY_MESSAGES, SAVED_PROMPTS);
				login();
				cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
				cy.get('[data-testid="lq-ai-suggestion"]', { timeout: 30000 }).first().click();
				// The chip label is the prompt NAME; clicking inserts the prompt BODY.
				cy.get('[data-testid="lq-ai-composer-input"]').should(
					'have.value',
					SAVED_PROMPTS[0].prompt_text
				);
			});

			it('hides the chips once the conversation has messages', () => {
				stubChat(POPULATED_MESSAGES, SAVED_PROMPTS);
				login();
				cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
				// The composer (hence SavedPromptsPanel) renders, but the starter
				// chips do not — they are an empty-state affordance only.
				cy.get('[data-testid="lq-ai-composer"]', { timeout: 30000 }).should('exist');
				cy.get('[data-testid="lq-ai-suggestions"]').should('not.exist');
			});

			it('shows NO chips when the user has no saved prompts (no invention)', () => {
				stubChat(EMPTY_MESSAGES, []);
				login();
				cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
				cy.get('[data-testid="lq-ai-composer"]', { timeout: 30000 }).should('exist');
				cy.get('[data-testid="lq-ai-suggestions"]').should('not.exist');
			});
		});
	}

	// ---- before/after capture ----
	describe('capture', () => {
		it('captures the starter chips (light + dark, wide + narrow)', () => {
			stubChat(EMPTY_MESSAGES, SAVED_PROMPTS);
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
				// On the post-AE7 bundle the chips exist; on the pre-AE7 bundle they
				// don't — element-guard so the same spec captures both.
				cy.get('[data-testid="lq-ai-composer"]').should('be.visible');

				cy.viewport(1281, 900);
				cy.viewport(1280, 900);
				cy.wait(400);
				cy.screenshot(`ae7-${PHASE()}-suggestions-${theme}-wide`, { capture: 'viewport' });

				cy.viewport(701, 900);
				cy.viewport(700, 900);
				cy.wait(400);
				cy.screenshot(`ae7-${PHASE()}-suggestions-${theme}-narrow`, { capture: 'viewport' });
			}
		});
	});
});

// --- fixtures (SHORT, mirrors ae5) ---
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
			title: 'New matter chat',
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
const EMPTY_MESSAGES = { items: [], next_cursor: null };
const POPULATED_MESSAGES = {
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
			content: 'Clause 9.2 carries an **uncapped** indemnity. Recommend negotiating a cap.',
			routed_inference_tier: 4,
			routed_provider: 'minimax',
			routed_model: 'MiniMax-M3',
			created_at: NOW
		}
	],
	next_cursor: null
};
const SAVED_PROMPTS = [
	{
		id: 's1',
		user_id: 'admin',
		name: 'Executive summary',
		prompt_text: 'Give me a one-paragraph executive summary of this document.',
		tags: ['summary'],
		created_at: NOW,
		updated_at: NOW
	},
	{
		id: 's2',
		user_id: 'admin',
		name: 'Redline risks',
		prompt_text: 'List the top redline risks in this agreement, most severe first.',
		tags: [],
		created_at: NOW,
		updated_at: NOW
	},
	{
		id: 's3',
		user_id: 'admin',
		name: 'Plain-English clause',
		prompt_text: 'Explain clause 9.2 in plain English for a non-lawyer.',
		tags: [],
		created_at: NOW,
		updated_at: NOW
	}
];
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

function stubChat(messages: unknown, savedPrompts: unknown) {
	cy.intercept('GET', /\/api\/v1\/projects(\?.*)?$/, [PROJECT]).as('projects');
	cy.intercept('GET', `**/api/v1/projects/${PROJ_ID}`, PROJECT).as('project');
	cy.intercept('GET', /\/api\/v1\/chats(\?.*)?$/, CHATS).as('chats');
	cy.intercept('GET', '**/api/v1/chats/*/messages*', messages).as('messages');
	cy.intercept('GET', '**/api/v1/chats/*/messages/*/citations', []).as('citations');
	cy.intercept('GET', /\/api\/v1\/models(\?.*)?$/, MODELS).as('models');
	cy.intercept('GET', '**/api/v1/saved-prompts', savedPrompts).as('savedPrompts');
}
