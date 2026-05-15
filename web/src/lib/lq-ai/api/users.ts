/**
 * /api/v1/users/me — per-user data export and account deletion (GDPR Art. 20 / Art. 17).
 */
import { apiRequest } from './client';
import type { DeleteScheduledResponse, ExportJob } from '../types';

/** POST /api/v1/users/me/export — enqueue an export worker job. Returns initial job status. */
export async function startExport(): Promise<ExportJob> {
	return apiRequest<ExportJob>('/users/me/export', { method: 'POST' });
}

/** GET /api/v1/users/me/export/{job_id} — poll until status=completed or failed. */
export async function getExportJob(jobId: string): Promise<ExportJob> {
	return apiRequest<ExportJob>(`/users/me/export/${encodeURIComponent(jobId)}`);
}

/** POST /api/v1/users/me/delete — schedule a soft delete with a grace period. Idempotent. */
export async function requestDeletion(): Promise<DeleteScheduledResponse> {
	return apiRequest<DeleteScheduledResponse>('/users/me/delete', { method: 'POST' });
}

/** POST /api/v1/users/me/delete/cancel — cancel the pending deletion. */
export async function cancelDeletion(): Promise<void> {
	await apiRequest<void>('/users/me/delete/cancel', { method: 'POST' });
}
