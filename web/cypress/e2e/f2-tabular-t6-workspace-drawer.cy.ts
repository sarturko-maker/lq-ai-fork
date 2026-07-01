/**
 * F2 Tabular T6 — grid review workspace + docked cell drawer + human override.
 *
 * Deterministic: all API responses are mocked via cy.intercept so the spec runs
 * against the built web bundle (`docker compose up -d web`) with no DB state.
 * Visits `/lq-ai/tabular/[id]` directly (the standalone grid view, which inlines
 * the SAME TabularGrid + TabularCellDrawer the cockpit stage-takeover uses) and
 * exercises: cell → docked drawer (value / verbatim source quote / citations /
 * open-source) → the lawyer override (the ADR-F042 human-write) → the "edited"
 * badge in-grid + the overridden banner in the drawer.
 *
 * Run:
 *   docker compose up -d web
 *   npx cypress run --project web --spec web/cypress/e2e/f2-tabular-t6-workspace-drawer.cy.ts
 */

/// <reference types="cypress" />

const GRID_ID = 'tex-t6';

const mockUser = {
	id: 'u1',
	email: 'admin@lq.ai',
	display_name: 'Admin',
	is_admin: true,
	role: 'admin' as const,
	mfa_enabled: false,
	must_change_password: false,
	created_at: '2026-01-01T00:00:00Z'
};

const baseCell = (over: Record<string, unknown> = {}) => ({
	value: 'Two (2) years',
	confidence: 'high',
	citations: [
		{
			citation_id: 'cit-1',
			document_id: 'doc-1',
			chunk_id: 'chunk-1',
			confidence: 'high',
			source_file_id: 'file-1',
			source_page: 3,
			source_text: 'The initial term of this Agreement shall be two (2) years.'
		}
	],
	source_quote: 'The initial term of this Agreement shall be two (2) years from the Effective Date.',
	notes: null,
	...over
});

const gridCompleted = {
	id: GRID_ID,
	user_id: 'u1',
	parent_execution_id: null,
	skill_name: null,
	status: 'completed',
	document_ids: ['doc-1', 'doc-2'],
	document_names: ['Helios MSA.docx', 'Meridian MSA.docx'],
	columns: [
		{ name: 'Term', query: '?' },
		{ name: 'Governing law', query: '?' },
		{ name: 'Liability cap', query: '?' }
	],
	results: {
		rows: [
			{
				document_id: 'doc-1',
				document_name: 'Helios MSA.docx',
				cells: {
					Term: baseCell(),
					'Governing law': baseCell({
						value: 'Singapore',
						source_quote: 'This Agreement is governed by the laws of Singapore.'
					}),
					'Liability cap': baseCell({
						value: '12 months of fees',
						confidence: 'medium',
						citations: [],
						source_quote: null,
						notes: 'Ambiguous — cap references fees paid in the preceding 12 months.'
					})
				}
			},
			{
				document_id: 'doc-2',
				document_name: 'Meridian MSA.docx',
				cells: {
					Term: baseCell({ value: 'One (1) year' }),
					'Governing law': baseCell({ value: 'England & Wales', citations: [] }),
					'Liability cap': {
						value: null,
						confidence: 'failed',
						citations: [],
						error: 'no citation found'
					}
				}
			}
		]
	},
	cost_estimate_usd: '0.0500',
	cost_actual_usd: '0.0412',
	error_text: null,
	created_at: '2026-07-02T09:00:00Z',
	started_at: '2026-07-02T09:00:01Z',
	completed_at: '2026-07-02T09:00:20Z'
};

// After a successful override POST: doc-1 / Term now carries the lawyer value.
const gridOverridden = JSON.parse(JSON.stringify(gridCompleted));
gridOverridden.results.rows[0].cells.Term = {
	...gridOverridden.results.rows[0].cells.Term,
	override_value: 'Three (3) years',
	override_note: 'Per Amendment No. 2',
	overridden_by: 'u1',
	overridden_at: '2026-07-02T10:00:00Z'
};

function pinTheme(theme: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', theme);
		win.document.documentElement.classList.toggle('dark', theme === 'dark');
	});
}

