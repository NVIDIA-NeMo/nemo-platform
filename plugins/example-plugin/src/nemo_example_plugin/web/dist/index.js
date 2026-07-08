// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import e from "react";
import { createRoot as t } from "react-dom/client";
import { BrowserRouter as n, NavLink as r, Navigate as i, Outlet as a, Route as o, Routes as s } from "react-router-dom";
import { jsx as c, jsxs as l } from "react/jsx-runtime";
//#region src/App.tsx
function u({ workspaceId: e, accessToken: t, basename: r }) {
	let a = `/workspaces/${e}/plugin/example`;
	return /* @__PURE__ */ c(n, {
		basename: r,
		children: /* @__PURE__ */ c(s, { children: /* @__PURE__ */ l(o, {
			path: `${a}/*`,
			element: /* @__PURE__ */ c(d, { base: a }),
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
					element: /* @__PURE__ */ c(f, {})
				}),
				/* @__PURE__ */ c(o, {
					path: "auth",
					element: /* @__PURE__ */ c(p, { accessToken: t })
				}),
				/* @__PURE__ */ c(o, {
					path: "workspace",
					element: /* @__PURE__ */ c(m, {
						workspaceId: e,
						accessToken: t
					})
				}),
				/* @__PURE__ */ c(o, {
					path: "*",
					element: /* @__PURE__ */ c(h, {})
				})
			]
		}) })
	});
}
function d({ base: e }) {
	let t = ({ isActive: e }) => `px-3 py-1 rounded text-sm font-medium ${e ? "bg-blue-100 text-blue-700" : "text-gray-600 hover:text-gray-900"}`;
	return /* @__PURE__ */ l("div", {
		className: "flex flex-col h-full p-4 gap-4",
		children: [/* @__PURE__ */ l("nav", {
			className: "flex gap-2 border-b pb-2",
			children: [
				/* @__PURE__ */ c(r, {
					to: "overview",
					className: t,
					children: "Overview"
				}),
				/* @__PURE__ */ c(r, {
					to: "auth",
					className: t,
					children: "Auth"
				}),
				/* @__PURE__ */ c(r, {
					to: "workspace",
					className: t,
					children: "Workspace"
				})
			]
		}), /* @__PURE__ */ c("div", {
			className: "flex-1",
			children: /* @__PURE__ */ c(a, {})
		})]
	});
}
function f() {
	return /* @__PURE__ */ l("div", {
		className: "space-y-2",
		children: [/* @__PURE__ */ c("h1", {
			className: "text-lg font-semibold",
			children: "Example Plugin"
		}), /* @__PURE__ */ c("p", {
			className: "text-sm text-gray-500",
			children: "This is an example Studio plugin. Use the tabs above or the Studio side nav to explore what information is available to a plugin at runtime."
		})]
	});
}
function p({ accessToken: e }) {
	let t = null;
	try {
		let n = e.split(".")[1];
		n && (t = JSON.parse(atob(n.replace(/-/g, "+").replace(/_/g, "/"))));
	} catch {}
	return /* @__PURE__ */ l("div", {
		className: "space-y-3",
		children: [
			/* @__PURE__ */ c("h1", {
				className: "text-lg font-semibold",
				children: "Auth"
			}),
			/* @__PURE__ */ l("p", {
				className: "text-sm text-gray-500",
				children: [
					"Studio passes an OIDC access token to every plugin via",
					" ",
					/* @__PURE__ */ l("code", { children: [
						"mount(container, ",
						"{ auth: { accessToken } }",
						")"
					] }),
					". Use it as a Bearer token when calling platform APIs."
				]
			}),
			/* @__PURE__ */ l("div", {
				className: "space-y-1",
				children: [/* @__PURE__ */ c("h2", {
					className: "text-sm font-medium text-gray-700",
					children: "Example API call"
				}), /* @__PURE__ */ c("pre", {
					className: "text-xs bg-gray-100 rounded p-3 overflow-x-auto",
					children: "fetch('/apis/v1/workspaces', {\n  headers: { Authorization: `Bearer ${accessToken}` },\n})"
				})]
			}),
			/* @__PURE__ */ l("div", {
				className: "space-y-1",
				children: [/* @__PURE__ */ c("h2", {
					className: "text-sm font-medium text-gray-700",
					children: "Token claims (decoded, not verified)"
				}), t ? /* @__PURE__ */ c("pre", {
					className: "text-xs bg-gray-100 rounded p-3 overflow-x-auto",
					children: JSON.stringify(t, null, 2)
				}) : /* @__PURE__ */ c("p", {
					className: "text-xs text-gray-400",
					children: e ? "Could not decode token." : "No token provided."
				})]
			})
		]
	});
}
function m({ workspaceId: e, accessToken: t }) {
	return /* @__PURE__ */ l("div", {
		className: "space-y-3",
		children: [
			/* @__PURE__ */ c("h1", {
				className: "text-lg font-semibold",
				children: "Workspace"
			}),
			/* @__PURE__ */ l("p", {
				className: "text-sm text-gray-500",
				children: [
					"Studio passes the current workspace ID to every plugin via",
					" ",
					/* @__PURE__ */ l("code", { children: [
						"mount(container, ",
						"{ workspaceId }",
						")"
					] }),
					"."
				]
			}),
			/* @__PURE__ */ l("div", {
				className: "space-y-1",
				children: [/* @__PURE__ */ c("h2", {
					className: "text-sm font-medium text-gray-700",
					children: "Current workspace"
				}), /* @__PURE__ */ c("pre", {
					className: "text-xs bg-gray-100 rounded p-3",
					children: e
				})]
			}),
			/* @__PURE__ */ l("div", {
				className: "space-y-1",
				children: [/* @__PURE__ */ c("h2", {
					className: "text-sm font-medium text-gray-700",
					children: "Example API call scoped to this workspace"
				}), /* @__PURE__ */ c("pre", {
					className: "text-xs bg-gray-100 rounded p-3 overflow-x-auto",
					children: "fetch(`/apis/v1/workspaces/${workspaceId}/models`, {\n  headers: { Authorization: `Bearer ${accessToken}` },\n})"
				})]
			})
		]
	});
}
function h() {
	return /* @__PURE__ */ c("p", {
		className: "text-sm text-gray-500",
		children: "Page not found."
	});
}
//#endregion
//#region src/mount.tsx
function g(n, r) {
	let i = window.history.pushState.bind(window.history), a = window.history.replaceState.bind(window.history);
	function o(e) {
		window.dispatchEvent(new PopStateEvent("popstate", { state: e }));
	}
	window.history.pushState = (e, ...t) => {
		i(e, ...t), o(e);
	}, window.history.replaceState = (e, ...t) => {
		a(e, ...t), o(e);
	};
	let s = t(n);
	return s.render(e.createElement(u, {
		workspaceId: r.workspaceId,
		accessToken: r.auth.accessToken,
		basename: r.basename
	})), () => {
		window.history.pushState = i, window.history.replaceState = a, s.unmount();
	};
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
export { g as mount, _ as navItems };
