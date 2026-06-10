/**
 * F0-S4 — real tools on real documents (live matter-bound run).
 *
 * Self-contained ADR-F005 evidence: seeds a fresh Matter through the API
 * (cy.exec + curl — binary-safe multipart for the PDF fixture), waits for
 * the ingest worker to chunk it, then drives a REAL agent run from the UI
 * with the matter bound and asserts the model itself dispatched
 * `search_documents` against the matter's document — no demo tools exist
 * anywhere anymore.
 *
 * Run requires the live dev stack (api + ingest-worker + gateway model):
 *   docker compose up -d
 *   cd web && npx cypress run --spec 'cypress/e2e/f0-s4-matter-tools.cy.ts'
 *
 * Spec name MUST stay `f0-s4-*` (fork pattern in cypress/support/e2e.ts —
 * any other name bootstraps an OpenWebUI user that breaks /lq-ai/*).
 */

/// <reference types="cypress" />

const EMAIL = Cypress.env('LQ_AI_EMAIL') ?? 'admin@lq.ai';
const PASSWORD = Cypress.env('LQ_AI_PASSWORD') ?? 'LQ-AI-local-Pw1!';
const API = Cypress.env('LQ_AI_API_URL') ?? 'http://localhost:8000/api/v1';

// The matter-bound loop is longer than S3's (search + read + answer).
const RUN_TIMEOUT_MS = 120_000;
// One small PDF through parse + chunk on the dev box.
const INGEST_ATTEMPTS = 40;
const INGEST_POLL_MS = 3_000;

/** Recursively poll the file row until ingestion_status === 'ready'. */
function waitForIngestion(token: string, fileId: string, attempt = 0): void {
	if (attempt >= INGEST_ATTEMPTS) {
		throw new Error(`file ${fileId} not ingested after ${INGEST_ATTEMPTS} polls`);
	}
	cy.exec(`curl -s ${API}/files/${fileId} -H 'Authorization: Bearer ${token}'`, {
		log: false
	}).then((res) => {
		const status = JSON.parse(res.stdout).ingestion_status;
		if (status === 'ready') return;
		if (status === 'failed') throw new Error(`ingestion failed for file ${fileId}`);
		cy.wait(INGEST_POLL_MS);
		waitForIngestion(token, fileId, attempt + 1);
	});
}

describe('F0-S4 — matter-bound deep agent uses real document tools', () => {
	it('seeds a matter, binds the run, and watches search_documents ground the answer', () => {
		const matterName = `S4 Acme MSA ${Date.now()}`;

		// ---- Seed through the API (curl: multipart upload stays binary-safe).
		cy.exec(
			`curl -s -X POST ${API}/auth/login -H 'Content-Type: application/json' ` +
				`-d '{"email":"${EMAIL}","password":"${PASSWORD}"}'`,
			{ log: false }
		).then((login) => {
			const token = JSON.parse(login.stdout).access_token as string;
			expect(token, 'login token').to.be.a('string').and.not.be.empty;

			cy.exec(
				`curl -s -X POST ${API}/projects -H 'Authorization: Bearer ${token}' ` +
					`-H 'Content-Type: application/json' -d '{"name":"${matterName}"}'`,
				{ log: false }
			).then((created) => {
				const project = JSON.parse(created.stdout);
				expect(project.id, 'project id').to.be.a('string');

				// Upload + attach in one call (files API project_id form field).
				cy.exec(
					`curl -s -X POST ${API}/files -H 'Authorization: Bearer ${token}' ` +
						`-F 'file=@cypress/fixtures/f0-s4-msa.pdf;type=application/pdf' ` +
						`-F 'project_id=${project.id}'`,
					{ log: false }
				).then((uploaded) => {
					const file = JSON.parse(uploaded.stdout);
					expect(file.id, 'file id').to.be.a('string');
					waitForIngestion(token, file.id);
				});
			});
		});

		// ---- UI: bind the matter and run the agent.
		cy.visit('/lq-ai/login');
		cy.get('[data-testid="lq-ai-login-email"]').type(EMAIL);
		cy.get('[data-testid="lq-ai-login-password"]').type(PASSWORD, { log: false });
		cy.get('[data-testid="lq-ai-login-submit"]').click();

		cy.contains('[role="tab"]', 'Agents', { timeout: 15_000 }).click();
		cy.location('pathname').should('eq', '/lq-ai/agents');

		// Await the option, then bind. The rail flips to the matter universe:
		// 2 document tools + 9 builtins, all dim.
		cy.get('[data-testid="lq-ai-agents-matter-select"] option', { timeout: 15_000 }).contains(
			matterName
		);
		cy.get('[data-testid="lq-ai-agents-matter-select"]').select(matterName);
		cy.get('[data-testid="lq-ai-agents-rail"] li').should('have.length', 11);
		cy.get('[data-testid="lq-ai-agents-rail"] li[title="search_documents"]').should(
			'have.class',
			'ag-rail__tool--dim'
		);
		cy.screenshot('f0-s4-1-matter-bound-idle');

		cy.get('[data-testid="lq-ai-agents-composer"] textarea').type(
			'What is the liability cap under the MSA? Search the matter documents and cite the clause.'
		);
		cy.get('[data-testid="lq-ai-agents-composer"] button[type="submit"]').click();

		// The run renders bound to the matter and steps settle in.
		cy.get('[data-testid="lq-ai-agents-run"]').should('exist');
		cy.get('[data-testid="lq-ai-agents-run-matter"]').should('contain.text', matterName);
		cy.get('[data-testid="lq-ai-agents-run"] .ag-steps li', { timeout: RUN_TIMEOUT_MS }).should(
			'have.length.at.least',
			1
		);
		cy.screenshot('f0-s4-2-agent-working');

		// The MODEL dispatched the real document tool and the result step
		// carries the real document's name — not canned text.
		cy.get('[data-testid="lq-ai-agents-rail"] li[title="search_documents"]', {
			timeout: RUN_TIMEOUT_MS
		}).should('not.have.class', 'ag-rail__tool--dim');
		cy.get('[data-testid="lq-ai-agents-run"] .ag-steps', { timeout: RUN_TIMEOUT_MS }).should(
			'contain.text',
			'f0-s4-msa.pdf'
		);

		// Completion: the answer is grounded in the ingested clause (the cap
		// is "twelve (12) months" — any faithful answer carries 12/twelve).
		cy.get('[data-testid="lq-ai-agents-run"]')
			.contains('.ag-badge', 'Completed', { timeout: RUN_TIMEOUT_MS })
			.should('exist');
		cy.get('[data-testid="lq-ai-agents-answer"] .prose')
			.invoke('text')
			.should('match', /twelve|12/i);
		cy.screenshot('f0-s4-3-agent-grounded-answer');
	});
});
