# Brian Auth Call

## Executive Summary

This conversation clarified the emerging authentication direction for NeMo Platform and surfaced the major gaps that still need to be closed. The architectural preference is to keep authentication primarily outside the platform by relying on customer-managed identity providers (IDPs), while NeMo Platform focuses on authorization, internal role handling, and plugin-extensible permissions. That direction is considered technically sound, but the current user experience is still incomplete.

The most important immediate gap is that there is no translation layer today between external OIDC scopes and NeMo Platform scopes. That makes enterprise identity integration conceptually viable but operationally incomplete. In parallel, documentation is missing for the recommended path, especially for enterprise service accounts, API keys, and common IDP setups. Several people see that as the fastest way to reduce friction in the short term.

The discussion also placed authentication in a broader strategic frame. NeMo Platform may become part of a larger "One NeMo" platform story that connects NVIDIA products, plugins, and agent workflows. Within that vision, Agent Optimizer appears likely to be a major product driver and power-user entry point, which means its needs may materially influence platform priorities, including auth.

The practical next step coming out of the call is to validate the enterprise path from a customer perspective using Entra, document what is required, and use that as input for both platform documentation and future product work.

## Meeting Context

The discussion was driven by real friction experienced while trying to use the platform in practice. That experience created concern that NeMo Platform is still too difficult for teams that want to move quickly, especially those trying to get from experimentation to working product behavior without a large amount of platform-specific setup.

There was broad alignment that the platform needs a clearer authentication story, stronger developer experience, and better written guidance. At the same time, the participants acknowledged that the product and platform have been changing rapidly, which has contributed both to real gaps and to inconsistent understanding across teams.

## Key Themes

### 1. Preferred Authentication Model

The dominant architectural position in the conversation was that NeMo Platform should avoid owning full authentication if possible. Instead, customers should be able to bring their own identity provider, and the platform should accept identity information from that upstream system.

In this model:

- Authentication is handled externally by an IDP or a gateway.
- NeMo Platform consumes authenticated identity context rather than becoming the identity system itself.
- The platform's core responsibility is authorization: roles, permissions, policy boundaries, and plugin-aware access control.

This approach was viewed as cleaner from an architecture standpoint and more aligned with enterprise deployment expectations.

### 2. Current Experience Is Still Too Hard

Even though the high-level architecture makes sense, the current experience was described as difficult. The pain point is not theoretical. It comes from teams trying to use the platform directly and finding it hard to get running in a straightforward way.

The conversation highlighted that users who want to move quickly should not need to solve a complicated enterprise authentication integration before they can get value out of the platform. That is especially relevant for startup-style users or internal builders trying to experiment fast.

### 3. Documentation Is a Critical Gap

One of the strongest points of agreement was that the platform needs better authentication documentation immediately. Several forms of documentation were implied or explicitly requested:

- A written authentication story that explains the intended model.
- Recipes for integrating common IDPs.
- Quickstarts for practical setup.
- Enterprise-oriented guidance for service accounts and API key flows.
- Blueprint-style docs that shorten time to first success.

The group viewed this as one of the fastest ways to reduce friction while deeper product gaps are still being worked out.

### 4. Authorization Is More Central Than Authentication

A meaningful distinction was made between authentication and authorization. Authentication is something the platform would ideally consume from upstream systems. Authorization, by contrast, is deeply tied to the platform itself.

This is particularly important because NeMo Platform needs to support:

- plugin-defined roles,
- internal platform scopes,
- role bindings,
- and future extensibility for product-specific permission models.

The current work appears to be more focused on making authorization extensible, especially so plugins can define and use their own custom roles.

### 5. Missing Scope Translation Layer

The most concrete technical gap identified in the call was the lack of a mapping layer between external OIDC scopes and NeMo Platform scopes.

That means the platform may be able to authenticate a user or service principal through an upstream IDP, but it still lacks the internal translation needed to turn that identity data into meaningful platform permissions in a clean and supported way.

This gap was treated as one of the most obvious missing pieces in the current design.

## Target Users and Product Tension

The conversation identified three especially relevant user groups:

- Enterprise customers who want a robust IDP-integrated deployment model.
- Startup-style builders who want to move quickly and avoid heavy setup.
- ML engineers who want a local-first workflow for experimentation.

These audiences create competing pressures:

- Enterprise customers increase the need for mature auth and authorization integration.
- Startup users increase pressure for minimal-friction onboarding.
- Local ML engineers reinforce the need for fast setup and smooth experimentation.

The discussion suggested that enterprise needs are clearly on the roadmap, while startup-friendly support is understood as valuable but may not yet be formally prioritized. That creates some risk that simpler auth paths remain underdeveloped unless they are tied to broader strategic goals.

## Startup-Friendly Auth Remains an Open Question

The conversation explored the possibility of a middle-ground experience for smaller teams. Rather than requiring a full enterprise identity integration, the platform might eventually support a lighter-weight setup such as:

- social login,
- a minimal IDP path,
- a native API key experience,
- or a dedicated auth plugin that can be enabled when needed.

This idea was seen as appealing from a usability standpoint because many products offer simple login or API key flows without forcing a full identity rollout. At the same time, there was concern that such a feature could easily add product clutter if it is not carefully scoped.

So the concept has support, but it is still exploratory rather than committed.

## Enterprise Alignment

The conversation made clear that enterprise auth is already a known gap in the platform's broader product offering. Enterprise stakeholders want to improve the situation, and auth is considered part of that gap.

That creates useful alignment:

