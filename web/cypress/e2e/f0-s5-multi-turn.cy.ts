/**
 * F0-S5 — multi-turn conversations + composer upload (live, ADR-F008).
 *
 * ADR-F005 live-verification evidence, three acts on one conversation:
 *
 *  1. A matter-bound run grounds an answer in the matter's documents
 *     (the S4 behavior, now as turn 1 of a conversation).
 *  2. A FOLLOW-UP on the same thread proves durable agent state: the
 *     model is asked what the previous question was — answerable only
 *     if the checkpointer restored turn 1.
 *  3. A document uploaded FROM THE COMPOSER (ADR-F007 upload-time
 *     membership) becomes searchable in the same conversation once the
 *     ingestion chip flips to ready.
 *
 * Run requires the live dev stack. Dev-box rules (see f0-s4 header):
 * always `--config video=false`; on a constrained box PRE-SEED the
 * matter and pass CYPRESS_LQ_AI_MATTER_NAME to skip seeding:
 *   cd web && CYPRESS_LQ_AI_MATTER_NAME="<name>" npx cypress run \
 *     --spec 'cypress/e2e/f0-s5-multi-turn.cy.ts' --config video=false
 *
 * The composer upload (act 3) cannot be pre-seeded — it IS the thing
 * under test. If the ingest worker wedges ("connection is closed"),
 * `docker compose restart ingest-worker arq-worker` and re-run.
 *
 * (The pre-S6 spec-name-pattern constraint is gone: the OpenWebUI
 * bootstrap died with the husk in F0-S6.)
 */

/// <reference types="cypress" />

const EMAIL = Cypress.env('LQ_AI_EMAIL') ?? 'admin@lq.ai';
const PASSWORD = Cypress.env('LQ_AI_PASSWORD') ?? 'LQ-AI-local-Pw1!';
const API = Cypress.env('LQ_AI_API_URL') ?? 'http://localhost:8000/api/v1';

const RUN_TIMEOUT_MS = 120_000;
const INGEST_TIMEOUT_MS = 120_000;
const INGEST_ATTEMPTS = 40;
const INGEST_POLL_MS = 3_000;

/** Poll the file row until ingestion_status === 'ready' (seeding only). */
function waitForIngestion(token: string, fileId: string, attempt = 0): void {
	if (attempt >= INGEST_ATTEMPTS) {
		throw new Error(`file ${fileId} not ingested after ${INGEST_ATTEMPTS} polls`);
	}
	cy.exec(`curl -s ${API}/files/${fileId} -H 'Authorization: Bearer ${token}'`, {
		log: false
	}).then((res) => {
		let status: string | undefined;
		try {
			status = JSON.parse(res.stdout).ingestion_status;
		} catch {
			status = undefined; // transient API hiccup — retry
		}
		if (status === 'ready') return;
		if (status === 'failed') throw new Error(`ingestion failed for file ${fileId}`);
		cy.wait(INGEST_POLL_MS);
		waitForIngestion(token, fileId, attempt + 1);
	});
}

