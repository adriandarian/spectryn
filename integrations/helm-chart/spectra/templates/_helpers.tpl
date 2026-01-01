{{/*
Copyright (c) spectra
SPDX-License-Identifier: MIT
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "spectra.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "spectra.fullname" -}}
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

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "spectra.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "spectra.labels" -}}
helm.sh/chart: {{ include "spectra.chart" . }}
{{ include "spectra.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "spectra.selectorLabels" -}}
app.kubernetes.io/name: {{ include "spectra.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "spectra.serviceAccountName" -}}
{{- if .Values.operator.serviceAccount.create }}
{{- default (include "spectra.fullname" .) .Values.operator.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.operator.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Operator image
*/}}
{{- define "spectra.operatorImage" -}}
{{- printf "%s:%s" .Values.operator.image.repository .Values.operator.image.tag }}
{{- end }}

{{/*
Spectra image
*/}}
{{- define "spectra.spectraImage" -}}
{{- printf "%s:%s" .Values.spectra.image.repository .Values.spectra.image.tag }}
{{- end }}

{{/*
Image pull secrets
*/}}
{{- define "spectra.imagePullSecrets" -}}
{{- with .Values.global.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}
