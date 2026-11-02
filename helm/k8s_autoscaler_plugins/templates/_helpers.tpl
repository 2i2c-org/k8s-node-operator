{{/*
Expand the name of the chart.
*/}}
{{- define "k8s-autoscaler-plugins.name" -}}
{{- .Release.Name }}-node-operator
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "k8s-autoscaler-plugins.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "k8s-autoscaler-plugins.resourceName" -}}
{{- include "k8s-autoscaler-plugins.name" . -}}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "k8s-autoscaler-plugins.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "k8s-autoscaler-plugins.labels" -}}
helm.sh/chart: {{ include "k8s-autoscaler-plugins.chart" . }}
{{ include "k8s-autoscaler-plugins.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "k8s-autoscaler-plugins.selectorLabels" -}}
app.kubernetes.io/name: {{ include "k8s-autoscaler-plugins.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- /* ServiceAccount name */}}
{{- define "k8s-autoscaler-plugins.serviceaccount.fullname" -}}
    {{- if .Values.serviceAccount.create }}
        {{- .Values.serviceAccount.name | default (include "k8s-autoscaler-plugins.fullname" .) }}
    {{- else }}
        {{- .Values.serviceAccount.name }}
    {{- end }}
{{- end }}

{{- /* ClusterRole name */}}
{{- define "k8s-autoscaler-plugins.clusterrole.fullname" -}}
    {{- if .Values.rbac.create }}
        {{- .Values.rbac.name | default (include "k8s-autoscaler-plugins.fullname" .) }}
    {{- else }}
        {{- .Values.rbac.name }}
    {{- end }}
{{- end }}