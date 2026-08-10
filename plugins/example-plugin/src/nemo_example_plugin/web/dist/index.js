// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
import { Button as e, Flex as t, Stack as n, Text as r } from "@nvidia/foundations-react-core";
import { NavLink as i, Navigate as a, Outlet as o, Route as s, Routes as c } from "react-router";
import { RelativeTime as l, StatusBadge as u, StudioDataView as d, TableEmptyState as f, useStudioDataViewState as p } from "@nemo/common";
import { useCallback as m } from "react";
import { jsx as h, jsxs as g } from "react/jsx-runtime";
//#region src/paths.ts
var _ = (e, t) => `/workspaces/${e}/plugin/example/${t}`, v = [
	"overview",
	"auth",
	"workspace",
	"shared-ui"
], y = {
	overview: "Overview",
	auth: "Auth",
	workspace: "Workspace",
	"shared-ui": "Shared UI"
};
//#endregion
//#region src/SharedUiPage.tsx
function b({ host: e }) {
	let { data: t, isPending: i, isError: a } = e.sdk.platform.useEntitiesListWorkspaces({
		page: 1,
		page_size: 100
	}), o = t?.data ?? [], s = p(), c = m((e) => [
		e.accessor("name", {
			header: "Name",
			size: 240
		}),
		e.display({
			id: "status",
			header: "Status",
			size: 120,
			cell: ({ row: e }) => /* @__PURE__ */ h(u, { status: e.original.status ?? "ready" })
		}),
		e.display({
			id: "created",
			header: "Created",
			size: 160,
			cell: ({ row: e }) => e.original.created_at ? /* @__PURE__ */ h(l, { datetime: e.original.created_at }) : /* @__PURE__ */ h(r, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "—"
			})
		})
	], []);
	return /* @__PURE__ */ g(n, {
		gap: "2",
		children: [
			/* @__PURE__ */ h(r, {
				kind: "label/bold/md",
				children: "Shared UI"
			}),
			/* @__PURE__ */ h(r, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "This table is Studio's own StudioDataView, imported from @nemo/common and resolved through Studio's import map — not a copy bundled into the plugin."
			}),
			a ? /* @__PURE__ */ h(f, {
				header: "Couldn't load workspaces",
				emptyMessage: "The request failed. Try again."
			}) : !i && o.length === 0 ? /* @__PURE__ */ h(f, {
				header: "No workspaces",
				emptyMessage: "Create a workspace to see it listed here."
			}) : /* @__PURE__ */ h(n, {
				className: "min-h-[320px]",
				children: /* @__PURE__ */ h(d, {
					dataViewState: s,
					makeColumns: c,
					attributes: { DataViewRoot: {
						data: o,
						totalCount: o.length,
						reactTableOptions: { getRowId: (e) => e.name }
					} }
				})
			})
		]
	});
}
//#endregion
//#region src/Root.tsx
function x({ host: e }) {
	return /* @__PURE__ */ h(c, { children: /* @__PURE__ */ g(s, {
		element: /* @__PURE__ */ h(S, { workspaceId: e.workspaceId }),
		children: [
			/* @__PURE__ */ h(s, {
				index: !0,
				element: /* @__PURE__ */ h(a, {
					to: _(e.workspaceId, "overview"),
					replace: !0
				})
			}),
			/* @__PURE__ */ h(s, {
				path: "overview",
				element: /* @__PURE__ */ h(w, { host: e })
			}),
			/* @__PURE__ */ h(s, {
				path: "auth",
				element: /* @__PURE__ */ h(T, { getAccessToken: e.auth.getAccessToken })
			}),
			/* @__PURE__ */ h(s, {
				path: "workspace",
				element: /* @__PURE__ */ h(E, { workspaceId: e.workspaceId })
			}),
			/* @__PURE__ */ h(s, {
				path: "shared-ui",
				element: /* @__PURE__ */ h(b, { host: e })
			}),
			/* @__PURE__ */ h(s, {
				path: "*",
				element: /* @__PURE__ */ h(D, {})
			})
		]
	}) });
}
function S({ workspaceId: e }) {
	let r = ({ isActive: e }) => `px-3 py-1 rounded text-sm font-medium transition-colors ${e ? "text-primary bg-surface-hover" : "text-subtle hover:text-primary"}`;
	return /* @__PURE__ */ g(n, {
		gap: "4",
		className: "h-full p-4",
		children: [/* @__PURE__ */ h(t, {
			gap: "2",
			className: "border-b border-subtle pb-2",
			children: v.map((t) => /* @__PURE__ */ h(i, {
				to: _(e, t),
				className: r,
				children: y[t]
			}, t))
		}), /* @__PURE__ */ h("div", {
			className: "flex-1",
			children: /* @__PURE__ */ h(o, {})
		})]
	});
}
function C({ children: e }) {
	return /* @__PURE__ */ h("pre", {
		className: "bg-surface-sunken text-subtle rounded p-3 text-xs overflow-x-auto font-mono",
		children: e
	});
}
function w({ host: i }) {
	let { data: a, isPending: o, isError: s } = i.sdk.platform.useEntitiesListWorkspaces({
		page: 1,
		page_size: 100
	}, { query: { staleTime: 5e3 } }), c = a?.data ?? [];
	return /* @__PURE__ */ g(n, {
		gap: "2",
		children: [
			/* @__PURE__ */ h(r, {
				kind: "label/bold/lg",
				children: "Example Plugin"
			}),
			/* @__PURE__ */ h(r, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "This is an example Studio plugin. Use the tabs above or the Studio side nav to explore what information is available to a plugin at runtime."
			}),
			/* @__PURE__ */ g(n, {
				gap: "1",
				children: [
					/* @__PURE__ */ h(r, {
						kind: "label/bold/sm",
						children: "Shared SDK"
					}),
					/* @__PURE__ */ h(r, {
						kind: "body/regular/xs",
						color: "secondary",
						children: "Listed via Studio's sdk.platform.useEntitiesListWorkspaces() — the platform's typed hook, running on Studio's authenticated axios and shared QueryClient rather than a plugin copy."
					}),
					o ? /* @__PURE__ */ h(r, {
						kind: "body/regular/xs",
						color: "secondary",
						children: "Loading…"
					}) : s ? /* @__PURE__ */ h(r, {
						kind: "body/regular/xs",
						color: "danger",
						children: "Request failed."
					}) : /* @__PURE__ */ g(r, {
						kind: "body/regular/sm",
						children: [
							c.length,
							" workspaces:",
							" ",
							c.map((e) => e.name).join(", ")
						]
					})
				]
			}),
			/* @__PURE__ */ g(n, {
				gap: "1",
				children: [
					/* @__PURE__ */ h(r, {
						kind: "label/bold/sm",
						children: "Host capabilities"
					}),
					/* @__PURE__ */ h(r, {
						kind: "body/regular/xs",
						color: "secondary",
						children: "Studio's notifications, telemetry, and navigation, all off the host handle — no plugin-side setup."
					}),
					/* @__PURE__ */ g(t, {
						gap: "2",
						children: [/* @__PURE__ */ h(e, {
							kind: "secondary",
							onClick: () => {
								i.notifications.notify("Toast from the example plugin", "success"), i.telemetry.event("overview_notify_clicked");
							},
							children: "Notify"
						}), /* @__PURE__ */ h(e, {
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
function T({ getAccessToken: e }) {
	let t = e(), i = null;
	try {
		let e = t.split(".")[1];
		e && (i = JSON.parse(atob(e.replace(/-/g, "+").replace(/_/g, "/"))));
	} catch {}
	return /* @__PURE__ */ g(n, {
		gap: "3",
		children: [
			/* @__PURE__ */ h(r, {
				kind: "label/bold/md",
				children: "Auth"
			}),
			/* @__PURE__ */ h(r, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "Studio passes an OIDC access token to every plugin via the plugin's auth prop. Call getAccessToken() per request — it returns the current token after silent renewal — and use it as a Bearer token."
			}),
			/* @__PURE__ */ g(n, {
				gap: "1",
				children: [/* @__PURE__ */ h(r, {
					kind: "label/bold/sm",
					children: "Example API call"
				}), /* @__PURE__ */ h(C, { children: "fetch('/apis/v1/workspaces', {\n  headers: { Authorization: `Bearer ${getAccessToken()}` },\n})" })]
			}),
			/* @__PURE__ */ g(n, {
				gap: "1",
				children: [/* @__PURE__ */ h(r, {
					kind: "label/bold/sm",
					children: "Token claims (decoded, not verified)"
				}), i ? /* @__PURE__ */ h(C, { children: JSON.stringify(i, null, 2) }) : /* @__PURE__ */ h(r, {
					kind: "body/regular/xs",
					color: "secondary",
					children: t ? "Could not decode token." : "No token provided."
				})]
			})
		]
	});
}
function E({ workspaceId: e }) {
	return /* @__PURE__ */ g(n, {
		gap: "3",
		children: [
			/* @__PURE__ */ h(r, {
				kind: "label/bold/md",
				children: "Workspace"
			}),
			/* @__PURE__ */ h(r, {
				kind: "body/regular/sm",
				color: "secondary",
				children: "Studio passes the current workspace ID to every plugin via the plugin's workspaceId prop."
			}),
			/* @__PURE__ */ g(n, {
				gap: "1",
				children: [/* @__PURE__ */ h(r, {
					kind: "label/bold/sm",
					children: "Current workspace"
				}), /* @__PURE__ */ h(C, { children: e })]
			}),
			/* @__PURE__ */ g(n, {
				gap: "1",
				children: [/* @__PURE__ */ h(r, {
					kind: "label/bold/sm",
					children: "Example API call scoped to this workspace"
				}), /* @__PURE__ */ h(C, { children: "fetch(`/apis/v1/workspaces/${workspaceId}/models`, {\n  headers: { Authorization: `Bearer ${getAccessToken()}` },\n})" })]
			})
		]
	});
}
function D() {
	return /* @__PURE__ */ h(r, {
		kind: "body/regular/sm",
		color: "secondary",
		children: "Page not found."
	});
}
//#endregion
//#region src/Nav.tsx
var O = (e) => [{
	group: "Example Plugin",
	items: [
		{
			id: "example-overview",
			iconName: "flask-conical",
			label: "Overview",
			href: _(e, "overview")
		},
		{
			id: "example-auth",
			iconName: "key-round",
			label: "Auth",
			href: _(e, "auth")
		},
		{
			id: "example-workspace",
			iconName: "building-2",
			label: "Workspace",
			href: _(e, "workspace")
		},
		{
			id: "example-shared-ui",
			iconName: "table",
			label: "Shared UI",
			href: _(e, "shared-ui")
		}
	]
}];
//#endregion
export { x as Root, O as navItems };
