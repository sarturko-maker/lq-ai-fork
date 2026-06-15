<!--
	PageShell — the calm centered page container (F2-M1, ADR-F012).

	Extracts the `mx-auto w-full max-w-* px-* py-*` idiom repeated verbatim
	across the cockpit surfaces (AreaGrid / MattersPanel / ConversationHost)
	into one primitive, so the scira-style whitespace + max-width are set in
	ONE place and stay consistent as F2 calms each surface. Presentation only;
	semantic tokens / Tailwind scale only — no new token scale (ADR-F012).

	`size` picks the reading-width cap; `pad` picks the padding rhythm; `class`
	is appended for additive needs. The `default` pad matches the cockpit landing
	idiom (`px-6 py-10 sm:px-8`); `compact` (`py-8`, the matters list) and `tight`
	(`px-4 py-4 sm:px-6`, the conversation column) were added in F2-M6 so those
	surfaces consolidate onto this primitive instead of repeating the inline idiom
	(don't override pad via `class` — Tailwind utility order makes a px/py
	passthrough unreliable; add a named variant here instead).
-->
<script module lang="ts">
	export type PageShellSize = 'narrow' | 'default' | 'wide';
	export type PageShellPad = 'default' | 'compact' | 'tight';

	const WIDTH: Record<PageShellSize, string> = {
		narrow: 'max-w-3xl',
		default: 'max-w-4xl',
		wide: 'max-w-5xl'
	};

	const PAD: Record<PageShellPad, string> = {
		default: 'px-6 py-10 sm:px-8',
		compact: 'px-6 py-8 sm:px-8',
		tight: 'px-4 py-4 sm:px-6'
	};

	/** The full container class string for a width + pad (+ optional extra). */
	export function pageShellClass(
		size: PageShellSize,
		pad: PageShellPad = 'default',
		extra = ''
	): string {
		const base = `mx-auto w-full ${WIDTH[size]} ${PAD[pad]}`;
		return extra.trim() ? `${base} ${extra.trim()}` : base;
	}
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		size = 'default',
		pad = 'default',
		class: klass = '',
		children,
		...rest
	}: {
		size?: PageShellSize;
		pad?: PageShellPad;
		class?: string;
		children: Snippet;
	} & HTMLAttributes<HTMLDivElement> = $props();
</script>

<div class={pageShellClass(size, pad, klass)} {...rest}>
	{@render children()}
</div>
