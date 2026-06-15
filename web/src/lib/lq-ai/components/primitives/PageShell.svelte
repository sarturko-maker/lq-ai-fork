<!--
	PageShell — the calm centered page container (F2-M1, ADR-F012).

	Extracts the `mx-auto w-full max-w-* px-* py-*` idiom repeated verbatim
	across the cockpit surfaces (AreaGrid / MattersPanel / ConversationHost)
	into one primitive, so the scira-style whitespace + max-width are set in
	ONE place and stay consistent as F2 calms each surface. Presentation only;
	semantic tokens / Tailwind scale only — no new token scale (ADR-F012).

	`size` picks the reading-width cap; `class` is appended for additive needs.
	The default padding matches the cockpit landing idiom (`px-6 py-10 sm:px-8`);
	a later slice can add a `pad` variant if a consumer needs a different rhythm
	(don't speculate one here — M1 proves the primitive on AreaGrid only).
-->
<script module lang="ts">
	export type PageShellSize = 'narrow' | 'default' | 'wide';

	const WIDTH: Record<PageShellSize, string> = {
		narrow: 'max-w-3xl',
		default: 'max-w-4xl',
		wide: 'max-w-5xl'
	};

	/** The full container class string for a given width (+ optional extra). */
	export function pageShellClass(size: PageShellSize, extra = ''): string {
		const base = `mx-auto w-full ${WIDTH[size]} px-6 py-10 sm:px-8`;
		return extra.trim() ? `${base} ${extra.trim()}` : base;
	}
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		size = 'default',
		class: klass = '',
		children,
		...rest
	}: {
		size?: PageShellSize;
		class?: string;
		children: Snippet;
	} & HTMLAttributes<HTMLDivElement> = $props();
</script>

<div class={pageShellClass(size, klass)} {...rest}>
	{@render children()}
</div>
