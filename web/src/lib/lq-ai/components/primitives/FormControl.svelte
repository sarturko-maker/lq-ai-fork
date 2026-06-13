<!--
	FormControl — label + control + (help|error) for a single form field (R1a).

	Stacks a `<label for={id}>`, the slotted control (`{@render children()}`),
	optional help text, and an error message with a stable `id={`${id}-error`}`
	so the control can point `aria-describedby` at it. The caller owns the
	control element (Input / Textarea / native select) and must give it the
	matching `id` and `aria-invalid={!!error}` — FormControl supplies the label
	association and the error node, not the input itself.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		id,
		label,
		required = false,
		optional = false,
		error = null,
		help = undefined,
		children
	}: {
		id: string;
		label: string;
		required?: boolean;
		optional?: boolean;
		error?: string | null;
		help?: string;
		children: Snippet;
	} = $props();
</script>

<div class="flex flex-col gap-1">
	<label class="text-[13px] font-medium text-foreground" for={id}>
		{label}
		{#if required}<span class="ml-0.5 text-destructive" aria-hidden="true">*</span>{/if}
		{#if optional}<span class="text-xs font-normal text-muted-foreground"> (optional)</span>{/if}
	</label>

	{@render children()}

	{#if help}
		<p class="text-xs text-muted-foreground">{help}</p>
	{/if}
	{#if error}
		<!-- `dark:text-red-300` keeps the inline error >=4.5:1 (AA) on the dark popover
		     surface; bare `text-destructive` is 4.15:1 in dark (R1a review regression fix). -->
		<p id={`${id}-error`} class="text-xs text-destructive dark:text-red-300" role="alert">
			{error}
		</p>
	{/if}
</div>
