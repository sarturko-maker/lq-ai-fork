/**
 * Unit tests for the AttachKBModal logic helpers.
 *
 * No @testing-library/svelte is available in this codebase (and CLAUDE.md
 * says don't add libraries without justification), so we test the outcome
 * mapping the same way NewMatterModal and ComingSoonModal do: the modal
 * exports its pure decision functions from <script context="module">, and
 * we exercise those here. The Svelte template itself is glue — it composes
 * these helpers and wires user input. Behavior coverage at the helper layer
 * gives us 7 deterministic assertions for the core surface: filter, sort
 * (3 keys), attached-split, CTA-label-counter, status roll-up.
 */
import { describe, expect, it } from 'vitest';
import {
  filterKBs,
  sortKBs,
  splitAttached,
  attachCtaLabel,
  kbDisplayStatus,
  JIT_BANNER_DISMISSED_KEY
} from '../components/AttachKBModal.svelte';
import type { KnowledgeBase } from '../types';

function makeKB(overrides: Partial<KnowledgeBase> = {}): KnowledgeBase {
  return {
    id: 'kb-default',
    name: 'Default KB',
    owner_id: 'u1',
    hybrid_alpha: 0.5,
    file_count: 1,
    chunk_count: 10,
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
    ...overrides
  };
}

const SAMPLE_KBS: KnowledgeBase[] = [
  makeKB({
    id: 'kb1',
    name: 'NDA-Playbook',
    file_count: 47,
    chunk_count: 940,
    ingestion_status: 'ready',
    updated_at: '2026-05-01T00:00:00Z'
  }),
  makeKB({
    id: 'kb2',
    name: 'M&A Templates',
    file_count: 23,
    chunk_count: 230,
    ingestion_status: 'processing',
    updated_at: '2026-05-10T00:00:00Z'
  }),
  makeKB({
    id: 'kb3',
    name: 'Lease KB',
    file_count: 12,
    chunk_count: 120,
    ingestion_status: 'ready',
    updated_at: '2026-04-20T00:00:00Z'
  })
];

describe('AttachKBModal helpers', () => {
  it('filterKBs is case-insensitive substring match on name', () => {
    expect(filterKBs(SAMPLE_KBS, '').map((k) => k.id)).toEqual([
      'kb1',
      'kb2',
      'kb3'
    ]);
    expect(filterKBs(SAMPLE_KBS, 'm&a').map((k) => k.id)).toEqual(['kb2']);
    // Case-insensitive
    expect(filterKBs(SAMPLE_KBS, 'NDA').map((k) => k.id)).toEqual(['kb1']);
    // No match
    expect(filterKBs(SAMPLE_KBS, 'zzz')).toEqual([]);
  });

  it('sortKBs alphabetical orders by name asc', () => {
    const sorted = sortKBs(SAMPLE_KBS, 'alphabetical');
    expect(sorted.map((k) => k.name)).toEqual([
      'Lease KB',
      'M&A Templates',
      'NDA-Playbook'
    ]);
  });

  it('sortKBs recent orders by updated_at desc', () => {
    const sorted = sortKBs(SAMPLE_KBS, 'recent');
    expect(sorted.map((k) => k.id)).toEqual(['kb2', 'kb1', 'kb3']);
  });

  it('sortKBs indexing_status surfaces ready first, indexing next', () => {
    const sorted = sortKBs(SAMPLE_KBS, 'indexing_status');
    // ready KBs (kb1, kb3) before indexing (kb2). Tie-break is alphabetical.
    expect(sorted.map((k) => k.id)).toEqual(['kb3', 'kb1', 'kb2']);
  });

  it('splitAttached partitions filtered KBs into attached + available', () => {
    const { attached, available } = splitAttached(SAMPLE_KBS, ['kb3']);
    expect(attached.map((k) => k.id)).toEqual(['kb3']);
    expect(available.map((k) => k.id)).toEqual(['kb1', 'kb2']);
  });

  it('attachCtaLabel reflects selection count (the "Attach N selected" CTA counter)', () => {
    expect(attachCtaLabel(0)).toBe('Attach knowledge bases');
    expect(attachCtaLabel(1)).toBe('Attach 1 selected');
    expect(attachCtaLabel(2)).toBe('Attach 2 selected');
    expect(attachCtaLabel(7)).toBe('Attach 7 selected');
  });

  it('kbDisplayStatus rolls up from ingestion_status with file_count fallback', () => {
    // Explicit ingestion_status wins
    expect(
      kbDisplayStatus(makeKB({ ingestion_status: 'ready', file_count: 0 }))
    ).toBe('ready');
    expect(
      kbDisplayStatus(makeKB({ ingestion_status: 'processing' }))
    ).toBe('indexing');
    expect(
      kbDisplayStatus(makeKB({ ingestion_status: 'failed' }))
    ).toBe('failed');

    // Fallback when ingestion_status is absent: file_count > 0 → ready
    expect(
      kbDisplayStatus(makeKB({ ingestion_status: undefined, file_count: 5 }))
    ).toBe('ready');
    expect(
      kbDisplayStatus(makeKB({ ingestion_status: undefined, file_count: 0 }))
    ).toBe('pending');

    // Banner key contract — guard against accidental renames
    expect(JIT_BANNER_DISMISSED_KEY).toBe('lq_ai_jit_kb_attach_seen');
  });
});
