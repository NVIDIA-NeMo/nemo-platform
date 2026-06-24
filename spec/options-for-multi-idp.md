# Multi-IdP, SSO, and Tenant Isolation Research for NeMo Platform

## Executive Summary

NeMo Platform today supports a single OIDC configuration per deployment, plus a small `additional_issuers` escape hatch intended for issuer-format variance such as Azure AD v1/v2. It does **not** currently support:

- multiple first-class IdPs in one deployment
- home realm discovery (HRD) or domain-based IdP routing
- user account linking across IdPs
- true multi-tenant isolation

The repo also explicitly documents that workspaces are a logical authorization boundary, **not** a tenant-isolation boundary.

If the product requirement is:

1. one NeMo deployment that supports many customer IdPs, and
2. users from different organizations signing in through different IdPs, and
3. true tenant isolation where one tenant cannot affect or observe another,

then these should be treated as **two separate architectures**:

- **Multi-IdP federation for a single deployment**: solve with an identity broker / gateway in front of NeMo.
- **Tenant isolation**: solve with a separate NeMo Platform deployment per tenant.

That split is the core recommendation of this document.

## Current State in This Repo

### 1. Auth config is single-provider

`OIDCConfig` models one provider: one `issuer`, one `client_id`, optional endpoint overrides, and one claim-mapping profile. See [packages/nmp_common/src/nmp/common/config/base.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/config/base.py:89).

Relevant indicators:

- single `issuer`: [base.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/config/base.py:97)
- single `client_id`: [base.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/config/base.py:110)
- single `email_claim`, `groups_claim`, `subject_claim`: [base.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/config/base.py:143)
- one nested `auth.oidc` object under `AuthConfig`: [base.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/config/base.py:234)

### 2. JWT validation assumes one primary discovery source

`JWTValidator` fetches discovery from `config.oidc.issuer`, builds one JWKS client, and validates tokens against one audience profile plus a flat list of allowed issuers. See [packages/nmp_common/src/nmp/common/auth/jwt.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/auth/jwt.py:43).

Important details:

- discovery URL is built from a single issuer: [jwt.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/auth/jwt.py:63)
- one JWKS client instance is cached: [jwt.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/auth/jwt.py:71)
- allowed issuers are `[issuer] + additional_issuers`: [jwt.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/auth/jwt.py:178)

This is not a provider registry. It is a single-provider validator with a compatibility list.

### 3. Auth discovery is single-provider

The auth discovery endpoint exposes one `oidc` object with one issuer, one token endpoint, one device authorization endpoint, and one client ID. See [services/core/auth/src/nmp/core/auth/api/v2/discovery/endpoints.py](/Users/rsadler/src/nemo-platform/services/core/auth/src/nmp/core/auth/api/v2/discovery/endpoints.py:24).

This matters because the CLI and SDK bootstrap from this shape today.

### 4. Studio is single-authority

Studio runtime env exposes a single `VITE_AUTH_AUTHORITY` and `VITE_AUTH_CLIENT_ID`. See [web/packages/studio/src/constants/environment.ts](/Users/rsadler/src/nemo-platform/web/packages/studio/src/constants/environment.ts:64).

Auto-login also assumes exactly one authority and redirects there immediately when auth is enabled: [web/packages/studio/src/providers/auth/useAuthLogin.ts](/Users/rsadler/src/nemo-platform/web/packages/studio/src/providers/auth/useAuthLogin.ts:21).

This means there is no native pre-login organization picker, no HRD screen, and no provider selection UX.

### 5. Authorization is workspace-scoped, not tenant-isolated

The docs are explicit:

- principals are typically human users identified by email: [docs/auth/concepts.md](/Users/rsadler/src/nemo-platform/docs/auth/concepts.md:28)
- workspaces are the auth boundary: [docs/get-started/concepts/workspaces.md](/Users/rsadler/src/nemo-platform/docs/get-started/concepts/workspaces.md:4)
- the product does **not** provide database-isolated multi-tenancy: [docs/auth/security-model.md](/Users/rsadler/src/nemo-platform/docs/auth/security-model.md:172)

