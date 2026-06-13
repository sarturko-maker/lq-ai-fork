/**
 * R6 — MessageBubble family + `<think>` reasoning ribbon.
 *
 * Drives the legacy chat surface (`/lq-ai/chats`) with a DETERMINISTIC,
 * backend-free fixture (intercepted `GET /chats`, `GET /chats/:id/messages`,
 * `GET /messages/:id/citations`) so the same render can be captured against
 * the pre-R6 bundle (PHASE=before) and the R6 bundle (PHASE=after) for a clean
 * A/B. The fixture exercises every R6 surface in one chat:
 *
 *   1. user message, `is_enhanced` → ✨ ProvenancePill (sage → accent token)
 *   2. assistant message carrying `<think>…</think>` → the reasoning RIBBON
 *      (collapsed; the raw <think> used to leak as prose), a citation marker
 *      → M2Citations chip, and a Tier-4 badge
 *   3. assistant message with `error_code` → the error banner (now R1a <Alert>)
 *
 * Run (live stack, headed for honest dark-theme capture):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/r6-message-bubble.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!,PHASE=before
 */
const PHASE = () => (Cypress.env('PHASE') as string) || 'after';

const CHAT_ID = '00000000-0000-4000-8000-0000000000a6';
const MSG_USER = '00000000-0000-4000-8000-000000000d00';
const MSG_THINK = '00000000-0000-4000-8000-000000000d01';
const MSG_ERR = '00000000-0000-4000-8000-000000000d02';

const NOW = '2026-06-13T10:00:00Z';

const CHAT = {
	id: CHAT_ID,
	title: 'R6 — reasoning ribbon demo',
	owner_id: 'admin',
	project_id: null,
	archived_at: null,
	message_count: 3,
	created_at: NOW,
	updated_at: NOW
};

const MESSAGES = {
	items: [
		{
			id: MSG_USER,
			chat_id: CHAT_ID,
			role: 'user',
			kind: 'user',
			content: 'Does the indemnity survive termination of the agreement?',
			is_enhanced: true,
			created_at: NOW
		},
		{
			id: MSG_THINK,
			chat_id: CHAT_ID,
			role: 'assistant',
			kind: 'ai',
			content:
				'<think>\nThe user asks whether the indemnity survives termination. The controlling ' +
				'language is in §12.3 ("survival"). I should quote it and flag the 6-year limitation ' +
				'in §12.4 so the answer is not over-broad.\n</think>\n\n' +
				'Yes — the indemnity **survives termination**. ' +
				'"The indemnity survives termination of this Agreement" (Source: [1]). ' +
				'Note the six-year limitation period in §12.4.',
			routed_inference_tier: 4,
			routed_provider: 'minimax',
			routed_model: 'MiniMax-M3',
			applied_skills: [],
			created_at: NOW
		},
		{
			id: MSG_ERR,
			chat_id: CHAT_ID,
			role: 'assistant',
			kind: 'ai',
			content: 'Here is the partial analysis before the provider connection dropped…',
			error_code: 'provider_timeout',
			routed_inference_tier: 4,
			routed_provider: 'minimax',
			created_at: NOW
		}
	],
	next_cursor: null
};

const CITATIONS = [
	{
		id: 'cit-1',
		source_file_id: 'file-1',
		source_offset_start: 0,
		source_offset_end: 48,
		source_page: 12,
		source_text: 'The indemnity survives termination of this Agreement',
		verified: true,
		verification_method: 'exact_match',
		verification_confidence: 1,
		created_at: NOW
	}
];

function login() {
	cy.visit('/lq-ai/login');
	cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
	cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!');
	cy.get('button[type="submit"]').click();
	cy.url({ timeout: 15000 }).should('not.include', '/login');
}

function setTheme(mode: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', mode);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(mode);
	});
}

function stubChat() {
	// Anchor every stub to the `/api/v1` API path. A looser pattern (e.g. a
	// bare `/chats`) also matches the `cy.visit('/lq-ai/chats?id=…')` DOCUMENT
	// request, so Cypress receives our JSON instead of the page HTML and dies
	// with "could not load · 200 application/json". The three API routes are
	// mutually disjoint (`*` never crosses `/`).
	cy.intercept('GET', /\/api\/v1\/chats(\?.*)?$/, { items: [CHAT], next_cursor: null }).as('chats');
	cy.intercept('GET', '**/api/v1/chats/*/messages*', MESSAGES).as('messages');
	cy.intercept('GET', '**/api/v1/chats/*/messages/*/citations', CITATIONS).as('citations');
}

function openChat() {
	cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
	// The assistant bubble renders once messages resolve.
	cy.get('[data-testid="lq-ai-message-content"]', { timeout: 15000 }).should('exist');
	// The legacy ChatPanel shell is a non-responsive flex row (sidebar +
	// flex-1 conversation + attachments); below ~700px the conversation is
	// squeezed — that's R9's shell, not R6's bubbles. At the widths used here
	// the column stays usable; scroll the answer into view to be safe.
	cy.contains('Yes — the indemnity').scrollIntoView().should('be.visible');
}

describe('R6 — MessageBubble reasoning ribbon + semantic tokens', () => {
	beforeEach(() => {
		stubChat();
		login();
	});

	// ── Behaviour: the <think> block is collapsed, not leaked as prose ──────────
	it('extracts <think> into a collapsed Reasoning ribbon, leaving clean prose', () => {
		cy.viewport(1280, 800);
		openChat();

		// The reasoning text must NOT appear in the rendered answer prose.
		cy.get('[data-testid="lq-ai-message-content"]')
			.first()
			.should('not.contain', 'controlling language is in §12.3');

		// It lives in a collapsed <details> ribbon instead.
		cy.get('[data-testid="lq-ai-reasoning-ribbon"]').should('exist');
		cy.contains('summary', /reasoning/i).should('be.visible');
		// Collapsed by default — body hidden.
		cy.get('[data-testid="lq-ai-reasoning-ribbon"]').should('not.have.attr', 'open');

		// Expanding reveals the reasoning.
		cy.contains('summary', /reasoning/i).click();
		cy.get('[data-testid="lq-ai-reasoning-ribbon"]').should('have.attr', 'open');
		cy.contains('controlling language is in §12.3').should('be.visible');
	});

	// ── Visual evidence: light/dark × wide/narrow ───────────────────────────────
	it('captures the chat surface across themes and widths', () => {
		const shots: Array<{ theme: 'light' | 'dark'; w: number; h: number; tag: string }> = [
			{ theme: 'light', w: 1280, h: 900, tag: 'wide' },
			{ theme: 'dark', w: 1280, h: 900, tag: 'wide' },
			{ theme: 'light', w: 860, h: 1180, tag: 'narrow' },
			{ theme: 'dark', w: 860, h: 1180, tag: 'narrow' }
		];
		for (const s of shots) {
			cy.viewport(s.w, s.h);
			openChat();
			setTheme(s.theme);
			cy.wait(150);
			cy.screenshot(`${PHASE()}-r6-${s.theme}-${s.tag}`, { capture: 'viewport' });
		}

		// Ribbon expanded (wide light) so the reasoning panel styling is captured.
		cy.viewport(1280, 900);
		openChat();
		setTheme('light');
		cy.contains('summary', /reasoning/i).click();
		cy.wait(150);
		cy.screenshot(`${PHASE()}-r6-ribbon-expanded`, { capture: 'viewport' });
	});
});
