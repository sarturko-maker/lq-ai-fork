/**
 * AE2 — Reasoning + Actions (ADR-F011).
 *
 * Two surfaces:
 *
 *   1. The internal lab (`/lq-ai/_ae-lab`, auth-gated, no API of its own) drives
 *      the AE2 pieces DETERMINISTICALLY:
 *        - ReasoningRibbon (AE identity, option-2 hand-build): brain icon,
 *          "Reasoning" idle → "Thinking…" shimmer while streaming → measured
 *          "Thought for Ns" + one-shot auto-collapse when it ends.
 *        - MessageActionsBar: Copy (→ clipboard), Retry (→ callback),
 *          Copy-sources (→ clipboard).
 *
 *   2. The live chat workspace (`/lq-ai/chats`) with backend-free fixtures, for
 *      the before/after screenshots — the AE2 changes a user sees are the new
 *      brain-iconed reasoning ribbon and the per-message actions toolbar.
 *
 * The functional `describe` asserts AE2-only behaviour and is skipped under
 * CAPTURE_ONLY=1 (the pre-AE2 bundle has no actions bar / brain ribbon). The
 * capture `describe` is element-guarded so it runs on BOTH phases.
 *
 * Run (live stack, headed for honest dark capture):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ae2-reasoning-actions.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!,PHASE=after
 */
const PHASE = () => (Cypress.env('PHASE') as string) || 'after';
const CAPTURE_ONLY = String(Cypress.env('CAPTURE_ONLY')) === '1';

const NOW = '2026-06-14T10:00:00Z';
const PROJ_ID = '00000000-0000-4000-8000-0000000000c1';
const CHAT_ID_SHORT = '00000000-0000-4000-8000-0000000000c9';

const DEMO_ANSWER =
	'Clause 9.2 carries an uncapped indemnity. Recommend negotiating a liability cap.';

// cy.session caches the token so we hit the auth backend ONCE per spec (the
// per-user session cap + bcrypt cost make rapid repeated logins flaky under
// load — see auth-refresh-scan-blank-fix).
function login() {
	cy.session('lq-admin', () => {
		cy.visit('/lq-ai/login');
		cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
		cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!');
		cy.get('button[type="submit"]').click();
		cy.url({ timeout: 15000 }).should('not.include', '/login');
	});
}

// Stub the clipboard so Copy resolves deterministically regardless of the
// Electron permission/secure-context state, and we can assert the payload.
function stubClipboard() {
	cy.window().then((win) => {
		cy.stub(win.navigator.clipboard, 'writeText').resolves().as('clip');
	});
}

