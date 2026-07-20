{{- define "nemo-platform-authentik.envoyConfig" -}}
{{- $authentik := required "nemo-platform.authentikEnvoy is required" .Values.authentikEnvoy -}}
{{- $oidc := .Values.platformConfig.auth.oidc -}}
{{- $tlsMountPath := "" -}}
{{- range .Values.envoyProxy.extraVolumeMounts -}}
{{- if eq (index . "name") "workload-token-tls" -}}
{{- $tlsMountPath = index . "mountPath" -}}
{{- end -}}
{{- end -}}
{{- $tlsMountPath = required "nemo-platform.envoyProxy.extraVolumeMounts must include workload-token-tls" $tlsMountPath -}}
{{- $apiServiceName := include "nmp-api.api-servicename" . -}}
{{- $envoyServiceName := include "nmp-envoy.servicename" . -}}
{{- $spoofHeaders := concat .Values.envoyProxy.trustedHeaders (list "x-nmp-authorized" "x-nmp-scopes") | uniq -}}
admin:
  address:
    socket_address:
      address: 0.0.0.0
      port_value: {{ .Values.envoyProxy.adminPort }}
static_resources:
  listeners:
    - name: listener_0
      address:
        socket_address:
          address: 0.0.0.0
          port_value: {{ .Values.envoyProxy.service.port }}
      filter_chains:
        - transport_socket:
            name: envoy.transport_sockets.tls
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext
              common_tls_context:
                tls_certificates:
                  - certificate_chain:
                      filename: {{ printf "%s/tls.crt" $tlsMountPath | quote }}
                    private_key:
                      filename: {{ printf "%s/tls.key" $tlsMountPath | quote }}
          filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
                stat_prefix: ingress_http
                route_config:
                  name: local_route
                  virtual_hosts:
                    - name: nemo
                      domains: ["*"]
                      routes:
                        - match:
                            prefix: "/.well-known/nemo-platform/"
                          route:
                            cluster: nemo
                          request_headers_to_add:
                            - header:
                                key: x-forwarded-proto
                                value: https
                              append_action: OVERWRITE_IF_EXISTS_OR_ADD
                        - match:
                            prefix: "/apis/"
                          route:
                            cluster: nemo
                          request_headers_to_add:
                            - header:
                                key: x-forwarded-proto
                                value: https
                              append_action: OVERWRITE_IF_EXISTS_OR_ADD
                        - match:
                            path: "/health/gateway/ready"
                          direct_response:
                            status: 503
                            body:
                              inline_string: '{"status":"not_ready"}'
                        - match:
                            prefix: "/health/"
                          route:
                            cluster: nemo
                          request_headers_to_add:
                            - header:
                                key: x-forwarded-proto
                                value: https
                              append_action: OVERWRITE_IF_EXISTS_OR_ADD
                        - match:
                            path: "/status"
                          route:
                            cluster: nemo
                          request_headers_to_add:
                            - header:
                                key: x-forwarded-proto
                                value: https
                              append_action: OVERWRITE_IF_EXISTS_OR_ADD
                        - match:
                            prefix: "/studio/"
                          route:
                            cluster: nemo
                          request_headers_to_add:
                            - header:
                                key: x-forwarded-proto
                                value: https
                              append_action: OVERWRITE_IF_EXISTS_OR_ADD
                        - match:
                            prefix: "/"
                          route:
                            cluster: authentik
                http_filters:
                  - name: envoy.filters.http.lua
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
                      inline_code: |
                        local function gateway_ready_http_call(request_handle, cluster, authority, path)
                          local ok, response_headers = pcall(function()
                            local headers, _ = request_handle:httpCall(
                              cluster,
                              {
                                [":method"] = "GET",
                                [":path"] = path,
                                [":authority"] = authority
                              },
                              "",
                              5000
                            )
                            return headers
                          end)
                          if not ok then
                            return false, "error"
                          end
                          if response_headers == nil then
                            return false, "missing"
                          end

                          local status = response_headers[":status"] or "missing"
                          return status == "200", status
                        end

                        function envoy_on_request(request_handle)
                          local headers = request_handle:headers()
{{- range $header := $spoofHeaders }}
                          headers:remove({{ $header | quote }})
{{- end }}

                          if headers:get(":path") ~= "/health/gateway/ready" then
                            return
                          end

                          local nemo_ready, nemo_status = gateway_ready_http_call(request_handle, "nemo", {{ $apiServiceName | quote }}, "/health/ready")
                          local authentik_ready, authentik_status = gateway_ready_http_call(request_handle, "authentik", {{ $authentik.serviceName | quote }}, "/application/o/nemo/.well-known/openid-configuration")
                          if nemo_ready and authentik_ready then
                            request_handle:respond({[":status"] = "200", ["content-type"] = "application/json"}, '{"status":"ready"}')
                            return
                          end

                          request_handle:respond(
                            {[":status"] = "503", ["content-type"] = "application/json"},
                            string.format('{"status":"not_ready","nemo":"%s","authentik":"%s"}', nemo_status, authentik_status)
                          )
                        end
                  - name: envoy.filters.http.jwt_authn
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication
                      providers:
                        authentik_workload:
                          audiences:
                            - {{ $oidc.workload_audience | quote }}
                            - {{ $oidc.client_id | quote }}
                            - {{ $oidc.workload_client_id | quote }}
                          remote_jwks:
                            http_uri:
                              uri: {{ printf "https://%s:%v/application/o/nemo/jwks/" $envoyServiceName .Values.envoyProxy.service.port | quote }}
                              cluster: nemo_envoy_https
                              timeout: 5s
                            cache_duration: 600s
                          claim_to_headers:
                            - header_name: "X-NMP-Principal-Id"
                              claim_name: "sub"
                            - header_name: "X-NMP-Principal-Groups"
                              claim_name: "groups"
                        workload_exchange:
                          audiences:
                            - {{ $oidc.workload_audience | quote }}
                          remote_jwks:
                            http_uri:
                              uri: {{ printf "https://%s:%v/apis/auth/jwks" $envoyServiceName .Values.envoyProxy.service.port | quote }}
                              cluster: nemo_envoy_https
                              timeout: 5s
                            cache_duration: 600s
                          claim_to_headers:
                            - header_name: "X-NMP-Principal-Id"
                              claim_name: "sub"
                            - header_name: "X-NMP-Principal-Groups"
                              claim_name: "groups"
                      rules:
                        - match:
                            path: "/apis/auth/discovery"
                        - match:
                            path: "/apis/auth/jwks"
                        - match:
                            path: "/apis/auth/token"
                        - match:
                            prefix: "/health/"
                        - match:
                            prefix: "/apis/"
                          requires:
                            requires_any:
                              requirements:
                                - provider_name: "authentik_workload"
                                - provider_name: "workload_exchange"
                  - name: envoy.filters.http.router
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
  clusters:
    - name: nemo
      connect_timeout: 5s
      type: LOGICAL_DNS
      load_assignment:
        cluster_name: nemo
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: {{ $apiServiceName }}
                      port_value: {{ .Values.api.service.port }}
    - name: authentik
      connect_timeout: 5s
      type: LOGICAL_DNS
      load_assignment:
        cluster_name: authentik
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: {{ $authentik.serviceName }}
                      port_value: {{ $authentik.servicePort }}
    - name: nemo_envoy_https
      connect_timeout: 5s
      type: LOGICAL_DNS
      transport_socket:
        name: envoy.transport_sockets.tls
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
          sni: {{ $envoyServiceName }}
          common_tls_context:
            validation_context:
              trusted_ca:
                filename: {{ printf "%s/ca.crt" $tlsMountPath | quote }}
      load_assignment:
        cluster_name: nemo_envoy_https
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: {{ $envoyServiceName }}
                      port_value: {{ .Values.envoyProxy.service.port }}
{{- end -}}