This confirms the current model is:

- one deployment
- many workspaces
- shared control plane and shared storage surfaces

That is not equivalent to enterprise tenant isolation.

### 6. There is at least one user-experience assumption tied to email-local-part

Studio derives a default workspace name from the email local part: [web/packages/studio/src/providers/auth/useAuthProfile.ts](/Users/rsadler/src/nemo-platform/web/packages/studio/src/providers/auth/useAuthProfile.ts:18).

That is fragile in any serious enterprise identity design and would need reconsideration even before multi-IdP.

## Requirements Decomposition

The original request actually bundles three different problems:

### A. Multiple IdP types for one NeMo deployment

Examples:

- one customer uses Entra ID
- another uses Okta
- another uses Ping or Keycloak
- some enterprise connections are OIDC, others are SAML

### B. SSO for users that may authenticate through different IdPs

Examples:

- same human can sign in with corporate IdP or a backup/social/provider-managed identity
- one user belongs to two organizations with different upstream IdPs
- one deployment needs email-domain routing or organization routing

### C. True tenant isolation

Your requirement is stronger than workspace isolation:

> Multitenant should be a completely separate instance of nemo-platform isolated from every other tenant.

That is not "multitenancy inside a deployment." That is a **fleet of isolated single-tenant deployments**.

This is the right framing if the goal is enterprise-grade isolation.

## Industry Patterns

### Pattern 1: Identity broker in front of the app

This is the dominant pattern for apps that want:

- multiple upstream IdPs
- OIDC plus SAML support
- HRD / IdP routing
- JIT provisioning
- account linking
- one stable downstream OIDC integration for the app

The app talks to exactly one downstream OIDC provider. The broker talks to many upstream IdPs.

Examples from vendor docs:

- Auth0 supports identifier-first login and HRD based on enterprise connection domains, redirecting users based on email domain.
- Okta supports external IdPs, IdP Discovery routing rules, account linking, and JIT provisioning.
- Keycloak supports identity brokering and can broker both OIDC and SAML IdPs.

This matches NeMo well because NeMo already knows how to be an OIDC relying party. It does **not** know how to be a multi-protocol identity broker.

### Pattern 2: Native multi-provider auth inside the app

The app itself owns:

- provider registry
- routing rules
- login UX
- callback handling
- token validation for many issuers
- account linking
- provider-specific claim normalization

This is possible, but expensive and security-sensitive. It turns NeMo from "OIDC consumer" into "identity platform."

### Pattern 3: Separate deployment per tenant

For strong isolation, each tenant gets:

- separate NeMo deployment
- separate auth config
- separate DB and persistent stores
- separate secrets
- separate ingress / hostname
- separate admin surface

This is the cleanest interpretation of your tenant-isolation requirement.

## External Research

### Auth0: identifier-first and HRD

Auth0 documents an identifier-first flow where the user enters email first, and if the email domain matches a configured enterprise connection domain, the user is redirected to that enterprise IdP. Auth0 explicitly calls this HRD.

Source:

- Auth0, "Configure Identifier First Authentication": https://auth0.com/docs/authenticate/login/auth0-universal-login/identifier-first

Why it matters for NeMo:

- this is the exact UX pattern Studio would need if one deployment supports many enterprise IdPs
- NeMo does not have this UX today

### Okta: external IdPs, account linking, JIT, and IdP discovery

Okta documents:

- external OIDC and SAML IdPs
- account linking so many IdP identities map to one Okta user
- JIT provisioning
- IdP Discovery routing rules

Sources:

- Okta, "External Identity Providers": https://developer.okta.com/docs/concepts/identity-providers/
- Okta, "Add an enterprise identity provider": https://developer.okta.com/docs/guides/add-an-external-idp/

Why it matters for NeMo:

