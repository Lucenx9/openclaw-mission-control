"use client";

import Link from "next/link";
import { useState } from "react";

import { useAuth } from "@/auth/clerk";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/mutator";
import {
  type listAgentsApiV1AgentsGetResponse,
  getListAgentsApiV1AgentsGetQueryKey,
  useListAgentsApiV1AgentsGet,
} from "@/api/generated/agents/agents";
import {
  type listBoardsApiV1BoardsGetResponse,
  useListBoardsApiV1BoardsGet,
} from "@/api/generated/boards/boards";
import {
  type listGatewaysApiV1GatewaysGetResponse,
  useListGatewaysApiV1GatewaysGet,
} from "@/api/generated/gateways/gateways";
import type { AgentRead, BoardRead, LlmModelRead, LlmProviderAuthRead } from "@/api/generated/model";
import {
  type listModelsApiV1ModelRegistryModelsGetResponse,
  type listProviderAuthApiV1ModelRegistryProviderAuthGetResponse,
  getListModelsApiV1ModelRegistryModelsGetQueryKey,
  getListProviderAuthApiV1ModelRegistryProviderAuthGetQueryKey,
  useDeleteModelApiV1ModelRegistryModelsModelIdDelete,
  useDeleteProviderAuthApiV1ModelRegistryProviderAuthProviderAuthIdDelete,
  useListModelsApiV1ModelRegistryModelsGet,
  useListProviderAuthApiV1ModelRegistryProviderAuthGet,
} from "@/api/generated/model-registry/model-registry";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { useOrganizationMembership } from "@/lib/use-organization-membership";

const agentRoleLabel = (agent: AgentRead): string | null => {
  const role = agent.identity_profile?.role;
  if (typeof role !== "string") return null;
  const value = role.trim();
  return value || null;
};

type RoutingStatus = "override" | "default" | "unconfigured";
type ProviderSortKey = "gateway" | "provider" | "config_path" | "secret" | "updated";
type ModelSortKey = "gateway" | "display_name" | "model_id" | "provider" | "settings" | "updated";
type RoutingSortKey = "agent" | "role" | "gateway" | "board" | "primary" | "status";
type SortDirection = "asc" | "desc";
export type ModelsView = "provider-auth" | "catalog" | "routing";

const routingStatusLabel = (status: RoutingStatus): string => {
  if (status === "override") return "Primary override";
  if (status === "default") return "Using default";
  return "No primary";
};

const routingStatusVariant = (
  status: RoutingStatus,
): "success" | "accent" | "warning" => {
  if (status === "override") return "success";
  if (status === "default") return "accent";
  return "warning";
};

const formatTimestamp = (value: unknown): string => {
  if (!value) return "-";
  const parsed = new Date(String(value));
  if (Number.isNaN(parsed.getTime())) return "-";
  return parsed.toLocaleString();
};

const VIEW_META: Record<
  ModelsView,
  { title: string; description: string; addLabel?: string; addHref?: string }
> = {
  "provider-auth": {
    title: "Provider Auth",
    description: "Gateway provider credentials managed by Mission Control.",
    addLabel: "Add provider auth",
    addHref: "/models/provider-auth/new",
  },
  catalog: {
    title: "Model Catalog",
    description: "Gateway model catalog used for agent routing assignments.",
    addLabel: "Add model",
    addHref: "/models/catalog/new",
  },
  routing: {
    title: "Agent Routing",
    description: "Per-agent primary and fallback model assignments across gateways.",
  },
};

const withGatewayQuery = (href: string, gatewayId: string): string => {
  if (!gatewayId) return href;
  return `${href}?gateway=${encodeURIComponent(gatewayId)}`;
};

