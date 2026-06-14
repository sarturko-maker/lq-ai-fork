/**
 * `buildMessageSources` — collapse a message's flat citation rows into the
 * distinct source documents they reference, for the AI Elements "Sources"
 * card (AE3, ADR-F011): a collapsible "Used N sources" summary beneath an
 * assistant message.
 *
 * The M2 Citation Engine persists one row per cited passage; a single
 * document is typically cited several times. This groups by `source_file_id`
 * (preserving first-seen order so the list is stable across re-fetches) and
 * rolls each document up to: a human-readable label, the cited pages, a
 * representative quote, and the MOST CAUTIONARY verification state across its
 * passages — so one unverified passage flags the whole source for a reviewer.
 *
 * Pure + DOM-free so it unit-tests in the node vitest env. Display strings are
 * model/document output — the consumer escapes them (never `{@html}`).
 */
import type { Citation } from '../types';
import { citationRenderState, type CitationRenderState } from './state';
import { previewQuote } from './format';

export interface MessageSource {
	/** Stable key + group identity — the source document id. */
	sourceFileId: string;
	/** Human-readable label: the joined filename, else an ordinal fallback. */
	label: string;
	/** How many cited passages reference this document. */
	passageCount: number;
	/** Sorted distinct page numbers cited (empty when unknown). */
	pages: number[];
	/** A representative cited quote (first passage), truncated for display. */
	quotePreview: string;
	/** The most cautionary render state across this document's passages. */
	state: CitationRenderState;
}

// Precedence: lower rank = more confident. The card surfaces the WORST (highest
// rank) state across a document's passages.
const STATE_RANK: Record<CitationRenderState, number> = {
	'verified-exact': 0,
	'verified-tolerant': 1,
	'verified-paraphrase': 2,
	unverified: 3
};

export function buildMessageSources(citations: Citation[]): MessageSource[] {
	const order: string[] = [];
	const byFile = new Map<string, Citation[]>();
	for (const c of citations) {
		let group = byFile.get(c.source_file_id);
		if (!group) {
			group = [];
			byFile.set(c.source_file_id, group);
			order.push(c.source_file_id);
		}
		group.push(c);
	}

	return order.map((fileId, i) => {
		const group = byFile.get(fileId) ?? [];
		const filename = group.find((c) => c.source_filename)?.source_filename ?? null;
		const pages = Array.from(
			new Set(group.map((c) => c.source_page).filter((p): p is number => p != null))
		).sort((a, b) => a - b);
		const state = group
			.map((c) => citationRenderState(c))
			.reduce<CitationRenderState>(
				(worst, s) => (STATE_RANK[s] > STATE_RANK[worst] ? s : worst),
				'verified-exact'
			);
		return {
			sourceFileId: fileId,
			label: filename ?? `Source ${i + 1}`,
			passageCount: group.length,
			pages,
			quotePreview: previewQuote(group[0]?.source_text ?? '', 120),
			state
		};
	});
}
