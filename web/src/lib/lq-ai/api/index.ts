/**
 * Barrel re-export for the LQ.AI canonical /api/v1 client.
 *
 * Per ADR 0009 (superseded by ADR-F006 for shell topology) this is the only
 * API surface the LQ.AI shell talks to.
 */
export * from './client';
export * as authApi from './auth';
export * as bootstrapApi from './bootstrap';
export * as projectsApi from './projects';
export * as chatsApi from './chats';
export * as messagesApi from './messages';
export * as citationsApi from './citations';
export * as skillsApi from './skills';
export * as filesApi from './files';
export * as knowledgeBasesApi from './knowledgeBases';
export * as projectKnowledgeBasesApi from './projectKnowledgeBases';
export * as modelsApi from './models';
export * as adminApi from './admin';
export * as auditLogApi from './auditLog';
export * as intakeBridgesApi from './intakeBridges';
export * as savedPromptsApi from './savedPrompts';
export * as userSkillsApi from './userSkills';
export * as teamsApi from './teams';
export * as preferencesApi from './preferences';
export * as usersApi from './users';
export * as enhancePromptApi from './enhancePrompt';
export * as autonomousApi from './autonomous';
export * as agentsApi from './agents';
export * as practiceAreasApi from './practiceAreas';