- The platform already needs a stronger enterprise auth story.
- The Agent Optimizer team and other platform users can provide concrete pressure and real use cases.
- Improvements in this area are likely to have value beyond a single team.

The timing was therefore seen as favorable for formalizing the auth approach.

## Agent Optimizer as a Strategic Driver

A major product theme in the conversation was that Agent Optimizer may become a central use case for NeMo Platform. The team working on it was described as likely to become a major power user of the platform, with significant influence over what gets prioritized.

The implication is that:

- if Agent Optimizer needs better auth support, the platform may respond quickly,
- product gaps exposed by that team are likely to matter,
- and their requests may help unlock additional investment or execution focus.

This matters because the authentication discussion is not happening in isolation. It is taking place inside a broader shift in how NeMo Platform may be positioned and adopted.

## The "One NeMo" Platform Vision

The conversation also surfaced a larger strategic narrative. Across NVIDIA, the word "NeMo" is used in many places, but there is not yet a coherent story tying those efforts together. One view expressed in the meeting is that NeMo Platform could become part of that unifying layer.

In this framing, NeMo Platform could serve as a path that connects:

- research outputs,
- product capabilities,
- plugins,
- CLIs,
- and customer-facing delivery.

Agent Optimizer was discussed as a possible entry point through which customers begin discovering and using a broader set of NVIDIA capabilities. If that becomes true, then authentication and authorization become foundational platform concerns rather than isolated infrastructure details.

## Current State of Deployments

There was visible uncertainty during the conversation about what is actually running in development environments and how far authentication support has progressed.

Some believed that Entra integration had regressed or was no longer meaningfully working. During the call, however, a working login flow appeared to exist in at least one recent deployment. This led to the realization that deployment status, environment freshness, and current feature state are not consistently understood across the team.

That confusion matters because it suggests two parallel problems:

- some platform capabilities may exist but be poorly communicated,
- and some gaps may be worsened by weak shared visibility into what is deployed and supported.

This reinforced the need for better written documentation and stronger internal alignment.

## Entra as the Immediate Enterprise Path

By the end of the call, the most practical enterprise path appeared to be Entra-based authentication. The working assumption became:

- Entra login appears to be functioning in at least some deployment flow.
- A customer may be able to create a service account or API key in Entra.
- That identity can potentially be used with NeMo Platform once role bindings and permissions are configured.
- The missing piece is the translation from external scopes to internal NeMo permissions.

So the challenge is no longer just "can login work?" but "what is the full supported machine and service identity story?"

## The Current State: Customer Responsibility

One of the clearest summary statements in the meeting was that, today, authentication is effectively the customer's responsibility.

That was treated as an accurate description of the current state, but not a sufficient end state. The desired future is not necessarily that NeMo Platform owns all auth directly. Rather, the goal is to reduce burden on the customer by providing:

- clearer options,
- better docs,
- supported patterns,
- easier integration,
- and possibly selective built-in helpers where they add real value.

## Possible Deliverables Discussed

Several potential outputs were implied by the conversation:

- an auth spec or RFC,
- a formal written authentication story,
- enterprise setup documentation,
- customer-style walkthroughs for Entra,
- quickstart recipes for common IDPs,
- and possibly a proposal for native API key support through a plugin or optional built-in path.

These were not all formal commitments, but they represent the most concrete work products suggested in the discussion.

## Agreed Near-Term Next Step

The clearest next step was practical rather than abstract. Brian planned to try to solve the auth problem in Entra the way a real customer would, then document what was required.

That was seen as valuable for several reasons:

- It tests the recommended enterprise path in reality.
- It produces a concrete example rather than an architectural abstraction.
- It generates material that can become documentation.
- It reveals where additional product work is truly needed.

The call ended with a sense that this path is likely enough to unblock immediate internal needs, even if broader product improvements still remain ahead.

## Risks and Open Questions

The meeting surfaced several unresolved tensions and risks:

- The platform may remain too tactical if it does not anchor on a clearer long-term product direction.
- Startup-friendly auth may continue to lag if it is not tied to roadmap priorities.
- The lack of a shared mental model across teams may continue to create confusion about what works today.
- Enterprise auth may be directionally correct but still hard to operate until scope mapping and documentation are complete.
- Agent Optimizer may become the main driver of platform evolution, which is helpful for momentum but could create tension with other customer needs.

There is also a more strategic uncertainty: customers are not yet clearly asking for Agent Optimizer as a product category, but that may simply be because the product has not yet been clearly delivered or positioned.

## Overall Assessment

The meeting produced a coherent directional answer, even if it did not produce a finished auth plan. The direction is to rely on external identity providers for authentication, invest inside the platform on authorization and plugin-extensible roles, and close the near-term usability gaps with documentation and a missing scope translation layer.

This is a reasonable enterprise-oriented architecture, but it is not yet a complete customer experience. The platform still needs better written guidance, validated integration paths, and clearer support for service accounts, API keys, and scope mapping. The next useful move is to document the Entra path from the perspective of an actual customer and use that exercise to sharpen both the product and the docs.

## Action Items

- Validate the Entra-based customer path for service accounts and API-key-style access.
- Document every required step, dependency, and role-binding assumption in that flow.
- Turn that walkthrough into internal documentation or a draft quickstart.
- Write down the formal NeMo Platform authentication story as a spec or RFC.
- Define the missing OIDC-scope-to-NeMo-scope translation layer.
- Continue evaluating whether a lighter-weight startup-friendly auth option is worth supporting.