- this is the feature envelope enterprises will expect if we claim "multiple IdPs"
- it also shows why brokering is attractive: app speaks OIDC once, broker handles the rest

### Auth0: account linking is not automatic and must be done carefully

Auth0 documents that identities are separate by default and that account linking should require authentication for both accounts before linking.

Source:

- Auth0, "User Account Linking": https://auth0.com/docs/manage-users/user-accounts/user-account-linking

Why it matters for NeMo:

- "same email across providers" is not enough to merge identities safely
- if NeMo ever owns account linking, it must be deliberate, audited, and re-authenticated

### Microsoft Entra ID: multitenant issuer handling is stricter than single-tenant

Microsoft documents that multitenant apps must validate tokens differently because the issuer varies by tenant, and that `/common` or `/organizations` sign-in requires tenant-aware issuer validation.

Sources:

- Microsoft Learn, "Convert single-tenant app to multitenant on Microsoft Entra ID": https://learn.microsoft.com/en-us/entra/identity-platform/howto-convert-app-to-be-multi-tenant
- Microsoft Learn, "OpenID Connect (OIDC) on the Microsoft identity platform": https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc

Why it matters for NeMo:

- the current `additional_issuers` pattern is not a general answer for arbitrary multi-tenant / multi-issuer acceptance
- any direct support for many Entra tenants needs issuer-aware key lookup and stricter tenant binding

### OIDC core: `login_hint`

OpenID Connect defines `login_hint` as a way for the RP to pass an email, phone number, or username to the OP as a hint.

Source:

- OpenID Foundation, "OpenID Connect Core 1.0": https://openid.net/specs/openid-connect-core-1_0.html

Why it matters for NeMo:

- if NeMo uses a broker or a provider that supports it, email-first discovery can hand off the identifier cleanly
- for Entra specifically, `domain_hint` can skip email-based discovery in federated setups

### Keycloak: identity brokering for OIDC and SAML

Keycloak documents:

- Identity Provider Redirector in auth flows
- configuring generic OIDC IdPs
- configuring SAML IdPs

Source:

- Keycloak Server Administration Guide: https://www.keycloak.org/docs/latest/server_admin/

Why it matters for NeMo:

- Keycloak is a realistic self-hosted broker option if NVIDIA does not want a managed CIAM dependency

## Recommendation 1: keep NeMo as an OIDC consumer, not an identity broker

This is the strongest recommendation in the document.

For one NeMo deployment that needs many upstream IdPs, put a broker in front:

- managed: Auth0, Okta, WorkOS, Microsoft Entra External ID
- self-hosted: Keycloak

Then configure NeMo to trust **one** broker-issued OIDC issuer per deployment.

Benefits:

- minimal changes to NeMo auth core
- OIDC and SAML can both be supported upstream
- HRD / IdP routing is delegated to software built for it
- account linking stays out of NeMo
- CLI and Studio stay downstream OIDC clients instead of becoming provider routers

Tradeoff:

- adds broker dependency and operational surface

This tradeoff is still much cheaper than turning NeMo into a multi-provider IAM product.

## Recommendation 2: tenant isolation should mean separate NeMo deployments

If the tenant boundary must be strong, the right unit is a deployment, not a workspace.

Each tenant should get:

- separate NeMo Platform instance
- separate database
- separate files / buckets / storage prefixes with separate credentials
- separate secrets backend or namespace
- separate auth broker / auth app config
- separate ingress hostname
- separate telemetry labels and audit sinks

Within each tenant deployment, keep using workspaces for teams, environments, and projects.

That gives a clean layering:

- **deployment** = tenant boundary
- **workspace** = team/project boundary inside a tenant

## Recommendation 3: if native multi-IdP is still required, limit phase 1 to OIDC-only

If product direction insists on native support inside NeMo, do not start with SAML.

Start with:

- multiple OIDC issuers
- explicit provider aliases
- domain / organization routing
- no account linking in phase 1

