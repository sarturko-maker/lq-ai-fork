import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	AUTO_ENHANCE_STORAGE_KEY,
	readAutoEnhance,
	writeAutoEnhance
} from '../preferences/autoEnhance';

let mockStorage: Record<string, string> = {};
const localStorageMock = {
	getItem: (key: string) => mockStorage[key] ?? null,
	setItem: (key: string, val: string) => { mockStorage[key] = val; },
	removeItem: (key: string) => { delete mockStorage[key]; },
	clear: () => { mockStorage = {}; }
};

beforeEach(() => {
	mockStorage = {};
	vi.stubGlobal('localStorage', localStorageMock);
});
afterEach(() => {
	vi.unstubAllGlobals();
});

describe('autoEnhance preference (§7.1 Settings)', () => {
	it('exposes the documented storage key', () => {
		expect(AUTO_ENHANCE_STORAGE_KEY).toBe('lq_ai_composer_auto_enhance');
	});

	it('readAutoEnhance returns false when unset', () => {
		expect(readAutoEnhance()).toBe(false);
	});

	it('round-trips true', () => {
		writeAutoEnhance(true);
		expect(mockStorage[AUTO_ENHANCE_STORAGE_KEY]).toBe('true');
		expect(readAutoEnhance()).toBe(true);
	});

	it('round-trips false (explicit)', () => {
		writeAutoEnhance(true);
		writeAutoEnhance(false);
		expect(mockStorage[AUTO_ENHANCE_STORAGE_KEY]).toBe('false');
		expect(readAutoEnhance()).toBe(false);
	});

	it('returns false for unexpected values', () => {
		mockStorage[AUTO_ENHANCE_STORAGE_KEY] = 'maybe';
		expect(readAutoEnhance()).toBe(false);
	});
});
