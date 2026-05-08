/**
 * Unit tests for the minimal `inputs:` parser used by `getSkill`.
 *
 * The parser is intentionally a YAML *subset*; these tests pin the shape of
 * the M1 starter-skill corpus's `inputs` blocks and ensure the form-driver
 * gets the right type discriminators.
 */
import { describe, it, expect } from 'vitest';

import { parseInputsFromYaml } from '../api/skills';

describe('parseInputsFromYaml', () => {
	it('returns [] when there is no inputs block', () => {
		expect(parseInputsFromYaml('name: foo\ntitle: bar')).toEqual([]);
	});

	it('parses a single string input', () => {
		const out = parseInputsFromYaml(`
inputs:
  - name: matter_name
    type: string
    required: true
    description: The matter being reviewed
`);
		expect(out).toHaveLength(1);
		expect(out[0]).toMatchObject({
			name: 'matter_name',
			type: 'string',
			required: true,
			description: 'The matter being reviewed'
		});
	});

	it('parses an enum input with flow-list options', () => {
		const out = parseInputsFromYaml(`
inputs:
  - name: perspective
    type: enum
    enum: [recipient, discloser, both]
    required: true
`);
		expect(out[0]).toMatchObject({
			name: 'perspective',
			type: 'enum',
			required: true,
			enum: ['recipient', 'discloser', 'both']
		});
	});

	it('parses multiple inputs of mixed type', () => {
		const out = parseInputsFromYaml(`
inputs:
  - name: perspective
    type: enum
    enum: [recipient, discloser]
    required: true
    description: Whose side are we on
  - name: deal_type
    type: string
    default: vendor
  - name: aggressive_review
    type: boolean
    default: false
`);
		expect(out).toHaveLength(3);
		expect(out[0].name).toBe('perspective');
		expect(out[1].name).toBe('deal_type');
		expect(out[1].default).toBe('vendor');
		expect(out[2].type).toBe('boolean');
		expect(out[2].default).toBe(false);
	});

	it('stops at the next top-level key', () => {
		const out = parseInputsFromYaml(`
inputs:
  - name: a
    type: string
output_format: report
`);
		expect(out).toHaveLength(1);
		expect(out[0].name).toBe('a');
	});

	it('drops unknown type values gracefully (no crash)', () => {
		const out = parseInputsFromYaml(`
inputs:
  - name: weirdo
    type: object
`);
		expect(out).toHaveLength(1);
		expect(out[0].type).toBeUndefined();
	});
});
