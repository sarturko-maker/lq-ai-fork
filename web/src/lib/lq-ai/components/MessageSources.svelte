<!--
	MessageSources — AE3 (ADR-F011). The collapsible "Used N sources" summary
	beneath an assistant message, composed from the AI Elements **Sources** +
	**Inline Citation** identities over OUR M2 Citation Engine data.

	It groups the message's persisted citation rows by source document
	(`buildMessageSources`) and renders one entry per distinct document: a
	5-state verification marker (the M2-C2 legal contract — green verified /
	amber paraphrase / grey unverified, AA in light + dark), the document name,
	a passages·pages meta line, and a representative cited quote.

	Why a runes wrapper (mirrors AE2's MessageActionsBar): the legacy
	`MessageBubble` feeds it a plain `citations` prop; all rune state + the
	vendored AE components live here. Display strings are model/document output
	bound as TEXT (Svelte auto-escapes) — never `{@html}`.
-->
<script lang="ts">
	import { Sources, Source } from './ai-elements/sources/index.js';
	import {
		InlineCitationSource,
		InlineCitationQuote
	} from './ai-elements/inline-citation/index.js';
	import BadgeCheck from '@lucide/svelte/icons/badge-check';
	import CircleAlert from '@lucide/svelte/icons/circle-alert';
	import { buildMessageSources } from '$lib/lq-ai/citations/sources';
	import type { Citation } from '$lib/lq-ai/types';
	import type { CitationRenderState } from '$lib/lq-ai/citations/state';

	let { citations = [] }: { citations?: Citation[] } = $props();

	const sources = $derived(buildMessageSources(citations));

	// 5-state → marker. Colours match M2Citations' AA-tuned emerald/amber/grey
	// (verified-exact + verified-tolerant share the green; paraphrase/ensemble =
	// amber; unverified = grey) so the two surfaces read identically.
	const STATE_META: Record<
		CitationRenderState,
		{ color: string; label: string; verified: boolean }
	> = {
		'verified-exact': {
			color: 'text-emerald-700 dark:text-emerald-300',
			label: 'Verified',
			verified: true
		},
		'verified-tolerant': {
			color: 'text-emerald-700 dark:text-emerald-300',
			label: 'Verified',
			verified: true
		},
		'verified-paraphrase': {
			color: 'text-amber-700 dark:text-amber-300',
			label: 'Verified (paraphrase)',
			verified: true
		},
		unverified: {
			color: 'text-gray-500 dark:text-gray-400',
			label: 'Unverified',
			verified: false
		}
	};

	function metaLine(passageCount: number, pages: number[]): string {
		const passages = `${passageCount} ${passageCount === 1 ? 'passage' : 'passages'}`;
		if (pages.length === 0) return passages;
		const prefix = pages.length === 1 ? 'p.' : 'pp.';
		return `${passages} · ${prefix} ${pages.join(', ')}`;
	}
</script>

{#if sources.length > 0}
	<Sources count={sources.length}>
		{#each sources as s (s.sourceFileId)}
			<Source
				class="items-start rounded-md border border-border bg-card/40 p-2"
				data-testid="lq-ai-source"
				data-state={s.state}
			>
				<span
					class="mt-0.5 {STATE_META[s.state].color}"
					title={STATE_META[s.state].label}
					aria-label={STATE_META[s.state].label}
				>
					{#if STATE_META[s.state].verified}
						<BadgeCheck class="h-4 w-4 shrink-0" aria-hidden="true" />
					{:else}
						<CircleAlert class="h-4 w-4 shrink-0" aria-hidden="true" />
					{/if}
				</span>
				<div class="min-w-0 flex-1">
					<InlineCitationSource title={s.label} url={metaLine(s.passageCount, s.pages)} />
					{#if s.quotePreview}
						<InlineCitationQuote class="mt-1.5">{s.quotePreview}</InlineCitationQuote>
					{/if}
				</div>
			</Source>
		{/each}
	</Sources>
{/if}
