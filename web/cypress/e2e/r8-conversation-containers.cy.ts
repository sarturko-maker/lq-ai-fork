/**
 * R8 — Conversation containers: ChatSidebar / AttachedFilesPanel /
 * MessageOverflowMenu / AttachedSkillPill + the chat-shell responsive collapse.
 *
 * Drives the legacy chat workspace (`/lq-ai/chats`) with DETERMINISTIC,
 * backend-free fixtures so the same render is captured against the pre-R8
 * bundle (PHASE=before) and the R8 bundle (PHASE=after). Two concerns:
 *
 *   1. Token migration of the side panes — sidebar (chats grouped by a
 *      PRIVILEGED project + a no-project bucket, active row highlighted, the
 *      "+ New Chat" shadcn Button) and the attached-files panel (read-only
 *      project files with ready/processing/failed status badges).
 *   2. SHELL responsive collapse (maintainer directive): below 880px the two
 *      side panes leave the flex row and become off-canvas drawers behind the
 *      header ☰ / Files toggles + a shared scrim (the cockpit idiom).
 *
 * The functional `describe` exercises R8-only behaviour (drawers, the
 * Svelte-4→runes Button onclick forward) and is skipped when CAPTURE_ONLY=1
 * (the pre-R8 bundle has no drawers). The capture `describe` is element-guarded
 * so it runs on BOTH phases; only the screenshot tags differ.
 *
 * Run (live stack, headed for honest dark-theme capture):
 *   cd web && npx cypress run --headed --browser electron \
 *     --spec 'cypress/e2e/r8-conversation-containers.cy.ts' \
 *     --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!,PHASE=after
 */
const PHASE = () => (Cypress.env('PHASE') as string) || 'after';
const CAPTURE_ONLY = String(Cypress.env('CAPTURE_ONLY')) === '1';

const NOW = '2026-06-14T10:00:00Z';
const PROJ_ID = '00000000-0000-4000-8000-0000000000b1';
const CHAT_ID = '00000000-0000-4000-8000-0000000000b8';
const CHAT_ID_2 = '00000000-0000-4000-8000-0000000000b9';
const CHAT_ID_NP = '00000000-0000-4000-8000-0000000000ba';
const FILE_READY = '00000000-0000-4000-8000-0000000000f1';
const FILE_PROC = '00000000-0000-4000-8000-0000000000f2';
const FILE_FAIL = '00000000-0000-4000-8000-0000000000f3';

const PROJECT = {
	id: PROJ_ID,
	name: 'Acme ⇄ Globex Merger',
	slug: 'acme-globex',
	description: null,
	context_md: null,
	owner_id: 'admin',
	privileged: true,
	minimum_inference_tier: 4,
	attached_skill_names: [],
	attached_file_ids: [FILE_READY, FILE_PROC, FILE_FAIL],
	attached_knowledge_base_ids: [],
	archived_at: null,
	is_sandbox: false,
	created_at: NOW,
	updated_at: NOW
};

function chat(id: string, title: string, project_id: string | null) {
	return {
		id,
		title,
		owner_id: 'admin',
		project_id,
		archived_at: null,
		message_count: 0,
		created_at: NOW,
		updated_at: NOW
	};
}

const CHATS = {
	items: [
		chat(CHAT_ID, 'Disclosure-schedule review', PROJ_ID),
		chat(CHAT_ID_2, 'Reps & warranties markup', PROJ_ID),
		chat(CHAT_ID_NP, 'Quick research thread', null)
	],
	next_cursor: null
};

const MESSAGES = {
	items: [
		{
			id: 'm-user-1',
			chat_id: CHAT_ID,
			role: 'user',
			content: 'Summarise the indemnity cap in the disclosure schedule.',
			created_at: NOW
		},
		{
			id: 'm-asst-1',
			chat_id: CHAT_ID,
			role: 'assistant',
			content:
				'The indemnity cap is 15% of the purchase price, with a 12-month survival ' +
				'period for general reps and 6 years for fundamental reps and tax.',
			routed_inference_tier: 4,
			routed_provider: 'minimax',
			routed_model: 'MiniMax-M3',
			created_at: NOW
		}
	],
	next_cursor: null
};

