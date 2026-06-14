/**
 * AE1 — Conversation + Message + Response (full-width) (ADR-F011).
 *
 * Drives the legacy chat workspace (`/lq-ai/chats`) with DETERMINISTIC,
 * backend-free fixtures so the same render is captured against the pre-AE1
 * bundle (PHASE=before) and the AE1 bundle (PHASE=after). What AE1 changes:
 *
 *   - MessageList → AI Elements **Conversation** (scroll container + sticky
 *     scroll-to-bottom button; the old `afterUpdate` hard-scroll is gone).
 *   - MessageBubble → **Message + MessageContent**: full-width document-style
 *     assistant (our sanitized prose — NOT the port's Streamdown sink) + a
 *     soft right-aligned `bg-secondary` user bubble.
 *
 * The functional `describe` asserts AE1-only structure and is skipped when
 * CAPTURE_ONLY=1 (the pre-AE1 bundle has no Message wrappers / scroll button).
 * The capture `describe` is element-guarded so it runs on BOTH phases.
 *
 * Run (live stack, headed for honest dark-theme capture):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ae1-conversation.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!,PHASE=after
 */
const PHASE = () => (Cypress.env('PHASE') as string) || 'after';
const CAPTURE_ONLY = String(Cypress.env('CAPTURE_ONLY')) === '1';

const NOW = '2026-06-14T10:00:00Z';
const PROJ_ID = '00000000-0000-4000-8000-0000000000c1';
const CHAT_ID = '00000000-0000-4000-8000-0000000000c8';

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

function chat(id: string, title: string, project_id: string | null) {
	return {
		id,
		title,
		owner_id: 'admin',
		project_id,
		archived_at: null,
		message_count: 0,
		created_at: NOW,
		updated_at: NOW
	};
}

const CHAT_ID_SHORT = '00000000-0000-4000-8000-0000000000c9';
const CHATS = {
	items: [
		chat(CHAT_ID, 'Indemnity review', PROJ_ID),
		chat(CHAT_ID_SHORT, 'Indemnity (short)', PROJ_ID)
	],
	next_cursor: null
};

// Capture fixture: just the two meaningful turns (no filler) so nothing scrolls
// out of view and the auto-scroll observer doesn't fight the screenshot.
const SHORT_ITEMS = [
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
			'- **General reps:** 12-month survival\n' +
			'- **Fundamental reps & tax:** 6 years\n\n' +
			'See the *cap clause* for the de-minimis basket.',
		routed_inference_tier: 4,
		routed_provider: 'minimax',
		routed_model: 'MiniMax-M3',
		created_at: NOW
	}
];
const MESSAGES_SHORT = { items: SHORT_ITEMS, next_cursor: null };

// A user turn + an assistant turn with markdown + a <think> reasoning block,
// then filler turns so the scroll container overflows (exercises the sticky
// scroll-to-bottom button).
const ITEMS: Array<Record<string, unknown>> = [
	{
		id: 'm-user-1',
		chat_id: CHAT_ID,
		role: 'user',
		content: 'Summarise the indemnity cap and survival periods in the disclosure schedule.',
		created_at: NOW
	},
	{
		id: 'm-asst-1',
		chat_id: CHAT_ID,
		role: 'assistant',
		content:
			'<think>Check the cap clause, then the survival table.</think>' +
			'Here is the **indemnity position**:\n\n' +
			'- **Cap:** 15% of the purchase price\n' +
			'- **General reps:** 12-month survival\n' +
			'- **Fundamental reps & tax:** 6 years\n\n' +
			'See the *cap clause* for the de-minimis basket.',
		routed_inference_tier: 4,
		routed_provider: 'minimax',
		routed_model: 'MiniMax-M3',
		created_at: NOW
	}
];
for (let i = 0; i < 8; i++) {
	ITEMS.push({
		id: `m-user-f${i}`,
		chat_id: CHAT_ID,
		role: 'user',
		content: `Follow-up question number ${i + 1} about the schedule.`,
		created_at: NOW
	});
	ITEMS.push({
		id: `m-asst-f${i}`,
		chat_id: CHAT_ID,
		role: 'assistant',
		content: `Answer ${i + 1}: the relevant clause is unchanged from the prior draft.`,
		routed_inference_tier: 4,
		routed_provider: 'minimax',
		created_at: NOW
	});
}
const MESSAGES = { items: ITEMS, next_cursor: null };

// cy.session caches the auth token across tests so we hit the auth backend
// ONCE per spec, not once per test — the per-user session cap + bcrypt cost
// make rapid repeated logins flaky under load (see auth-refresh-scan-blank-fix).
function login() {
	cy.session('lq-admin', () => {
		cy.visit('/lq-ai/login');
		cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
		cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!');
		cy.get('button[type="submit"]').click();
		cy.url({ timeout: 15000 }).should('not.include', '/login');
	});
}

function setTheme(mode: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', mode);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(mode);
	});
}

