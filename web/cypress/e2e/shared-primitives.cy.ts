/**
 * R1a — shared modal/form primitives, proven on NewMatterModal.
 *
 * NewMatterModal was migrated off its hand-rolled `nmm-*` backdrop/panel + the
 * legacy `--lq-*` tokens onto ModalShell (over shadcn/bits-ui Dialog) +
 * FormControl + Alert + semantic Tailwind tokens. These checks lock in the
 * behavior the primitives must preserve — and capture the visual evidence
 * (light/dark, wide/narrow, default/error) the rollout DoD requires.
 *
 * The bits-ui Dialog now owns focus-trap / Escape / overlay-close — we assert
 * the wiring (focus lands inside, Escape closes), not the library internals.
 *
 * Run (live stack):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/shared-primitives.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
 */
const PHASE = () => (Cypress.env('PHASE') as string) || 'after';

function login() {
	cy.visit('/lq-ai/login');
	cy.get('input[type="email"]').type(Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai');
	cy.get('input[type="password"]').type(Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-local-Pw1!');
	cy.get('button[type="submit"]').click();
	cy.url({ timeout: 15000 }).should('not.include', '/login');
}

function setTheme(mode: 'light' | 'dark') {
	cy.window().then((win) => {
		win.localStorage.setItem('theme', mode);
		win.document.documentElement.classList.remove('light', 'dark');
		win.document.documentElement.classList.add(mode);
	});
}

function openModal() {
	cy.visit('/lq-ai/matters');
	cy.contains('h1', /matters/i, { timeout: 15000 }).should('be.visible');
	cy.contains('button', '+ New matter', { timeout: 10000 }).first().click();
	cy.get('[role="dialog"]', { timeout: 10000 }).should('exist');
}

describe('R1a — shared primitives on NewMatterModal', () => {
	beforeEach(() => {
		cy.viewport(1280, 800);
		login();
	});

	it('opens as a dialog with the title, traps focus, and closes on Escape', () => {
		openModal();
		// bits-ui Dialog.Title is the labeled heading (a div[data-slot=dialog-title],
		// linked via aria-labelledby) — not a literal <h2>.
		cy.get('[data-slot="dialog-title"]').should('contain', 'New matter');
		// Focus-trap: bits-ui moves focus into the dialog on open.
		cy.focused().should(($el) => {
			expect($el.closest('[role="dialog"]').length, 'focus is inside the dialog').to.eq(1);
		});
		cy.get('body').type('{esc}');
		cy.get('[role="dialog"]').should('not.exist');
	});

	it('Cancel dismisses the dialog', () => {
		openModal();
		cy.contains('button', 'Cancel').click();
		cy.get('[role="dialog"]').should('not.exist');
	});

	it('shows the required-name error and keeps the dialog open', () => {
		openModal();
		cy.contains('button', 'Create matter').click();
		cy.contains(/matter name is required/i).should('be.visible');
		cy.get('[role="dialog"]').should('exist');
	});

	it('reveals the tier select when privileged and enforces the tier floor', () => {
		openModal();
		cy.get('[role="dialog"]')
			.find('input[type="text"]')
			.first()
			.clear()
			.type('R1a privileged test');
		cy.get('#nmm-privileged').check();
		cy.get('#nmm-tier').should('be.visible');
		cy.contains('button', 'Create matter').click();
		cy.contains(/privileged matters require a minimum tier floor/i).should('be.visible');
		cy.get('[role="dialog"]').should('exist');
	});

	it('creates a matter and routes to the workspace', () => {
		openModal();
		const matterName = `R1a Primitives Matter ${Date.now()}`;
		cy.get('[role="dialog"]').find('input[type="text"]').first().clear().type(matterName);
		cy.contains('button', 'Create matter').click();
		cy.url({ timeout: 10000 }).should('match', /\/lq-ai\/matters\/[a-f0-9-]+$/);
		cy.contains(matterName).should('be.visible');
	});

	it('captures visual evidence (light + dark, wide + narrow, default + error)', () => {
		const p = PHASE();

		// Light, wide — default.
		openModal();
		cy.screenshot(`${p}-1-modal-light-wide`, { capture: 'viewport' });

		// Light, wide — error state (name + privileged-tier).
		cy.get('#nmm-privileged').check();
		cy.contains('button', 'Create matter').click();
		cy.contains(/matter name is required/i).should('be.visible');
		cy.screenshot(`${p}-2-modal-light-wide-error`, { capture: 'viewport' });

		// Dark, wide — default.
		setTheme('dark');
		openModal();
		cy.screenshot(`${p}-3-modal-dark-wide`, { capture: 'viewport' });

		// Dark, wide — error.
		cy.get('#nmm-privileged').check();
		cy.contains('button', 'Create matter').click();
		cy.contains(/matter name is required/i).should('be.visible');
		cy.screenshot(`${p}-4-modal-dark-wide-error`, { capture: 'viewport' });

		// Narrow — light then dark.
		cy.viewport(480, 800);
		setTheme('light');
		openModal();
		cy.screenshot(`${p}-5-modal-light-narrow`, { capture: 'viewport' });
		setTheme('dark');
		openModal();
		cy.screenshot(`${p}-6-modal-dark-narrow`, { capture: 'viewport' });
	});
});
