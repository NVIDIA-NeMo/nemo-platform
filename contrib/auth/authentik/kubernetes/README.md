# Authentik Kubernetes Runtime

This directory contains the Kubernetes runtime documentation for the Authentik
reference example. The Kubernetes deployment is installed through the umbrella
Helm chart at `contrib/auth/authentik/helm`.

Use the single shared tutorial for the end-to-end walkthrough:

- [Authentik Reference Tutorial](../tutorial.md)

For Kubernetes-specific architecture and wiring, see:

- [Implementation Details](implementation-details.md)

The Kubernetes runtime starts from the shared tutorial with `kind`, `kubectl`,
and `helm --kube-context`.
