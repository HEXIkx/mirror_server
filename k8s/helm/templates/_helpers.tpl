{{/*
创建完整名称
*/}}
{{- define "hyc.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "hyc.name" .) | trunc 63 -}}
{{- end -}}

{{/*
标签
*/}}
{{- define "hyc.labels" -}}
helm.sh/chart: {{ include "hyc.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: {{ .Chart.Name }}
{{- end -}}

{{/*
选择器标签
*/}}
{{- define "hyc.selectorLabels" -}}
app.kubernetes.io/name: {{ include "hyc.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
图表名称
*/}}
{{- define "hyc.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 -}}
{{- end -}}

{{/*
图表版本
*/}}
{{- define "hyc.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version -}}
{{- end -}}

{{/*
PostgreSQL 主机
*/}}
{{- define "hyc.postgresql.host" -}}
{{- if .Values.postgresql.enabled -}}
{{- printf "%s-%s" .Release.Name "postgresql" -}}
{{- else -}}
{{- .Values.config.database.postgresql.host | default "localhost" -}}
{{- end -}}
{{- end -}}

{{/*
Redis 主机
*/}}
{{- define "hyc.redis.host" -}}
{{- if .Values.redis.enabled -}}
{{- printf "%s-%s" .Release.Name "redis" -}}
{{- else -}}
{{- .Values.config.database.redis.host | default "localhost" -}}
{{- end -}}
{{- end -}}
