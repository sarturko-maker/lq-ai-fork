/**
 * Sidebar grouping derived-store tests.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { get } from 'svelte/store';

import { chatsByProject, chatsStore, projectsStore } from '../stores';
import type { Chat, Project } from '../types';

function project(id: string, name: string, overrides: Partial<Project> = {}): Project {
	return {
		id,
		name,
		slug: name.toLowerCase().replace(/\s+/g, '-'),
		owner_id: 'u',
		privileged: false,
		created_at: '2025-01-01T00:00:00Z',
		updated_at: '2025-01-01T00:00:00Z',
		...overrides
	};
}

function chat(
	id: string,
	project_id: string | null,
	updated_at: string,
	archived_at: string | null = null
): Chat {
	return {
		id,
		title: `Chat ${id}`,
		owner_id: 'u',
		project_id,
		archived_at,
		created_at: updated_at,
		updated_at
	};
}

describe('chatsByProject', () => {
	beforeEach(() => {
		projectsStore.set([]);
		chatsStore.set([]);
	});

	it('groups chats under their project, newest-first within group', () => {
		projectsStore.set([project('p1', 'Acme'), project('p2', 'Beta')]);
		chatsStore.set([
			chat('c1', 'p1', '2025-01-01T00:00:00Z'),
			chat('c2', 'p1', '2025-01-02T00:00:00Z'),
			chat('c3', 'p2', '2025-01-01T00:00:00Z')
		]);

		const groups = get(chatsByProject);
		expect(groups).toHaveLength(2);
		expect(groups[0].project?.id).toBe('p1');
		expect(groups[0].chats.map((c) => c.id)).toEqual(['c2', 'c1']);
		expect(groups[1].project?.id).toBe('p2');
	});

	it('puts the no-project bucket last', () => {
		projectsStore.set([project('p1', 'Acme')]);
		chatsStore.set([
			chat('c1', null, '2025-01-01T00:00:00Z'),
			chat('c2', 'p1', '2025-01-02T00:00:00Z')
		]);

		const groups = get(chatsByProject);
		expect(groups).toHaveLength(2);
		expect(groups[0].project?.id).toBe('p1');
		expect(groups[1].project).toBeNull();
	});

	it('excludes archived chats from the active groups', () => {
		projectsStore.set([project('p1', 'Acme')]);
		chatsStore.set([
			chat('c1', 'p1', '2025-01-01T00:00:00Z', '2025-01-02T00:00:00Z'),
			chat('c2', 'p1', '2025-01-02T00:00:00Z')
		]);

		const groups = get(chatsByProject);
		expect(groups).toHaveLength(1);
		expect(groups[0].chats.map((c) => c.id)).toEqual(['c2']);
	});

	it('hides empty project groups (project with no chats)', () => {
		projectsStore.set([project('p1', 'Empty'), project('p2', 'Active')]);
		chatsStore.set([chat('c1', 'p2', '2025-01-01T00:00:00Z')]);
		const groups = get(chatsByProject);
		expect(groups).toHaveLength(1);
		expect(groups[0].project?.id).toBe('p2');
	});
});
