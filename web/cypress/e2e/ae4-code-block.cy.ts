/**
 * AE4 — Code Block (Shiki) (ADR-F011).
 *
 * Two surfaces:
 *
 *   1. The internal lab (`/lq-ai/_ae-lab`, auth-gated, no API of its own) drives
 *      the AE4 code-block card DETERMINISTICALLY through the REAL chat path:
 *      untrusted markdown → `renderModelMarkdown` (marked + DOMPurify) → `{@html}`
 *      → the `enhanceCodeBlocks` action (Shiki highlight + card). Four fences:
 *      python, sql, an unsupported `cobol` (→ plain text), and a no-language
 *      block whose body contains a literal `<script>` to prove the
 *      escaped-text → highlight pipeline is injection-safe.
 *
 *   2. The live chat workspace (`/lq-ai/chats`) with backend-free fixtures whose
 *      assistant turn contains a fenced code block — proves the card binds on the
 *      real message surface + gives the before/after shots.
 *
 * The functional `describe` asserts AE4-only behaviour and is skipped under
 * CAPTURE_ONLY=1 (the pre-AE4 bundle has no code card). The capture `describe`
 * is element-guarded so it can run on BOTH phases.
 *
 * Run (live stack, headed for honest dark capture):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ae4-code-block.cy.ts' \
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

describe('AE4 — Code Block (Shiki)', { retries: { runMode: 2, openMode: 0 } }, () => {
	if (!CAPTURE_ONLY) {
		describe('lab — code-block cards', () => {
			const root = '[data-testid="ae-lab-code"] ';
			beforeEach(() => {
				login();
				cy.visit('/lq-ai/_ae-lab');
				cy.get('[data-testid="ae-lab-code"]', { timeout: 30000 }).should('be.visible');
				// Highlight is async (lazy grammar/theme load) — wait for the swap.
				cy.get(root + '[data-testid="lq-ai-code-block"]', { timeout: 30000 }).should(
					'have.length',
					4
				);
			});

			it('renders one card per fence with a language header and copy button', () => {
				cy.get(root + '[data-testid="lq-ai-code-block"]').then(($cards) => {
					const langs = $cards.toArray().map((c) => c.getAttribute('data-lang'));
					expect(langs).to.deep.equal(['python', 'sql', 'text', 'text']);
				});
				// Each card has a copy button + a Shiki-highlighted block.
				cy.get(root + '[data-testid="lq-ai-code-block"]').each(($card) => {
					cy.wrap($card).find('[data-testid="lq-ai-code-copy"]').should('exist');
					cy.wrap($card).find('pre.shiki').should('exist');
				});
			});

			it('applies syntax token colours (Shiki ran, not a plain <pre>)', () => {
				// A highlighted token carries an inline colour from the theme.
				cy.get(root + '[data-testid="lq-ai-code-block"][data-lang="python"] pre.shiki span[style*="color"]')
					.its('length')
					.should('be.greaterThan', 1);
			});

			it('preserves the Shiki dark-mode variable through DOMPurify (dark mode works)', () => {
				// The core sanitiser risk: DOMPurify must keep the `--shiki-dark`
				// CSS custom property in the inline style, or class-based dark mode
				// silently falls back to light colours.
				cy.get(root + '[data-testid="lq-ai-code-block"] pre.shiki span[style*="--shiki-dark"]')
					.its('length')
					.should('be.greaterThan', 0);
			});

			it('renders an injected <script> as inert text, never as an element', () => {
				const noLang = root + '[data-testid="lq-ai-code-block"]:last-of-type';
				// The literal appears as visible source…
				cy.get(noLang).should('contain.text', 'alert(1)');
				// …but no executable <script> element was created inside the card.
				cy.get(noLang + ' script').should('not.exist');
			});

			it('copies the raw source to the clipboard with accessible feedback', () => {
				cy.window().then((win) => {
					cy.stub(win.navigator.clipboard, 'writeText').as('copy').resolves();
				});
				cy.get(root + '[data-testid="lq-ai-code-block"][data-lang="python"] [data-testid="lq-ai-code-copy"]')
					.click()
					.should('have.text', 'Copied')
					.and('have.attr', 'aria-label', 'Code copied to clipboard');
				cy.get('@copy').should('have.been.calledWithMatch', /def redline/);
			});
		});

		describe('live chat — code block on a real assistant message', () => {
			beforeEach(() => {
				stubChat();
				login();
			});

			it('renders the code card inside the assistant turn only', () => {
				cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
				cy.get('[data-testid="lq-ai-message-m-asst-1"]', { timeout: 30000 }).should('exist');
				cy.get('[data-testid="lq-ai-message-m-asst-1"] [data-testid="lq-ai-code-block"]', {
					timeout: 30000
				})
					.should('exist')
					.and('have.attr', 'data-lang', 'python');
				cy.get('[data-testid="lq-ai-message-m-asst-1"] [data-testid="lq-ai-code-block"] pre.shiki').should(
					'exist'
				);
				// The user turn has no code card.
				cy.get('[data-testid="lq-ai-message-m-user-1"] [data-testid="lq-ai-code-block"]').should(
					'not.exist'
				);
			});
		});
	}

	// ---- before/after capture ----
	describe('capture', () => {
		it('captures the lab code cards (light + dark)', () => {
			login();
			for (const theme of ['light', 'dark'] as const) {
				cy.window().then((w) => w.localStorage.setItem('theme', theme));
				cy.visit('/lq-ai/_ae-lab');
				cy.get('[data-testid="ae-lab-code"]', { timeout: 30000 }).should('be.visible');
				cy.window().then((win) => {
					win.localStorage.setItem('theme', theme);
					win.document.documentElement.classList.remove('light', 'dark');
					win.document.documentElement.classList.add(theme);
				});
				cy.get('html').should('have.class', theme);
				cy.viewport(1281, 900);
				cy.viewport(1280, 900);
				cy.wait(400);
				cy.get('[data-testid="ae-lab-code"]').scrollIntoView();
				cy.screenshot(`ae4-${PHASE()}-lab-code-${theme}`, { capture: 'viewport' });
			}
		});

		it('captures the chat surface with a code block (light + dark, wide + narrow)', () => {
			stubChat();
			login();
			for (const theme of ['light', 'dark'] as const) {
				cy.window().then((w) => w.localStorage.setItem('theme', theme));
				cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
				cy.get('[data-testid="lq-ai-message-list"]', { timeout: 30000 }).should('exist');
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
				cy.screenshot(`ae4-${PHASE()}-chat-${theme}-wide`, { capture: 'viewport' });

				cy.viewport(701, 900);
				cy.viewport(700, 900);
				cy.wait(400);
				cy.screenshot(`ae4-${PHASE()}-chat-${theme}-narrow`, { capture: 'viewport' });
			}
		});
	});
});

// --- fixtures (mirrors ae3 SHORT fixture) ---
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
			title: 'Redline helper (code)',
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
			content: 'Give me a Python helper that flags uncapped indemnities.',
			created_at: NOW
		},
		{
			id: 'm-asst-1',
			chat_id: CHAT_ID,
			role: 'assistant',
			content:
				'Here is a small helper:\n\n' +
				'```python\n' +
				'def redline(clause: str) -> bool:\n' +
				'    # flag uncapped indemnities\n' +
				'    return "without limit" in clause.lower()\n' +
				'```\n\n' +
				'Call it per clause.',
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
	cy.intercept('GET', '**/api/v1/chats/*/messages*', MESSAGES).as('messages');
	cy.intercept('GET', '**/api/v1/chats/*/messages/*/citations', []).as('citations');
}
