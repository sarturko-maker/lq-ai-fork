/**
 * Tab → Lucide glyph map (UX-A). One source of truth for the icons that
 * represent each tool surface, so the cockpit header Tools menu, the legacy
 * `TopTabBar`, and (UX-A-2) the cockpit rail's Tools section all render the
 * same glyphs — replacing the emoji placeholders that predate the F013 look.
 *
 * Presentation only. Unknown ids fall back to a generic glyph.
 */
import type { Component } from 'svelte';

import BotIcon from '@lucide/svelte/icons/bot';
import BookmarkIcon from '@lucide/svelte/icons/bookmark';
import ClipboardListIcon from '@lucide/svelte/icons/clipboard-list';
import FolderIcon from '@lucide/svelte/icons/folder';
import GraduationCapIcon from '@lucide/svelte/icons/graduation-cap';
import HomeIcon from '@lucide/svelte/icons/home';
import LibraryIcon from '@lucide/svelte/icons/library';
import MessageSquareIcon from '@lucide/svelte/icons/message-square';
import PencilRulerIcon from '@lucide/svelte/icons/pencil-ruler';
import ScaleIcon from '@lucide/svelte/icons/scale';
import ShieldIcon from '@lucide/svelte/icons/shield';
import Table2Icon from '@lucide/svelte/icons/table-2';

import type { TabId } from '$lib/lq-ai/tabs';

const TAB_ICON: Partial<Record<TabId, Component>> = {
	home: HomeIcon,
	agents: ScaleIcon,
	chats: MessageSquareIcon,
	matters: FolderIcon,
	skills: PencilRulerIcon,
	knowledge: LibraryIcon,
	playbooks: ClipboardListIcon,
	tabular: Table2Icon,
	'saved-prompts': BookmarkIcon,
	learn: GraduationCapIcon,
	autonomous: BotIcon,
	admin: ShieldIcon
};

/** The Lucide glyph for a tab id (generic folder fallback for unknown ids). */
export function tabIcon(id: TabId): Component {
	return TAB_ICON[id] ?? FolderIcon;
}
