{{/*
Standard helpers used across DataSync templates.
*/}}

{{- define "datasync.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "datasync.labels" -}}
app.kubernetes.io/name: datasync
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "datasync.selectorLabels" -}}
app.kubernetes.io/name: datasync
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "datasync.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "datasync.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
