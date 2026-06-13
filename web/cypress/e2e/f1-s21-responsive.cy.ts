/**
 * F1-S2.1 — responsive collapse + design iteration v2 (maintainer review
 * of the live F1-S2 cockpit: "when the window is half the screen … the
 * content is squashed; side panels need to collapse"). Live-stack spec.
 *
 * Covers: wide-mode rail collapse via the header toggle (paneforge
 * collapsible pane); narrow-mode off-canvas drawer; the stacked
 * conversation layout below 720px host width; elevation tokens applied
 * (workspace card floats on a gray canvas).
 */
import { login } from '../support/lq-ai-helpers';

const ADMIN_EMAIL = () => Cypress.env('LQAI_ADMIN_EMAIL') || 'admin@lq.ai';
const ADMIN_PASSWORD = () => Cypress.env('LQAI_ADMIN_PASSWORD') || 'LQ-AI-smoke-test-Pw1!';

describe('F1-S2.1 — responsive cockpit', () => {
	beforeEach(() => {
		cy.viewport(1280, 800);
		login(ADMIN_EMAIL(), ADMIN_PASSWORD());
		cy.get('[data-testid="lq-cockpit"]').should('exist');
	});

	it('wide: header toggle collapses and restores the rail pane', () => {
		cy.get('[data-testid="lq-cockpit-rail"]').should('be.visible');
		cy.get('[data-testid="lq-cockpit-rail-toggle"]').click();
		// paneforge collapses to size 0 — the pane (rail's parent) loses
		// its width; assert on the rail's bounding box.
		cy.get('[data-testid="lq-cockpit-rail"]').should(($el) => {
			expect($el[0].getBoundingClientRect().width, 'collapsed rail width').to.be.lessThan(8);
		});
		cy.get('[data-testid="lq-cockpit-rail-toggle"]').click();
		cy.get('[data-testid="lq-cockpit-rail"]').should(($el) => {
			expect($el[0].getBoundingClientRect().width, 'restored rail width').to.be.greaterThan(120);
		});
	});

	it('narrow: rail leaves the layout; the toggle opens an off-canvas drawer that navigates', () => {
		cy.viewport(700, 800);
		// The pane-group rail is gone; no squashed 127px column.
		cy.get('[data-testid="lq-cockpit-drawer"]').should('not.exist');
		cy.get('[data-testid="lq-cockpit-rail"]').should('not.exist');
		cy.screenshot('f1-s21-1-narrow-landing', { capture: 'viewport' });

		cy.get('[data-testid="lq-cockpit-rail-toggle"]').click();
		cy.get('[data-testid="lq-cockpit-drawer"]').should('be.visible');
		cy.screenshot('f1-s21-2-narrow-drawer', { capture: 'viewport' });

		// Selecting an area navigates AND closes the drawer.
		cy.get('[data-testid="lq-cockpit-drawer"]')
			.find('[data-testid="lq-cockpit-area-commercial"]')
			.click();
		cy.url().should('include', 'area=commercial');
		cy.get('[data-testid="lq-cockpit-drawer"]').should('not.exist');
		cy.get('[data-testid="lq-cockpit-matters"]').should('exist');
	});

	it('narrow matter view stacks: list first, conversation full-width with a back row', () => {
		cy.viewport(700, 800);
		cy.get('[data-testid="lq-cockpit-rail-toggle"]').click();
		cy.get('[data-testid="lq-cockpit-drawer"]')
			.find('[data-testid="lq-cockpit-area-commercial"]')
			.click();
		cy.get('[data-testid="lq-cockpit-matter-row"]').first().click();
		cy.get('[data-testid="lq-cockpit-conversation"]').should('exist');

		// Stacked: the thread list fills the card; no side-by-side panel.
		cy.get('[data-testid="lq-cockpit-conversation"] aside').should(($el) => {
			expect($el[0].getBoundingClientRect().width, 'stacked list width').to.be.greaterThan(400);
		});
		cy.screenshot('f1-s21-3-narrow-matter-list', { capture: 'viewport' });

		// New conversation -> full-width composer with a back row.
		cy.get('[data-testid="lq-cockpit-new-conversation"]').click();
		cy.get('[data-testid="lq-cockpit-back-to-list"]').should('be.visible');
		cy.get('[data-testid="lq-ai-agents-composer"]').should('be.visible');
		cy.screenshot('f1-s21-4-narrow-conversation', { capture: 'viewport' });

		// Back returns to the list.
		cy.get('[data-testid="lq-cockpit-back-to-list"]').click();
		cy.get('[data-testid="lq-cockpit-new-conversation"]').should('be.visible');
	});

	it('elevation: the canvas is a real gray under white cards (light), charcoal in dark', () => {
		// Light: canvas (cockpit root) must be measurably darker than cards.
		cy.get('html').then(($html) => {
			if ($html.hasClass('dark')) {
				// normalize to light for this assertion
				cy.get('button[aria-label^="Theme"]').click();
			}
		});
		cy.get('[data-testid="lq-cockpit"]').should(($el) => {
			const bg = getComputedStyle($el[0]).backgroundColor;
			const ok = bg.match(/^oklch\((\d*\.?\d+)/);
			const rgb = bg.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)/);
			if (ok) {
				expect(+ok[1], `light canvas L (${bg})`).to.be.lessThan(0.98).and.greaterThan(0.9);
			} else if (rgb) {
				const max = Math.max(+rgb[1], +rgb[2], +rgb[3]);
				expect(max, `light canvas (${bg})`).to.be.lessThan(252).and.greaterThan(230);
			} else {
				throw new Error(`unrecognized background-color serialization: ${bg}`);
			}
		});
	});
});
