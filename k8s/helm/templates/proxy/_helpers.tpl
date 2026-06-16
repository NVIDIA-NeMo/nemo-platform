{{/*
Create a named Envoy service name which can be included from parent chart
*/}}
{{- define "nmp-envoy.servicename" }}
{{- printf "%s-envoy" ( include "nemo-platform.fullname" . | trunc 57 ) }}
{{- end }}

{{/*
Labels for Envoy proxy resources (component + platform labels).
*/}}
{{- define "nmp-envoy.labels" -}}
app.kubernetes.io/component: nmp-envoy
{{ include "nemo-platform.labels" . }}
{{- end }}

{{/*
Create the name of the Envoy service account to use
*/}}
{{- define "nmp-envoy.serviceAccountName" -}}
{{- if .Values.envoyProxy.serviceAccount.create }}
{{- default (printf "%s-envoy" (include "nemo-platform.fullname" .)) .Values.envoyProxy.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.envoyProxy.serviceAccount.name }}
{{- end }}
{{- end }}
