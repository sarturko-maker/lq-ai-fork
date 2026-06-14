import { describe, it, expect } from 'vitest';
import { normalizeLang, SUPPORTED_LANGS } from '../shiki';

describe('normalizeLang', () => {
	it('returns text for empty / nullish input', () => {
		expect(normalizeLang(null)).toBe('text');
		expect(normalizeLang(undefined)).toBe('text');
		expect(normalizeLang('')).toBe('text');
		expect(normalizeLang('   ')).toBe('text');
	});

	it('passes through every supported language', () => {
		for (const lang of SUPPORTED_LANGS) {
			expect(normalizeLang(lang)).toBe(lang);
		}
	});

	it('is case- and whitespace-insensitive', () => {
		expect(normalizeLang('Python')).toBe('python');
		expect(normalizeLang('  TypeScript  ')).toBe('typescript');
		expect(normalizeLang('JSON')).toBe('json');
	});

	it('resolves common aliases to a loaded grammar', () => {
		expect(normalizeLang('sh')).toBe('bash');
		expect(normalizeLang('shell')).toBe('bash');
		expect(normalizeLang('js')).toBe('javascript');
		expect(normalizeLang('ts')).toBe('typescript');
		expect(normalizeLang('py')).toBe('python');
		expect(normalizeLang('yml')).toBe('yaml');
		expect(normalizeLang('postgres')).toBe('sql');
		expect(normalizeLang('golang')).toBe('go');
	});

	it('falls back to text for unknown languages (never throws)', () => {
		expect(normalizeLang('cobol')).toBe('text');
		expect(normalizeLang('brainfuck')).toBe('text');
		expect(normalizeLang('text')).toBe('text');
		expect(normalizeLang('plaintext')).toBe('text');
	});
});
