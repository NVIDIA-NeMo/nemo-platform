// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
import { Button as e, Flex as t, Stack as n, Text as r } from "@nvidia/foundations-react-core";
import { NavLink as i, Navigate as a, Outlet as o, Route as s, Routes as c } from "react-router-dom";
import { jsx as l, jsxs as u } from "react/jsx-runtime";
//#region src/Root.tsx
function d({ host: e }) {
	return /* @__PURE__ */ l(c, { children: /* @__PURE__ */ u(s, {
		element: /* @__PURE__ */ l(f, {}),
		children: [
			/* @__PURE__ */ l(s, {
				index: !0,
				element: /* @__PURE__ */ l(a, {
					to: "overview",
					replace: !0
				})
			}),
			/* @__PURE__ */ l(s, {
				path: "overview",
				element: /* @__PURE__ */ l(m, { host: e })
			}),
			/* @__PURE__ */ l(s, {
				path: "auth",
				element: /* @__PURE__ */ l(h, { getAccessToken: e.auth.getAccessToken })
			}),
			/* @__PURE__ */ l(s, {
				path: "workspace",
				element: /* @__PURE__ */ l(g, { workspaceId: e.workspaceId })
			}),
			/* @__PURE__ */ l(s, {
				path: "*",
				element: /* @__PURE__ */ l(_, {})
			})
		]
	}) });
}
function f() {
	let e = ({ isActive: e }) => `px-3 py-1 rounded text-sm font-medium transition-colors ${e ? "text-primary bg-surface-hover" : "text-subtle hover:text-primary"}`;
	return /* @__PURE__ */ u(n, {
		gap: "4",
		className: "h-full p-4",
		children: [/* @__PURE__ */ u(t, {
			gap: "2",
			className: "border-b border-subtle pb-2",
			children: [
				/* @__PURE__ */ l(i, {
					to: "overview",
					className: e,
					children: "Overview"
				}),
				/* @__PURE__ */ l(i, {
					to: "auth",
					className: e,
					children: "Auth"
				}),
				/* @__PURE__ */ l(i, {
					to: "workspace",
					className: e,
					children: "Workspace"
				})
			]
		}), /* @__PURE__ */ l("div", {
			className: "flex-1",
			children: /* @__PURE__ */ l(o, {})
		})]
	});
}
function p({ children: e }) {
	return /* @__PURE__ */ l("pre", {
		className: "bg-surface-sunken text-subtle rounded p-3 text-xs overflow-x-auto font-mono",
		children: e
	});
}
function m({ host: i }) {
	let { data: a, isPending: o, isError: s } = i.sdk.platform.useEntitiesListWorkspaces({
		page: 1,
		page_size: 100
	}, { query: { staleTime: 5e3 } }), c = a?.data ?? [];
	return /* @__PURE__ */ u(n, {
		gap: "2",
		children: [
			/* @__PURE__ */ l(r, {
				kind: "label/bold/lg",
				children: "Example Plugin"
			}),
			/* @__PURE__ */ l(r, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "This is an example Studio plugin. Use the tabs above or the Studio side nav to explore what information is available to a plugin at runtime."
			}),
			/* @__PURE__ */ u(n, {
				gap: "1",
				children: [
					/* @__PURE__ */ l(r, {
						kind: "label/bold/sm",
						children: "Shared SDK"
					}),
					/* @__PURE__ */ l(r, {
						kind: "body/regular/xs",
						color: "secondary",
						children: "Listed via Studio's sdk.platform.useEntitiesListWorkspaces() — the platform's typed hook, running on Studio's authenticated axios and shared QueryClient rather than a plugin copy."
					}),
					o ? /* @__PURE__ */ l(r, {
						kind: "body/regular/xs",
						color: "secondary",
						children: "Loading…"
					}) : s ? /* @__PURE__ */ l(r, {
						kind: "body/regular/xs",
						color: "danger",
						children: "Request failed."
					}) : /* @__PURE__ */ u(r, {
						kind: "body/regular/sm",
						children: [
							c.length,
							" workspaces: ",
							c.map((e) => e.name).join(", ")
						]
					})
				]
			}),
			/* @__PURE__ */ u(n, {
				gap: "1",
				children: [
					/* @__PURE__ */ l(r, {
						kind: "label/bold/sm",
						children: "Host capabilities"
					}),
					/* @__PURE__ */ l(r, {
						kind: "body/regular/xs",
						color: "secondary",
						children: "Studio's notifications, telemetry, and navigation, all off the host handle — no plugin-side setup."
					}),
					/* @__PURE__ */ u(t, {
						gap: "2",
						children: [/* @__PURE__ */ l(e, {
							kind: "secondary",
							onClick: () => {
								i.notifications.notify("Toast from the example plugin", "success"), i.telemetry.event("overview_notify_clicked");
							},
							children: "Notify"
						}), /* @__PURE__ */ l(e, {
							kind: "secondary",
							onClick: () => i.navigation.navigate(`/workspaces/${i.workspaceId}/base-models`),
							children: "Go to Base Models"
						})]
					})
				]
			})
		]
	});
}
function h({ getAccessToken: e }) {
	let t = e(), i = null;
	try {
		let e = t.split(".")[1];
		e && (i = JSON.parse(atob(e.replace(/-/g, "+").replace(/_/g, "/"))));
	} catch {}
	return /* @__PURE__ */ u(n, {
		gap: "3",
		children: [
			/* @__PURE__ */ l(r, {
				kind: "label/bold/md",
				children: "Auth"
			}),
			/* @__PURE__ */ l(r, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "Studio passes an OIDC access token to every plugin via the plugin's auth prop. Call getAccessToken() per request — it returns the current token after silent renewal — and use it as a Bearer token."
			}),
			/* @__PURE__ */ u(n, {
				gap: "1",
				children: [/* @__PURE__ */ l(r, {
					kind: "label/bold/sm",
					children: "Example API call"
				}), /* @__PURE__ */ l(p, { children: "fetch('/apis/v1/workspaces', {\n  headers: { Authorization: `Bearer ${getAccessToken()}` },\n})" })]
			}),
			/* @__PURE__ */ u(n, {
				gap: "1",
				children: [/* @__PURE__ */ l(r, {
					kind: "label/bold/sm",
					children: "Token claims (decoded, not verified)"
				}), i ? /* @__PURE__ */ l(p, { children: JSON.stringify(i, null, 2) }) : /* @__PURE__ */ l(r, {
					kind: "body/regular/xs",
					color: "secondary",
					children: t ? "Could not decode token." : "No token provided."
				})]
			})
		]
	});
}
function g({ workspaceId: e }) {
	return /* @__PURE__ */ u(n, {
		gap: "3",
		children: [
			/* @__PURE__ */ l(r, {
				kind: "label/bold/md",
				children: "Workspace"
			}),
			/* @__PURE__ */ l(r, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "Studio passes the current workspace ID to every plugin via the plugin's workspaceId prop."
			}),
			/* @__PURE__ */ u(n, {
				gap: "1",
				children: [/* @__PURE__ */ l(r, {
					kind: "label/bold/sm",
					children: "Current workspace"
				}), /* @__PURE__ */ l(p, { children: e })]
			}),
			/* @__PURE__ */ u(n, {
				gap: "1",
				children: [/* @__PURE__ */ l(r, {
					kind: "label/bold/sm",
					children: "Example API call scoped to this workspace"
				}), /* @__PURE__ */ l(p, { children: "fetch(`/apis/v1/workspaces/${workspaceId}/models`, {\n  headers: { Authorization: `Bearer ${getAccessToken()}` },\n})" })]
			})
		]
	});
}
function _() {
	return /* @__PURE__ */ l(r, {
		kind: "body/regular/sm",
		color: "secondary",
		children: "Page not found."
	});
}
//#endregion
//#region src/Nav.tsx
var v = (e) => [{
	group: "Example Plugin",
	items: [
		{
			id: "example-overview",
			iconName: "flask-conical",
			label: "Overview",
			href: `/workspaces/${e}/plugin/example/overview`
		},
		{
			id: "example-auth",
			iconName: "key-round",
			label: "Auth",
			href: `/workspaces/${e}/plugin/example/auth`
		},
		{
			id: "example-workspace",
			iconName: "building-2",
			label: "Workspace",
			href: `/workspaces/${e}/plugin/example/workspace`
		}
	]
}];
//#endregion
export { d as Root, v as navItems };