function stub() {
	cy.intercept('GET', /\/api\/v1\/projects(\?.*)?$/, [PROJECT]).as('projects');
	cy.intercept('GET', `**/api/v1/projects/${PROJ_ID}`, PROJECT).as('project');
	cy.intercept('GET', /\/api\/v1\/chats(\?.*)?$/, CHATS).as('chats');
	cy.intercept('GET', '**/api/v1/chats/*/messages*', (req) => {
		req.reply(req.url.includes(CHAT_ID_SHORT) ? MESSAGES_SHORT : MESSAGES);
	}).as('messages');
	// No citations persisted for these fixtures.
	cy.intercept('GET', '**/api/v1/messages/*/citations', { statusCode: 404, body: {} });
}

// Live-backend e2e: retry transient login/load hiccups on the local stack
// (a retry re-runs beforeEach, so cy.session re-attempts the cached login).
describe('AE1 — Conversation + Message + Response', { retries: { runMode: 2, openMode: 0 } }, () => {
	if (!CAPTURE_ONLY) {
		describe('structure', () => {
			beforeEach(() => {
				stub();
				login();
			});

			// Content tests use the SHORT fixture: both meaningful turns always
			// exist + stay in view (the long thread auto-scrolls the assistant turn
			// out of frame, which is flaky under testIsolation:false re-visits).
			function visitShortChat() {
				cy.visit(`/lq-ai/chats?id=${CHAT_ID_SHORT}`);
				cy.get('[data-testid="lq-ai-message-list"]', { timeout: 15000 }).should('exist');
				cy.get('[data-testid="lq-ai-message-m-asst-1"]', { timeout: 15000 }).should('exist');
			}

			it('renders the user turn as a soft right-aligned bubble', () => {
				visitShortChat();
				cy.get('[data-testid="lq-ai-message-m-user-1"]').should(($el) => {
					expect($el).to.have.attr('data-role', 'user');
					expect($el.attr('class')).to.contain('is-user');
				});
				// The soft bubble lives on MessageContent (group-[.is-user]:bg-secondary).
				cy.get(
					'[data-testid="lq-ai-message-m-user-1"] [data-testid="lq-ai-message-content"]'
				).should('contain.text', 'Summarise the indemnity cap');
			});

			it('renders the assistant turn full-width with sanitized markdown + reasoning', () => {
				visitShortChat();
				cy.get('[data-testid="lq-ai-message-m-asst-1"]').should(($el) => {
					expect($el).to.have.attr('data-role', 'assistant');
					expect($el.attr('class')).to.contain('is-assistant');
				});
				// Markdown rendered through OUR renderer (strong + list), not raw text.
				cy.get(
					'[data-testid="lq-ai-message-m-asst-1"] [data-testid="lq-ai-message-content"]'
				).within(() => {
					cy.get('strong').should('contain.text', 'indemnity position');
					cy.get('ul li').should('have.length.greaterThan', 1);
				});
				// <think> went to the reasoning ribbon, NOT the answer prose.
				cy.get(
					'[data-testid="lq-ai-message-m-asst-1"] [data-testid="lq-ai-message-content"]'
				).should('not.contain.text', 'Check the cap clause');
			});

			it('shows the sticky scroll-to-bottom button after scrolling up', () => {
				// Long fixture so the thread overflows the scroll container.
				cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
				cy.get('[data-testid="lq-ai-message-list"]', { timeout: 15000 }).should('exist');
				cy.get('[data-testid="lq-ai-message-m-asst-f7"]', { timeout: 15000 }).should('exist');
				cy.get('[data-testid="lq-ai-scroll-bottom"]').should('not.exist');
				cy.get('[data-testid="lq-ai-message-list"]').scrollTo('top');
				cy.get('[data-testid="lq-ai-scroll-bottom"]', { timeout: 6000 })
					.should('be.visible')
					.click();
				cy.get('[data-testid="lq-ai-scroll-bottom"]').should('not.exist');
			});
		});
	}

	// Theme set in localStorage BEFORE visit so the app's pre-paint script boots
	// in that theme (a same-load class toggle leaves the wide layout painted
	// light — the R8 finding). Short fixture so nothing scrolls out of view.
	describe('capture', () => {
		beforeEach(() => {
			stub();
			login();
		});

		function visitShort(theme: 'light' | 'dark') {
			cy.window().then((w) => w.localStorage.setItem('theme', theme));
			cy.visit(`/lq-ai/chats?id=${CHAT_ID_SHORT}`);
			cy.get('[data-testid="lq-ai-message-list"]', { timeout: 15000 }).should('exist');
			setTheme(theme); // belt-and-suspenders: pin the class post-boot
			cy.get('html').should('have.class', theme); // the class IS applied
			cy.get('[data-testid="lq-ai-message-m-asst-1"]').should('be.visible');
		}

		it('captures the conversation wide (light + dark)', () => {
			for (const theme of ['light', 'dark'] as const) {
				cy.viewport(1281, 900);
				visitShort(theme);
				// Nudge the viewport to force Electron to repaint the new theme.
				cy.viewport(1280, 900);
				cy.wait(300);
				cy.screenshot(`ae1-${PHASE()}-conversation-${theme}-wide`, { capture: 'viewport' });
			}
		});

		it('captures the conversation narrow (light + dark)', () => {
			for (const theme of ['light', 'dark'] as const) {
				cy.viewport(600, 900);
				visitShort(theme);
				cy.viewport(601, 900);
				cy.wait(300);
				cy.screenshot(`ae1-${PHASE()}-conversation-${theme}-narrow`, { capture: 'viewport' });
			}
		});
	});
});
