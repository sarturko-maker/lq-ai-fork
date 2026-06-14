<script lang="ts">
	/**
	 * `/lq-ai/_ae-lab` — internal AI Elements scratch surface (AE0, ADR-F011).
	 *
	 * Unadvertised + auth-gated + linked from nowhere: it changes NO live
	 * surface. The web container always serves a prod build (no separate dev
	 * deploy exists), so "dev-only" is realized as an internal, leading-`_`,
	 * non-navigable route rather than an `import.meta.env.DEV` compile-out —
	 * which keeps it Cypress-testable on :3000 and proves the vendored AE
	 * components render in the real bundle.
	 *
	 * Used to eyeball + interaction-check vendored AI Elements components as
	 * they land (AE0: Loader, Suggestion/Suggestions).
	 */
	import { Loader } from '$lib/lq-ai/components/ai-elements/loader/index.js';
	import { Suggestion, Suggestions } from '$lib/lq-ai/components/ai-elements/suggestion/index.js';
	import ReasoningRibbon from '$lib/lq-ai/components/primitives/ReasoningRibbon.svelte';
	import MessageActionsBar from '$lib/lq-ai/components/MessageActionsBar.svelte';
	import MessageSources from '$lib/lq-ai/components/MessageSources.svelte';
	import { renderModelMarkdown } from '$lib/lq-ai/sanitize-markdown';
	import { enhanceCodeBlocks } from '$lib/lq-ai/code/enhance';
	import type { Citation } from '$lib/lq-ai/types';

	const SUGGESTIONS = [
		'Summarise this contract',
		'Flag unusual indemnities',
		'Draft a termination clause',
		'Compare against our playbook',
		'What are the key dates?'
	];

	let lastPicked = $state('');
	let pickCount = $state(0);
	let dark = $state(false);

	function pick(s: string) {
		lastPicked = s;
		pickCount += 1;
	}

	function toggleTheme() {
		dark = !dark;
		// Local, non-persisting toggle — does not touch the saved `theme`
		// preference (this is a scratch surface).
		const root = document.documentElement;
		root.classList.remove('dark', 'light');
		root.classList.add(dark ? 'dark' : 'light');
	}

	// AE2 — Reasoning demo. The streaming toggle exercises the shimmer +
	// auto-open while "streaming", then the measured duration + one-shot
	// auto-collapse when it ends (the path the live chat surface can't show yet
	// — reasoning deltas land with F1-S4).
	let reasoningStreaming = $state(false);
	const REASONING_BODY =
		'The indemnity at clause 9.2 is uncapped, which is unusual for a mutual ' +
		'agreement of this size; flag it against the playbook before signature.';

	// AE2 — Actions demo. Retry just bumps a counter here (the live surface
	// re-dispatches the preceding prompt); Copy / Copy-sources are self-contained.
	let retryCount = $state(0);
	const DEMO_ANSWER =
		'Clause 9.2 carries an uncapped indemnity. Recommend negotiating a liability cap.';
	const DEMO_SOURCES = [
		'[1] "...indemnify and hold harmless..." (p.12)',
		'[2] "...without limit..." (p.13)'
	];

	// AE3 — Sources card demo. Three distinct documents with mixed verification
	// states (green exact, amber paraphrase, grey unverified) exercising the
	// per-source rollup marker + the pages/passages meta + the quote.
	function makeCite(o: Partial<Citation>): Citation {
		return {
			id: o.id ?? 'c',
			source_file_id: o.source_file_id ?? 'f',
			source_offset_start: 0,
			source_offset_end: 0,
			source_text: '',
			verified: true,
			...o
		};
	}
	const DEMO_CITATIONS: Citation[] = [
		makeCite({
			id: 'c1',
			source_file_id: 'f1',
			source_filename: 'Master Services Agreement.pdf',
			source_page: 12,
			source_text: 'The Supplier shall indemnify and hold harmless the Customer…',
			verification_method: 'exact_match'
		}),
		makeCite({
			id: 'c2',
			source_file_id: 'f1',
			source_filename: 'Master Services Agreement.pdf',
			source_page: 13,
			source_text: 'such indemnity to apply without limit of liability',
			verification_method: 'exact_match'
		}),
		makeCite({
			id: 'c3',
			source_file_id: 'f2',
			source_filename: 'Data Processing Addendum.pdf',
			source_page: 4,
			source_text: 'the processor notifies the controller within 24 hours of a breach',
			verification_method: 'paraphrase_judge'
		}),
		makeCite({
			id: 'c4',
			source_file_id: 'f3',
			source_filename: 'Side Letter (unsigned).pdf',
			source_text: 'the parties intend to negotiate a cap in good faith',
			verified: false,
			verification_method: 'failed'
		})
	];

	// AE4 — Code Block demo. Goes through the REAL chat path: untrusted markdown
	// → renderModelMarkdown (marked + DOMPurify, media-forbidden) → {@html} →
	// the enhanceCodeBlocks action (Shiki highlight + card). The `<script>` and
	// `&` below prove the escaped-text→highlight pipeline is injection-safe; the
	// `cobol` fence proves an unsupported language degrades to plain text.
	const DEMO_CODE_MD = [
		'```python',
		'def redline(clause: str) -> bool:',
		'    # flag uncapped indemnities',
		'    return "without limit" in clause.lower()  # 1 < 2 && safe',
		'```',
		'',
		'```sql',
		'SELECT party, MAX(liability_cap)',
		'FROM contracts WHERE signed IS NULL;',
		'```',
		'',
		'```cobol',
		'IDENTIFICATION DIVISION.',
		'PROGRAM-ID. UNKNOWN-LANG.',
		'```',
		'',
		'```',
		'<script>alert(1)<\/script> & plain "fence" — no language',
		'```'
	].join('\n');
	const demoCodeHtml = renderModelMarkdown(DEMO_CODE_MD);
