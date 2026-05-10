/**
 * GET /api/v1/models — model availability for the LQ.AI shell's picker (D0).
 *
 * The backend proxies the gateway's merged-discovery payload (aliases +
 * Ollama tags + Anthropic catalog). The shape is single-sourced in
 * `docs/api/gateway-openapi.yaml` and `docs/api/backend-openapi.yaml`.
 */
import { apiRequest } from './client';

/**
 * One row of `GET /api/v1/models`.
 *
 * `id` is either an alias (`"smart"`) or a raw provider/model form
 * (`"anthropic-prod/claude-haiku-4-5"`). Either form is sendable
 * verbatim as `MessageCreate.model` per D0 — the gateway's router
 * resolves both.
 */
export interface ModelEntry {
	id: string;
	object: 'model';
	created: number;
	owned_by: string;
	lq_ai_kind: 'alias' | 'provider_native';
	/** Tier 1-5 the request would land at; omitted on aliases. */
	routed_inference_tier?: 1 | 2 | 3 | 4 | 5;
	/** Provider type (`anthropic`, `ollama`, ...) for grouping. */
	provider_type?: string;
	/**
	 * ADR 0011: for aliases, the resolved `<provider>/<model>` form of
	 * the primary target. Lets the picker render "smart →
	 * anthropic-prod/claude-opus-4-7" so aliases are convenience, not
	 * opacity. Omitted on provider-native rows.
	 */
	lq_ai_resolves_to?: string;
	/** Number of fallback entries past the primary (alias only). */
	lq_ai_fallback_count?: number;
}

export interface ModelListResponse {
	object: 'list';
	data: ModelEntry[];
}

/**
 * Grouped view consumed by the picker. Aliases first; native rows
 * grouped by provider name (alphabetical for stable ordering across
 * sessions).
 */
export interface GroupedModels {
	aliases: ModelEntry[];
	/** Map of `<provider_name> -> entries` keyed by `owned_by`. */
	nativeByProvider: Map<string, ModelEntry[]>;
}

/** Fetch the merged model list. */
export async function listModels(): Promise<ModelListResponse> {
	return apiRequest<ModelListResponse>('/models');
}

/**
 * Group a flat model list into `{aliases, nativeByProvider}` for the
 * picker UI. Stable ordering: aliases preserve API order; native
 * groups sort by provider name; entries within a native group sort by id.
 */
export function groupModels(list: ModelListResponse): GroupedModels {
	const aliases: ModelEntry[] = [];
	const native = new Map<string, ModelEntry[]>();
	for (const entry of list.data) {
		if (entry.lq_ai_kind === 'alias') {
			aliases.push(entry);
			continue;
		}
		const bucket = native.get(entry.owned_by);
		if (bucket) {
			bucket.push(entry);
		} else {
			native.set(entry.owned_by, [entry]);
		}
	}
	// Stable per-group sort.
	for (const entries of native.values()) {
		entries.sort((a, b) => a.id.localeCompare(b.id));
	}
	// Stable per-provider sort.
	const sorted = new Map<string, ModelEntry[]>(
		[...native.entries()].sort((a, b) => a[0].localeCompare(b[0]))
	);
	return { aliases, nativeByProvider: sorted };
}

/**
 * Pick a sensible default selection from a grouped list.
 *
 * Priority: `smart` alias if present → first alias → first native row →
 * `null` if nothing is configured (the picker renders an empty state).
 */
export function defaultSelection(grouped: GroupedModels): ModelEntry | null {
	const smart = grouped.aliases.find((a) => a.id === 'smart');
	if (smart) return smart;
	if (grouped.aliases.length > 0) return grouped.aliases[0];
	for (const entries of grouped.nativeByProvider.values()) {
		if (entries.length > 0) return entries[0];
	}
	return null;
}
