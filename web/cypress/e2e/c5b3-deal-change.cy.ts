/**
 * C5b-3 — live negotiation verdict chips (browser visual, deterministic).
 *
 * When the Commercial agent responds to a counterparty's marked-up contract, its
 * run stream carries a `data-deal-change` frame per item (ADR-F032) over the
 * cross-process transport (ADR-F025); the cockpit flashes a transient verdict
 * CHIP per ref INLINE in the conversation (Commercial has no register to wash).
 * This spec drives the REAL chip code path in the REAL browser: a Commercial
 * matter is opened and the thread poll + the run STREAM are intercepted so real
 * `data-deal-change` frames land — deterministically, no LLM, no flake. (The same
 * frames fire LIVE on DeepSeek; see docs/fork/evidence/c5b3/.)
 *
 * The run is held `running` with no `data-run`. In PRODUCTION the chips ride a
 * client-side decay timer (data-deal-change is transient — drained once, no server
 * replay); here the static `cy.intercept` body re-sends the frames on every stream
 * re-open as a TEST CONVENIENCE, which keeps the chips lit for the screenshot and is
 * NOT how the real transport behaves.
 *
 * Run (live stack for auth + the matters rollup):
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/c5b3-deal-change.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
// The seeded Atlas Commercial matter (the documented dev test vehicle).
const COMMERCIAL_MATTER = '905720d1-5d17-43cd-a8f0-3a76d095de34';
const TID = '00000000-0000-4000-8000-00000000c5b3';
const RID = '00000000-0000-4000-8000-00000000c5d3';

function pinTheme(theme: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', theme);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(theme);
	});
	cy.get('html').should('have.class', theme);
}

// One real AI SDK UI Message Stream: open the message, emit a data-deal-change
// frame per verdict (covering every chip tone), then end. No data-run, so the run
// stays "running" and the panel re-opens the stream on the next poll (chips lit).
const FRAMES = [
	{ ref: 'C1', verdict: 'accept' },
	{ ref: 'C2', verdict: 'counter' },
	{ ref: 'C3', verdict: 'reject' },
	{ ref: 'C4', verdict: 'escalate' },
	{ ref: 'Com:1', verdict: 'reply' }
];
const SSE_BODY = [
	`data: ${JSON.stringify({ type: 'start', messageId: RID })}`,
	'',
	...FRAMES.flatMap((f) => [
		`data: ${JSON.stringify({ type: 'data-deal-change', transient: true, data: f })}`,
		''
	]),
	'data: [DONE]',
	'',
	''
].join('\n');

describe('C5b-3 — live verdict chips', { retries: { runMode: 1, openMode: 0 } }, () => {
	it('flashes a verdict chip per counterparty item the agent decided (real stream frame)', () => {
		const runRow = () => {
			const now = new Date().toISOString();
			return {
				id: RID,
				user_id: 'admin',
				thread_id: TID,
				project_id: COMMERCIAL_MATTER,
				status: 'running',
				prompt: 'Respond to the counterparty markup on the NDA.',
				final_answer: null,
				model_alias: 'deepseek',
				purpose: 'agent_loop',
				max_steps: 80,
				started_at: now, // fresh each reply → never trips the staleness cutoff
				finished_at: null,
				error: null,
				cost_usd: null
			};
		};
		const threadDetail = () => {
			const now = new Date().toISOString();
			return {
				thread: {
					id: TID,
					user_id: 'admin',
					project_id: COMMERCIAL_MATTER,
					title: 'Counterparty round 2',
					created_at: now,
					last_run_at: now,
					last_run_status: 'running'
				},
				runs: [{ run: runRow(), steps: [] }],
				continuable: false
			};
		};

		cy.viewport(1280, 850);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());

		cy.intercept('GET', '**/api/v1/agents/threads?*', {
			threads: [
				{
					id: TID,
					user_id: 'admin',
					project_id: COMMERCIAL_MATTER,
					title: 'Counterparty round 2',
					created_at: new Date().toISOString(),
					last_run_at: new Date().toISOString(),
					last_run_status: 'running'
				}
			],
			total_count: 1,
			limit: 100,
			offset: 0
		});
		cy.intercept('GET', `**/api/v1/agents/threads/${TID}*`, (req) => req.reply(threadDetail()));
		// The run stream carries REAL data-deal-change frames (the thing C5b-3 adds).
		cy.intercept('GET', '**/api/v1/agents/runs/*/stream', {
			statusCode: 200,
			headers: { 'content-type': 'text/event-stream' },
			body: SSE_BODY
		});

		cy.visit(`/lq-ai?area=commercial&matter=${COMMERCIAL_MATTER}&thread=${TID}`);
		cy.get('[data-testid="lq-cockpit-conversation"]', { timeout: 30000 }).should('exist');

		// THE CHIPS: each data-deal-change frame flashes a verdict chip inline.
		cy.get('[data-testid="lq-ai-agents-deal-chips"]', { timeout: 30000 }).should('be.visible');
		cy.get('[data-testid="lq-ai-agents-deal-chip"]').should('have.length', FRAMES.length);
		// The verdicts render with their human labels + tone classes.
		cy.contains('[data-testid="lq-ai-agents-deal-chip"]', 'C1').should('contain', 'accepted');
		cy.get('.ag-deal-chip--positive').should('contain', 'C1');
		cy.get('.ag-deal-chip--negative').should('contain', 'C3');
		cy.get('.ag-deal-chip--warning').should('contain', 'C4');
		cy.contains('[data-testid="lq-ai-agents-deal-chip"]', 'Com:1').should('contain', 'replied');

		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			// The chips stay lit (the panel re-opens the stream each poll), so a theme
			// flip + paint settle still captures them.
			cy.get('[data-testid="lq-ai-agents-deal-chips"]', { timeout: 15000 }).should('be.visible');
			// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
			cy.wait(300);
			cy.screenshot(`c5b3-deal-change-${theme}`, { capture: 'viewport' });
		}
	});
});
