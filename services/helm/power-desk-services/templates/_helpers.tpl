{{- define "pds.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/* a service's resource name: <fullname>-<service> */}}
{{- define "pds.serviceName" -}}
{{- printf "%s-%s" (include "pds.fullname" .root) .name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pds.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: power-desk
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end -}}

{{/* selector labels of one service; call with (dict "root" $ "name" $name) */}}
{{- define "pds.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}

{{/* all labels of one service's resources */}}
{{- define "pds.serviceLabels" -}}
{{ include "pds.labels" .root }}
app.kubernetes.io/name: {{ .name }}
{{- end -}}

