import { describe, expect, it } from 'vitest';
import {
	MATTER_NAME_MAX_LENGTH,
	validateMetadata,
	validateName,
	validateNewMatter,
	validateTierFloor,
	type MatterValidationFields
} from './matter';

function fields(overrides: Partial<MatterValidationFields> = {}): MatterValidationFields {
	return {
		name: 'Acme NDA Review',
		description: '',
		privileged: false,
		minimum_inference_tier: null,
		...overrides
	};
}

describe('validateName', () => {
	it('accepts a normal name', () => {
		expect(validateName('Acme NDA Review')).toBeNull();
	});

	it('rejects an empty name', () => {
		expect(validateName('')).toBe('Matter name is required.');
	});

	it('rejects a whitespace-only name', () => {
		expect(validateName('   ')).toBe('Matter name is required.');
	});

	it('accepts a name at exactly the max length', () => {
		expect(validateName('A'.repeat(MATTER_NAME_MAX_LENGTH))).toBeNull();
	});

	it('rejects a name one character over the max length', () => {
		const error = validateName('A'.repeat(MATTER_NAME_MAX_LENGTH + 1));
		expect(error).toMatch(/200/);
	});

	it('measures length AFTER trimming (trailing space does not count)', () => {
		expect(validateName(`${'A'.repeat(MATTER_NAME_MAX_LENGTH)}   `)).toBeNull();
	});
});

describe('validateTierFloor', () => {
	it('requires a tier when privileged and none is set', () => {
		expect(validateTierFloor(true, null, 'required')).toBe('required');
	});

	it('passes when privileged and a tier is set', () => {
		expect(validateTierFloor(true, 3, 'required')).toBeNull();
	});

	it('passes when not privileged (no tier needed)', () => {
		expect(validateTierFloor(false, null, 'required')).toBeNull();
	});

	it('passes when not privileged even if a tier is set', () => {
		expect(validateTierFloor(false, 2, 'required')).toBeNull();
	});
});

describe('validateNewMatter', () => {
	it('passes a plain valid matter', () => {
		const result = validateNewMatter(fields());
		expect(result.valid).toBe(true);
		expect(result.nameError).toBeNull();
		expect(result.tierError).toBeNull();
	});

	it('rejects an empty name', () => {
		const result = validateNewMatter(fields({ name: '' }));
		expect(result.valid).toBe(false);
		expect(result.nameError).toBeTruthy();
	});

	it('rejects a name that is whitespace only', () => {
		const result = validateNewMatter(fields({ name: '   ' }));
		expect(result.valid).toBe(false);
		expect(result.nameError).toBeTruthy();
	});

	it('rejects a name longer than 200 characters', () => {
		const result = validateNewMatter(fields({ name: 'A'.repeat(201) }));
		expect(result.valid).toBe(false);
		expect(result.nameError).toMatch(/200/);
	});

	it('requires tier floor when privileged=true and no tier is set', () => {
		const result = validateNewMatter(fields({ privileged: true, minimum_inference_tier: null }));
		expect(result.valid).toBe(false);
		expect(result.tierError).toBeTruthy();
		expect(result.tierError).toMatch(/privileged/i);
	});

	it('passes when privileged=true and a tier floor is provided', () => {
		const result = validateNewMatter(fields({ privileged: true, minimum_inference_tier: 3 }));
		expect(result.valid).toBe(true);
		expect(result.tierError).toBeNull();
	});

	it('does not require tier floor when privileged=false', () => {
		const result = validateNewMatter(fields({ privileged: false, minimum_inference_tier: null }));
		expect(result.valid).toBe(true);
		expect(result.tierError).toBeNull();
	});

	it('uses the create-flow tier copy (references the PRD)', () => {
		const result = validateNewMatter(fields({ privileged: true, minimum_inference_tier: null }));
		expect(result.tierError).toBe(
			'Privileged matters require a minimum tier floor — see PRD §5.x for why.'
		);
	});
});

describe('validateMetadata', () => {
	it('passes a plain valid matter', () => {
		const result = validateMetadata(fields());
		expect(result.valid).toBe(true);
		expect(result.nameError).toBeNull();
		expect(result.tierError).toBeNull();
	});

	it('rejects an empty name with the same copy as the create flow', () => {
		const result = validateMetadata(fields({ name: '' }));
		expect(result.valid).toBe(false);
		expect(result.nameError).toBe('Matter name is required.');
	});

	it('requires tier floor when privileged=true and no tier is set', () => {
		const result = validateMetadata(fields({ privileged: true, minimum_inference_tier: null }));
		expect(result.valid).toBe(false);
		expect(result.tierError).toMatch(/privileged/i);
	});

	it('passes when privileged=true and a tier floor is provided', () => {
		const result = validateMetadata(fields({ privileged: true, minimum_inference_tier: 5 }));
		expect(result.valid).toBe(true);
		expect(result.tierError).toBeNull();
	});

	it('uses the terser tier copy (no PRD reference) — diverges from the create flow', () => {
		const result = validateMetadata(fields({ privileged: true, minimum_inference_tier: null }));
		expect(result.tierError).toBe('Privileged matters require a minimum tier floor.');
		expect(result.tierError).not.toMatch(/PRD/);
	});
});
