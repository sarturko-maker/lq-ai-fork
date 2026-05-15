{{/*
Common name helpers — mirrors the standard Helm chart pattern.
*/}}
{{- define "lq-ai.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "lq-ai.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "lq-ai.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "lq-ai.labels" -}}
helm.sh/chart: {{ include "lq-ai.chart" . }}
{{ include "lq-ai.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "lq-ai.selectorLabels" -}}
app.kubernetes.io/name: {{ include "lq-ai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
ServiceAccount sanity check.
If operators set serviceAccount.create=false, they MUST also set
serviceAccount.name to an existing SA. Otherwise pods reference a
non-existent SA and fail admission silently. Fail fast at install time
with a clear message instead.
*/}}
{{- define "lq-ai.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "lq-ai.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- if not .Values.serviceAccount.name -}}
{{- fail "serviceAccount.create=false requires serviceAccount.name to be set to an existing ServiceAccount in the target namespace" -}}
{{- else -}}
{{- .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
{{- end -}}