export default function ModelsWorkspace({ view }: { view: ModelsView }) {
  const { isSignedIn } = useAuth();
  const queryClient = useQueryClient();
  const { isAdmin } = useOrganizationMembership(isSignedIn);
  const [providerSortKey, setProviderSortKey] = useState<ProviderSortKey>("gateway");
  const [providerSortDirection, setProviderSortDirection] = useState<SortDirection>("asc");
  const [modelSortKey, setModelSortKey] = useState<ModelSortKey>("gateway");
  const [modelSortDirection, setModelSortDirection] = useState<SortDirection>("asc");
  const [routingSortKey, setRoutingSortKey] = useState<RoutingSortKey>("agent");
  const [routingSortDirection, setRoutingSortDirection] = useState<SortDirection>("asc");

  const modelsKey = getListModelsApiV1ModelRegistryModelsGetQueryKey();
  const providerAuthKey = getListProviderAuthApiV1ModelRegistryProviderAuthGetQueryKey();
  const agentsKey = getListAgentsApiV1AgentsGetQueryKey();

  const gatewaysQuery = useListGatewaysApiV1GatewaysGet<
    listGatewaysApiV1GatewaysGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchOnMount: "always",
    },
  });

  const modelsQuery = useListModelsApiV1ModelRegistryModelsGet<
    listModelsApiV1ModelRegistryModelsGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchOnMount: "always",
    },
  });

  const boardsQuery = useListBoardsApiV1BoardsGet<
    listBoardsApiV1BoardsGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchOnMount: "always",
    },
  });

  const providerAuthQuery = useListProviderAuthApiV1ModelRegistryProviderAuthGet<
    listProviderAuthApiV1ModelRegistryProviderAuthGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchOnMount: "always",
    },
  });

  const agentsQuery = useListAgentsApiV1AgentsGet<
    listAgentsApiV1AgentsGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchOnMount: "always",
    },
  });

  const deleteProviderMutation =
    useDeleteProviderAuthApiV1ModelRegistryProviderAuthProviderAuthIdDelete<ApiError>(
      {
        mutation: {
          onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: providerAuthKey });
          },
        },
      },
    );

  const deleteModelMutation =
    useDeleteModelApiV1ModelRegistryModelsModelIdDelete<ApiError>({
      mutation: {
        onSuccess: async () => {
          await Promise.all([
            queryClient.invalidateQueries({ queryKey: modelsKey }),
            queryClient.invalidateQueries({ queryKey: agentsKey }),
          ]);
        },
      },
    });

  const gateways =
    gatewaysQuery.data?.status === 200 ? (gatewaysQuery.data.data.items ?? []) : [];
  const models: LlmModelRead[] =
    modelsQuery.data?.status === 200 ? modelsQuery.data.data : [];
  const boards: BoardRead[] =
    boardsQuery.data?.status === 200 ? (boardsQuery.data.data.items ?? []) : [];
  const providerAuth: LlmProviderAuthRead[] =
    providerAuthQuery.data?.status === 200 ? providerAuthQuery.data.data : [];
  const agents: AgentRead[] =
    agentsQuery.data?.status === 200 ? (agentsQuery.data.data.items ?? []) : [];

  const gatewaysById = new Map(gateways.map((gateway) => [gateway.id, gateway] as const));
  const boardsById = new Map(boards.map((board) => [board.id, board] as const));
  const modelsById = new Map(models.map((model) => [model.id, model] as const));

  const gatewayDefaultById = (() => {
    const grouped = new Map<string, LlmModelRead[]>();
    for (const model of models) {
      const bucket = grouped.get(model.gateway_id) ?? [];
      bucket.push(model);
      grouped.set(model.gateway_id, bucket);
    }
    const defaults = new Map<string, LlmModelRead>();
    for (const [gatewayId, bucket] of grouped.entries()) {
      const sorted = [...bucket].sort((a, b) =>
        String(a.created_at).localeCompare(String(b.created_at)),
      );
      if (sorted[0]) {
        defaults.set(gatewayId, sorted[0]);
      }
    }
    return defaults;
  })();

  const providerRows = [...providerAuth].sort((left, right) => {
    const resolveString = (row: LlmProviderAuthRead): string => {
      if (providerSortKey === "gateway") {
        return gatewaysById.get(row.gateway_id)?.name ?? "Unknown gateway";
      }
      if (providerSortKey === "provider") return row.provider;
      if (providerSortKey === "config_path") return row.config_path;
      return "";
    };
    const resolveNumber = (row: LlmProviderAuthRead): number => {
      if (providerSortKey === "secret") return row.has_secret ? 1 : 0;
      if (providerSortKey === "updated") return new Date(String(row.updated_at)).getTime() || 0;
      return 0;
    };

    if (providerSortKey === "secret" || providerSortKey === "updated") {
      const a = resolveNumber(left);
      const b = resolveNumber(right);
      const baseCompare = a - b;
      if (baseCompare !== 0) {
        return providerSortDirection === "asc" ? baseCompare : -baseCompare;
      }
    } else {
      const a = resolveString(left).toLowerCase();
      const b = resolveString(right).toLowerCase();
      const baseCompare = a.localeCompare(b);
      if (baseCompare !== 0) {
        return providerSortDirection === "asc" ? baseCompare : -baseCompare;
      }
    }

    const fallbackCompare = left.provider.localeCompare(right.provider);
    return providerSortDirection === "asc" ? fallbackCompare : -fallbackCompare;
  });

  const modelRows = [...models].sort((left, right) => {
    const resolveString = (row: LlmModelRead): string => {
      if (modelSortKey === "gateway") {
        return gatewaysById.get(row.gateway_id)?.name ?? "Unknown gateway";
      }
      if (modelSortKey === "display_name") return row.display_name;
      if (modelSortKey === "model_id") return row.model_id;
      if (modelSortKey === "provider") return row.provider;
      return "";
    };
    const resolveNumber = (row: LlmModelRead): number => {
      if (modelSortKey === "settings") return row.settings ? Object.keys(row.settings).length : 0;
      if (modelSortKey === "updated") return new Date(String(row.updated_at)).getTime() || 0;
      return 0;
    };

    if (modelSortKey === "settings" || modelSortKey === "updated") {
      const a = resolveNumber(left);
      const b = resolveNumber(right);
      const baseCompare = a - b;
      if (baseCompare !== 0) {
        return modelSortDirection === "asc" ? baseCompare : -baseCompare;
      }
    } else {
      const a = resolveString(left).toLowerCase();
      const b = resolveString(right).toLowerCase();
      const baseCompare = a.localeCompare(b);
      if (baseCompare !== 0) {
        return modelSortDirection === "asc" ? baseCompare : -baseCompare;
      }
    }

    const fallbackCompare = left.display_name.localeCompare(right.display_name);
    return modelSortDirection === "asc" ? fallbackCompare : -fallbackCompare;
  });

  const routingRows = agents
    .map((agent) => {
      const primary = agent.primary_model_id ? modelsById.get(agent.primary_model_id) : null;
      const defaultPrimary = gatewayDefaultById.get(agent.gateway_id) ?? null;
      const effectivePrimary = primary ?? defaultPrimary;
      const board = agent.board_id ? (boardsById.get(agent.board_id) ?? null) : null;
      const role = agentRoleLabel(agent) ?? "Unspecified";
      const fallbackCount = (agent.fallback_model_ids ?? []).length;
      const status: RoutingStatus = primary
        ? "override"
        : effectivePrimary
          ? "default"
          : "unconfigured";

      return {
        agent,
        board,
        role,
        primary,
        effectivePrimary,
        fallbackCount,
        gatewayName: gatewaysById.get(agent.gateway_id)?.name ?? "Unknown gateway",
        status,
      };
    });

  const sortedRoutingRows = [...routingRows].sort((left, right) => {
    const resolveValue = (row: (typeof routingRows)[number]): string => {
      if (routingSortKey === "agent") return row.agent.name;
      if (routingSortKey === "role") return row.role;
      if (routingSortKey === "gateway") return row.gatewayName;
      if (routingSortKey === "board") return row.board?.name ?? "Gateway main";
      if (routingSortKey === "primary") {
        return row.primary?.display_name ?? row.effectivePrimary?.display_name ?? "";
      }
      return routingStatusLabel(row.status);
    };

    const a = resolveValue(left).toLowerCase();
    const b = resolveValue(right).toLowerCase();
    const baseCompare = a.localeCompare(b);
    if (baseCompare !== 0) {
      return routingSortDirection === "asc" ? baseCompare : -baseCompare;
    }
    const fallbackCompare = left.agent.name.localeCompare(right.agent.name);
    return routingSortDirection === "asc" ? fallbackCompare : -fallbackCompare;
  });

  const setRoutingSort = (key: RoutingSortKey) => {
    if (routingSortKey === key) {
      setRoutingSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setRoutingSortKey(key);
    setRoutingSortDirection("asc");
  };

  const routingSortLabel = (key: RoutingSortKey): string => {
    if (routingSortKey !== key) return "";
    return routingSortDirection === "asc" ? " ▲" : " ▼";
  };

  const setProviderSort = (key: ProviderSortKey) => {
    if (providerSortKey === key) {
      setProviderSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setProviderSortKey(key);
    setProviderSortDirection("asc");
  };

  const providerSortLabel = (key: ProviderSortKey): string => {
    if (providerSortKey !== key) return "";
    return providerSortDirection === "asc" ? " ▲" : " ▼";
  };

  const setModelSort = (key: ModelSortKey) => {
    if (modelSortKey === key) {
      setModelSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setModelSortKey(key);
    setModelSortDirection("asc");
  };

  const modelSortLabel = (key: ModelSortKey): string => {
    if (modelSortKey !== key) return "";
    return modelSortDirection === "asc" ? " ▲" : " ▼";
  };

  const pageError =
    gatewaysQuery.error?.message ??
    modelsQuery.error?.message ??
    boardsQuery.error?.message ??
    providerAuthQuery.error?.message ??
    agentsQuery.error?.message ??
    null;

  const activeViewMeta = VIEW_META[view];

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to manage gateway models.",
        forceRedirectUrl: "/models/routing",
        signUpForceRedirectUrl: "/models/routing",
      }}
      title={activeViewMeta.title}
      description={activeViewMeta.description}
      headerActions={
        activeViewMeta.addHref && activeViewMeta.addLabel ? (
          <Link href={activeViewMeta.addHref} className={buttonVariants()}>
            {activeViewMeta.addLabel}
          </Link>
        ) : null
      }
      isAdmin={isAdmin}
      adminOnlyMessage="Only organization owners and admins can access model management."
    >
      <div className="space-y-6">
        {view === "provider-auth" ? (
          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="max-h-[760px] overflow-auto">
              <table className="min-w-full border-collapse text-left text-sm">
                <thead className="sticky top-0 z-10 bg-slate-100 text-xs uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">
                      <button
                        type="button"
                        onClick={() => setProviderSort("gateway")}
                        className="text-left text-inherit hover:text-slate-700"
                      >
                        Gateway{providerSortLabel("gateway")}
                      </button>
                    </th>
                    <th className="px-4 py-3 font-medium">
                      <button
                        type="button"
                        onClick={() => setProviderSort("provider")}
                        className="text-left text-inherit hover:text-slate-700"
                      >
                        Provider{providerSortLabel("provider")}
                      </button>
                    </th>
                    <th className="px-4 py-3 font-medium">
                      <button
                        type="button"
                        onClick={() => setProviderSort("config_path")}
                        className="text-left text-inherit hover:text-slate-700"
                      >
                        Config path{providerSortLabel("config_path")}
                      </button>
                    </th>
                    <th className="px-4 py-3 font-medium">
                      <button
                        type="button"
                        onClick={() => setProviderSort("secret")}
                        className="text-left text-inherit hover:text-slate-700"
                      >
                        Secret{providerSortLabel("secret")}
                      </button>
                    </th>
                    <th className="px-4 py-3 font-medium">
                      <button
                        type="button"
                        onClick={() => setProviderSort("updated")}
                        className="text-left text-inherit hover:text-slate-700"
                      >
                        Updated{providerSortLabel("updated")}
                      </button>
                    </th>
                    <th className="px-4 py-3 font-medium text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {providerRows.length === 0 ? (
                    <tr className="border-t border-slate-200">
                      <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-500">
                        No provider auth entries yet.
                      </td>
                    </tr>
                  ) : (
                    providerRows.map((item) => (
                      <tr key={item.id} className="border-t border-slate-200 bg-white">
                        <td className="px-4 py-3 align-top text-slate-700">
                          {gatewaysById.get(item.gateway_id)?.name ?? "Unknown gateway"}
                        </td>
                        <td className="px-4 py-3 align-top">
                          <Badge variant="accent">{item.provider}</Badge>
                        </td>
                        <td className="px-4 py-3 align-top text-slate-700">
                          <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">
                            {item.config_path}
                          </code>
                        </td>
                        <td className="px-4 py-3 align-top text-slate-700">
                          {item.has_secret ? "Configured" : "Missing"}
                        </td>
                        <td className="px-4 py-3 align-top text-slate-600">
                          {formatTimestamp(item.updated_at)}
                        </td>
                        <td className="px-4 py-3 text-right align-top">
                          <div className="flex justify-end gap-2">
                            <Link
                              href={withGatewayQuery(
                                `/models/provider-auth/${item.id}/edit`,
                                item.gateway_id,
                              )}
                              className={buttonVariants({ size: "sm", variant: "outline" })}
                            >
                              Edit
                            </Link>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => deleteProviderMutation.mutate({ providerAuthId: item.id })}
                              disabled={deleteProviderMutation.isPending}
                              className="border-red-300 text-red-700 hover:border-red-500 hover:text-red-800"
                            >
                              Delete
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {view === "catalog" ? (
          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="max-h-[760px] overflow-auto">
              <table className="min-w-full border-collapse text-left text-sm">
                <thead className="sticky top-0 z-10 bg-slate-100 text-xs uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">
                      <button
                        type="button"
                        onClick={() => setModelSort("gateway")}
                        className="text-left text-inherit hover:text-slate-700"
                      >
                        Gateway{modelSortLabel("gateway")}
                      </button>
                    </th>
                    <th className="px-4 py-3 font-medium">
                      <button
                        type="button"
                        onClick={() => setModelSort("display_name")}
                        className="text-left text-inherit hover:text-slate-700"
                      >
                        Display name{modelSortLabel("display_name")}
                      </button>
                    </th>
                    <th className="px-4 py-3 font-medium">
                      <button
                        type="button"
                        onClick={() => setModelSort("model_id")}
                        className="text-left text-inherit hover:text-slate-700"
                      >
                        Model ID{modelSortLabel("model_id")}
                      </button>
                    </th>
                    <th className="px-4 py-3 font-medium">
                      <button
                        type="button"
                        onClick={() => setModelSort("provider")}
                        className="text-left text-inherit hover:text-slate-700"
                      >
                        Provider{modelSortLabel("provider")}
                      </button>
                    </th>
                    <th className="px-4 py-3 font-medium">
                      <button
                        type="button"
                        onClick={() => setModelSort("settings")}
                        className="text-left text-inherit hover:text-slate-700"
                      >
                        Settings{modelSortLabel("settings")}
                      </button>
                    </th>
                    <th className="px-4 py-3 font-medium">
                      <button
                        type="button"
                        onClick={() => setModelSort("updated")}
                        className="text-left text-inherit hover:text-slate-700"
                      >
                        Updated{modelSortLabel("updated")}
                      </button>
                    </th>
                    <th className="px-4 py-3 font-medium text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {modelRows.length === 0 ? (
                    <tr className="border-t border-slate-200">
                      <td colSpan={7} className="px-4 py-8 text-center text-sm text-slate-500">
                        No models in catalog yet.
                      </td>
                    </tr>
                  ) : (
                    modelRows.map((item) => (
                      <tr key={item.id} className="border-t border-slate-200 bg-white">
                        <td className="px-4 py-3 align-top text-slate-700">
                          {gatewaysById.get(item.gateway_id)?.name ?? "Unknown gateway"}
                        </td>
                        <td className="px-4 py-3 align-top font-medium text-slate-800">{item.display_name}</td>
                        <td className="px-4 py-3 align-top text-slate-700">{item.model_id}</td>
                        <td className="px-4 py-3 align-top">
                          <Badge variant="accent">{item.provider}</Badge>
                        </td>
                        <td className="px-4 py-3 align-top text-slate-600">
                          {item.settings ? `${Object.keys(item.settings).length} keys` : "-"}
                        </td>
                        <td className="px-4 py-3 align-top text-slate-600">
                          {formatTimestamp(item.updated_at)}
                        </td>
                        <td className="px-4 py-3 text-right align-top">
                          <div className="flex justify-end gap-2">
                            <Link
                              href={withGatewayQuery(`/models/catalog/${item.id}/edit`, item.gateway_id)}
                              className={buttonVariants({ size: "sm", variant: "outline" })}
                            >
                              Edit
                            </Link>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => deleteModelMutation.mutate({ modelId: item.id })}
                              disabled={deleteModelMutation.isPending}
                              className="border-red-300 text-red-700 hover:border-red-500 hover:text-red-800"
                            >
                              Delete
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {view === "routing" ? (
          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="max-h-[780px] overflow-auto">
              {routingRows.length === 0 ? (
                <p className="mx-4 my-4 rounded-lg border border-dashed border-slate-300 px-3 py-5 text-sm text-slate-500">
                  No agents found.
                </p>
              ) : (
                <table className="min-w-full table-fixed border-collapse text-left text-sm">
                  <thead className="sticky top-0 z-10 bg-slate-100 text-xs uppercase tracking-wider text-slate-500">
                    <tr>
                      <th className="w-[18%] px-4 py-3 font-medium">
                        <button
                          type="button"
                          onClick={() => setRoutingSort("agent")}
                          className="text-left text-inherit hover:text-slate-700"
                        >
                          Agent{routingSortLabel("agent")}
                        </button>
                      </th>
                      <th className="w-[14%] px-4 py-3 font-medium">
                        <button
                          type="button"
                          onClick={() => setRoutingSort("role")}
                          className="text-left text-inherit hover:text-slate-700"
                        >
                          Role{routingSortLabel("role")}
                        </button>
                      </th>
                      <th className="w-[16%] px-4 py-3 font-medium">
                        <button
                          type="button"
                          onClick={() => setRoutingSort("gateway")}
                          className="text-left text-inherit hover:text-slate-700"
                        >
                          Gateway{routingSortLabel("gateway")}
                        </button>
                      </th>
                      <th className="w-[16%] px-4 py-3 font-medium">
                        <button
                          type="button"
                          onClick={() => setRoutingSort("board")}
                          className="text-left text-inherit hover:text-slate-700"
                        >
                          Board{routingSortLabel("board")}
                        </button>
                      </th>
                      <th className="w-[24%] px-4 py-3 font-medium">
                        <button
                          type="button"
                          onClick={() => setRoutingSort("primary")}
                          className="text-left text-inherit hover:text-slate-700"
                        >
                          Primary{routingSortLabel("primary")}
                        </button>
                      </th>
                      <th className="w-[12%] px-4 py-3 font-medium">
                        <button
                          type="button"
                          onClick={() => setRoutingSort("status")}
                          className="text-left text-inherit hover:text-slate-700"
                        >
                          Status{routingSortLabel("status")}
                        </button>
                      </th>
                      <th className="px-4 py-3 font-medium text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedRoutingRows.map((row) => (
                      <tr key={row.agent.id} className="border-t border-slate-200 bg-white hover:bg-slate-50">
                        <td className="px-4 py-3 align-top">
                          <Link
                            href={`/agents/${row.agent.id}`}
                            className="block truncate font-semibold text-blue-700 underline-offset-2 hover:underline"
                          >
                            {row.agent.name}
                          </Link>
                          <p className="mt-1 truncate text-xs text-slate-500">
                            Fallbacks: {row.fallbackCount}
                          </p>
                        </td>
                        <td className="px-4 py-3 align-top text-slate-700">{row.role}</td>
                        <td className="px-4 py-3 align-top text-slate-700">{row.gatewayName}</td>
                        <td className="px-4 py-3 align-top">
                          {row.agent.board_id ? (
                            <div>
                              <Link
                                href={`/boards/${row.agent.board_id}`}
                                className="block truncate text-blue-700 underline-offset-2 hover:underline"
                              >
                                {row.board?.name ?? "Open board"}
                              </Link>
                            </div>
                          ) : (
                            <span className="text-slate-600">Gateway main</span>
                          )}
                        </td>
                        <td className="px-4 py-3 align-top text-slate-700">
                          {row.primary ? (
                            <p className="truncate font-medium text-slate-800">{row.primary.display_name}</p>
                          ) : row.effectivePrimary ? (
                            <p className="truncate font-medium text-slate-800">
                              {row.effectivePrimary.display_name}
                            </p>
                          ) : (
                            "None"
                          )}
                        </td>
                        <td className="px-4 py-3 align-top">
                          <Badge variant={routingStatusVariant(row.status)}>
                            {routingStatusLabel(row.status)}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-right align-top">
                          <div className="flex justify-end gap-2">
                            <Link
                              href={withGatewayQuery(`/models/routing/${row.agent.id}/edit`, row.agent.gateway_id)}
                              className={buttonVariants({ size: "sm", variant: "outline" })}
                            >
                              Edit
                            </Link>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>
        ) : null}

        {pageError ? <p className="text-sm text-red-500">{pageError}</p> : null}
      </div>
    </DashboardPageLayout>
  );
}
