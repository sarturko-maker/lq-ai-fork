/**
 * Shared slug/kebab utilities for the LQ.AI skill surfaces.
 *
 * Extracted from CaptureSkillModal.svelte and SkillWizard.svelte (Polish
 * POL-002) so the implementation lives in one place. Both components import
 * from here; the module has no Svelte dependency and can be exercised in
 * Vitest without @testing-library/svelte.
 */

/**
 * Convert a display-name string to a kebab-case slug suitable for the
 * LQ.AI backend's `slug` field:
 *
 *   - Lowercases.
 *   - Collapses any run of non-[a-z0-9] characters to a single dash.
 *   - Trims leading and trailing dashes.
 *   - Caps at 80 characters (backend ``UserSkillCreate.slug`` max).
 *
 * Examples:
 *   kebab("NDA Review")      → "nda-review"
 *   kebab("  Foo & Bar  ")   → "foo-bar"
 *   kebab("Already-kebab")   → "already-kebab"
 */
export function kebab(s: string): string {
	return s
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-+|-+$/g, '')
		.slice(0, 80);
}