describe('AE2 — Reasoning + Actions', { retries: { runMode: 2, openMode: 0 } }, () => {
	if (!CAPTURE_ONLY) {
		describe('lab — reasoning ribbon', () => {
			beforeEach(() => {
				login();
				cy.visit('/lq-ai/_ae-lab');
				cy.get('[data-testid="ae-lab-reasoning"]', { timeout: 15000 }).should('be.visible');
			});

			it('renders the AE identity (brain icon) and is collapsed when idle', () => {
				cy.get('[data-testid="lq-ai-reasoning-ribbon"] svg.lucide-brain').should('exist');
				cy.get('[data-testid="lq-ai-reasoning-ribbon"] summary span').should('have.text', 'Reasoning');
				cy.get('[data-testid="lq-ai-reasoning-ribbon"]').should('not.have.attr', 'open');
			});

			it('shimmers + auto-opens while streaming, then shows a duration + auto-collapses', () => {
				cy.get('[data-testid="ae-lab-reasoning-toggle"]').click(); // start streaming
				cy.get('[data-testid="lq-ai-reasoning-ribbon"]').should('have.attr', 'open');
				cy.get('[data-testid="lq-ai-reasoning-ribbon"] summary span')
					.should('have.text', 'Thinking…')
					.and('have.class', 'animate-pulse');
				cy.get('[data-testid="lq-ai-reasoning-ribbon-body"]').should('be.visible');

				cy.get('[data-testid="ae-lab-reasoning-toggle"]').click(); // stop streaming
				cy.get('[data-testid="lq-ai-reasoning-ribbon"] summary span').should(
					'contain.text',
					'Thought for'
				);
				// One-shot auto-collapse fires ~1s after the stream ends.
				cy.get('[data-testid="lq-ai-reasoning-ribbon"]', { timeout: 4000 }).should(
					'not.have.attr',
					'open'
				);
			});
		});

		describe('lab — message actions', () => {
			beforeEach(() => {
				login();
				cy.visit('/lq-ai/_ae-lab');
				cy.get('[data-testid="ae-lab-actions"]', { timeout: 15000 }).should('be.visible');
				stubClipboard();
			});

			it('copies the answer to the clipboard and shows the copied tick', () => {
				cy.get('[data-testid="lq-ai-action-copy"] svg.lucide-copy').should('exist');
				cy.get('[data-testid="lq-ai-action-copy"]').click();
				cy.get('@clip').should('have.been.calledWith', DEMO_ANSWER);
				cy.get('[data-testid="lq-ai-action-copy"] svg.lucide-check').should('exist');
			});

			it('copies the formatted sources when present', () => {
				cy.get('[data-testid="lq-ai-action-copy-sources"]').click();
				cy.get('@clip').should('have.been.calledWithMatch', /^\[1\] .*\n\[2\] /);
			});

			it('fires Retry through the callback', () => {
				cy.get('[data-testid="ae-lab-retry-count"]').should('have.text', '0');
				cy.get('[data-testid="lq-ai-action-retry"]').click();
				cy.get('[data-testid="ae-lab-retry-count"]').should('have.text', '1');
			});
		});

		describe('live chat — actions on a real assistant message', () => {
			beforeEach(() => {
				stubChat();
				login();
			});

			it('shows the Copy + Retry actions on the assistant turn', () => {
				cy.visit(`/lq-ai/chats?id=${CHAT_ID_SHORT}`);
				cy.get('[data-testid="lq-ai-message-m-asst-1"]', { timeout: 15000 }).should('exist');
				cy.get(
					'[data-testid="lq-ai-message-m-asst-1"] [data-testid="lq-ai-action-copy"]'
				).should('exist');
				cy.get(
					'[data-testid="lq-ai-message-m-asst-1"] [data-testid="lq-ai-action-retry"]'
				).should('exist');
				// The user turn carries NO actions bar (assistant-only affordance).
				cy.get(
					'[data-testid="lq-ai-message-m-user-1"] [data-testid="lq-ai-message-actions"]'
				).should('not.exist');
			});
		});
	}

	// ---- before/after capture on the live chat surface ----
	describe('capture', () => {
		beforeEach(() => {
			stubChat();
			login();
		});

		function visitShort(theme: 'light' | 'dark') {
			cy.window().then((w) => w.localStorage.setItem('theme', theme));
			cy.visit(`/lq-ai/chats?id=${CHAT_ID_SHORT}`);
			cy.get('[data-testid="lq-ai-message-list"]', { timeout: 15000 }).should('exist');
			cy.window().then((win) => {
				win.localStorage.setItem('theme', theme);
				win.document.documentElement.classList.remove('light', 'dark');
				win.document.documentElement.classList.add(theme);
			});
			cy.get('html').should('have.class', theme);
			cy.get('[data-testid="lq-ai-message-m-asst-1"]').should('be.visible');
		}

		it('captures the chat surface with reasoning + actions (light + dark)', () => {
			for (const theme of ['light', 'dark'] as const) {
				cy.viewport(1281, 900);
				visitShort(theme);
				cy.viewport(1280, 900);
				cy.wait(300);
				cy.screenshot(`ae2-${PHASE()}-chat-${theme}-wide`, { capture: 'viewport' });
			}
		});
	});
});

// --- fixtures (mirrors ae1-conversation.cy.ts SHORT fixture) ---
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

function stubChat() {
	cy.intercept('GET', /\/api\/v1\/projects(\?.*)?$/, [PROJECT]).as('projects');
	cy.intercept('GET', `**/api/v1/projects/${PROJ_ID}`, PROJECT).as('project');
	cy.intercept('GET', /\/api\/v1\/chats(\?.*)?$/, CHATS).as('chats');
	cy.intercept('GET', '**/api/v1/chats/*/messages*', MESSAGES_SHORT).as('messages');
	cy.intercept('GET', '**/api/v1/messages/*/citations', { statusCode: 404, body: {} });
}
