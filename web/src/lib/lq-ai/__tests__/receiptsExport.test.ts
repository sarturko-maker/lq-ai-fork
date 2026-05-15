import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { triggerJsonlDownload, isValidJsonl } from '../lib/receiptsExport';

describe('triggerJsonlDownload', () => {
  const originalDocument = (globalThis as any).document;
  const originalURL = (globalThis as any).URL;

  let appendChildSpy: ReturnType<typeof vi.fn>;
  let removeChildSpy: ReturnType<typeof vi.fn>;
  let createElementSpy: ReturnType<typeof vi.fn>;
  let createObjectURLSpy: ReturnType<typeof vi.fn>;
  let revokeObjectURLSpy: ReturnType<typeof vi.fn>;
  let clickSpy: ReturnType<typeof vi.fn>;
  let fakeAnchor: any;

  beforeEach(() => {
    clickSpy = vi.fn();
    fakeAnchor = {
      href: '', download: '', style: { display: '' },
      click: clickSpy,
    };
    appendChildSpy = vi.fn();
    removeChildSpy = vi.fn();
    createElementSpy = vi.fn((tag: string) => {
      if (tag === 'a') return fakeAnchor;
      return {} as any;
    });
    createObjectURLSpy = vi.fn(() => 'blob:fake');
    revokeObjectURLSpy = vi.fn();

    (globalThis as any).document = {
      createElement: createElementSpy,
      body: { appendChild: appendChildSpy, removeChild: removeChildSpy },
    };
    (globalThis as any).URL = {
      createObjectURL: createObjectURLSpy,
      revokeObjectURL: revokeObjectURLSpy,
    };
    // Blob is provided by node's global; if not, provide a tiny shim.
    if (typeof (globalThis as any).Blob === 'undefined') {
      (globalThis as any).Blob = class { constructor(public parts: any[], public opts: any) {} };
    }
  });

  afterEach(() => {
    if (originalDocument === undefined) delete (globalThis as any).document;
    else (globalThis as any).document = originalDocument;
    if (originalURL === undefined) delete (globalThis as any).URL;
    else (globalThis as any).URL = originalURL;
  });

  it('creates a blob, appends anchor, clicks it, revokes URL', () => {
    triggerJsonlDownload('{"a":1}\n{"b":2}', 'chat-c1-receipts.jsonl');

    expect(createObjectURLSpy).toHaveBeenCalled();
    expect(createElementSpy).toHaveBeenCalledWith('a');
    expect(appendChildSpy).toHaveBeenCalledWith(fakeAnchor);
    expect(clickSpy).toHaveBeenCalled();
    expect(removeChildSpy).toHaveBeenCalledWith(fakeAnchor);
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:fake');
    expect(fakeAnchor.download).toBe('chat-c1-receipts.jsonl');
    expect(fakeAnchor.href).toBe('blob:fake');
  });
});

describe('isValidJsonl', () => {
  it('returns valid for well-formed JSONL', () => {
    const text = '{"a":1}\n{"b":2}\n{"c":3}';
    expect(isValidJsonl(text)).toEqual({ valid: true });
  });

  it('returns invalid for empty input', () => {
    expect(isValidJsonl('')).toEqual({ valid: false, error: expect.stringContaining('Empty') });
  });

  it('returns invalid pointing at the first bad line', () => {
    const text = '{"a":1}\nnot json\n{"c":3}';
    const r = isValidJsonl(text);
    expect(r.valid).toBe(false);
    expect(r.error).toMatch(/Line 2/);
  });
});
