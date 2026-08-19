{{/*
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
*/}}

{{/*
Image Definition Parsing
Favor not using a separate registry because it is confusing, but support it.
*/}}
{{- define "nmp-core.image" -}}
{{- if .Values.core.image.registry -}}
{{ .Values.core.image.registry }}/{{ .Values.core.image.repository }}:{{ default .Chart.AppVersion .Values.core.image.tag }}
{{- else -}}
{{ .Values.core.image.repository }}:{{ default .Chart.AppVersion .Values.core.image.tag }}
{{- end }}
{{- end }}

{{/*
Create a named core service name which can be included from parent chart
*/}}
{{- define "nmp-core.api-servicename" }}
{{- printf "%s-core" ( include "nemo-platform.fullname" . | trunc 59 ) }}
{{- end }}

{{/*
Create a named core controller service name which can be included from parent chart
*/}}
{{- define "nmp-core.controller-servicename" }}
{{- printf "%s-core-controller" ( include "nemo-platform.fullname" . | trunc 52 ) }}
{{- end }}

{{/*
Create a named core controller service name which can be included from parent chart
*/}}
{{- define "nmp-core.database-migrations-servicename" }}
{{- printf "%s-core-migrations" ( include "nemo-platform.fullname" .) }}
{{- end }}

{{/*
Create the name of the API service account to use
*/}}
{{- define "nmp-core.apiServiceAccountName" -}}
{{- if .Values.core.api.serviceAccount.create }}
{{- default (printf "%s-core" (include "nemo-platform.fullname" .)) .Values.core.api.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.core.api.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the Controller service account to use
*/}}
{{- define "nmp-core.controllerServiceAccountName" -}}
{{- if .Values.core.controller.serviceAccount.create }}
{{- default (printf "%s-core-controller" (include "nemo-platform.fullname" .)) .Values.core.controller.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.core.controller.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Detect legacy controller selection flags passed through core.controller.extraArgs.
*/}}
{{- define "nmp-core.hasControllerSelectionExtraArgs" -}}
{{- $hasSelection := false -}}
{{- range .Values.core.controller.extraArgs }}
{{- $arg := toString . -}}
{{- if or (eq $arg "--controllers") (hasPrefix "--controllers=" $arg) (eq $arg "--controller-group") (hasPrefix "--controller-group=" $arg) -}}
{{- $hasSelection = true -}}
{{- end -}}
{{- end -}}
{{- if $hasSelection -}}
true
{{- end -}}
{{- end }}

{{/*
Render the `nemo services run` controller selection arg for the controller pod.
core.controller.controllers takes precedence over core.controller.controllerGroup.
*/}}
{{- define "nmp-core.controllerSelectionArgs" -}}
{{- if not (include "nmp-core.hasControllerSelectionExtraArgs" .) -}}
{{- $controllers := .Values.core.controller.controllers | default list -}}
{{- if $controllers -}}
{{- $controllerList := "" -}}
{{- if kindIs "slice" $controllers -}}
{{- $controllerList = join "," $controllers -}}
{{- else -}}
{{- $controllerList = toString $controllers -}}
{{- end -}}
{{- if not ($controllerList | trim) -}}
{{- fail "core.controller.controllers must not be empty when set" -}}
{{- end -}}
- {{ printf "--controllers=%s" $controllerList | quote }}
{{- else if .Values.core.controller.controllerGroup -}}
- {{ printf "--controller-group=%s" .Values.core.controller.controllerGroup | quote }}
{{- else -}}
{{- fail "one of core.controller.controllerGroup or core.controller.controllers must be set for the controller deployment" -}}
{{- end -}}
{{- end -}}
{{- end }}

{{/*
Create the name of the Jobs service account to use (for pods created by the jobs controller)
*/}}
{{- define "nmp-core.jobsServiceAccountName" -}}
{{- if .Values.core.jobs.serviceAccount.create }}
{{- default (printf "%s-jobs" (include "nemo-platform.fullname" .)) .Values.core.jobs.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.core.jobs.serviceAccount.name }}
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