</script>

<div class="min-h-full bg-background text-foreground">
	<div class="mx-auto max-w-3xl px-6 py-8">
		<div
			class="mb-6 rounded-md border border-dashed border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground"
			data-testid="ae-lab-banner"
		>
			<strong class="font-semibold text-foreground">Internal — AI Elements lab.</strong>
			Vendored component scratch surface (ADR-F011). Not linked from any nav; not a user surface.
		</div>

		<div class="mb-8 flex items-center justify-between">
			<h1 class="text-xl font-semibold">AI Elements lab — AE0 + AE2 + AE3 + AE4</h1>
			<button
				type="button"
				class="rounded-md border border-border bg-card px-3 py-1.5 text-sm font-medium hover:bg-muted/60"
				data-testid="ae-lab-theme-toggle"
				onclick={toggleTheme}
			>
				{dark ? 'Light' : 'Dark'} mode
			</button>
		</div>

		<section class="mb-10" data-testid="ae-lab-loader">
			<h2 class="mb-3 text-sm font-semibold text-muted-foreground">Loader</h2>
			<div class="flex items-center gap-6 rounded-lg border border-border bg-card p-6">
				<Loader size={16} />
				<Loader size={24} />
				<Loader size={32} />
				<span class="text-sm text-muted-foreground">inherits text colour (currentColor)</span>
			</div>
		</section>

		<section data-testid="ae-lab-suggestions">
			<h2 class="mb-3 text-sm font-semibold text-muted-foreground">Suggestions</h2>
			<div class="rounded-lg border border-border bg-card p-6">
				<Suggestions>
					{#each SUGGESTIONS as s (s)}
						<Suggestion suggestion={s} onclick={pick} />
					{/each}
				</Suggestions>
				<p class="mt-4 text-sm text-muted-foreground">
					Picked
					<span class="font-semibold text-foreground" data-testid="ae-lab-pick-count"
						>{pickCount}</span
					>
					×{#if lastPicked}
						— last: <span class="font-medium text-foreground" data-testid="ae-lab-last-pick"
							>{lastPicked}</span
						>{/if}
				</p>
			</div>
		</section>

		<section class="mt-10" data-testid="ae-lab-reasoning">
			<h2 class="mb-3 text-sm font-semibold text-muted-foreground">Reasoning (AE2)</h2>
			<div class="rounded-lg border border-border bg-card p-6">
				<button
					type="button"
					class="mb-4 rounded-md border border-border bg-card px-3 py-1.5 text-sm font-medium hover:bg-muted/60"
					data-testid="ae-lab-reasoning-toggle"
					onclick={() => (reasoningStreaming = !reasoningStreaming)}
				>
					{reasoningStreaming ? 'Stop streaming' : 'Start streaming'}
				</button>
				<ReasoningRibbon streaming={reasoningStreaming}>
					{REASONING_BODY}
				</ReasoningRibbon>
			</div>
		</section>

		<section class="mt-10" data-testid="ae-lab-actions">
			<h2 class="mb-3 text-sm font-semibold text-muted-foreground">Message actions (AE2)</h2>
			<div class="group rounded-lg border border-border bg-card p-6">
				<p class="mb-3 text-sm">{DEMO_ANSWER}</p>
				<MessageActionsBar
					answer={DEMO_ANSWER}
					sources={DEMO_SOURCES}
					onRetry={() => (retryCount += 1)}
				/>
				<p class="mt-4 text-sm text-muted-foreground">
					Retried
					<span class="font-semibold text-foreground" data-testid="ae-lab-retry-count"
						>{retryCount}</span
					>
					×
				</p>
			</div>
		</section>

		<section class="mt-10" data-testid="ae-lab-sources">
			<h2 class="mb-3 text-sm font-semibold text-muted-foreground">Sources (AE3)</h2>
			<div class="rounded-lg border border-border bg-card p-6">
				<p class="mb-3 text-sm">
					Clause 9.2 carries an uncapped indemnity "…without limit of liability" (Source: [1]).
				</p>
				<MessageSources citations={DEMO_CITATIONS} />
			</div>
		</section>

		<section class="mt-10" data-testid="ae-lab-code">
			<h2 class="mb-3 text-sm font-semibold text-muted-foreground">Code blocks (AE4)</h2>
			<div class="rounded-lg border border-border bg-card p-6">
				<div
					class="prose prose-sm dark:prose-invert max-w-none"
					data-testid="ae-lab-code-content"
					use:enhanceCodeBlocks={{ enabled: true }}
				>
					<!-- eslint-disable-next-line svelte/no-at-html-tags — DOMPurify-sanitized via renderModelMarkdown -->
					{@html demoCodeHtml}
				</div>
			</div>
		</section>
	</div>
</div>
