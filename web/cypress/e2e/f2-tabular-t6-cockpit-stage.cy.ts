/**
 * F2 Tabular T6 — the COCKPIT stage-takeover (TabularWorkspace) is interactive.
 *
 * Regression guard for the maintainer-reported bug: navigating to a grid THROUGH
 * the Commercial cockpit (Expand on the in-chat preview → the docked
 * `TabularWorkspace` fly-in) left the grid non-interactive — clicking a cell
 * showed no drawer, and the cells didn't scroll horizontally. Root cause: the
 * workspace root wasn't filling the fly-in's flex row, so it sized to the
 * max-content grid and overflowed the `overflow:hidden` pane — the grid couldn't
 * scroll and the docked drawer opened off-screen (Cypress treats an
 * overflow-clipped element as NOT visible, so both asserts below catch it).
 *
 * Real login (live stack for auth + the matters rollup) + mocked thread/steps +
 * mocked GET /tabular/executions/{id}. A WIDE grid (6 columns) so the table
 * exceeds the pane and horizontal scroll is exercised.
 *
 * Run:
 *   docker compose up -d
 *   npx cypress run --project web --spec web/cypress/e2e/f2-tabular-t6-cockpit-stage.cy.ts \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
const COMMERCIAL_MATTER = '905720d1-5d17-43cd-a8f0-3a76d095de34';
const TID = '00000000-0000-4000-8000-0000000037a2';
const RID = '00000000-0000-4000-8000-0000000037d2';
const GID = '00000000-0000-4000-8000-0000000037f2';

const COLS = [
	'Term',
	'Governing law',
	'Liability cap',
	'Confidentiality',
	'Assignment',
	'Termination'
];

function cell(value: string) {
	return {
		value,
		citations: [],
		confidence: 'high',
		source_quote: `The clause provides: ${value}.`,
		notes: null
	};
}
function row(id: string, name: string) {
	const cells: Record<string, ReturnType<typeof cell>> = {};
	for (const c of COLS) cells[c] = cell(`${c} for ${name}`);
	return { document_id: id, document_name: name, cells };
}

const GRID = {
	id: GID,
	user_id: 'admin',
	parent_execution_id: null,
	skill_name: null,
	mode: 'agentic',
	status: 'completed',
	document_ids: ['d-alpha', 'd-beta', 'd-gamma'],
	document_names: ['helios-msa.txt', 'meridian-msa.txt', 'cobalt-msa.txt'],
	columns: COLS.map((name) => ({ name, query: `What is the ${name}?` })),
	results: {
		rows: [
			row('d-alpha', 'helios-msa.txt'),
			row('d-beta', 'meridian-msa.txt'),
			row('d-gamma', 'cobalt-msa.txt')
		]
	},
	cost_estimate_usd: null,
	cost_actual_usd: null,
	error_text: null,
	created_at: new Date().toISOString(),
	started_at: new Date().toISOString(),
	completed_at: new Date().toISOString()
};

describe('F2 Tabular T6 — cockpit stage-takeover is interactive', { retries: { runMode: 1, openMode: 0 } }, () => {
	it('Expand → cell click shows the drawer; the grid scrolls horizontally', () => {
		const now = new Date().toISOString();
		const runRow = {
			id: RID,
			user_id: 'admin',
			thread_id: TID,
			project_id: COMMERCIAL_MATTER,
			status: 'completed',
			prompt: 'Build a comparison grid across these MSAs.',
			final_answer: 'Here is the comparison grid across the three MSAs.',
			model_alias: 'deepseek',
			purpose: 'agent_loop',
			max_steps: 80,
			started_at: now,
			finished_at: now,
			error: null,
			cost_usd: null
		};
		const steps = [
			{
				id: '00000000-0000-4000-8000-000000003701',
				run_id: RID,
				seq: 1,
				kind: 'tool_call',
				name: 'finalize_tabular_review',
				summary: JSON.stringify({ grid_id: GID }),
				parent_step_id: null,
				created_at: now
			},
			{
				id: '00000000-0000-4000-8000-000000003702',
				run_id: RID,
				seq: 2,
				kind: 'tool_result',
				name: 'finalize_tabular_review',
				summary: `Finalized grid ${GID}: 3 document(s) x 6 column(s), all cells attempted.`,
				parent_step_id: null,
				created_at: now
			}
		];
		const threadDetail = {
			thread: {
				id: TID,
				user_id: 'admin',
				project_id: COMMERCIAL_MATTER,
				title: 'MSA comparison grid',
				created_at: now,
				last_run_at: now,
				last_run_status: 'completed'
			},
			runs: [{ run: runRow, steps }],
			continuable: true
		};

		cy.viewport(1440, 900);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());

		cy.intercept('GET', '**/api/v1/agents/threads?*', {
			threads: [threadDetail.thread],
			total_count: 1,
			limit: 100,
			offset: 0
		});
		cy.intercept('GET', `**/api/v1/agents/threads/${TID}*`, threadDetail);
		cy.intercept('GET', `**/api/v1/tabular/executions/${GID}*`, GRID);

		cy.visit(`/lq-ai?area=commercial&matter=${COMMERCIAL_MATTER}&thread=${TID}`);
		cy.get('[data-testid="lq-cockpit-conversation"]', { timeout: 30000 }).should('exist');

		// Preview card → Expand opens the stage-takeover workspace.
		cy.get('[data-testid="lq-ai-tabular-preview-expand"]', { timeout: 30000 }).first().click();
		cy.get('[data-testid="lq-tabular-workspace"]', { timeout: 15000 }).should('be.visible');
		cy.get('[data-testid="lq-tabgrid"]').should('be.visible');

		// BUG #1 — the grid must scroll horizontally (6 cols overflow the pane).
		cy.get('[data-testid="lq-tabgrid"]').then(($s) => {
			const el = $s[0];
			expect(el.scrollWidth, 'grid is horizontally scrollable').to.be.greaterThan(el.clientWidth + 4);
		});

		// BUG #2 — clicking a cell must show the docked drawer (not clipped off-screen).
		cy.get('[data-testid="lq-tabcell"][data-document-name="helios-msa.txt"][data-column-name="Term"]')
			.click();
		cy.get('[data-testid="lq-tabular-cell-drawer"]').should('be.visible');
		cy.get('[data-testid="lq-tabular-cell-drawer-value"]').should('contain', 'Term for helios');
		// And it must sit within the viewport (the clip bug pushed it off-screen right).
		cy.get('[data-testid="lq-tabular-cell-drawer"]').then(($d) => {
			const r = $d[0].getBoundingClientRect();
			expect(r.right, 'drawer right edge within viewport').to.be.lessThan(1441);
			expect(r.width, 'drawer has real width').to.be.greaterThan(100);
		});
		// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
		cy.wait(300);
		cy.screenshot('f2-tabular-t6-cockpit-stage', { capture: 'viewport' });
	});
});
