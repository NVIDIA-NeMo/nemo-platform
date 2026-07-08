import { Flex as e, Stack as t, Text as n } from "@nvidia/foundations-react-core";
import { NavLink as r, Navigate as i, Outlet as a, Route as o, Routes as s } from "react-router-dom";
import { jsx as c, jsxs as l } from "react/jsx-runtime";
//#region src/Root.tsx
function u({ workspaceId: e, auth: t }) {
	return /* @__PURE__ */ c(s, { children: /* @__PURE__ */ l(o, {
		element: /* @__PURE__ */ c(d, {}),
		children: [
			/* @__PURE__ */ c(o, {
				index: !0,
				element: /* @__PURE__ */ c(i, {
					to: "overview",
					replace: !0
				})
			}),
			/* @__PURE__ */ c(o, {
				path: "overview",
				element: /* @__PURE__ */ c(p, {})
			}),
			/* @__PURE__ */ c(o, {
				path: "auth",
				element: /* @__PURE__ */ c(m, { getAccessToken: t.getAccessToken })
			}),
			/* @__PURE__ */ c(o, {
				path: "workspace",
				element: /* @__PURE__ */ c(h, { workspaceId: e })
			}),
			/* @__PURE__ */ c(o, {
				path: "*",
				element: /* @__PURE__ */ c(g, {})
			})
		]
	}) });
}
function d() {
	let n = ({ isActive: e }) => `px-3 py-1 rounded text-sm font-medium transition-colors ${e ? "text-primary bg-surface-hover" : "text-subtle hover:text-primary"}`;
	return /* @__PURE__ */ l(t, {
		gap: "4",
		className: "h-full p-4",
		children: [/* @__PURE__ */ l(e, {
			gap: "2",
			className: "border-b border-subtle pb-2",
			children: [
				/* @__PURE__ */ c(r, {
					to: "overview",
					className: n,
					children: "Overview"
				}),
				/* @__PURE__ */ c(r, {
					to: "auth",
					className: n,
					children: "Auth"
				}),
				/* @__PURE__ */ c(r, {
					to: "workspace",
					className: n,
					children: "Workspace"
				})
			]
		}), /* @__PURE__ */ c("div", {
			className: "flex-1",
			children: /* @__PURE__ */ c(a, {})
		})]
	});
}
function f({ children: e }) {
	return /* @__PURE__ */ c("pre", {
		className: "bg-surface-sunken text-subtle rounded p-3 text-xs overflow-x-auto font-mono",
		children: e
	});
}
function p() {
	return /* @__PURE__ */ l(t, {
		gap: "2",
		children: [/* @__PURE__ */ c(n, {
			kind: "label/bold/lg",
			children: "Example Plugin"
		}), /* @__PURE__ */ c(n, {
			kind: "body/regular/sm",
			color: "secondary",
			children: "This is an example Studio plugin. Use the tabs above or the Studio side nav to explore what information is available to a plugin at runtime."
		})]
	});
}
function m({ getAccessToken: e }) {
	let r = e(), i = null;
	try {
		let e = r.split(".")[1];
		e && (i = JSON.parse(atob(e.replace(/-/g, "+").replace(/_/g, "/"))));
	} catch {}
	return /* @__PURE__ */ l(t, {
		gap: "3",
		children: [
			/* @__PURE__ */ c(n, {
				kind: "label/bold/md",
				children: "Auth"
			}),
			/* @__PURE__ */ c(n, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "Studio passes an OIDC access token to every plugin via the plugin's auth prop. Call getAccessToken() per request — it returns the current token after silent renewal — and use it as a Bearer token."
			}),
			/* @__PURE__ */ l(t, {
				gap: "1",
				children: [/* @__PURE__ */ c(n, {
					kind: "label/bold/sm",
					children: "Example API call"
				}), /* @__PURE__ */ c(f, { children: "fetch('/apis/v1/workspaces', {\n  headers: { Authorization: `Bearer ${getAccessToken()}` },\n})" })]
			}),
			/* @__PURE__ */ l(t, {
				gap: "1",
				children: [/* @__PURE__ */ c(n, {
					kind: "label/bold/sm",
					children: "Token claims (decoded, not verified)"
				}), i ? /* @__PURE__ */ c(f, { children: JSON.stringify(i, null, 2) }) : /* @__PURE__ */ c(n, {
					kind: "body/regular/xs",
					color: "secondary",
					children: r ? "Could not decode token." : "No token provided."
				})]
			})
		]
	});
}
function h({ workspaceId: e }) {
	return /* @__PURE__ */ l(t, {
		gap: "3",
		children: [
			/* @__PURE__ */ c(n, {
				kind: "label/bold/md",
				children: "Workspace"
			}),
			/* @__PURE__ */ c(n, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "Studio passes the current workspace ID to every plugin via the plugin's workspaceId prop."
			}),
			/* @__PURE__ */ l(t, {
				gap: "1",
				children: [/* @__PURE__ */ c(n, {
					kind: "label/bold/sm",
					children: "Current workspace"
				}), /* @__PURE__ */ c(f, { children: e })]
			}),
			/* @__PURE__ */ l(t, {
				gap: "1",
				children: [/* @__PURE__ */ c(n, {
					kind: "label/bold/sm",
					children: "Example API call scoped to this workspace"
				}), /* @__PURE__ */ c(f, { children: "fetch(`/apis/v1/workspaces/${workspaceId}/models`, {\n  headers: { Authorization: `Bearer ${getAccessToken()}` },\n})" })]
			})
		]
	});
}
function g() {
	return /* @__PURE__ */ c(n, {
		kind: "body/regular/sm",
		color: "secondary",
		children: "Page not found."
	});
}
//#endregion
//#region src/Nav.tsx
var _ = (e) => [{
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
export { u as Root, _ as navItems };