function fileMeta(id: string, filename: string, status: string, error: string | null = null) {
	return {
		id,
		owner_id: 'admin',
		project_id: PROJ_ID,
		filename,
		mime_type: 'application/pdf',
		size_bytes: 824_000,
		ingestion_status: status,
		ingestion_error: error
	};
}

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

function stub() {
	// Anchor every stub to `/api/v1` (a bare `/chats` regex also catches the
	// `cy.visit` DOCUMENT request → "could not load · 200 application/json").
	cy.intercept('GET', /\/api\/v1\/projects(\?.*)?$/, [PROJECT]).as('projects');
	cy.intercept('GET', `**/api/v1/projects/${PROJ_ID}`, PROJECT).as('project');
	cy.intercept('GET', /\/api\/v1\/chats(\?.*)?$/, CHATS).as('chats');
	cy.intercept('GET', '**/api/v1/chats/*/messages*', MESSAGES).as('messages');
	cy.intercept('GET', `**/api/v1/files/${FILE_READY}`, fileMeta(FILE_READY, 'SPA-execution-copy.pdf', 'ready'));
	cy.intercept('GET', `**/api/v1/files/${FILE_PROC}`, fileMeta(FILE_PROC, 'disclosure-schedule.pdf', 'processing'));
	cy.intercept(
		'GET',
		`**/api/v1/files/${FILE_FAIL}`,
		fileMeta(FILE_FAIL, 'scanned-side-letter.pdf', 'failed', 'OCR failed: page 3 unreadable')
	);
	cy.intercept('POST', '**/api/v1/chats', {
		statusCode: 201,
		body: chat('00000000-0000-4000-8000-0000000000bf', 'New chat', null)
	}).as('createChat');
	// Let skills/models fall through to the real backend (non-deterministic but
	// off-surface for R8).
}

function openChat() {
	cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
	cy.get('[data-testid="lq-ai-chat-sidebar"]', { timeout: 15000 }).should('exist');
}

// ── Functional (R8-only behaviour; skipped on the pre-R8 bundle) ─────────────
(CAPTURE_ONLY ? describe.skip : describe)('R8 — conversation containers: behaviour', () => {
	beforeEach(() => {
		stub();
		login();
	});

	it('renders the migrated sidebar (privileged badge, grouping, active row)', () => {
		cy.viewport(1280, 860);
		openChat();
		cy.get('[data-testid="lq-ai-chat-sidebar"]').within(() => {
			cy.contains('PRIVILEGED').should('be.visible');
			cy.contains('Acme ⇄ Globex Merger').should('be.visible');
			cy.contains('Without a project').should('be.visible');
			// Active chat row carries the cockpit selected wash.
			cy.get(`[data-testid="lq-ai-chat-${CHAT_ID}"]`).should('have.class', 'bg-accent');
		});
	});

	it('+ New Chat (shadcn Button) forwards onclick from the Svelte-4 parent', () => {
		cy.viewport(1280, 860);
		openChat();
		cy.get('[data-testid="lq-ai-new-chat-btn"]').click();
		// Proves the runes-child Button's onclick reached createNewChat.
		cy.wait('@createChat');
	});

	it('shows attached project files with status badges (read-only UploadChip)', () => {
		cy.viewport(1280, 860);
		openChat();
		cy.get('[data-testid="lq-ai-attached-files-panel"]').within(() => {
			cy.contains('SPA-execution-copy.pdf').should('be.visible');
			cy.contains('ready').should('be.visible');
			cy.contains('processing').should('be.visible');
			cy.contains('failed').should('be.visible');
		});
	});

	it('collapses the side panes into drawers below 880px (cockpit idiom)', () => {
		cy.viewport(760, 1000);
		openChat();
		// Sidebar is off-canvas: present in the DOM but translated away AND
		// `inert` so its controls leave the tab order + a11y tree when closed
		// (R8 review fix — no invisible focusable controls). Multiple attribute
		// checks go in one `.should(cb)` because chaining `.and('have.attr')`
		// rebinds the subject to the attribute value, breaking the next link.
		cy.get('[data-testid="lq-ai-sidebar-drawer"]').should(($el) => {
			expect($el).to.have.class('-translate-x-full');
			expect($el).to.have.attr('inert');
		});
		cy.get('[data-testid="lq-ai-chat-scrim"]').should('not.exist');

		// ☰ opens the nav drawer + scrim, drops `inert`, and exposes the dialog
		// role. (Focus-on-open is implemented in the toggle handler — `await
		// tick(); el.focus()` — but document.activeElement is unreliable under
		// headed-Electron/Xvfb, where programmatic focus doesn't register
		// without OS window focus, so it is not asserted here.)
		cy.get('[data-testid="lq-ai-nav-toggle"]').click();
		cy.get('[data-testid="lq-ai-sidebar-drawer"]').should(($el) => {
			expect($el).to.have.class('translate-x-0');
			expect($el).not.to.have.attr('inert');
			expect($el).to.have.attr('role', 'dialog');
		});
		cy.get('[data-testid="lq-ai-chat-scrim"]').should('be.visible');

		// Escape closes it (and re-asserts `inert`).
		cy.get('body').type('{esc}');
		cy.get('[data-testid="lq-ai-sidebar-drawer"]').should(($el) => {
			expect($el).to.have.class('-translate-x-full');
			expect($el).to.have.attr('inert');
		});
		cy.get('[data-testid="lq-ai-chat-scrim"]').should('not.exist');

		// Files toggle opens the right drawer; the scrim closes it.
		cy.get('[data-testid="lq-ai-files-toggle"]').click();
		cy.get('[data-testid="lq-ai-files-drawer"]').should(($el) => {
			expect($el).to.have.class('translate-x-0');
			expect($el).not.to.have.attr('inert');
		});
		cy.get('[data-testid="lq-ai-chat-scrim"]').click({ force: true });
		cy.get('[data-testid="lq-ai-files-drawer"]').should(($el) => {
			expect($el).to.have.class('translate-x-full');
			expect($el).to.have.attr('inert');
		});
	});
});

