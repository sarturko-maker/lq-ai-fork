/**
 * Unit tests for the pure helpers exported from CapabilitiesPanel's `<script module>`
 * (ADR-F054). No DOM / no @testing-library/svelte — the helpers are computational and
 * carry the panel's logic (locked rows, section summaries, optimistic toggle, PUT body).
 */
import { describe, expect, it } from 'vitest';
import {
	applyOptimisticToggle,
	emptyCaption,
	entryId,
	isLocked,
	sectionSummary,
	togglePayload
} from '../components/matter/CapabilitiesPanel.svelte';
import type {
	CapabilityEntry,
	CapabilityInventory,
	CapabilitySection
} from '../types';

function entry(over: Partial<CapabilityEntry> = {}): CapabilityEntry {
	return {
		capability_kind: 'tool',
		capability_key: 'redlining',
		label: 'Redlining',
		description: 'Redline contracts.',
		available: true,
		enabled: true,
		default_enabled: true,
		toggleable: true,
		...over
	};
}

function section(kind: CapabilitySection['kind'], entries: CapabilityEntry[]): CapabilitySection {
	return { kind, label: kind, entries };
}

const MCP_ENTRY = entry({
	capability_kind: 'mcp',
	capability_key: 'mcp',
	label: 'MCP servers',
	available: false,
	enabled: false,
	default_enabled: false,
	toggleable: false
});

describe('isLocked', () => {
	it('locks unavailable or non-toggleable entries (MCP)', () => {
		expect(isLocked(MCP_ENTRY)).toBe(true);
		expect(isLocked(entry({ available: false }))).toBe(true);
		expect(isLocked(entry({ toggleable: false }))).toBe(true);
	});
	it('does not lock an available, toggleable entry', () => {
		expect(isLocked(entry())).toBe(false);
	});
});

describe('sectionSummary', () => {
	it('counts on/total over toggleable entries', () => {
		const s = section('tool', [entry({ enabled: true }), entry({ capability_key: 'x', enabled: false })]);
		expect(sectionSummary(s)).toBe('1 of 2 on');
	});
	it('is empty when there are no toggleable entries (MCP-only / empty)', () => {
		expect(sectionSummary(section('mcp', [MCP_ENTRY]))).toBe('');
		expect(sectionSummary(section('skill', []))).toBe('');
	});
});

describe('emptyCaption', () => {
	it('always captions the MCP section coming-soon', () => {
		expect(emptyCaption(section('mcp', [MCP_ENTRY]))).toMatch(/coming soon/i);
	});
	it('captions an empty area section per kind', () => {
		expect(emptyCaption(section('playbook', []))).toMatch(/no playbooks/i);
		expect(emptyCaption(section('skill', []))).toMatch(/no skills/i);
		expect(emptyCaption(section('tool', []))).toMatch(/no tools/i);
		expect(emptyCaption(section('knowledge', []))).toMatch(/no knowledge collections/i);
	});
	it('returns null for a populated non-mcp section', () => {
		expect(emptyCaption(section('tool', [entry()]))).toBeNull();
	});
});

describe('togglePayload', () => {
	it('builds a single-toggle PUT body', () => {
		expect(togglePayload(entry({ capability_kind: 'skill', capability_key: 'nda' }), false)).toEqual([
			{ kind: 'skill', key: 'nda', enabled: false }
		]);
	});
});

describe('entryId', () => {
	it('is kind:key', () => {
		expect(entryId(entry({ capability_kind: 'playbook', capability_key: 'abc' }))).toBe(
			'playbook:abc'
		);
	});
});

describe('applyOptimisticToggle', () => {
	function inv(): CapabilityInventory {
		return {
			practice_area_key: 'commercial',
			unit_label: 'Matter',
			sections: [
				section('tool', [
					entry({ capability_key: 'redlining', enabled: true }),
					entry({ capability_key: 'other', enabled: true })
				]),
				section('mcp', [MCP_ENTRY])
			]
		};
	}

	it('flips only the targeted entry', () => {
		const target = entry({ capability_key: 'redlining' });
		const next = applyOptimisticToggle(inv(), target, false);
		const tools = next.sections[0].entries;
		expect(tools.find((e) => e.capability_key === 'redlining')!.enabled).toBe(false);
		expect(tools.find((e) => e.capability_key === 'other')!.enabled).toBe(true);
	});

	it('never mutates a locked (MCP) entry', () => {
		const next = applyOptimisticToggle(inv(), MCP_ENTRY, true);
		expect(next.sections[1].entries[0].enabled).toBe(false);
	});

	it('returns a new object (does not mutate the input)', () => {
		const original = inv();
		const next = applyOptimisticToggle(original, entry({ capability_key: 'redlining' }), false);
		expect(next).not.toBe(original);
		expect(original.sections[0].entries[0].enabled).toBe(true); // input untouched
	});
});
