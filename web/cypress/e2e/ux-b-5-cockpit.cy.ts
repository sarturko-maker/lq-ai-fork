/**
 * UX-B-5 — cockpit perfection (web) capture.
 *
 * Surfaces the now-proven backend loop honestly (ADR-F012/F013 design
 * language): (1) explicit practice-area selection at matter creation, (2) the
 * read-only area-config disclosure (profile / skills / subagents — the
 * transparency rule), and (3) the subagent DELEGATION BOUNDARY in a run.
 *
 * (1) + (2) run against the LIVE dev backend (Commercial is configured with a
 * `document-researcher` subagent — real evidence). (3) is STUBBED: a tier-4
 * model usually won't fan out at a small matter size (UX-B-4), so a live
 * delegated run isn't guaranteed — the deterministic unit test
 * (`groupTurnTree`) is the gate; this stub renders the boundary for the
 * screenshot. Headed for an honest dark capture.
 *
 * Run:
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/ux-b-5-cockpit.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
const PHASE = () => (Cypress.env('PHASE') as string) || 'after';

function login() {
	cy.session('lq-admin', () => {
		cy.visit('/lq-ai/login');
		cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
		cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!');
		cy.get('button[type="submit"]').click();
		cy.url({ timeout: 30000 }).should('not.include', '/login');
	});
}

function pinTheme(theme: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', theme);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(theme);
	});
	cy.get('html').should('have.class', theme);
}

describe('UX-B-5 cockpit perfection', { retries: { runMode: 2, openMode: 0 } }, () => {
	it('area-config disclosure + area-pick at matter creation (live Commercial)', () => {
		login();
		cy.visit('/lq-ai');
		cy.get('[data-testid="lq-cockpit"]', { timeout: 30000 }).should('be.visible');
		// Enter Commercial (the one area configured with skills + a subagent).
		cy.get('[data-testid="lq-cockpit-area-grid"]', { timeout: 30000 }).should('exist');
		cy.contains('[data-testid="lq-cockpit-area-grid"] *', 'Commercial', { timeout: 30000 })
			.scrollIntoView()
			.click();
		cy.get('[data-testid="lq-cockpit-matters"]', { timeout: 30000 }).should('be.visible');

		// (2) The read-only area-config disclosure — open it.
		cy.get('[data-testid="lq-cockpit-area-config"]', { timeout: 15000 }).should('exist');
		cy.get('[data-testid="lq-cockpit-area-config"] > summary').click();
		cy.get('[data-testid="lq-cockpit-area-subagents"]', { timeout: 10000 }).should('be.visible');
		cy.contains('[data-testid="lq-cockpit-area-subagents"]', 'document-researcher').should(
			'be.visible'
		);
		cy.wait(500);

		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			cy.viewport(1281, 950);
			cy.viewport(1280, 950);
			cy.wait(300);
			cy.screenshot(`ux-b-5-${PHASE()}-area-config-${theme}-wide`, { capture: 'viewport' });
		}

		// (1) The new-matter dialog now carries an explicit area PICKER. Scope the
		// click to the matters panel — the rail also has a "New matter" button
		// (which navigates away rather than opening the dialog).
		pinTheme('light');
		cy.get('[data-testid="lq-cockpit-matters"]').contains('button', /New /).click();
		cy.get('[data-testid="lq-cockpit-new-matter-area"]', { timeout: 10000 }).should('be.visible');
		cy.get('[data-testid="lq-cockpit-new-matter-name"]').should('be.visible');
		cy.wait(400);
		cy.screenshot(`ux-b-5-${PHASE()}-new-matter-area-pick-light`, { capture: 'viewport' });
		pinTheme('dark');
		cy.wait(300);
		cy.screenshot(`ux-b-5-${PHASE()}-new-matter-area-pick-dark`, { capture: 'viewport' });
	});

	it('subagent delegation boundary in a run (stubbed fixture)', () => {
		const MID = 'p-uxb5-rfq';
		const TID = 't-uxb5-rfq';
		const RID = 'r-uxb5-rfq';
		const created = '2026-06-17T10:00:00.000Z';

		// Matter activity → the cockpit resolves the selected matter (Commercial).
		cy.intercept('GET', '**/api/v1/agents/matters', {
			matters: [
				{
					project_id: MID,
					name: 'Acme RFQ — vendor review',
					practice_area_id: null,
					practice_area_key: 'commercial',
					privileged: false,
					thread_count: 1,
					last_run_status: 'completed',
					last_run_at: created
				}
			],
			unfiled: { thread_count: 0, last_run_status: null, last_run_at: null }
		}).as('matters');

		// Threads list for the matter → the one conversation.
		cy.intercept('GET', '**/api/v1/agents/threads?*', {
			threads: [
				{
					id: TID,
					user_id: 'u-1',
					project_id: MID,
					title: 'Review the RFQ across all the documents',
					created_at: created,
					last_run_at: created,
					last_run_status: 'completed'
				}
			],
			total: 1
		}).as('threads');

		// The conversation detail with a `task` delegation: a root search, then a
		// delegated `document-researcher` whose nested steps carry parent_step_id,
		// then the task's return — exactly what groupTurnTree folds into a boundary.
		cy.intercept('GET', `**/api/v1/agents/threads/${TID}`, {
			thread: {
				id: TID,
				user_id: 'u-1',
				project_id: MID,
				title: 'Review the RFQ across all the documents',
				created_at: created,
				last_run_at: created,
				last_run_status: 'completed'
			},
			runs: [
				{
					run: {
						id: RID,
						user_id: 'u-1',
						thread_id: TID,
						project_id: MID,
						status: 'completed',
						prompt: 'Review the RFQ across all the documents and compare the two vendors.',
						final_answer:
							'Northstar bids £420k (99.5% SLA, 100% liability cap); Brightpath £390k (98% SLA, 50% cap + indemnity). Against our draft terms, Brightpath’s 50% cap is below our 150% requirement.',
						model_alias: 'smart',
						purpose: 'agent_loop',
						max_steps: 28,
						started_at: created,
						finished_at: created,
						error: null,
						cost_usd: null
					},
					steps: [
						{
							id: 's1',
							run_id: RID,
							seq: 1,
							kind: 'tool_call',
							name: 'task',
							summary:
								'{"description": "Read all four RFQ documents and compare the vendors on price, SLA and liability.", "subagent_type": "document-researcher"}',
							parent_step_id: null,
							created_at: created
						},
						{
							id: 's2',
							run_id: RID,
							seq: 2,
							kind: 'tool_call',
							name: 'search_documents',
							summary: '{"query": "liability cap"}',
							parent_step_id: 's1',
							created_at: created
						},
						{
							id: 's3',
							run_id: RID,
							seq: 3,
							kind: 'tool_result',
							name: 'search_documents',
							summary: 'Vendor-Proposal-Brightpath: liability cap 50% of fees; indemnity included.',
							parent_step_id: 's1',
							created_at: created
						},
						{
							id: 's4',
							run_id: RID,
							seq: 4,
							kind: 'tool_call',
							name: 'read_document',
							summary: '{"document_id": "draft-msa-terms"}',
							parent_step_id: 's1',
							created_at: created
						},
						{
							id: 's5',
							run_id: RID,
							seq: 5,
							kind: 'tool_result',
							name: 'read_document',
							summary: 'Draft MSA: liability cap 150% of annual fees; indemnity required.',
							parent_step_id: 's1',
							created_at: created
						},
						{
							id: 's6',
							run_id: RID,
							seq: 6,
							kind: 'tool_result',
							name: 'task',
							summary:
								'Compared Northstar vs Brightpath on price/SLA/liability and checked both against the draft MSA cap.',
							parent_step_id: null,
							created_at: created
						}
					]
				}
			],
			continuable: false
		}).as('thread');

		login();
		cy.visit(`/lq-ai?area=commercial&matter=${MID}&thread=${TID}`);
		cy.wait('@thread', { timeout: 30000 });
		cy.get('[data-testid="lq-ai-agents-thread"]', { timeout: 30000 }).should('exist');
		// The delegation boundary renders, labelled with the subagent type.
		cy.get('[data-testid="lq-ai-agents-delegation"]', { timeout: 15000 }).should('be.visible');
		cy.contains('[data-testid="lq-ai-agents-delegation"]', 'document-researcher').should(
			'be.visible'
		);
		cy.wait(500);

		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			cy.viewport(1281, 950);
			cy.viewport(1280, 950);
			cy.wait(300);
			cy.screenshot(`ux-b-5-${PHASE()}-delegation-boundary-${theme}-wide`, { capture: 'viewport' });
			cy.viewport(821, 950);
			cy.viewport(820, 950);
			cy.wait(300);
			cy.screenshot(`ux-b-5-${PHASE()}-delegation-boundary-${theme}-narrow`, {
				capture: 'viewport'
			});
		}
	});
});
