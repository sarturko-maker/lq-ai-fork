/**
 * F0-S3 — Agents tab v0: the first visible deep agent.
 *
 * Drives a REAL agent run end-to-end against the live dev stack: logs in
 * through the UI, opens the Agents tab, submits a prompt, watches the
 * capability rail light up as polled steps settle, and asserts the final
 * answer renders with reasoning collapsed. Screenshots double as the
 * ADR-F005 live-verification evidence.
 *
 * Run requires a live stack (and a gateway model that answers):
 *   docker compose up -d
 *   cd web && npx cypress run --spec 'cypress/e2e/f0-s3-agents-tab.cy.ts'
 *
 * The run costs one short MiniMax-M3 loop (~4 steps). Credentials are the
 * local dev defaults; this spec never runs in CI (CI has no stack).
 */

/// <reference types="cypress" />

const EMAIL = Cypress.env('LQ_AI_EMAIL') ?? 'admin@lq.ai';
const PASSWORD = Cypress.env('LQ_AI_PASSWORD') ?? 'LQ-AI-local-Pw1!';

// A full loop is model turn -> tool call -> tool result -> model turn at
// MiniMax latitude; 90s absorbs slow first-token without masking hangs.
const RUN_TIMEOUT_MS = 90_000;

describe('F0-S3 — Agents tab v0 (live deep agent)', () => {
	it('logs in, runs the Commercial preview agent, and watches it work', () => {
		cy.visit('/lq-ai/login');
		cy.get('[data-testid="lq-ai-login-email"]').type(EMAIL);
		cy.get('[data-testid="lq-ai-login-password"]').type(PASSWORD, { log: false });
		cy.get('[data-testid="lq-ai-login-submit"]').click();

		// Tab is registered and reachable from the shell.
		cy.contains('[role="tab"]', 'Agents', { timeout: 15_000 }).click();
		cy.location('pathname').should('eq', '/lq-ai/agents');
		cy.get('[data-testid="lq-ai-agents-area-card"]').should('contain.text', 'Commercial');

		// Capability rail renders the honest tool universe, all dim. With no
		// matter selected this is the 9 deepagents builtins — the matter
		// document tools only appear on matter-bound runs (F0-S4), and the
		// demo tool is gone for good.
		cy.get('[data-testid="lq-ai-agents-rail"] li').should('have.length', 9);
		cy.get('[data-testid="lq-ai-agents-rail"] li.ag-rail__tool--lit').should('have.length', 0);
		cy.screenshot('f0-s3-1-agents-tab-idle');

		// Count detail polls so we can prove polling stops after the run settles.
		cy.intercept('GET', '**/api/v1/agents/runs/*').as('pollRun');

		// Kick off a real run.
		cy.get('[data-testid="lq-ai-agents-composer"] textarea').type(
			'What is the liability cap under this contract? Use your tools.'
		);
		cy.get('[data-testid="lq-ai-agents-composer"] button[type="submit"]').click();

		// The run surface appears and activity settles in via polling. A
		// single-turn direct answer dedups its only model turn out of the
		// timeline (visibleSteps), so accept EITHER a step OR the answer —
		// the comma selector is a union.
		cy.get('[data-testid="lq-ai-agents-run"]').should('exist');
		cy.get(
			'[data-testid="lq-ai-agents-run"] .ag-steps li, [data-testid="lq-ai-agents-answer"]',
			{ timeout: RUN_TIMEOUT_MS }
		).should('have.length.at.least', 1);
		cy.screenshot('f0-s3-2-agent-working');

		// No tool lighting is asserted on an UNBOUND run: with no matter there
		// are no document tools and an honest agent may answer directly. The
		// f0-s4 spec pins tool dispatch on a matter-bound run deterministically.

		// Completion: badge flips and a non-empty final answer renders.
		// (No assertion on model-chosen prose — that flakes; on an unbound
		// run there is nothing deterministic to pin. Grounded-content
		// assertions live in the f0-s4 matter-bound spec.)
		cy.get('[data-testid="lq-ai-agents-run"]')
			.contains('.ag-badge', 'Completed', { timeout: RUN_TIMEOUT_MS })
			.should('exist');
		cy.get('[data-testid="lq-ai-agents-answer"] .prose')
			.invoke('text')
			.should('have.length.greaterThan', 20);
		// Reasoning is collapsed behind the <details> affordance, not inlined.
		// MiniMax-M3 reliably opens with a <think> block; if a future dev model
		// stops emitting them, relax this to a conditional on the API record.
		cy.get('[data-testid="lq-ai-agents-answer"] details.ag-thinking').should('exist');
		cy.get('[data-testid="lq-ai-agents-answer"] .prose').should(($el) => {
			expect($el.text()).not.to.contain('<think>');
		});
		cy.screenshot('f0-s3-3-agent-completed');

		// Polling actually stops once the run settles (no zombie 2s loop).
		cy.get('@pollRun.all').then((calls) => {
			const settled = (calls as unknown as unknown[]).length;
			cy.wait(5000);
			cy.get('@pollRun.all').then((later) => {
				expect((later as unknown as unknown[]).length).to.eq(settled);
			});
		});

		// The settled run shows up in the previous-runs list.
		cy.get('[data-testid="lq-ai-agents-runs-list"] li').should('have.length.at.least', 1);
	});
});
