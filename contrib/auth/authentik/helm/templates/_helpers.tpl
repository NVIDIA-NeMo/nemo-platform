{{- define "nemo-platform-authentik.namespace" -}}
{{- .Release.Namespace -}}
{{- end -}}

{{- define "nemo-platform-authentik.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
app.kubernetes.io/name: {{ .Chart.Name | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
{{- end -}}

{{- define "nemo-platform-authentik.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
{{- end -}}

{{- define "nemo-platform-authentik.sharedPostgresql.selectorLabels" -}}
{{ include "nemo-platform-authentik.selectorLabels" . }}
app.kubernetes.io/component: shared-postgresql
{{- end -}}

{{- define "nemo-platform-authentik.sharedPostgresql.serviceAccountName" -}}
{{- if .Values.sharedPostgresql.serviceAccount.create -}}
{{- default (printf "%s-postgres" .Values.sharedPostgresql.serviceName) .Values.sharedPostgresql.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.sharedPostgresql.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "nemo-platform-authentik.serviceNamespacedHost" -}}
{{- $namespace := .namespace | default .root.Release.Namespace -}}
{{- printf "%s.%s" .serviceName $namespace -}}
{{- end -}}

{{- define "nemo-platform-authentik.serviceFqdn" -}}
{{- $clusterDomain := .clusterDomain | default "cluster.local" -}}
{{- printf "%s.svc.%s" (include "nemo-platform-authentik.serviceNamespacedHost" .) $clusterDomain -}}
{{- end -}}

{{- define "nemo-platform-authentik.serviceUrl" -}}
{{- $host := include "nemo-platform-authentik.serviceFqdn" . -}}
{{- if hasKey . "port" -}}
{{- printf "%s://%s:%s" .scheme $host (toString .port) -}}
{{- else -}}
{{- printf "%s://%s" .scheme $host -}}
{{- end -}}
{{- end -}}

{{- define "nemo-platform-authentik.publicGatewayUrl" -}}
{{- $gateway := required "nemo-platform.authentikPublicGateway is required" .Values.authentikPublicGateway -}}
{{- $scheme := required "nemo-platform.authentikPublicGateway.scheme is required" (index $gateway "scheme") -}}
{{- $host := required "nemo-platform.authentikPublicGateway.host is required" (index $gateway "host") -}}
{{- $port := required "nemo-platform.authentikPublicGateway.port is required" (index $gateway "port") -}}
{{- printf "%s://%s:%s" $scheme $host (toString $port) -}}
{{- end -}}

{{- define "nemo-platform-authentik.serviceDnsNames" -}}
{{- $namespacedHost := include "nemo-platform-authentik.serviceNamespacedHost" . -}}
names:
  - {{ .serviceName | quote }}
  - {{ $namespacedHost | quote }}
  - {{ printf "%s.svc" $namespacedHost | quote }}
  - {{ include "nemo-platform-authentik.serviceFqdn" . | quote }}
{{- end -}}

{{/*
Return existing Secret data as JSON. Callers can pipe through fromJson and
decide whether to reuse existing keys or generate first-install values.
*/}}
{{- define "nemo-platform-authentik.existingSecretData" -}}
{{- $existingSecret := lookup "v1" "Secret" .root.Release.Namespace .secretName -}}
{{- if and $existingSecret $existingSecret.data -}}
{{- $existingSecret.data | toJson -}}
{{- else -}}
{{- dict | toJson -}}
{{- end -}}
{{- end -}}

{{- define "nemo-platform-authentik.workloadTokenSigningKey.secretName" -}}
{{- required "workloadTokenSigningKey.secretName is required" .Values.workloadTokenSigningKey.secretName -}}
{{- end -}}

{{- define "nemo-platform-authentik.workloadTokenSigningKey.key" -}}
{{- required "workloadTokenSigningKey.key is required" .Values.workloadTokenSigningKey.key -}}
{{- end -}}

{{/*
Resolve the workload token signing private key. Prefer an explicitly supplied
value, preserve an existing Secret key across upgrades, then generate one for
first install.
*/}}
{{- define "nemo-platform-authentik.workloadTokenSigningKey.privateKeyPem" -}}
{{- $secretName := include "nemo-platform-authentik.workloadTokenSigningKey.secretName" . -}}
{{- $secretKey := include "nemo-platform-authentik.workloadTokenSigningKey.key" . -}}
{{- $privateKeyPem := .Values.workloadTokenSigningKey.privateKeyPem | default "" -}}
{{- $existingData := include "nemo-platform-authentik.existingSecretData" (dict "root" . "secretName" $secretName) | fromJson -}}
{{- if $privateKeyPem -}}
{{- $privateKeyPem -}}
{{- else if hasKey $existingData $secretKey -}}
{{- index $existingData $secretKey | b64dec -}}
{{- else -}}
{{- genPrivateKey "rsa" -}}
{{- end -}}
{{- end -}}

{{/*
Resolve a shared PostgreSQL password once. The initdb script only provisions
roles when the data directory is empty, so existing Secret data must remain the
source of truth while the StatefulSet PVC exists.
*/}}
{{- define "nemo-platform-authentik.sharedPostgresql.password" -}}
{{- $root := .root -}}
{{- $secretName := .secretName -}}
{{- $secretKey := .secretKey -}}
{{- $value := .value | default "" -}}
{{- $generate := .generate | default false -}}
{{- $existingData := include "nemo-platform-authentik.existingSecretData" (dict "root" $root "secretName" $secretName) | fromJson -}}
{{- if hasKey $existingData $secretKey -}}
{{- index $existingData $secretKey | b64dec -}}
{{- else -}}
{{- if $root.Values.sharedPostgresql.persistence.enabled -}}
{{- $pvcName := printf "data-%s-0" $root.Values.sharedPostgresql.serviceName -}}
{{- $existingPvc := lookup "v1" "PersistentVolumeClaim" $root.Release.Namespace $pvcName -}}
{{- if $existingPvc -}}
{{- fail (printf "cannot change or regenerate %s/%s while PersistentVolumeClaim %s exists; restore the Secret or rotate the PostgreSQL role before changing it" $secretName $secretKey $pvcName) -}}
{{- end -}}
{{- end -}}
{{- if $value -}}
{{- $value -}}
{{- else if $generate -}}
{{- randAlphaNum 32 -}}
{{- else -}}
{{- fail (printf "%s/%s must be set before initial PostgreSQL provisioning" $secretName $secretKey) -}}
{{- end -}}
{{- end -}}
{{- end -}}
