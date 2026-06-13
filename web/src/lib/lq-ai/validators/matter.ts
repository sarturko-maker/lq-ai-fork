/**
 * Matter form validation — shared, framework-free logic.
 *
 * Extracted from NewMatterModal.svelte / MatterRailMetadata.svelte (R0) so the
 * cockpit quick-create dialog and the matter rail can import the rules without
 * pulling a legacy `.svelte` module through the build graph.
 *
 * Two flows validate the same fields with the SAME truth table but DIFFERENT
 * tier-floor copy, so they stay as two thin wrappers over shared helpers — never
 * collapsed into one context-flagged function (their messages are allowed to
 * diverge, and conflating them would couple the two surfaces).
 */

export type TierFloor = 1 | 2 | 3 | 4 | 5;

/** The fields every matter form validates. */
export interface MatterValidationFields {
	name: string;
	description: string;
	privileged: boolean;
	minimum_inference_tier: TierFloor | null;
}

/** Per-field errors plus an aggregate validity flag. `null` error = that field is fine. */
export interface MatterValidationResult {
	valid: boolean;
	nameError: string | null;
	tierError: string | null;
}

/** Matter names are trimmed and capped to match the server + the inputs' `maxlength`. */
export const MATTER_NAME_MAX_LENGTH = 200;

const NEW_MATTER_TIER_MESSAGE =
	'Privileged matters require a minimum tier floor — see PRD §5.x for why.';
const METADATA_TIER_MESSAGE = 'Privileged matters require a minimum tier floor.';

/** Required, trimmed, ≤ {@link MATTER_NAME_MAX_LENGTH}. Returns the error string or `null`. */
export function validateName(name: string): string | null {
	const trimmed = name.trim();
	if (!trimmed) {
		return 'Matter name is required.';
	}
	if (trimmed.length > MATTER_NAME_MAX_LENGTH) {
		return `Matter name must be ${MATTER_NAME_MAX_LENGTH} characters or fewer.`;
	}
	return null;
}

/**
 * A privileged matter must pin a tier floor; an unprivileged one never can
 * (the field is hidden, so `null` is expected). The required-message differs
 * per surface, so the caller supplies it.
 */
export function validateTierFloor(
	privileged: boolean,
	tier: TierFloor | null,
	privilegedRequiresTierMessage: string
): string | null {
	if (privileged && tier === null) {
		return privilegedRequiresTierMessage;
	}
	return null;
}

/** Create-matter rules (Matters-page modal + cockpit quick-create). */
export function validateNewMatter(fields: MatterValidationFields): MatterValidationResult {
	const nameError = validateName(fields.name);
	const tierError = validateTierFloor(
		fields.privileged,
		fields.minimum_inference_tier,
		NEW_MATTER_TIER_MESSAGE
	);
	return { valid: nameError === null && tierError === null, nameError, tierError };
}

/** Edit-metadata rules (matter rail). Same truth table, terser tier copy. */
export function validateMetadata(fields: MatterValidationFields): MatterValidationResult {
	const nameError = validateName(fields.name);
	const tierError = validateTierFloor(
		fields.privileged,
		fields.minimum_inference_tier,
		METADATA_TIER_MESSAGE
	);
	return { valid: nameError === null && tierError === null, nameError, tierError };
}
