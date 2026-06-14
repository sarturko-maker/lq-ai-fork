/**
 * AE6 — Tool + Task (ADR-F011).
 *
 * The agent timeline (`ConversationPanel`) is driven on the legacy agents
 * surface (`/lq-ai/agents`) with backend-free fixtures — a single SETTLED
 * conversation, so polling/streaming never engage and the render is
 * deterministic. The functional `describe` asserts the AE identity: the
 * turn's steps live in one collapsible **Task** list, each tool is an AE
 * **Tool** card (wrench glyph + name + status badge + collapsible
 * Parameters/Result), and the kept **Reasoning** idiom (`<details>`) still
 * renders. The capture `describe` is element-guarded so it runs on BOTH the
 * pre- and post-AE6 bundle for before/after evidence — `.ag-layout` collapses
 * to one column below 900px, so the narrow shot proves the responsive reflow.
 *
 * Run (live stack, headed for honest dark capture):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ae6-tool-task.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!,PHASE=after
 */
const PHASE = () => (Cypress.env('PHASE') as string) || 'after';
const CAPTURE_ONLY = String(Cypress.env('CAPTURE_ONLY')) === '1';

const NOW = '2026-06-14T10:00:00Z';
const PROJ_ID = '00000000-0000-4000-8000-0000000000e1';
const THREAD_ID = '00000000-0000-4000-8000-0000000000e9';
const RUN_ID = '00000000-0000-4000-8000-0000000000ea';

function login() {
	cy.session('lq-admin', () => {
		cy.visit('/lq-ai/login');
		cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
		cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!');
		cy.get('button[type="submit"]').click();
		cy.url({ timeout: 30000 }).should('not.include', '/login');
	});
}

/** Open the fixture conversation: visit the agents page, click its row. */
function openThread() {
	cy.visit('/lq-ai/agents');
	cy.get('[data-testid="lq-ai-agents-runs-list"]', { timeout: 30000 }).should('be.visible');
	cy.get('[data-testid="lq-ai-agents-runs-list"] .ag-runs-list__row').first().click();
	cy.get('[data-testid="lq-ai-agents-task"]', { timeout: 30000 }).should('be.visible');
}

describe('AE6 — Tool + Task', { retries: { runMode: 2, openMode: 0 } }, () => {
	if (!CAPTURE_ONLY) {
		describe('agent timeline — Tool + Task identity', () => {
			beforeEach(() => {
				stubAgents();
				login();
				openThread();
			});

			it('groups the turn steps into one collapsible Task list', () => {
				// reasoning row + one paired tool row = 2 steps.
				cy.get('[data-testid="lq-ai-agents-task"]')
					.find('> summary')
					.should('contain.text', '2 steps');
				// The list is the AE rail; the live step-count selector still matches.
				cy.get('[data-testid="lq-ai-agents-task"] .ag-steps li').should('have.length', 2);
			});

			it('renders a paired tool_call + tool_result as one AE Tool card', () => {
				cy.get('[data-testid="lq-ai-agents-tool"]').should('have.length', 1);
				cy.get('[data-testid="lq-ai-agents-tool"]').within(() => {
					// wrench glyph + natural-language title.
					cy.get('svg.lucide-wrench').should('exist');
					cy.get('.ag-tool__title').should('contain.text', 'Searching');
					// settled run → Completed badge with the check glyph.
					cy.get('[data-testid="lq-ai-agents-tool-status"]')
						.should('contain.text', 'Completed')
						.find('svg.lucide-circle-check')
						.should('exist');
				});
			});

			it('keeps the tool body collapsed, revealing Parameters + Result on expand', () => {
				// Collapsed by default (F0-S8 — tool bodies must not drown the thread).
				// Assert on the <details open> attribute, not visibility: Chromium
				// renders a closed <details>'s content as zero-box without display:none,
				// which Cypress still reports as "visible".
				cy.get('[data-testid="lq-ai-agents-tool"]').should('not.have.attr', 'open');
				cy.get('[data-testid="lq-ai-agents-tool"] > summary').click();
				cy.get('[data-testid="lq-ai-agents-tool"]').should('have.attr', 'open');
				cy.get('[data-testid="lq-ai-agents-tool"]').within(() => {
					cy.contains('.ag-tool__label', 'Parameters').should('exist');
					cy.contains('.ag-tool__mono', 'liability cap').should('exist');
					cy.contains('.ag-tool__label', 'Result').should('exist');
					cy.contains('.ag-tool__mono', 'clause 9.2').should('exist');
				});
			});

			it('keeps the Reasoning idiom (a settled <details> in the step list)', () => {
				cy.get('[data-testid="lq-ai-agents-task"] .ag-steps')
					.find('details.ag-thinking')
					.should('exist')
					.find('> summary')
					.should('contain.text', 'Reasoning');
			});

			it('collapses the whole Task list when its trigger is toggled', () => {
				// Open by default; toggling the trigger closes it. Asserted on the
				// open attribute (see the tool-body note about closed-<details>).
				cy.get('[data-testid="lq-ai-agents-task"]').should('have.attr', 'open');
				cy.get('[data-testid="lq-ai-agents-task"] > summary').click();
				cy.get('[data-testid="lq-ai-agents-task"]').should('not.have.attr', 'open');
			});

			it('still renders the final answer beneath the timeline', () => {
				cy.get('[data-testid="lq-ai-agents-answer"] .prose')
					.invoke('text')
					.should('contain', 'uncapped');
			});
		});
	}

	// ---- before/after capture ----
	describe('capture', () => {
		it('captures the agent timeline (light + dark, wide + narrow)', () => {
			stubAgents();
			login();
			// ONE visit + row click; the themes are toggled in place afterwards so
			// the capture never re-triggers auth mid-test (a second cy.visit to
			// /lq-ai/agents intermittently bounces to /login — the documented
			// first-visit session flake).
			openThread();
			cy.get('[data-testid="lq-ai-agents-answer"]').should('be.visible');
			for (const theme of ['light', 'dark'] as const) {
				cy.window().then((win) => {
					win.localStorage.setItem('theme', theme);
					win.document.documentElement.classList.remove('light', 'dark');
					win.document.documentElement.classList.add(theme);
				});
				cy.get('html').should('have.class', theme);

				cy.viewport(1281, 900);
				cy.viewport(1280, 900);
				cy.wait(400);
				cy.screenshot(`ae6-${PHASE()}-timeline-${theme}-wide`, { capture: 'viewport' });

				cy.viewport(821, 900);
				cy.viewport(820, 900);
				cy.wait(400);
				cy.screenshot(`ae6-${PHASE()}-timeline-${theme}-narrow`, { capture: 'viewport' });
			}
		});
	});
});