// ── Visual evidence: light/dark × wide/narrow (both phases) ──────────────────
// Theme is set in localStorage BEFORE each visit so the app's pre-paint script
// boots in that theme — a same-load class toggle didn't reliably repaint the
// wide layout (the dark capture came back light).
describe('R8 — conversation containers: visual capture', () => {
	beforeEach(() => {
		stub();
		login();
	});

	const THEMES: Array<'light' | 'dark'> = ['light', 'dark'];

	function visitChat(theme: 'light' | 'dark') {
		cy.window().then((w) => w.localStorage.setItem('theme', theme));
		cy.visit(`/lq-ai/chats?id=${CHAT_ID}`);
		cy.get('[data-testid="lq-ai-chat-sidebar"]', { timeout: 15000 }).should('exist');
		setTheme(theme); // belt-and-suspenders: pin the class post-boot
		cy.get('html').should('have.class', theme); // the class IS applied
	}

	it('captures the panes wide (light + dark)', () => {
		for (const theme of THEMES) {
			cy.viewport(1281, 900);
			visitChat(theme);
			cy.get('[data-testid="lq-ai-attached-files-panel"]').should('exist');
			// Nudge the viewport to force Electron to repaint the new theme (a
			// same-frame class swap can leave the prior paint on screen).
			cy.viewport(1280, 900);
			cy.wait(250);
			cy.screenshot(`${PHASE()}-r8-panes-${theme}-wide`, { capture: 'viewport' });
		}
	});

	it('captures the shell narrow (light + dark) — collapsed after, squeezed before', () => {
		for (const theme of THEMES) {
			cy.viewport(760, 1000);
			visitChat(theme);
			cy.wait(150);
			// After R8 the toggle exists → open the nav drawer for the collapse shot.
			// Before R8 it's absent → capture the (squeezed) non-responsive layout.
			cy.get('body').then(($b) => {
				if ($b.find('[data-testid="lq-ai-nav-toggle"]').length) {
					cy.get('[data-testid="lq-ai-nav-toggle"]').click();
					cy.get('[data-testid="lq-ai-chat-scrim"]').should('be.visible');
					cy.wait(250); // let the drawer settle
				}
			});
			cy.screenshot(`${PHASE()}-r8-narrow-${theme}`, { capture: 'viewport' });
		}
	});
});
