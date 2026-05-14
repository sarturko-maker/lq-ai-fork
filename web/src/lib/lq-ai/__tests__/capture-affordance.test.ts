import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	CAPTURE_AFFORDANCE_STORAGE_KEY,
	captureAffordanceInline,
	readCaptureAffordanceInline,
	writeCaptureAffordanceInline
} from '../preferences/capture-affordance';

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

describe('captureAffordanceInline preference (Wave D.2 §7.1)', () => {
	it('exposes the documented storage key', () => {
		expect(CAPTURE_AFFORDANCE_STORAGE_KEY).toBe('lq_ai_capture_affordance_inline');
	});

	it('readCaptureAffordanceInline returns true when unset (default)', () => {
		expect(readCaptureAffordanceInline()).toBe(true);
	});

	it('readCaptureAffordanceInline returns false after writeCaptureAffordanceInline(false)', () => {
		writeCaptureAffordanceInline(false);
		expect(mockStorage[CAPTURE_AFFORDANCE_STORAGE_KEY]).toBe('false');
		expect(readCaptureAffordanceInline()).toBe(false);
	});

	it('readCaptureAffordanceInline returns true after writeCaptureAffordanceInline(true)', () => {
		writeCaptureAffordanceInline(false);
		writeCaptureAffordanceInline(true);
		expect(mockStorage[CAPTURE_AFFORDANCE_STORAGE_KEY]).toBe('true');
		expect(readCaptureAffordanceInline()).toBe(true);
	});

	it('returns true (default) for unexpected stored values', () => {
		// Strict parser: anything other than the canonical 'true' / 'false'
		// strings falls back to the documented default (true).
		mockStorage[CAPTURE_AFFORDANCE_STORAGE_KEY] = 'maybe';
		expect(readCaptureAffordanceInline()).toBe(true);
	});

	it('captureAffordanceInline.setValue(true) broadcasts to a fresh subscriber', () => {
		captureAffordanceInline.setValue(true);
		let received: boolean | undefined;
		const unsub = captureAffordanceInline.subscribe((v) => {
			received = v;
		});
		expect(received).toBe(true);
		unsub();
	});

	it('captureAffordanceInline.setValue(false) is observed by an existing subscriber', () => {
		const observed: boolean[] = [];
		const unsub = captureAffordanceInline.subscribe((v) => {
			observed.push(v);
		});
		captureAffordanceInline.setValue(false);
		captureAffordanceInline.setValue(true);
		// First entry is whatever the store held when subscribe() ran; the
		// last two entries should reflect the explicit setValue calls.
		expect(observed.slice(-2)).toEqual([false, true]);
		unsub();
	});

	it('captureAffordanceInline.load() picks up an out-of-band localStorage change', () => {
		mockStorage[CAPTURE_AFFORDANCE_STORAGE_KEY] = 'false';
		captureAffordanceInline.load();
		let received: boolean | undefined;
		const unsub = captureAffordanceInline.subscribe((v) => {
			received = v;
		});
		expect(received).toBe(false);
		unsub();
	});
});
