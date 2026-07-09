/**
 * HITL-3 — cockpit confirm card + resume round-trip (ADR-F071).
 *
 * DETERMINISTIC: the real seeded Commercial matter (Atlas) is opened (so the
 * cockpit + area are genuine), but the thread-detail poll, the run stream, the
 * resume, and the matter-files endpoints are INTERCEPTED — no LLM, no flake. It
 * proves the WEB half of the stop-and-ask loop end-to-end in a browser:
 *   1. a paused (`awaiting_input`) run renders the "Waiting for your go-ahead"
 *      confirm card with the gated tool (`apply_redline`) + Approve / Refuse;
 *   2. clicking Approve POSTs `{decision:{type:'approve'}}` to
 *      `/agents/runs/{id}/resume` and re-syncs by polling (ADR-F004);
 *   3. once the resume run is the thread tail, the card dissolves and the
 *      applied-redline answer shows.
 *
 * The LLM-driven live gate (a real gateway model emitting `apply_redline`,
 * pausing, then applying on Approve) is the maintainer's UAT — this spec pins
 * the deterministic web wiring the same way priv-9a-runlock pins the run-lock.
 *
 * Run (live stack for auth + the matters rollup):
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/hitl3-confirm-card.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
const COMMERCIAL_MATTER = '905720d1-5d17-43cd-a8f0-3a76d095de34';
const TID = '00000000-0000-4000-8000-0000000031c1';
const RID = '00000000-0000-4000-8000-0000000031c2';
const RID2 = '00000000-0000-4000-8000-0000000031c3';

describe('HITL-3 confirm card', () => {
	it('renders the pause card and resumes on Approve', () => {
		let paused = true;
		const now = () => new Date().toISOString();

		const pausedRun = () => ({
			id: RID,
			user_id: 'admin',
			thread_id: TID,
			project_id: COMMERCIAL_MATTER,
			status: 'awaiting_input',
			prompt: 'Redline the NDA to our positions.',
			final_answer: null,
			model_alias: 'balanced',
			purpose: 'commercial',
			max_steps: 40,
			started_at: now(),
			finished_at: now(),
			error: null,
			cost_usd: null,
			budget_profile: 'balanced'
		});

		const hitlStep = () => ({
			id: '00000000-0000-4000-8000-0000000031d1',
			run_id: RID,
			seq: 1,
			kind: 'hitl_request',
			name: 'apply_redline',
			// The runner's digest shape: json.dumps([{tool,args}], sort_keys=True).
			summary: '[{"args": {"start_fresh": false}, "tool": "apply_redline"}]',
			parent_step_id: null,
			created_at: now()
		});

		const resumeRun = () => ({
			...pausedRun(),
			id: RID2,
			status: 'completed',
			prompt: '[resume: approve]',
			final_answer: 'Applied the tracked-changes redline to the NDA.'
		});

		const threadRow = () => ({
			id: TID,
			user_id: 'admin',
			project_id: COMMERCIAL_MATTER,
			title: 'Redline the NDA',
			created_at: now(),
			last_run_at: now(),
			last_run_status: paused ? 'awaiting_input' : 'completed'
		});

		const threadDetail = () => ({
			thread: threadRow(),
			runs: paused
				? [{ run: pausedRun(), steps: [hitlStep()] }]
				: [
						{ run: pausedRun(), steps: [hitlStep()] },
						{ run: resumeRun(), steps: [] }
					],
			continuable: true
		});

		cy.viewport(1280, 850);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());

		// Auth + /agents/matters stay LIVE so the matter is a genuine Commercial
		// matter; the conversation + its side-loads are controlled here.
		cy.intercept('GET', '**/api/v1/agents/threads?*', {
			threads: [threadRow()],
			total_count: 1,
			limit: 100,
			offset: 0
		});
		cy.intercept('GET', `**/api/v1/agents/threads/${TID}*`, (req) => req.reply(threadDetail()));
		// The stream is animation only (ADR-F004) — empty so the panel falls back
		// to the polled contract we control.
		cy.intercept('GET', '**/api/v1/agents/runs/*/stream', { statusCode: 200, body: '' });
		// A matter-bound run loads produced files / redline baseline — keep quiet.
		cy.intercept('GET', '**/api/v1/matters/*/files*', { body: [] });
		cy.intercept('POST', `**/api/v1/agents/runs/${RID}/resume`, (req) => {
			paused = false;
			req.reply({ statusCode: 202, body: resumeRun() });
		}).as('resume');

		cy.visit(`/lq-ai?area=commercial&matter=${COMMERCIAL_MATTER}&thread=${TID}`);
		cy.get('[data-testid="lq-cockpit-conversation"]', { timeout: 30000 }).should('exist');

		// (1) The confirm card renders from the settled hitl_request step.
		cy.get('[data-testid="lq-ai-agents-hitl-card"]', { timeout: 30000 }).should('be.visible');
		cy.contains('[data-testid="lq-ai-agents-hitl-card"]', 'Waiting for your go-ahead').should(
			'be.visible'
		);
		cy.contains('[data-testid="lq-ai-agents-hitl-card"]', 'apply_redline').should('be.visible');
		cy.get('[data-testid="lq-ai-agents-hitl-refuse"]').should('be.visible');
		cy.screenshot('hitl3-confirm-card', { capture: 'viewport' });

		// (2) Approve → POSTs the closed-enum decision to /resume.
		cy.get('[data-testid="lq-ai-agents-hitl-approve"]').click();
		cy.wait('@resume').then((i) => {
			expect(i.request.method).to.eq('POST');
			expect(i.request.body).to.deep.equal({ decision: { type: 'approve' } });
		});

		// (3) The resume run becomes the thread tail → the card dissolves and the
		// applied-redline answer shows (settled rows decide, ADR-F004).
		cy.get('[data-testid="lq-ai-agents-hitl-card"]', { timeout: 30000 }).should('not.exist');
		cy.contains('Applied the tracked-changes redline', { timeout: 30000 }).should('be.visible');
		cy.screenshot('hitl3-after-approve', { capture: 'viewport' });
	});
});