// --- fixtures: one settled conversation (model turn + one tool pair) ---
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

const THREADS = {
	threads: [
		{
			id: THREAD_ID,
			user_id: 'admin',
			project_id: PROJ_ID,
			title: 'Liability cap review',
			created_at: NOW,
			last_run_at: NOW,
			last_run_status: 'completed'
		}
	],
	total_count: 1,
	limit: 20,
	offset: 0
};

function step(seq: number, kind: string, over: Record<string, unknown> = {}) {
	return {
		id: `step-${seq}`,
		run_id: RUN_ID,
		seq,
		kind,
		name: null,
		summary: null,
		parent_step_id: null,
		created_at: NOW,
		...over
	};
}

const THREAD_DETAIL = {
	thread: THREADS.threads[0],
	runs: [
		{
			run: {
				id: RUN_ID,
				user_id: 'admin',
				thread_id: THREAD_ID,
				project_id: PROJ_ID,
				status: 'completed',
				prompt: 'What is the liability cap under this contract?',
				final_answer:
					'The agreement carries an **uncapped** indemnity in clause 9.2 — unusual for a ' +
					'deal of this size. Recommend negotiating a liability cap before signature.',
				model_alias: 'smart',
				purpose: 'agent_loop',
				max_steps: 20,
				started_at: NOW,
				finished_at: NOW,
				error: null,
				cost_usd: null
			},
			steps: [
				step(1, 'model_turn', {
					summary:
						'<think>I should search the matter for the liability cap before answering.</think>' +
						'Let me check the contract documents.'
				}),
				step(2, 'tool_call', {
					name: 'search_documents',
					summary: '{"query": "liability cap", "k": 5}'
				}),
				step(3, 'tool_result', {
					name: 'search_documents',
					summary: 'Top passage: clause 9.2 — "Indemnification shall be without limit…" (p.14)'
				})
			]
		}
	],
	continuable: true
};

function stubAgents() {
	cy.intercept('GET', /\/api\/v1\/projects(\?.*)?$/, [PROJECT]).as('projects');
	cy.intercept('GET', /\/api\/v1\/agents\/threads(\?.*)?$/, THREADS).as('threads');
	cy.intercept('GET', `**/api/v1/agents/threads/${THREAD_ID}`, THREAD_DETAIL).as('thread');
}
