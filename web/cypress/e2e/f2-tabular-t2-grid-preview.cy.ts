/**
 * F2 Tabular T2 — in-chat grid preview + Expand overlay (browser visual, deterministic).
 *
 * When the Commercial agent finalizes a grid (`finalize_tabular_review`), the
 * cockpit renders a DURABLE preview card after the answer (ADR-F055): a compact
 * M×N table + column pills + an Expand button that opens the FULL reused
 * `TabularGrid` in an in-conversation overlay. The card derives from the SETTLED
 * finalize step already in the run timeline (ADR-F004) — no live-only stream
 * frame — so it re-renders identically on reload.
 *
 * This spec drives the REAL component code path in the REAL browser, no LLM:
 * the thread detail is intercepted to return a COMPLETED run whose steps include
 * a `finalize_tabular_review` tool call (`{"grid_id": …}`), and
 * `GET /tabular/executions/{id}` is intercepted with a completed agentic grid
 * (3 NDAs × Term/Governing-law, the T1 evidence data). (The same render fires
 * live on DeepSeek; see docs/fork/evidence/tabular-review/.)
 *
 * Run (live stack for auth + the matters rollup):
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/f2-tabular-t2-grid-preview.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
// The seeded Atlas Commercial matter (the documented dev test vehicle).
const COMMERCIAL_MATTER = '905720d1-5d17-43cd-a8f0-3a76d095de34';
const TID = '00000000-0000-4000-8000-0000000027a2';
const RID = '00000000-0000-4000-8000-0000000027d2';
const GID = '00000000-0000-4000-8000-0000000027f2';

function pinTheme(theme: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', theme);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(theme);
	});
	cy.get('html').should('have.class', theme);
}

function cell(value: string, quote: string) {
	return { value, citations: [], confidence: 'high', source_quote: quote, notes: null };
}

// A completed agentic grid exactly as GET /tabular/executions/{id} returns it.
const GRID = {
	id: GID,
	user_id: 'admin',
	parent_execution_id: null,
	skill_name: null,
	mode: 'agentic',
	status: 'completed',
	document_ids: ['d-alpha', 'd-beta', 'd-gamma'],
	document_names: ['nda-alpha.txt', 'nda-beta.txt', 'nda-gamma.txt'],
	columns: [
		{ name: 'Term', query: 'What is the term?' },
		{ name: 'Governing law', query: 'What is the governing law?' }
	],
	results: {
		rows: [
			{
				document_id: 'd-alpha',
				document_name: 'nda-alpha.txt',
				cells: {
					Term: cell('Two (2) years from the Effective Date', 'in force for two (2) years'),
					'Governing law': cell('Laws of England and Wales', 'governed by the laws of England and Wales')
				}
			},
			{
				document_id: 'd-beta',
				document_name: 'nda-beta.txt',
				cells: {
					Term: cell('Three (3) years', 'continues for a period of three (3) years'),
					'Governing law': cell('Laws of the State of New York', 'governed by the laws of the State of New York')
				}
			},
			{
				document_id: 'd-gamma',
				document_name: 'nda-gamma.txt',
				cells: {
					Term: cell('Five (5) years (confidentiality survival)', 'confidentiality obligations survive for five (5) years'),
					'Governing law': cell('Laws of Singapore', 'governed by the laws of Singapore')
				}
			}
		]
	},
	cost_estimate_usd: null,
	cost_actual_usd: null,
	error_text: null,
	created_at: new Date().toISOString(),
	started_at: new Date().toISOString(),
	completed_at: new Date().toISOString()
};

describe('F2 Tabular T2 — in-chat grid preview', { retries: { runMode: 1, openMode: 0 } }, () => {
	it('renders a grid preview card after the answer and expands to the full grid', () => {
		const now = new Date().toISOString();
		const runRow = {
			id: RID,
			user_id: 'admin',
			thread_id: TID,
			project_id: COMMERCIAL_MATTER,
			status: 'completed',
			prompt: 'Build a comparison grid of Term and Governing law across the three NDAs.',
			final_answer:
				'Here is a comparison grid across the three NDAs — Term and Governing law for each.',
			model_alias: 'deepseek',
			purpose: 'agent_loop',
			max_steps: 80,
			started_at: now,
			finished_at: now,
			error: null,
			cost_usd: null
		};
		// The SETTLED finalize step the preview anchors on (its input carries grid_id).
		const steps = [
			{
				id: '00000000-0000-4000-8000-000000002701',
				run_id: RID,
				seq: 1,
				kind: 'tool_call',
				name: 'finalize_tabular_review',
				summary: JSON.stringify({ grid_id: GID }),
				parent_step_id: null,
				created_at: now
			},
			{
				id: '00000000-0000-4000-8000-000000002702',
				run_id: RID,
				seq: 2,
				kind: 'tool_result',
				name: 'finalize_tabular_review',
				summary: `Finalized grid ${GID}: 3 document(s) x 2 column(s), all cells attempted.`,
				parent_step_id: null,
				created_at: now
			}
		];
		const threadDetail = {
			thread: {
				id: TID,
				user_id: 'admin',
				project_id: COMMERCIAL_MATTER,
				title: 'NDA comparison grid',
				created_at: now,
				last_run_at: now,
				last_run_status: 'completed'
			},
			runs: [{ run: runRow, steps }],
			continuable: true
		};

		cy.viewport(1280, 900);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());

		cy.intercept('GET', '**/api/v1/agents/threads?*', {
			threads: [
				{
					id: TID,
					user_id: 'admin',
					project_id: COMMERCIAL_MATTER,
					title: 'NDA comparison grid',
					created_at: now,
					last_run_at: now,
					last_run_status: 'completed'
				}
			],
			total_count: 1,
			limit: 100,
			offset: 0
		});
		cy.intercept('GET', `**/api/v1/agents/threads/${TID}*`, threadDetail);
		cy.intercept('GET', `**/api/v1/tabular/executions/${GID}*`, GRID);

		cy.visit(`/lq-ai?area=commercial&matter=${COMMERCIAL_MATTER}&thread=${TID}`);
		cy.get('[data-testid="lq-cockpit-conversation"]', { timeout: 30000 }).should('exist');

		// THE PREVIEW CARD: rendered after the answer, derived from the finalize step.
		cy.get('[data-testid="lq-ai-tabular-preview"]', { timeout: 30000 }).should('be.visible');
		cy.get('[data-testid="lq-ai-tabular-preview-status"]').should('contain', 'Ready');
		cy.get('[data-testid="lq-ai-tabular-preview-pills"]').should('contain', 'Term');
		cy.get('[data-testid="lq-ai-tabular-preview-pills"]').should('contain', 'Governing law');
		// The compact mini-table shows the documents + clamped values.
		cy.get('[data-testid="lq-ai-tabular-preview"]').should('contain', 'nda-alpha.txt');
		cy.get('[data-testid="lq-ai-tabular-preview"]').should('contain', 'England and Wales');

		// Centre the card in the viewport (clear of the floating composer, which
		// overlaps a bottom-anchored card at rest — a pre-existing cockpit layout
		// trait, reworked in T6) and capture the whole card: header + pills +
		// mini-table + the "+more" affordance + Expand.
		cy.get('[data-testid="lq-ai-tabular-preview"]').scrollIntoView({ offset: { top: -260, left: 0 } });
		// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
		cy.wait(300);
		cy.screenshot('f2-tabular-t2-preview-card', { capture: 'viewport' });

		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			cy.get('[data-testid="lq-ai-tabular-preview"]', { timeout: 15000 }).should('be.visible');
			// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
			cy.wait(300);
			cy.screenshot(`f2-tabular-t2-preview-${theme}`, { capture: 'viewport' });
		}

		// EXPAND (T6, ADR-F055): opens the grid as a cockpit stage-takeover — the
		// docked TabularWorkspace flies in, the conversation stays mounted.
		pinTheme('light');
		cy.get('[data-testid="lq-ai-tabular-preview-expand"]').first().click();
		cy.get('[data-testid="lq-tabular-workspace"]', { timeout: 15000 }).should('be.visible');
		cy.get('[data-testid="lq-tabgrid"]').should('be.visible');
		cy.get('[data-testid="lq-tabgrid"]').should('contain', 'Singapore');
		// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
		cy.wait(300);
		cy.screenshot('f2-tabular-t2-expanded', { capture: 'viewport' });

		// The "‹ Grids" breadcrumb closes the stage and returns to the cockpit.
		cy.get('[data-testid="lq-tabular-workspace-back"]').click();
		cy.get('[data-testid="lq-tabular-workspace"]').should('not.exist');
	});
});