describe('F0-S5 — multi-turn conversation with composer upload', () => {
	it('keeps context across turns and grounds on a composer-uploaded document', () => {
		const preSeeded = Cypress.env('LQ_AI_MATTER_NAME') as string | undefined;
		const matterName = preSeeded ?? `S5 Acme MSA ${Date.now()}`;

		// ---- Seed a matter + base document through the API (same as f0-s4).
		if (!preSeeded) {
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
		}

		// ---- Act 1: matter-bound turn 1 (the S4 behavior inside a thread).
		cy.visit('/lq-ai/login');
		cy.get('[data-testid="lq-ai-login-email"]', { timeout: 30_000 }).type(EMAIL);
		cy.get('[data-testid="lq-ai-login-password"]').type(PASSWORD, { log: false });
		cy.get('[data-testid="lq-ai-login-submit"]').click();

		// 30s: a postgres crash-recovery window (the dev-box gotcha) can stall
		// the login POST past the default — seen live during this slice's gate.
		cy.contains('[role="tab"]', 'Agents', { timeout: 30_000 }).click();
		cy.location('pathname').should('eq', '/lq-ai/agents');

		cy.get('[data-testid="lq-ai-agents-matter-select"] option', { timeout: 15_000 }).contains(
			matterName
		);
		cy.get('[data-testid="lq-ai-agents-matter-select"]').select(matterName);

		cy.get('[data-testid="lq-ai-agents-composer"] textarea').type(
			'What is the liability cap under the MSA? Search the matter documents and cite the clause.'
		);
		cy.get('[data-testid="lq-ai-agents-composer"] button[type="submit"]').click();

		// The conversation opens: matter chip on the thread head, one turn.
		cy.get('[data-testid="lq-ai-agents-run"]', { timeout: 30_000 }).should('have.length', 1);
		cy.get('[data-testid="lq-ai-agents-run-matter"]').should('contain.text', matterName);
		cy.get('[data-testid="lq-ai-agents-run"]')
			.contains('.ag-badge', 'Completed', { timeout: RUN_TIMEOUT_MS })
			.should('exist');
		cy.get('[data-testid="lq-ai-agents-answer"] .prose')
			.invoke('text')
			.should('match', /twelve|12/i);
		cy.screenshot('f0-s5-1-turn-one-grounded');

		// ---- Act 2: the follow-up proves the checkpointer restored turn 1.
		cy.get('[data-testid="lq-ai-agents-composer"] textarea', { timeout: 15_000 })
			.should('not.be.disabled')
			.type(
				'Without using any tools: what did I ask you in my previous message? Answer in one sentence.'
			);
		cy.get('[data-testid="lq-ai-agents-composer"] button[type="submit"]').click();

		cy.get('[data-testid="lq-ai-agents-run"]', { timeout: 30_000 }).should('have.length', 2);
		cy.get('[data-testid="lq-ai-agents-run"]')
			.last()
			.contains('.ag-badge', 'Completed', { timeout: RUN_TIMEOUT_MS })
			.should('exist');
		// Only the restored thread state can tell it the prior question.
		cy.get('[data-testid="lq-ai-agents-answer"]')
			.last()
			.find('.prose')
			.invoke('text')
			.should('match', /liability\s+cap|liability/i);
		cy.screenshot('f0-s5-2-follow-up-remembers');

		// ---- Act 3: upload FROM THE COMPOSER; the agent grounds on it.
		cy.get('[data-testid="lq-ai-agents-file-input"]').selectFile(
			'cypress/fixtures/f0-s5-amendment.pdf',
			{ force: true }
		);
		cy.get('[data-testid="lq-ai-agents-upload-chip"]').should('contain.text', 'f0-s5-amendment');
		cy.get('[data-testid="lq-ai-agents-upload-chip"]', { timeout: INGEST_TIMEOUT_MS }).should(
			'contain.text',
			'ready'
		);
		cy.screenshot('f0-s5-3-composer-upload-ready');

		cy.get('[data-testid="lq-ai-agents-composer"] textarea')
			.should('not.be.disabled')
			.type(
				'Search the matter documents for Amendment No. 2 and tell me what liability cap it sets.'
			);
		cy.get('[data-testid="lq-ai-agents-composer"] button[type="submit"]').click();

		cy.get('[data-testid="lq-ai-agents-run"]', { timeout: 30_000 }).should('have.length', 3);
		cy.get('[data-testid="lq-ai-agents-run"]')
			.last()
			.contains('.ag-badge', 'Completed', { timeout: RUN_TIMEOUT_MS })
			.should('exist');
		// The answer is grounded in the document that entered through the
		// composer minutes ago (Amendment No. 2: twenty-four (24) months).
		cy.get('[data-testid="lq-ai-agents-answer"]')
			.last()
			.find('.prose')
			.invoke('text')
			.should('match', /twenty-four|24/i);
		cy.screenshot('f0-s5-4-grounded-on-uploaded-doc');

		// The conversation (one thread, three turns) is in the list.
		cy.get('[data-testid="lq-ai-agents-runs-list"] li').should('have.length.at.least', 1);
	});
});
