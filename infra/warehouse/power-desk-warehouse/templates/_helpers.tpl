{{- define "pdw.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/* a component's resource name: <fullname>-<component>; call with (dict "root" $ "name" "orchestrator") */}}
{{- define "pdw.name" -}}
{{- printf "%s-%s" (include "pdw.fullname" .root) .name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pdw.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}

{{- define "pdw.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version }}
app.kubernetes.io/part-of: power-desk
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
{{ include "pdw.selectorLabels" . }}
{{- end -}}

{{/* call with (dict "root" $ "image" .Values.images.<name>) */}}
{{- define "pdw.image" -}}
{{- printf "%s:%s" .image.repository (.image.tag | default .root.Chart.AppVersion) -}}
{{- end -}}

{{/* the warehouse's directory on the node, and a writable /tmp (root filesystems are read-only) */}}
{{- define "pdw.volumes" -}}
- name: data
  hostPath: {path: {{ .Values.data.hostPath }}, type: Directory}
- {name: tmp, emptyDir: {}}
{{- end -}}

{{- define "pdw.podSecurity" -}}
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
seccompProfile: {type: RuntimeDefault}
{{- end -}}

{{- define "pdw.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities: {drop: [ALL]}
{{- end -}}

{{/* the orchestrator's environment; the image sets the file locations (elt/Dockerfile) */}}
{{- define "pdw.eltEnv" -}}
env:
  - {name: POWER_DESK_ENV, value: {{ .Values.environment | quote }}}
  - {name: POWER_DESK_DUCKDB_PATH, value: /app/data/warehouse_{{ .Values.environment }}.duckdb}
  {{- range $key, $value := .Values.env }}
  - {name: {{ $key }}, value: {{ $value | quote }}}
  {{- end }}
{{- with .Values.existingSecret }}
envFrom:
  - secretRef: {name: {{ . }}}
{{- end }}
{{- end -}}
