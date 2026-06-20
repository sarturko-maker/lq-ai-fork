/**
 * PRIV-A3 — assessment register tab + detail + ROPA write-back capture.
 *
 * The ROPA surface of a Privacy matter gains an "Assessments" tab (the company
 * PIA/DPIA/LIA/TIA record) with a list + detail (risks table + linked
 * activities), and the write-back marker: a "DPIA on file" badge on the
 * processing activities a completed DPIA covers, plus an Assessments chips
 * section on the activity detail. Runs against the LIVE dev backend (a seeded
 * "PRIV-A3 verify" DPIA), read-only. Headed for an honest light+dark capture.
 *
 * The cockpit remounts the register on a viewport breakpoint (resetting the tab
 * to Overview), so each block fixes its viewport ONCE up front and never changes
 * it mid-interaction (the PRIV-6c capture lesson).
 *
 * Run:
 *   cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/priv-a3-assessments.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
const PRIVACY_MATTER = '47519e68-d764-4a3f-b96b-2d703c16229c';

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

/**
 * Reveal the register tablist: wait for the matter surface to mount (any
 * role=tab), then — if the register is behind the narrow Conversation|ROPA
 * toggle (no "Overview" register tab present) — click the toggle to show it.
 * Co-visible (wide) needs no toggle.
 */
function revealRegister() {
	cy.get('[role="tab"]', { timeout: 30000 }).should('exist');
	cy.get('body').then(($b) => {
		if (!$b.find('[role="tab"]:contains("Overview")').length) {
			cy.contains('button', 'ROPA register', { timeout: 30000 }).click();
		}
	});
	cy.contains('[role="tab"]', 'Overview', { timeout: 30000 }).should('be.visible');
}

function selectTab(label: string) {
	cy.contains('[role="tab"]', label, { timeout: 30000 }).should('be.visible').click();
}

describe('PRIV-A3 assessment register', { retries: { runMode: 2, openMode: 0 } }, () => {
	it('the Assessments tab + detail render, and the activity shows DPIA on file', () => {
		login();
		cy.viewport(1280, 950);
		cy.visit(`/lq-ai?area=privacy&matter=${PRIVACY_MATTER}`);
		revealRegister();

		// Assessments tab → the live register (the seeded DPIA).
		selectTab('Assessments');
		cy.get('[data-testid="lq-assessments-table"]', { timeout: 30000 }).should('be.visible');
		cy.contains('[data-testid="lq-assessments-table"]', 'DPIA').should('be.visible');
		cy.wait(400);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			cy.wait(250);
			cy.screenshot(`priv-a3-assessments-${theme}-wide`, { capture: 'viewport' });
		}

		// Assessment detail: risks table + linked activities.
		pinTheme('light');
		cy.contains('[data-testid="lq-assessments-table"] tr', 'DPIA').click();
		cy.get('[data-testid="lq-assessment-detail"]', { timeout: 30000 }).should('be.visible');
		cy.contains('[data-testid="lq-assessment-detail"]', 'Risks').should('be.visible');
		cy.contains('[data-testid="lq-assessment-detail"]', 'Activities assessed').should('be.visible');
		cy.wait(300);
		cy.screenshot('priv-a3-assessment-detail-light-wide', { capture: 'viewport' });

		// Back to the list (the detail view hides the tablist), then switch tabs.
		cy.get('[data-testid="lq-assessment-detail"]').contains('button', 'Register').click();

		// Write-back: Processing activities tab shows "DPIA on file"; the activity
		// detail carries the Assessments chips section.
		selectTab('Processing activities');
		// The badge has overflow-hidden (trips strict be.visible); assert it exists
		// and scroll its row into view for the capture.
		cy.contains('DPIA on file', { timeout: 30000 }).should('exist').scrollIntoView();
		cy.wait(300);
		cy.screenshot('priv-a3-activities-dpia-on-file-light-wide', { capture: 'viewport' });

		cy.contains('td', 'PRIV-A3 verify').click({ force: true });
		cy.contains('h3', 'Assessments').should('be.visible');
		cy.contains('button', 'Employee monitoring DPIA').should('be.visible');
		cy.wait(300);
		cy.screenshot('priv-a3-activity-detail-writeback-light-wide', { capture: 'viewport' });
	});

	it('the Assessments tab renders narrow (light + dark)', () => {
		login();
		cy.viewport(820, 950);
		cy.visit(`/lq-ai?area=privacy&matter=${PRIVACY_MATTER}`);
		revealRegister();
		selectTab('Assessments');
		cy.get('[data-testid="lq-assessments-table"]', { timeout: 30000 }).should('be.visible');
		cy.wait(400);
		for (const theme of ['light', 'dark'] as const) {
			pinTheme(theme);
			cy.wait(250);
			cy.screenshot(`priv-a3-assessments-${theme}-narrow`, { capture: 'viewport' });
		}
	});
});
