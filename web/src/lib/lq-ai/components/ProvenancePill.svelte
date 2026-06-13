<script context="module" lang="ts">
	/**
	 * ProvenancePill — pill primitive attached to AI messages.
	 * Wave A defines the contract; Wave D wires it into the message renderer.
	 * See spec §5.2.
	 */
	export type ProvenanceKind = 'skill' | 'tier' | 'provider' | 'kb' | 'audit' | 'enhanced';

	const KIND_ICON: Record<ProvenanceKind, string> = {
		skill: '🛠️',
		tier: '🔒',
		provider: '🧠',
		kb: '📎',
		audit: '📜',
		enhanced: '✨'
	};

	/**
	 * Plain-English hover descriptions for each provenance kind.
	 * Surfaced via the button's `title` attribute so non-technical users
	 * can hover to learn what each pill means without having to click
	 * through to the detail panel.
	 */
	const KIND_DESCRIPTION: Record<ProvenanceKind, string> = {
		skill:
			'Skill — this answer was shaped by a reusable structured prompt. Click to read the skill source.',
		tier: 'Inference tier — where this answer was processed (Tier 1 = local, Tier 5 = consumer). Click for details.',
		provider: 'AI provider — which model produced this answer. Click for details.',
		kb: 'Knowledge base — documents the AI could search and cite from for this answer. Click to view.',
		audit:
			'Audit log — this action was recorded for compliance and review. Click to view the entry.',
		enhanced:
			'Enhanced Prompt — the AI rewrote your short prompt into a structured legal prompt before answering. Click to compare.'
	};

	export function iconFor(kind: ProvenanceKind): string {
		return KIND_ICON[kind];
	}

	export function descriptionFor(kind: ProvenanceKind): string {
		return KIND_DESCRIPTION[kind];
	}

	export type ProvenanceTone = 'sage' | 'slate' | 'amber';

	export function toneFor(kind: ProvenanceKind, tierMismatch: boolean): ProvenanceTone {
		if (kind === 'tier') return tierMismatch ? 'amber' : 'slate';
		return 'sage';
	}
</script>

<script lang="ts">
	export let kind: ProvenanceKind;
	export let summary: string;
	export let tierMismatch = false;
	export let onTap: (() => void) | undefined = undefined;

	// R6: legacy `--lq-accent/tier/warn-*` tones → semantic tokens. sage is the
	// soft-accent tint (the default metadata pill); slate is neutral muted (tier
	// OK); amber is the warning idiom shared with the R1a Alert — `text-amber-700`
	// / `dark:text-amber-300` clears WCAG AA on the tinted wash in both themes.
	const TONE_CLASS: Record<ProvenanceTone, string> = {
		sage: 'bg-accent text-accent-foreground hover:bg-accent/80',
		slate: 'bg-muted text-muted-foreground hover:bg-muted/80',
		amber:
			'border-amber-500/30 bg-amber-500/10 text-amber-700 hover:bg-amber-500/20 dark:text-amber-300'
	};

	$: tone = toneFor(kind, tierMismatch);
	$: icon = iconFor(kind);
	$: description = descriptionFor(kind);
	$: toneClass = TONE_CLASS[tone];
</script>

<button
	type="button"
	class="inline-flex cursor-pointer items-center gap-1 rounded-full border border-transparent px-2 py-0.5 text-[11px] font-medium leading-snug transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring {toneClass}"
	aria-label="{kind}: {summary}"
	title={description}
	on:click={onTap}
>
	<span class="text-[11px]" aria-hidden="true">{icon}</span>
	<span>{summary}</span>
</button>
