import { describe, expect, it } from 'vitest';
import { TABS, isTabVisible, isTabAvailable, activeTabFor, type TabId, type User } from '../tabs';

describe('tabs', () => {
  const adminUser: User = { id: '1', email: 'a@x.io', is_admin: true, must_change_password: false, role: 'admin' };
  const memberUser: User = { id: '2', email: 'm@x.io', is_admin: false, must_change_password: false, role: 'member' };

  it('defines six core tabs plus admin', () => {
    const ids = TABS.map((t) => t.id);
    expect(ids).toEqual(['home', 'chats', 'matters', 'skills', 'knowledge', 'saved-prompts', 'admin']);
  });

  it('hides admin tab for non-admin users', () => {
    expect(isTabVisible('admin', memberUser)).toBe(false);
    expect(isTabVisible('admin', adminUser)).toBe(true);
  });

  it('shows core tabs to all users', () => {
    for (const id of ['home', 'chats', 'matters', 'skills', 'knowledge', 'saved-prompts'] as TabId[]) {
      expect(isTabVisible(id, memberUser)).toBe(true);
      expect(isTabVisible(id, adminUser)).toBe(true);
    }
  });

  it('marks tabs whose routes are not yet implemented as not available', () => {
    expect(isTabAvailable('home')).toBe(true);
    expect(isTabAvailable('skills')).toBe(true);
    expect(isTabAvailable('admin')).toBe(true);
    expect(isTabAvailable('chats')).toBe(true);
    expect(isTabAvailable('matters')).toBe(false);
    expect(isTabAvailable('knowledge')).toBe(false);
    expect(isTabAvailable('saved-prompts')).toBe(false);
  });

  it('derives active tab from pathname', () => {
    expect(activeTabFor('/lq-ai')).toBe('home');
    expect(activeTabFor('/lq-ai/skills')).toBe('skills');
    expect(activeTabFor('/lq-ai/skills/new')).toBe('skills');
    expect(activeTabFor('/lq-ai/skills/abc-123')).toBe('skills');
    expect(activeTabFor('/lq-ai/admin/audit-log')).toBe('admin');
    expect(activeTabFor('/lq-ai/login')).toBe(null);
    expect(activeTabFor('/lq-ai/change-password')).toBe(null);
  });

  // Three-role gating — spec §4.1.1
  const viewerUser: User = { ...memberUser, role: 'viewer', is_admin: false };
  const adminUserNoRole: User = { ...adminUser, role: 'admin' };

  it('hides admin tab for viewer role', () => {
    expect(isTabVisible('admin', viewerUser)).toBe(false);
  });
  it('hides admin tab for member role', () => {
    expect(isTabVisible('admin', { ...memberUser, role: 'member' })).toBe(false);
  });
  it('shows admin tab for admin role even if is_admin flag is stale', () => {
    expect(isTabVisible('admin', { ...adminUserNoRole, is_admin: false })).toBe(true);
  });
});
