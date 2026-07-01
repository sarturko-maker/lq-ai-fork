/**
 * F2 Tabular T7 — the matter Grids tab (browser visual, deterministic).
 *
 * The cockpit gains a "Grids" tab (sibling to Documents) listing the matter's
 * agentic grids (ADR-F055): a derived-title row per grid with doc/column counts,
 * fill mode, status, and open/delete. This spec drives the REAL panel in the REAL
 * browser with `GET /tabular/matters/{id}/grids` intercepted (no LLM) — the
 * populated list and the empty state.
 *
 * Run (live stack for auth + the matters rollup):
 *   cd web && DISPLAY=:0 npx cypress run --browser electron \
 *     --spec 'cypress/e2e/f2-tabular-t7-grids-tab.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!';
const COMMERCIAL_MATTER = '905720d1-5d17-43cd-a8f0-3a76d095de34';

function pinTheme(theme: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', theme);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(theme);
	});
	cy.get('html').should('have.class', theme);
}

function grid(id: string, columns: string[], docs: number, fill: string, status: string) {
	return {
		id,
		user_id: 'admin',
		parent_execution_id: null,
		skill_name: null,
		status,
		document_count: docs,
		column_count: columns.length,
		column_names: columns,
		fill_mode: fill,
		cost_estimate_usd: null,
		cost_actual_usd: null,
		created_at: new Date().toISOString(),
		completed_at: new Date().toISOString()
	};
}

const GRIDS = [
	grid('00000000-0000-4000-8000-0000000071a1', ['Term', 'Governing law'], 3, 'fanout', 'completed'),
	grid(
		'00000000-0000-4000-8000-0000000071a2',
		['Counterparty', 'Value', 'Change of control', 'Liability cap'],
		12,
		'retrieval',
		'completed'
	)
];

describe('F2 Tabular T7 — Grids tab', { retries: { runMode: 1, openMode: 0 } }, () => {
	function openMatter() {
		cy.viewport(1280, 900);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
		cy.intercept('GET', '**/api/v1/agents/threads?*', {
			threads: [],
			total_count: 0,
			limit: 100,
			offset: 0
		});
		cy.visit(`/lq-ai?area=commercial&matter=${COMMERCIAL_MATTER}`);
		cy.get('[data-testid="lq-cockpit-conversation"]', { timeout: 30000 }).should('exist');
		cy.contains('button', 'Grids').click();
	}

	it('lists the matter grids with derived titles + fill mode', () => {
		cy.intercept('GET', `**/api/v1/tabular/matters/${COMMERCIAL_MATTER}/grids`, GRIDS).as('grids');
		openMatter();
		cy.wait('@grids');
		cy.get('[data-testid="lq-grids-list"]', { timeout: 15000 }).should('be.visible');
		cy.get('[data-testid="lq-grids-row"]').should('have.length', 2);
		// Derived title from column names + fill-mode subtitle.
		cy.contains('[data-testid="lq-grids-row"]', 'Term, Governing law').should('contain', 'fan-out');
		cy.contains('[data-testid="lq-grids-row"]', 'Counterparty, Value').should('contain', 'retrieval');
		cy.get('[data-testid="lq-grids-delete"]').should('have.length', 2);

		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
			cy.wait(300);
			cy.screenshot(`f2-tabular-t7-grids-${theme}`, { capture: 'viewport' });
		}
	});

	it('shows an empty state when the matter has no grids', () => {
		cy.intercept('GET', `**/api/v1/tabular/matters/${COMMERCIAL_MATTER}/grids`, []).as('empty');
		openMatter();
		cy.wait('@empty');
		cy.get('[data-testid="lq-grids-empty"]', { timeout: 15000 }).should('be.visible');
		cy.get('[data-testid="lq-grids-empty"]').should('contain', 'No grids yet');
		// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
		cy.wait(300);
		cy.screenshot('f2-tabular-t7-grids-empty', { capture: 'viewport' });
	});
});
