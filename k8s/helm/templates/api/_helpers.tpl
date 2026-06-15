{{/*
Image Definition Parsing
Favor not using a separate registry because it is confusing, but support it.
*/}}
{{- define "nmp-api.image" -}}
{{- if .Values.api.image.registry -}}
{{ .Values.api.image.registry }}/{{ .Values.api.image.repository }}:{{ default .Chart.AppVersion .Values.api.image.tag }}
{{- else -}}
{{ .Values.api.image.repository }}:{{ default .Chart.AppVersion .Values.api.image.tag }}
{{- end }}
{{- end }}

{{/*
Create a named api service name which can be included from parent chart
*/}}
{{- define "nmp-api.api-servicename" }}
{{- printf "%s-api" ( include "nemo-platform.fullname" . | trunc 59 ) }}
{{- end }}

{{/*
Create the name of the API service account to use
*/}}
{{- define "nmp-api.apiServiceAccountName" -}}
{{- if .Values.api.serviceAccount.create }}
{{- default (printf "%s-api" (include "nemo-platform.fullname" .)) .Values.api.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.api.serviceAccount.name }}
{{- end }}
{{- end }}


{{/*
Create the PVC name
*/}}
{{- define "nmp-core.persistentVolumeClaim" -}}
{{- printf "%s-core-storage" (include "nemo-platform.fullname" .) }}
{{- end }}

{{/*
Define whether local files backend is enabled
*/}}
{{- define "nmp-core.localStorageEnabled" -}}
{{- if (include "nemo-platform.calculatedConfig" . | fromYaml).files -}}
{{- eq ( (include "nemo-platform.calculatedConfig" . | fromYaml).files.default_storage_config.type ) "local" -}}
{{- else -}}
false
{{- end -}}
{{- end -}}

{{/*
Create the local storage path for files
*/}}
{{- define "nmp-core.localStoragePath" -}}
{{- if (include "nemo-platform.calculatedConfig" . | fromYaml).files -}}
{{ (include "nemo-platform.calculatedConfig" . | fromYaml).files.default_storage_config.path | default "" }}
{{- end -}}
{{- end }}
