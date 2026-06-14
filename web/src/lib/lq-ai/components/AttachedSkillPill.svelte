<script context="module" lang="ts">
	/**
	 * AttachedSkillPill — small pill rendered alongside the composer (and
	 * eventually inside message bubbles) to show that a skill is attached
	 * to the current turn. Tasks 3.3 (SlashPopover) and 7.1 (composer
	 * wiring) consume this.
	 *
	 * Convention notes for reviewers:
	 *   - Callback prop (onRemove), matching SkillPicker / AttachKBModal /
	 *     NewMatterModal — not createEventDispatcher.
	 *   - Pure helpers exported from <script context="module"> so vitest
	 *     can exercise them without @testing-library/svelte (which is not
	 *     installed; see AttachKBModal.test.ts header comment).
	 *   - Styling (R8): migrated off the legacy `--lq-*` palette onto the
	 *     shipped semantic tokens. The "secure / sage" wash is the cockpit
	 *     accent surface — `bg-accent` with `text-accent-foreground` ink
	 *     (NOT `text-primary`, which fails WCAG AA on the accent wash). No
	 *     `<style>` block — utility classes only.
	 */
	export interface AttachedSkill {
		slug: string;
		title: string;
		icon?: string | null;
	}

	/** A11y contract: aria-label on the remove button. */
	export function removeAriaLabel(title: string): string {
		return `Remove ${title}`;
	}

	/** Glyph to display when the skill omits a custom icon. */
	export function displayIcon(icon: string | null | undefined): string {
		return icon ? icon : '📜';
	}

	/**
	 * Invoke the onRemove callback with the skill's slug. Defensive: skips
	 * the call when the consumer didn't wire a handler (matches the
	 * default-no-op style used by SkillPicker.svelte).
	 */
	export function handleRemove(
		skill: AttachedSkill,
		onRemove: ((slug: string) => void) | undefined
	): void {
		if (!onRemove) return;
		onRemove(skill.slug);
	}
</script>

<script lang="ts">
	export let skill: AttachedSkill;
	export let onRemove: ((slug: string) => void) | undefined = undefined;

	$: icon = displayIcon(skill.icon);
	$: ariaLabel = removeAriaLabel(skill.title);
</script>

<span
	class="inline-flex items-center gap-1 rounded-full border border-border bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground"
	role="status"
>
	<span class="text-xs" aria-hidden="true">{icon}</span>
	<span class="whitespace-nowrap">{skill.title}</span>
	<button
		type="button"
		class="ml-0.5 rounded-sm px-0.5 leading-none opacity-60 transition-opacity hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
		aria-label={ariaLabel}
		on:click={() => handleRemove(skill, onRemove)}
	>×</button>
</span>