describe('F2 Tabular T6 — grid workspace + cell drawer + human override', () => {
	beforeEach(() => {
		cy.intercept('POST', '**/api/v1/auth/login', {
			statusCode: 200,
			body: { access_token: 'fake-token', token_type: 'Bearer', expires_in: 3600, user: mockUser }
		}).as('login');
		cy.intercept('GET', '**/api/v1/users/me', { statusCode: 200, body: mockUser }).as('getMe');
		cy.intercept('GET', '**/api/v1/admin/bootstrap-status', {
			statusCode: 200,
			body: { default_password_active: false, logs_hint: '' }
		});
		cy.intercept('GET', '**/api/v1/users/me/preferences', {
			statusCode: 200,
			body: {
				reasoning_visibility: 'on_request',
				featured_tools: 'inline',
				workspace_layout: 'three_pane',
				trust_pills: 'labels',
				provenance_pills: 'collapsed'
			}
		});
		cy.intercept('GET', '**/api/v1/projects**', { statusCode: 200, body: [] });
		cy.intercept('GET', '**/api/v1/chats**', {
			statusCode: 200,
			body: { items: [], next_cursor: null }
		});
		cy.intercept('GET', '**/api/v1/user-skills**', { statusCode: 200, body: [] });
		cy.intercept('GET', '**/api/v1/saved-prompts**', { statusCode: 200, body: [] });
		cy.intercept('GET', '**/api/v1/teams**', { statusCode: 200, body: [] });
		cy.intercept('GET', '**/api/v1/skills**', { statusCode: 200, body: [] });
		// The (app) shell also pulls these on load; an unmocked 401 bounces to login.
		cy.intercept('GET', '**/api/v1/practice-areas**', { statusCode: 200, body: [] });
		cy.intercept('GET', '**/api/v1/agents/matters**', { statusCode: 200, body: [] });

		cy.intercept('GET', `**/api/v1/tabular/executions/${GRID_ID}`, {
			statusCode: 200,
			body: gridCompleted
		}).as('getGrid');
		cy.intercept('POST', `**/api/v1/tabular/executions/${GRID_ID}/cells/override`, {
			statusCode: 200,
			body: gridOverridden
		}).as('override');
	});

	it('cell → docked drawer → lawyer override (with screenshots)', () => {
		// Login (mocked), then jump straight to the standalone grid view.
		cy.visit('/lq-ai/login');
		cy.get('[data-testid="lq-ai-login-email"]').type('admin@lq.ai');
		cy.get('[data-testid="lq-ai-login-password"]').type('password');
		cy.get('[data-testid="lq-ai-login-submit"]').click();
		cy.wait('@login');
		cy.url({ timeout: 15000 }).should('not.include', '/login');

		cy.visit(`/lq-ai/tabular/${GRID_ID}`);
		cy.wait('@getGrid');
		pinTheme('light');

		// The grid renders (no overlay, no modal).
		cy.get('[data-testid="lq-tabgrid"]', { timeout: 15000 }).should('be.visible');
		cy.get('[data-testid="lq-tabgrid-row"]').should('have.length', 2);
		cy.get('[data-testid="lq-tabgrid-header"]').should('have.length', 3);
		cy.get('[data-testid="lq-tabcell-failed"]').should('have.length', 1);
		// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
		cy.wait(300);
		cy.screenshot('f2-tabular-t6-grid', { capture: 'viewport' });

		// Click the Term × Helios cell → the DOCKED drawer (not a modal).
		cy.get('[data-testid="lq-tabcell"][data-document-name="Helios MSA.docx"][data-column-name="Term"]')
			.click();
		cy.get('[data-testid="lq-tabular-cell-drawer"]').should('be.visible');
		cy.get('[data-testid="lq-tabular-cell-drawer-value"]').should('contain', 'Two (2) years');
		cy.get('[data-testid="lq-tabular-cell-drawer-quote"]').should('contain', 'two (2) years');
		cy.get('[data-testid="lq-tabular-cell-drawer-open-source"]').should('be.visible');
		cy.get('[data-testid="lq-tabular-cell-drawer-override-value"]').should('be.visible');
		// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
		cy.wait(300);
		cy.screenshot('f2-tabular-t6-drawer', { capture: 'viewport' });

		// Override the cell → the human value wins in-grid + the drawer shows it.
		cy.get('[data-testid="lq-tabular-cell-drawer-override-value"]').clear().type('Three (3) years');
		cy.get('[data-testid="lq-tabular-cell-drawer-override-note"]').type('Per Amendment No. 2');
		cy.get('[data-testid="lq-tabular-cell-drawer-save"]').click();
		cy.wait('@override');

		cy.get('[data-testid="lq-tabular-cell-drawer-overridden"]').should('be.visible');
		cy.get('[data-testid="lq-tabular-cell-drawer-value"]').should('contain', 'Three (3) years');
		cy.get('[data-testid="lq-tabcell"][data-document-name="Helios MSA.docx"][data-column-name="Term"]')
			.find('[data-testid="lq-tabcell-edited"]')
			.should('exist');
		// eslint-disable-next-line cypress/no-unnecessary-waiting -- paint settle before capture
		cy.wait(300);
		cy.screenshot('f2-tabular-t6-overridden', { capture: 'viewport' });

		// Close the drawer.
		cy.get('[data-testid="lq-tabular-cell-drawer-close"]').click();
		cy.get('[data-testid="lq-tabular-cell-drawer"]').should('not.exist');
	});
});
