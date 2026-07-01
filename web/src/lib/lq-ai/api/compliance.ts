/**
 * /api/v1/compliance — the deployment-global AI-systems register (read-only) — AIC-1.
 *
 * The AI Compliance module's register of the organisation's AI systems under the
 * EU AI Act (Regulation (EU) 2024/1689). The register is the company's standing
 * record (LQ.AI is single-tenant; ADR-F019), so these read endpoints are global —
 * no project/matter id in the path. The AI Compliance Deep Agent is the only
 * writer (guarded, code-validated tools); the UI reads. The register carries FACTS
 * ONLY — the risk tier is a legal determination owned by the classification engine
 * (AIC-2, ADR-F057), not a stored field.
 *
 * Wire shapes mirror api/app/schemas/compliance.py (the Read DTO).
 */
import { apiRequest } from './client';

export type LifecycleStatus = 'in_development' | 'in_service' | 'decommissioned';
export type DevelopmentOrigin = 'in_house' | 'third_party' | 'hybrid';

export interface AiSystemRead {
	id: string;
	name: string;
	intended_purpose: string;
	lifecycle_status: LifecycleStatus;
	development_origin: DevelopmentOrigin;
	is_gpai: boolean;
	gpai_systemic: boolean;
	notes: string | null;
	created_at: string;
	updated_at: string;
	// Soft-retire: null = live (default reads hide retired rows).
	retired_at: string | null;
}

export function listAiSystems(): Promise<AiSystemRead[]> {
	return apiRequest<AiSystemRead[]>('/compliance/ai-systems');
}

export function getAiSystem(id: string): Promise<AiSystemRead> {
	return apiRequest<AiSystemRead>(`/compliance/ai-systems/${encodeURIComponent(id)}`);
}