Then decide later whether SAML belongs in NeMo at all.

## What Would Be Required for Native Multi-IdP in NeMo

This section assumes we ignore Recommendation 1 and build it in-repo.

### 1. New auth configuration model

Replace:

```yaml
auth:
  oidc:
    issuer: ...
    client_id: ...
```

with something like:

```yaml
auth:
  providers:
    - alias: entra-acme
      protocol: oidc
      issuer: https://login.microsoftonline.com/<tenant>/v2.0
      client_id: ...
      audience: ...
      email_claim: upn
      subject_claim: oid
      groups_claim: groups
      domains:
        - acme.com
    - alias: okta-foo
      protocol: oidc
      issuer: https://foo.okta.com/oauth2/default
      client_id: ...
      audience: ...
      domains:
        - foo.com
```

Likely future extension:

- SAML providers with metadata URL / entity ID / ACS settings

### 2. Provider registry and routing rules

NeMo would need a first-class provider registry with:

- alias
- protocol
- issuer / metadata
- client settings
- claim mapping
- allowed domains
- optional organization IDs
- enable/disable state

And routing rules such as:

- email domain -> provider alias
- explicit org slug -> provider alias
- default provider for unmanaged users

### 3. Discovery API redesign

Current discovery returns one `oidc` object. Native multi-IdP would require something more like:

- list of providers
- whether provider selection is user-facing
- an HRD endpoint
- browser auth initiation endpoints per provider
- CLI-compatible provider metadata

This would be a breaking change for CLI/SDK bootstrap unless versioned carefully.

### 4. Studio login UX redesign

Today Studio auto-redirects to one authority. Native multi-IdP would require:

- pre-login page
- email-first flow, or org slug input, or provider buttons
- callback handling per provider
- support for `login_hint` and possibly provider-specific params like Entra `domain_hint`

Because Studio uses `react-oidc-context` against one authority today, the cleanest implementation would likely be:

- a NeMo-owned broker endpoint, or
- a broker outside Studio that exposes one stable downstream authority

Directly teaching Studio to dynamically instantiate many OIDC authorities is possible, but it is still more complex than brokering.

### 5. CLI login redesign

Current CLI discovery assumes one client ID and one token endpoint. That works for a single downstream OIDC provider and for device flow.

Problems for native multi-IdP:

- which provider should `nemo auth login` use?
- SAML does not map cleanly to device flow
- some enterprise IdPs do not expose device flow in the same way the current NeMo CLI expects

CLI would need one or more of:

- `nemo auth login --provider <alias>`
- `nemo auth login --org <slug>`
- browser-based code+PKCE flow instead of device flow for some providers

This is another reason a downstream broker is attractive: the CLI still only needs one OIDC contract.

### 6. Identity model changes

This is one of the biggest design changes.

Today the docs describe principals as typically identified by email. That is not strong enough for cross-IdP identity.

Native multi-IdP needs:

- canonical principal key: internal UUID
- external identity table: `(provider_alias, subject)` unique
- email stored as attribute, not identity key
- email verification state
- account status and link provenance

Suggested shape:

- `users`
  - `id`
  - `primary_email`
  - `display_name`
  - `status`
- `external_identities`
  - `user_id`
  - `provider_alias`
  - `subject`
  - `email`
  - `email_verified`
  - `raw_claims_snapshot`
  - `linked_at`

Without this, email collisions and account takeover risks become very real.

### 7. Account linking policy

If NeMo owns cross-IdP SSO for the same person, it needs explicit policy for:

- user-initiated linking
- admin-assisted linking
- suggested linking when verified emails match
- forbidden automatic linking when email is unverified or provider is low trust

Minimum safe rule:

- no silent linking based only on same email
- require active authentication on both accounts before link creation
- audit every link / unlink action

### 8. Group and claim normalization

Group semantics differ by provider:

- Entra groups
- Okta groups
- Keycloak realm roles / client roles
- SAML attributes

