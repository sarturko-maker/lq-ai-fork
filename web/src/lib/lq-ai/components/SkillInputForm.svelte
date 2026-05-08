<script lang="ts">
	/**
	 * Renders the inputs declared in a skill's frontmatter as a form.
	 *
	 * For each input:
	 * - `enum` → <select>.
	 * - `boolean` → <input type=checkbox>.
	 * - `integer` → <input type=number>.
	 * - else → <input type=text> (string).
	 *
	 * `required` inputs that the user leaves empty block submission.
	 */
	import type { SkillInputDef } from '../types';

	export let inputs: SkillInputDef[] = [];
	export let values: Record<string, unknown> = {};
	export let onChange: (next: Record<string, unknown>) => void = () => undefined;

	function update(name: string, value: unknown) {
		const next = { ...values, [name]: value };
		onChange(next);
	}

	export function validate(): { ok: boolean; missing: string[] } {
		const missing: string[] = [];
		for (const inp of inputs) {
			if (!inp.required) continue;
			const v = values[inp.name];
			if (v === undefined || v === null || v === '') {
				missing.push(inp.name);
			}
		}
		return { ok: missing.length === 0, missing };
	}
</script>

{#if inputs.length === 0}
	<p class="text-xs text-gray-500 italic">This skill has no required inputs.</p>
{:else}
	<form class="space-y-2" data-testid="lq-ai-skill-input-form">
		{#each inputs as inp (inp.name)}
			<div>
				<label
					for={`lq-ai-skill-input-${inp.name}`}
					class="block text-xs font-medium text-gray-700 dark:text-gray-300"
				>
					{inp.name}
					{#if inp.required}
						<span class="text-rose-600">*</span>
					{/if}
				</label>
				{#if inp.description}
					<p class="text-xs text-gray-500">{inp.description}</p>
				{/if}

				{#if inp.type === 'enum' && inp.enum}
					<select
						class="mt-1 block w-full text-sm border border-gray-300 rounded px-2 py-1 dark:bg-gray-800"
						value={values[inp.name] ?? inp.default ?? ''}
						on:change={(e) => update(inp.name, (e.target as HTMLSelectElement).value)}
						data-testid={`lq-ai-skill-input-${inp.name}`}
					>
						<option value="" disabled>— select —</option>
						{#each inp.enum as opt}
							<option value={opt}>{opt}</option>
						{/each}
					</select>
				{:else if inp.type === 'boolean'}
					<input
						type="checkbox"
						class="mt-1"
						checked={Boolean(values[inp.name] ?? inp.default ?? false)}
						on:change={(e) => update(inp.name, (e.target as HTMLInputElement).checked)}
						data-testid={`lq-ai-skill-input-${inp.name}`}
					/>
				{:else if inp.type === 'integer'}
					<input
						type="number"
						class="mt-1 block w-full text-sm border border-gray-300 rounded px-2 py-1 dark:bg-gray-800"
						value={values[inp.name] ?? inp.default ?? ''}
						on:input={(e) =>
							update(inp.name, parseInt((e.target as HTMLInputElement).value, 10))}
						data-testid={`lq-ai-skill-input-${inp.name}`}
					/>
				{:else}
					<input
						type="text"
						class="mt-1 block w-full text-sm border border-gray-300 rounded px-2 py-1 dark:bg-gray-800"
						value={String(values[inp.name] ?? inp.default ?? '')}
						on:input={(e) => update(inp.name, (e.target as HTMLInputElement).value)}
						data-testid={`lq-ai-skill-input-${inp.name}`}
					/>
				{/if}
			</div>
		{/each}
	</form>
{/if}
