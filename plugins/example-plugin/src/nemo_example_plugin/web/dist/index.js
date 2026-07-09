import { Flex as e, Stack as t, Text as n } from "@nvidia/foundations-react-core";
import { useQuery as r } from "@tanstack/react-query";
import { NavLink as i, Navigate as a, Outlet as o, Route as s, Routes as c } from "react-router-dom";
import { jsx as l, jsxs as u } from "react/jsx-runtime";
//#region src/Root.tsx
function d({ workspaceId: e, auth: t }) {
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
				element: /* @__PURE__ */ l(m, {})
			}),
			/* @__PURE__ */ l(s, {
				path: "auth",
				element: /* @__PURE__ */ l(h, { getAccessToken: t.getAccessToken })
			}),
			/* @__PURE__ */ l(s, {
				path: "workspace",
				element: /* @__PURE__ */ l(g, { workspaceId: e })
			}),
			/* @__PURE__ */ l(s, {
				path: "*",
				element: /* @__PURE__ */ l(_, {})
			})
		]
	}) });
}
function f() {
	let n = ({ isActive: e }) => `px-3 py-1 rounded text-sm font-medium transition-colors ${e ? "text-primary bg-surface-hover" : "text-subtle hover:text-primary"}`;
	return /* @__PURE__ */ u(t, {
		gap: "4",
		className: "h-full p-4",
		children: [/* @__PURE__ */ u(e, {
			gap: "2",
			className: "border-b border-subtle pb-2",
			children: [
				/* @__PURE__ */ l(i, {
					to: "overview",
					className: n,
					children: "Overview"
				}),
				/* @__PURE__ */ l(i, {
					to: "auth",
					className: n,
					children: "Auth"
				}),
				/* @__PURE__ */ l(i, {
					to: "workspace",
					className: n,
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
function m() {
	let { data: e, isLoading: i, isError: a } = r({
		queryKey: ["example-plugin", "installed-plugins"],
		queryFn: async () => {
			let e = await fetch("/apis/plugins");
			if (!e.ok) throw Error(`/apis/plugins returned ${e.status}`);
			return await e.json();
		}
	});
	return /* @__PURE__ */ u(t, {
		gap: "2",
		children: [
			/* @__PURE__ */ l(n, {
				kind: "label/bold/lg",
				children: "Example Plugin"
			}),
			/* @__PURE__ */ l(n, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "This is an example Studio plugin. Use the tabs above or the Studio side nav to explore what information is available to a plugin at runtime."
			}),
			/* @__PURE__ */ u(t, {
				gap: "1",
				children: [
					/* @__PURE__ */ l(n, {
						kind: "label/bold/sm",
						children: "Shared QueryClient"
					}),
					/* @__PURE__ */ l(n, {
						kind: "body/regular/xs",
						color: "secondary",
						children: "Fetched from the platform's /apis/plugins endpoint via @tanstack/react-query — running on Studio's QueryClient, not a copy."
					}),
					i ? /* @__PURE__ */ l(n, {
						kind: "body/regular/xs",
						color: "secondary",
						children: "Loading…"
					}) : a ? /* @__PURE__ */ l(n, {
						kind: "body/regular/xs",
						color: "danger",
						children: "Request failed."
					}) : /* @__PURE__ */ u(n, {
						kind: "body/regular/sm",
						children: [
							e?.length,
							" plugins installed: ",
							e?.map((e) => e.name).join(", ")
						]
					})
				]
			})
		]
	});
}
function h({ getAccessToken: e }) {
	let r = e(), i = null;
	try {
		let e = r.split(".")[1];
		e && (i = JSON.parse(atob(e.replace(/-/g, "+").replace(/_/g, "/"))));
	} catch {}
	return /* @__PURE__ */ u(t, {
		gap: "3",
		children: [
			/* @__PURE__ */ l(n, {
				kind: "label/bold/md",
				children: "Auth"
			}),
			/* @__PURE__ */ l(n, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "Studio passes an OIDC access token to every plugin via the plugin's auth prop. Call getAccessToken() per request — it returns the current token after silent renewal — and use it as a Bearer token."
			}),
			/* @__PURE__ */ u(t, {
				gap: "1",
				children: [/* @__PURE__ */ l(n, {
					kind: "label/bold/sm",
					children: "Example API call"
				}), /* @__PURE__ */ l(p, { children: "fetch('/apis/v1/workspaces', {\n  headers: { Authorization: `Bearer ${getAccessToken()}` },\n})" })]
			}),
			/* @__PURE__ */ u(t, {
				gap: "1",
				children: [/* @__PURE__ */ l(n, {
					kind: "label/bold/sm",
					children: "Token claims (decoded, not verified)"
				}), i ? /* @__PURE__ */ l(p, { children: JSON.stringify(i, null, 2) }) : /* @__PURE__ */ l(n, {
					kind: "body/regular/xs",
					color: "secondary",
					children: r ? "Could not decode token." : "No token provided."
				})]
			})
		]
	});
}
function g({ workspaceId: e }) {
	return /* @__PURE__ */ u(t, {
		gap: "3",
		children: [
			/* @__PURE__ */ l(n, {
				kind: "label/bold/md",
				children: "Workspace"
			}),
			/* @__PURE__ */ l(n, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "Studio passes the current workspace ID to every plugin via the plugin's workspaceId prop."
			}),
			/* @__PURE__ */ u(t, {
				gap: "1",
				children: [/* @__PURE__ */ l(n, {
					kind: "label/bold/sm",
					children: "Current workspace"
				}), /* @__PURE__ */ l(p, { children: e })]
			}),
			/* @__PURE__ */ u(t, {
				gap: "1",
				children: [/* @__PURE__ */ l(n, {
					kind: "label/bold/sm",
					children: "Example API call scoped to this workspace"
				}), /* @__PURE__ */ l(p, { children: "fetch(`/apis/v1/workspaces/${workspaceId}/models`, {\n  headers: { Authorization: `Bearer ${getAccessToken()}` },\n})" })]
			})
		]
	});
}
function _() {
	return /* @__PURE__ */ l(n, {
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