NeMo would need:

- per-provider claim mapping
- optional group transformation
- optional group-to-role binding automation
- size and overage handling for providers that emit many groups

The current "one groups claim name" model is not enough for this.

### 9. Provisioning model

Native multi-IdP also raises user lifecycle questions:

- JIT provisioning on first login?
- pre-provisioned users only?
- SCIM inbound sync later?
- deprovision behavior when upstream account is disabled?

Phase 1 can likely survive with:

- JIT user record creation
- no SCIM
- role assignment still handled by NeMo workspace membership

But enterprise buyers will quickly ask for:

- SCIM
- group sync
- org-scoped user inventory

### 10. Authorization model adjustments

Workspace RBAC can stay, but some additions become likely:

- organization / tenant entity above workspace
- workspace ownership by organization
- provider-to-organization mapping
- org-scoped admin roles

If one deployment hosts many organizations, you do not want global wildcard patterns like `*` to span all orgs unintentionally.

This is a subtle but important risk in the current model.

### 11. Security and audit requirements

Native multi-IdP expands the security surface materially.

NeMo would need:

- secure routing rule evaluation
- callback CSRF/state validation per provider
- nonce / PKCE rigor
- account-link audit trail
- provider config change audit trail
- replay / confused-deputy protections
- stronger principal provenance in logs

## What Would Be Required for SAML Support

If "multiple types of IdPs" includes SAML, there are two realistic options:

### Option A: use a broker that converts SAML upstream to OIDC downstream

This is the recommended path.

NeMo continues to speak OIDC only.

### Option B: teach NeMo to be both OIDC RP and SAML SP

That requires:

- SAML metadata handling
- certificate rollover
- ACS endpoints
- NameID / attribute mapping
- SP-initiated and maybe IdP-initiated flow policy
- logout behavior decisions
- more frontend and CLI complexity

This is a large scope increase and does not appear justified while NeMo still has single-provider OIDC assumptions everywhere else.

## What "Completely Separate Instance Per Tenant" Implies

If the product requirement is hard isolation, the platform should model tenancy as deployment orchestration, not as shared runtime policy.

Each tenant deployment should have:

- dedicated auth configuration
- dedicated NeMo DB
- dedicated object/file storage namespace with dedicated credentials
- dedicated secrets namespace
- dedicated ingress hostname
- dedicated runtime config and feature flags
- dedicated audit and telemetry partitioning

Recommended shape:

- `tenant-a.nemo.example.com`
- `tenant-b.nemo.example.com`

Each points to a different NeMo installation.

Possible management-plane responsibilities:

- tenant provisioning
- DNS / TLS issuance
- broker or IdP connection setup
- deployment rollout / upgrades
- tenant suspension / deletion
- fleet health dashboard

This can be a control plane later. It does not need to exist before tenant isolation.

## Preferred Architecture Options

### Option 1: external identity broker + one NeMo deployment per tenant

Shape:

- per tenant: one broker realm / org / auth app
- per tenant: one NeMo deployment
- upstream: many customer IdPs if needed
- downstream into NeMo: one OIDC issuer

Pros:

- strongest isolation
- smallest NeMo code change
- easiest enterprise story

Cons:

- most infrastructure footprint

### Option 2: external identity broker + shared NeMo deployment for many orgs

Shape:

- one NeMo deployment
- broker handles many orgs and many IdPs
- NeMo uses workspace/org RBAC for isolation

Pros:

- cheaper footprint
- fastest path to multi-IdP

Cons:

- fails your strict tenant-isolation requirement
- shared blast radius

### Option 3: native NeMo multi-IdP + shared deployment

Pros:

- fewer external dependencies on paper

Cons:

- large engineering and security surface
- still does not solve tenant isolation by itself
- forces Studio and CLI redesign

This is the least attractive option.

## Recommended Incremental Roadmap

### Phase 0: state the product boundary clearly

Document:

