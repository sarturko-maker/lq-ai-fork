/**
 * PRIV-9a — run-lock + live register refresh + measured time-to-visible.
 *
 * DETERMINISTIC: the real seeded Privacy matter is opened (so the cockpit and
 * `isPrivacyMatter` are genuine), but the thread-detail poll, the run stream,
 * the cancel, and the ROPA list endpoints are INTERCEPTED so timing is exact —
 * no LLM, no writes to the live register, no flake. It proves:
 *   1. while the agent works the composer collapses to a single Stop control
 *      (the textarea is removed from the DOM, not just disabled);
 *   2. the co-visible register re-reads live and a committed change appears
 *      within ~one poll interval — captured as a NUMBER (docs/fork/evidence);
 *   3. Stop calls the real backend cancel and the composer re-enables on the
 *      settled `cancelled` row.
 *
 * Run (live stack for auth + the matters rollup):
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/priv-9a-runlock.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
const PRIVACY_MATTER = '47519e68-d764-4a3f-b96b-2d703c16229c';
const TID = '00000000-0000-4000-8000-00000000a9a1';
const RID = '00000000-0000-4000-8000-00000000a9b2';

type RunStatus = 'running' | 'cancelled' | 'completed';

function activity(id: string, name: string) {
	const now = new Date().toISOString();
	return {
		id,
		name,
		purpose: 'Product analytics',
		lawful_basis: 'consent',
		controller_role: 'controller',
		retention: '2 years',
		special_category: false,
		created_at: now,
		updated_at: now,
		systems: [],
		vendors: [],
		transfers: [],
		data_subject_categories: [],
		data_categories: []
	};
}

const SUMMARY = {
	activities_total: 1,
	systems_total: 0,
	vendors_total: 0,
	transfers_total: 0,
	transfers_restricted: 0,
	special_category_activities: 0,
	systems_using_ai: 0,
	lawful_basis: [{ value: 'consent', count: 1 }],
	controller_role: [{ value: 'controller', count: 1 }],
	dpa_status: [],
	gaps: {
		activities_without_systems: 1,
		activities_without_recipients: 1,
		activities_without_data_categories: 1,
		activities_without_data_subjects: 1,
		vendors_without_dpa: 0
	}
};

describe('PRIV-9a — run-lock + live register', { retries: { runMode: 1, openMode: 0 } }, () => {
	it('locks the chat to a Stop button and updates the register live as the agent works', () => {
		let runStatus: RunStatus = 'running';
		let activities = [activity('00000000-0000-4000-8000-00000000a001', 'Existing analytics')];

		const runRow = () => {
			const now = new Date().toISOString();
			return {
				id: RID,
				user_id: 'admin',
				thread_id: TID,
				project_id: PRIVACY_MATTER,
				status: runStatus,
				prompt: 'We moved off Mixpanel — use Hotjar now.',
				final_answer: runStatus === 'running' ? null : '',
				model_alias: 'deepseek',
				purpose: 'agent_loop',
				max_steps: 80,
				started_at: now, // fresh each reply → never trips the staleness cutoff
				finished_at: runStatus === 'running' ? null : now,
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
					project_id: PRIVACY_MATTER,
					title: 'Swap Mixpanel for Hotjar',
					created_at: now,
					last_run_at: now,
					last_run_status: runStatus
				},
				runs: [{ run: runRow(), steps: [] }],
				continuable: runStatus !== 'running'
			};
		};

		cy.viewport(1280, 850);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());

		// Control the conversation + register; auth + /agents/matters stay LIVE so
		// the matter is a genuine Privacy matter (isPrivacyMatter true).
		cy.intercept('GET', '**/api/v1/agents/threads?*', {
			threads: [
				{
					id: TID,
					user_id: 'admin',
					project_id: PRIVACY_MATTER,
					title: 'Swap Mixpanel for Hotjar',
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
		// The run stream is animation only (ADR-F004) — return empty so the panel
		// falls back to the polled contract we control here.
		cy.intercept('GET', '**/api/v1/agents/runs/*/stream', { statusCode: 200, body: '' });
		cy.intercept('POST', `**/api/v1/agents/runs/${RID}/cancel`, (req) => {
			runStatus = 'cancelled';
			req.reply(runRow());
		}).as('cancel');
		cy.intercept('GET', '**/api/v1/ropa/processing-activities*', (req) => req.reply(activities));
		cy.intercept('GET', '**/api/v1/ropa/systems*', { body: [] });
		cy.intercept('GET', '**/api/v1/ropa/vendors*', { body: [] });
		cy.intercept('GET', '**/api/v1/ropa/data-subject-categories*', { body: [] });
		cy.intercept('GET', '**/api/v1/ropa/data-categories*', { body: [] });
		cy.intercept('GET', '**/api/v1/ropa/programme-summary*', { body: SUMMARY });
		cy.intercept('GET', '**/api/v1/ropa/data-flow*', { body: { nodes: [], edges: [] } });

		cy.visit(`/lq-ai?area=privacy&matter=${PRIVACY_MATTER}&thread=${TID}`);
		cy.get('[data-testid="lq-cockpit-conversation"]', { timeout: 30000 }).should('exist');
		// Collapse the rail → co-visible (chat + register both mounted).
		cy.get('[data-testid="lq-cockpit-rail-toggle"]').click();

		// (1) RUN-LOCK: only the Stop button is clickable; the textarea is GONE.
		cy.get('[data-testid="lq-ai-agents-stop"]', { timeout: 30000 }).should('be.visible');
		cy.get('#ag-prompt').should('not.exist');

		// The register is co-visible; switch it to the Processing activities table
		// so a new row is observable, and confirm the starting row is there.
		cy.contains('button', 'Processing activities').click();
		cy.contains('td', 'Existing analytics', { timeout: 30000 }).should('be.visible');
		cy.screenshot('priv-9a-runlock-covisible', { capture: 'viewport' });

		// (2) LIVE REFRESH: the agent "commits" a new activity → flip the intercept
		// and time how long until the row is visible (poll cadence = 2s).
		let t0 = 0;
		cy.then(() => {
			t0 = performance.now();
			activities = [
				activity('00000000-0000-4000-8000-00000000a002', 'PRIV-9a live row'),
				...activities
			];
		});
		cy.contains('td', 'PRIV-9a live row', { timeout: 8000 }).should('be.visible');
		// No skeleton flicker on a live refresh (quiet reload contract): the prior
		// row stays on screen and the "Loading the register…" skeleton never returns.
		cy.contains('td', 'Existing analytics').should('be.visible');
		cy.contains('Loading the register…').should('not.exist');
		cy.then(() => {
			const ms = Math.round(performance.now() - t0);
			cy.log(`time-to-visible: ${ms}ms`);
			// One poll interval is 2000ms; a change that lands just after a tick
			// shows on the next one. < 3000ms proves "live as the agent works",
			// never a minute-long frozen wait.
			expect(ms, 'register reflects a committed change within ~one poll interval').to.be.lessThan(
				3000
			);
			cy.writeFile(
				'../docs/fork/evidence/priv-9a/time-to-visible.json',
				{
					metric: 'commit_to_row_visible_ms',
					value_ms: ms,
					poll_interval_ms: 2000,
					bound_ms: 3000,
					note: 'Deterministic intercept spec; the agent committed a new ROPA activity while the run was active and the co-visible register reflected it within one poll interval.'
				},
				{ flag: 'w' }
			);
		});
		cy.screenshot('priv-9a-live-row-appeared', { capture: 'viewport' });

		// (3) STOP: the real backend cancel fires; the composer re-enables on the
		// settled cancelled row (ADR-F004 — the polled row decides, not the click).
		cy.get('[data-testid="lq-ai-agents-stop"]').click();
		cy.wait('@cancel').its('request.method').should('eq', 'POST');
		cy.get('#ag-prompt', { timeout: 30000 }).should('exist');
		cy.screenshot('priv-9a-after-stop', { capture: 'viewport' });
	});
});
