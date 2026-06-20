/**
 * PRIV-9b — live changed-row highlight (browser visual, deterministic).
 *
 * The agent's run stream now carries a `data-ropa-change` frame (ADR-F024) over
 * the cross-process Redis transport (ADR-F025); the cockpit lifts the changed
 * entity id into a recently-changed set and the co-visible ROPA register WASHES
 * the matching row. This spec drives the REAL highlight code path in the REAL
 * browser: the seeded Privacy matter is opened (genuine `isPrivacyMatter`), and
 * the thread poll + the run STREAM + the ROPA lists are intercepted so a real
 * `data-ropa-change` frame lands on a real rendered row — deterministically, no
 * LLM, no flake. (The SAME frame is proven to fire LIVE on DeepSeek in
 * docs/fork/evidence/priv-9b/FINDINGS.md.)
 *
 * The run is held `running` so ConversationPanel re-opens the stream each poll
 * and re-delivers the change frame — the wash stays lit (no decay race).
 *
 * Run (live stack for auth + the matters rollup):
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/priv-9b-highlight.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
const PRIVACY_MATTER = '47519e68-d764-4a3f-b96b-2d703c16229c';
const TID = '00000000-0000-4000-8000-00000000b9c1';
const RID = '00000000-0000-4000-8000-00000000b9d2';
// The system the "agent just created" — the stream's change frame names this id,
// and the intercepted systems list renders a row with it, so the wash matches.
const SID = '00000000-0000-4000-8000-0000000059a1';

function pinTheme(theme: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', theme);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(theme);
	});
	cy.get('html').should('have.class', theme);
}

function systemRow(id: string, name: string) {
	const now = new Date().toISOString();
	return {
		id,
		name,
		system_type: 'analytics',
		description: null,
		owner: null,
		hosting_location: 'EU (Frankfurt)',
		retention: null,
		security_measures: null,
		ai_usage: false,
		created_at: now,
		updated_at: now,
		processing_activities: []
	};
}

// One real AI SDK UI Message Stream: open the message, emit the PRIV-9b change
// frame (the honest signal), then end. No data-run, so the run stays "running"
// and the panel re-opens the stream on the next poll (keeps the wash lit).
const SSE_BODY = [
	`data: ${JSON.stringify({ type: 'start', messageId: RID })}`,
	'',
	`data: ${JSON.stringify({
		type: 'data-ropa-change',
		transient: true,
		data: { kind: 'system', id: SID, verb: 'create' }
	})}`,
	'',
	'data: [DONE]',
	'',
	''
].join('\n');

describe('PRIV-9b — changed-row highlight', { retries: { runMode: 1, openMode: 0 } }, () => {
	it('washes the register row the agent just changed (real stream frame)', () => {
		const runRow = () => {
			const now = new Date().toISOString();
			return {
				id: RID,
				user_id: 'admin',
				thread_id: TID,
				project_id: PRIVACY_MATTER,
				status: 'running',
				prompt: 'Add Hotjar as a new analytics system.',
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
					project_id: PRIVACY_MATTER,
					title: 'Add Hotjar analytics',
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
					project_id: PRIVACY_MATTER,
					title: 'Add Hotjar analytics',
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
		// The run stream now carries a REAL data-ropa-change frame (the thing 9b adds).
		cy.intercept('GET', '**/api/v1/agents/runs/*/stream', {
			statusCode: 200,
			headers: { 'content-type': 'text/event-stream' },
			body: SSE_BODY
		});
		// The register: one system whose id the change frame names → it washes.
		cy.intercept('GET', '**/api/v1/ropa/systems*', { body: [systemRow(SID, 'Hotjar')] });
		cy.intercept('GET', '**/api/v1/ropa/processing-activities*', { body: [] });
		cy.intercept('GET', '**/api/v1/ropa/vendors*', { body: [] });
		cy.intercept('GET', '**/api/v1/ropa/data-subject-categories*', { body: [] });
		cy.intercept('GET', '**/api/v1/ropa/data-categories*', { body: [] });
		cy.intercept('GET', '**/api/v1/ropa/assessments*', { body: [] });
		cy.intercept('GET', '**/api/v1/ropa/programme-summary*', {
			body: {
				activities_total: 0,
				systems_total: 1,
				vendors_total: 0,
				transfers_total: 0,
				transfers_restricted: 0,
				special_category_activities: 0,
				systems_using_ai: 0,
				lawful_basis: [],
				controller_role: [],
				dpa_status: [],
				gaps: {
					activities_without_systems: 0,
					activities_without_recipients: 0,
					activities_without_data_categories: 0,
					activities_without_data_subjects: 0,
					vendors_without_dpa: 0
				}
			}
		});
		cy.intercept('GET', '**/api/v1/ropa/data-flow*', { body: { nodes: [], edges: [] } });

		cy.visit(`/lq-ai?area=privacy&matter=${PRIVACY_MATTER}&thread=${TID}`);
		cy.get('[data-testid="lq-cockpit-conversation"]', { timeout: 30000 }).should('exist');
		// Collapse the rail → co-visible (chat locked to Stop + register both mounted).
		cy.get('[data-testid="lq-cockpit-rail-toggle"]').click();
		cy.get('[data-testid="lq-ai-agents-stop"]', { timeout: 30000 }).should('be.visible');

		// Switch the co-visible register to the Systems table where the new row lives.
		cy.contains('button', 'Systems').click();
		cy.contains('td', 'Hotjar', { timeout: 30000 }).should('be.visible');

		// THE HIGHLIGHT: the stream's data-ropa-change frame washes the Hotjar row.
		cy.get('tr.lq-row-changed', { timeout: 15000 }).should('be.visible');
		cy.contains('tr.lq-row-changed', 'Hotjar').should('exist');

		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			// The wash stays lit (the panel re-opens the stream each poll), so a
			// theme flip + paint settle still captures it.
			cy.get('tr.lq-row-changed', { timeout: 15000 }).should('be.visible');
			// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
			cy.wait(300);
			cy.screenshot(`priv-9b-highlight-${theme}`, { capture: 'viewport' });
		}
	});
});