- workspaces are not tenants
- current auth is single-provider OIDC
- SAML and multi-IdP require a broker today

### Phase 1: formalize "bring your own broker"

Productize the current best path:

- validate NeMo against one brokered OIDC issuer
- document supported brokers
- document claim mapping and group mapping recipes
- document HRD via broker

Likely repo work:

- tighten docs
- add tested examples for Auth0 / Okta / Keycloak / Entra External ID
- possibly add better `subject_claim` / `email_claim` guidance per provider

### Phase 2: make one deployment broker-friendly

Small NeMo improvements that help without making NeMo the broker:

- richer claim mapping support
- explicit internal principal UUID instead of email-centric assumptions
- better audit metadata for source issuer / subject
- safer Studio defaulting than `email.split('@')[0]`

### Phase 3: isolated tenant deployment model

Build automation for:

- per-tenant deployment provisioning
- per-tenant auth configuration
- per-tenant DNS / ingress / storage / secrets

### Phase 4: revisit native multi-IdP only if still necessary

Only after phases 1-3 should NeMo consider:

- provider registry
- HRD UI
- account linking
- SAML SP support

## Concrete Repo Touchpoints If Work Proceeds

If NeMo implements any part of this, the main code surfaces are:

- auth config model:
  [packages/nmp_common/src/nmp/common/config/base.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/config/base.py:89)
- token validation:
  [packages/nmp_common/src/nmp/common/auth/jwt.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/auth/jwt.py:43)
- auth discovery:
  [services/core/auth/src/nmp/core/auth/api/v2/discovery/endpoints.py](/Users/rsadler/src/nemo-platform/services/core/auth/src/nmp/core/auth/api/v2/discovery/endpoints.py:24)
- middleware and principal propagation:
  [packages/nmp_common/src/nmp/common/auth/middleware.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/auth/middleware.py:1)
  [packages/nmp_common/src/nmp/common/auth/models.py](/Users/rsadler/src/nemo-platform/packages/nmp_common/src/nmp/common/auth/models.py:1)
- Studio auth runtime:
  [web/packages/studio/src/constants/environment.ts](/Users/rsadler/src/nemo-platform/web/packages/studio/src/constants/environment.ts:64)
  [web/packages/studio/src/providers/auth/useAuthLogin.ts](/Users/rsadler/src/nemo-platform/web/packages/studio/src/providers/auth/useAuthLogin.ts:16)
  [web/packages/studio/src/providers/auth/useAuthProfile.ts](/Users/rsadler/src/nemo-platform/web/packages/studio/src/providers/auth/useAuthProfile.ts:18)
- docs that should be updated with product boundaries:
  [docs/auth/security-model.md](/Users/rsadler/src/nemo-platform/docs/auth/security-model.md:172)
  [docs/get-started/concepts/workspaces.md](/Users/rsadler/src/nemo-platform/docs/get-started/concepts/workspaces.md:4)

## Open Questions

These should be answered before implementation planning:

1. Is the real target "many customer IdPs for one shared SaaS deployment", or "a deployment template that each customer installs separately"?
2. Is SAML a hard day-1 requirement, or is OIDC-first acceptable?
3. Must the CLI support all enterprise SSO paths, or is browser-based Studio login sufficient at first?
4. Do we want NeMo to own user lifecycle and account linking, or should that remain in an upstream broker?
5. Is a managed CIAM dependency acceptable, or must the solution be self-hosted?

## Final Recommendation

For NeMo Platform, the technically sound path is:

1. **Do not implement native multi-IdP first.**
2. **Use an identity broker in front of NeMo for multi-IdP and SAML.**
3. **Treat strict tenant isolation as separate NeMo deployments, not shared-workspace multitenancy.**
4. **Keep workspaces as intra-tenant segmentation only.**

That path aligns with the current repo architecture, minimizes auth risk, and matches the enterprise requirement more honestly than trying to stretch workspace RBAC into tenant isolation.
