/**
 * F1-S2 — Cockpit v0 shell (ADR-F002 "glass cockpit", ADR-F006 design
 * system). Live-stack spec (docker compose up; api seeded by migration
 * 0053). Covers: login lands in the cockpit; the area list with honest
 * configured / inert states; entering Commercial; pick-or-create in
 * place; the unfiled bucket; theme toggle (light-first, never-black
 * dark); Tools-menu navigation to the legacy surfaces.
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-smoke-test-Pw1!';

describe('F1-S2 — Cockpit v0', () => {
	beforeEach(() => {
		// 1280x800: headless Electron's window is 1280 wide — a 1440 viewport
		// gets CROPPED in viewport captures (evidence screenshots).
		cy.viewport(1280, 800);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
	});

	it('lands in the cockpit: rail + area grid, Commercial enterable, others inert', () => {
		cy.url().should('match', /\/lq-ai\/?$/);
		cy.get('[data-testid="lq-cockpit"]').should('exist');

		// Rail: all five seeded areas, four honestly "Not configured".
		cy.get('[data-testid="lq-cockpit-rail"]').within(() => {
			cy.get('[data-testid="lq-cockpit-area-commercial"]').should('not.have.attr', 'aria-disabled');
			for (const key of ['disputes', 'm-and-a', 'privacy', 'employment']) {
				cy.get(`[data-testid="lq-cockpit-area-${key}"]`)
					.should('have.attr', 'aria-disabled', 'true')
					.contains('Not configured');
			}
		});

		// Main pane: the AREA LIST (never auto-landed in an area).
		cy.get('[data-testid="lq-cockpit-area-grid"]').should('exist');
		cy.screenshot('f1-s2-1-cockpit-landing', { capture: 'viewport' });

		// Inert card: no navigation on click.
		cy.get('[data-testid="lq-cockpit-area-card-privacy"]').click({ force: true });
		cy.url().should('not.include', 'area=privacy');
	});

	it('enters Commercial, creates a matter in place, and gets a composer', () => {
		cy.get('[data-testid="lq-cockpit-area-card-commercial"]').click();
		cy.url().should('include', 'area=commercial');
		cy.get('[data-testid="lq-cockpit-matters"]').should('exist');
		cy.screenshot('f1-s2-2-matters-list', { capture: 'viewport' });

		const name = `Cockpit Matter ${Date.now()}`;
		cy.intercept('POST', '/api/v1/projects').as('createMatter');
		cy.contains('button', 'New matter').click();
		cy.get('[data-testid="lq-cockpit-new-matter-name"]').type(name);
		cy.get('[data-testid="lq-cockpit-new-matter-create"]').click();
		cy.wait('@createMatter').its('response.statusCode').should('eq', 201);

		// Created → straight into the matter's conversation view with the
		// matter pre-selected in the composer (no blank workspace, F002).
		cy.url().should('include', 'matter=');
		cy.get('[data-testid="lq-cockpit-conversation"]').should('exist');
		cy.get('[data-testid="lq-ai-agents-matter-select"]')
			.find('option:selected')
			.should('contain.text', name);
		cy.screenshot('f1-s2-3-matter-view', { capture: 'viewport' });
	});

	it('opens the unfiled bucket (resume-only, no composer offered)', () => {
		cy.get('[data-testid="lq-cockpit-unfiled"]').click();
		cy.url().should('include', 'view=unfiled');
		cy.get('[data-testid="lq-cockpit-conversation"]').should('exist');
		cy.contains(/resume/i).should('be.visible');
		cy.get('[data-testid="lq-cockpit-new-conversation"]').should('not.exist');
	});

	it('theme toggle cycles to dark — charcoal, never black', () => {
		// Cycle: system → light → dark.
		cy.get('button[aria-label^="Theme"]').click();
		cy.get('button[aria-label^="Theme"]').click();
		cy.get('html').should('have.class', 'dark');
		// Pin the no-black rule with a real floor, not just ≠#000: accept
		// either serialization (Chromium may return rgb() or oklch()) and
		// require meaningfully-above-black lightness (token: oklch 0.23).
		cy.get('[data-testid="lq-cockpit"]').should(($el) => {
			const bg = getComputedStyle($el[0]).backgroundColor;
			const rgb = bg.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)/);
			const ok = bg.match(/^oklch\((\d*\.?\d+)/);
			if (rgb) {
				expect(Math.max(+rgb[1], +rgb[2], +rgb[3]), `dark canvas ${bg}`).to.be.greaterThan(20);
			} else if (ok) {
				expect(+ok[1], `dark canvas ${bg}`).to.be.greaterThan(0.2);
			} else {
				throw new Error(`unrecognized background-color serialization: ${bg}`);
			}
		});
		cy.screenshot('f1-s2-4-dark-mode', { capture: 'viewport' });
		// Back to system for the next spec.
		cy.get('button[aria-label^="Theme"]').click();
	});

	it('Tools menu reaches the legacy surfaces (tab chrome intact there)', () => {
		cy.contains('button', 'Tools').click();
		cy.contains('[role="menuitem"]', 'Skills').click();
		cy.url().should('include', '/lq-ai/skills');
		cy.get('nav[aria-label="Primary"]').should('exist');
		// And the brand link returns to the cockpit.
		cy.get('a.lq-brand').click();
		cy.get('[data-testid="lq-cockpit"]').should('exist');
	});
});
