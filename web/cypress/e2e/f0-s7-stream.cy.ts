/**
 * F0-S7 — SSE v2: the agents surface streams like Claude Code.
 *
 * Drives a REAL matter-bound run against the live dev stack and asserts
 * the stream upgrade end-to-end: the page opens the run's UI Message
 * Stream v1 (`GET /agents/runs/{id}/stream`), the collapsed-by-default
 * thinking ribbon animates live reasoning deltas while the run works,
 * polling is parked while the stream is healthy, and the settled answer
 * renders exactly as the polled contract always did (ADR-F004: the
 * stream is animation; settled rows decide). Screenshots double as the
 * ADR-F005 live-verification evidence.
 *
 * Run requires a live stack, a gateway model that answers, and a
 * pre-seeded matter with ingested documents (HANDOFF: pre-seed with the
 * browser closed):
 *   CYPRESS_LQ_AI_MATTER_NAME="<matter>" npx cypress run \
 *     --spec 'cypress/e2e/f0-s7-stream.cy.ts' --config video=false
 *
 * Costs one short MiniMax-M3 loop. Never runs in CI (CI has no stack).
 */

/// <reference types="cypress" />

const EMAIL = Cypress.env('LQ_AI_EMAIL') ?? 'admin@lq.ai';
const PASSWORD = Cypress.env('LQ_AI_PASSWORD') ?? 'LQ-AI-local-Pw1!';
const MATTER_NAME = Cypress.env('LQ_AI_MATTER_NAME');

const RUN_TIMEOUT_MS = 120_000;

describe('F0-S7 — SSE v2 streaming (live deep agent)', () => {
	it('streams reasoning live, parks polling, and settles the answer', function () {
		if (!MATTER_NAME) {
			cy.log('CYPRESS_LQ_AI_MATTER_NAME not set — skipping (needs a pre-seeded matter)');
			this.skip();
		}

		cy.visit('/lq-ai/login');
		cy.get('[data-testid="lq-ai-login-email"]', { timeout: 30_000 }).type(EMAIL);
		cy.get('[data-testid="lq-ai-login-password"]').type(PASSWORD, { log: false });
		cy.get('[data-testid="lq-ai-login-submit"]').click();

		// F1-S2: post-login lands in the cockpit (no tab bar) — the legacy
		// agents tab keeps working at its URL. Wait out the redirect first:
		// visiting mid-login CANCELS the in-flight POST (the old tab-click
		// waited implicitly).
		cy.url({ timeout: 15_000 }).should('not.include', '/login');
		cy.visit('/lq-ai/agents');
		cy.location('pathname').should('eq', '/lq-ai/agents');

		// Polls must stay parked while the stream is healthy. NOTE: the
		// stream route itself is deliberately NOT intercepted — Cypress
		// buffers intercepted responses, which would deliver the whole SSE
		// stream in one burst and erase the very liveness under test. The
		// thinking ribbon below is the stream evidence instead: polling
		// can never feed it.
		cy.intercept('GET', '**/api/v1/agents/threads/*').as('pollThread');

		cy.get('[data-testid="lq-ai-agents-matter-select"]', { timeout: 15_000 })
			.find('option')
			.contains(MATTER_NAME);
		cy.get('[data-testid="lq-ai-agents-matter-select"]').select(MATTER_NAME);

		cy.get('[data-testid="lq-ai-agents-composer"] textarea').type(
			'What is the liability cap under this contract? Search the matter documents.'
		);
		cy.get('[data-testid="lq-ai-agents-composer"] button[type="submit"]').click();

		// Live reasoning deltas render as the thinking ribbon — only the
		// stream can put it there (polling never feeds it). Since F0-S8 the
		// ribbon is AUTO-EXPANDED (claude.ai-style clamped tail), so assert
		// the streamed reasoning text is actually visible, no click needed.
		cy.get('[data-testid="lq-ai-agents-thinking-live"]', { timeout: RUN_TIMEOUT_MS }).should(
			'exist'
		);
		cy.get('[data-testid="lq-ai-agents-thinking-live"] .ag-thinking-live__tail')
			.invoke('text')
			.should('have.length.greaterThan', 0);
		// Viewport capture: full-page stitching renders the sticky bottom
		// composer over the conversation and can hide the ribbon; the
		// auto-scroll keeps the ribbon in the viewport, so capture that.
		cy.screenshot('f0-s7-1-thinking-ribbon-live', { capture: 'viewport' });

		// The run settles: badge flips, the answer renders from settled
		// state, the ribbon is gone (rows decided).
		cy.get('[data-testid="lq-ai-agents-run"] .ag-badge', { timeout: RUN_TIMEOUT_MS }).should(
			'contain.text',
			'Completed'
		);
		cy.get('[data-testid="lq-ai-agents-answer"] .prose', { timeout: 15_000 })
			.invoke('text')
			.should('match', /liabilit|cap|fee/i);
		cy.get('[data-testid="lq-ai-agents-thinking-live"]').should('not.exist');
		cy.screenshot('f0-s7-2-settled-answer');

		// Streaming parked the poller: the handoff poll, the post-stream
		// reconcile, and slack for one retry. A broken handoff polls every
		// 2s, so even a short ~10s run would blow this bound (review: the
		// earlier <8 only discriminated for runs longer than ~14s).
		cy.get('@pollThread.all').its('length').should('be.lessThan', 5);

		// Steps still render from settled rows — the timeline survived the
		// streaming upgrade byte-for-byte.
		cy.get('[data-testid="lq-ai-agents-thread"] .ag-steps li').should('have.length.at.least', 2);
	});
});
