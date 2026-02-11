"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { useAuth } from "@/auth/clerk";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/mutator";
import {
  type listAgentsApiV1AgentsGetResponse,
  getListAgentsApiV1AgentsGetQueryKey,
  useListAgentsApiV1AgentsGet,
  useUpdateAgentApiV1AgentsAgentIdPatch,
} from "@/api/generated/agents/agents";
import {
  type listBoardsApiV1BoardsGetResponse,
  useListBoardsApiV1BoardsGet,
} from "@/api/generated/boards/boards";
import {
  type listGatewaysApiV1GatewaysGetResponse,
  useListGatewaysApiV1GatewaysGet,
} from "@/api/generated/gateways/gateways";
import type { AgentRead, BoardRead, LlmModelRead } from "@/api/generated/model";
import {
  type listModelsApiV1ModelRegistryModelsGetResponse,
  useListModelsApiV1ModelRegistryModelsGet,
} from "@/api/generated/model-registry/model-registry";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import SearchableSelect, {
  type SearchableSelectOption,
} from "@/components/ui/searchable-select";
import { useOrganizationMembership } from "@/lib/use-organization-membership";

type AgentRoutingEditPageProps = {
  agentId: string;
};

type RoutingStatus = "override" | "default" | "unconfigured";

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

const agentRoleLabel = (agent: AgentRead): string | null => {
  const role = agent.identity_profile?.role;
  if (typeof role !== "string") return null;
  const normalized = role.trim();
  return normalized || null;
};

const modelOptionLabel = (model: LlmModelRead): string =>
  `${model.display_name} (${model.model_id})`;

const stringListsMatch = (left: string[], right: string[]): boolean => {
  if (left.length !== right.length) return false;
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) return false;
  }
  return true;
};

const withGatewayQuery = (path: string, gatewayId: string): string => {
  if (!gatewayId) return path;
  return `${path}?gateway=${encodeURIComponent(gatewayId)}`;
};

export default function AgentRoutingEditPage({ agentId }: AgentRoutingEditPageProps) {
  const { isSignedIn } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const { isAdmin } = useOrganizationMembership(isSignedIn);

  const [primaryModelDraft, setPrimaryModelDraft] = useState<string | null>(null);
  const [fallbackModelDraft, setFallbackModelDraft] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const agentsKey = getListAgentsApiV1AgentsGetQueryKey();

  const agentsQuery = useListAgentsApiV1AgentsGet<
    listAgentsApiV1AgentsGetResponse,
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

  const updateAgentMutation = useUpdateAgentApiV1AgentsAgentIdPatch<ApiError>({
    mutation: {
      onSuccess: async () => {
        await queryClient.invalidateQueries({ queryKey: agentsKey });
        if (agent?.gateway_id) {
          router.push(withGatewayQuery("/models/routing", agent.gateway_id));
          return;
        }
        router.push("/models/routing");
      },
      onError: (updateError) => {
        setError(updateError.message || "Unable to save agent routing.");
      },
    },
  });

  const agents = useMemo<AgentRead[]>(() => {
    if (agentsQuery.data?.status !== 200) return [];
    return agentsQuery.data.data.items ?? [];
  }, [agentsQuery.data]);

  const boards = useMemo<BoardRead[]>(() => {
    if (boardsQuery.data?.status !== 200) return [];
    return boardsQuery.data.data.items ?? [];
  }, [boardsQuery.data]);

  const gateways = useMemo(() => {
    if (gatewaysQuery.data?.status !== 200) return [];
    return gatewaysQuery.data.data.items ?? [];
  }, [gatewaysQuery.data]);

  const models = useMemo<LlmModelRead[]>(() => {
    if (modelsQuery.data?.status !== 200) return [];
    return modelsQuery.data.data;
  }, [modelsQuery.data]);

  const boardsById = useMemo(() => new Map(boards.map((board) => [board.id, board] as const)), [boards]);
  const gatewaysById = useMemo(
    () => new Map(gateways.map((gateway) => [gateway.id, gateway] as const)),
    [gateways],
  );

  const agent = agents.find((item) => item.id === agentId) ?? null;
  const agentBoard = agent?.board_id ? (boardsById.get(agent.board_id) ?? null) : null;
  const modelsForGateway = agent?.gateway_id
    ? models.filter((model) => model.gateway_id === agent.gateway_id)
    : [];
  const modelsById = new Map(modelsForGateway.map((item) => [item.id, item] as const));
  const availableModelIds = new Set(modelsForGateway.map((model) => model.id));
  const defaultPrimaryModel = modelsForGateway[0] ?? null;
  const baselinePrimaryModelId = agent?.primary_model_id ?? "";
  const baselineFallbackModelIds = agent?.fallback_model_ids ?? [];
  const primaryModelIdCandidate = primaryModelDraft ?? baselinePrimaryModelId;
  const primaryModelId = availableModelIds.has(primaryModelIdCandidate)
    ? primaryModelIdCandidate
    : "";
  const fallbackModelIds = (() => {
    const source = fallbackModelDraft ?? baselineFallbackModelIds;
    return source.filter(
      (modelIdValue, index, list) =>
        modelIdValue !== primaryModelId &&
        availableModelIds.has(modelIdValue) &&
        list.indexOf(modelIdValue) === index,
    );
  })();

  const selectedPrimary = primaryModelId ? (modelsById.get(primaryModelId) ?? null) : null;

  const effectivePrimaryModel = selectedPrimary ?? defaultPrimaryModel;

  const status: RoutingStatus = primaryModelId
    ? "override"
    : effectivePrimaryModel
      ? "default"
      : "unconfigured";

  const selectedFallbackModels = fallbackModelIds
    .map((id) => modelsById.get(id) ?? null)
    .filter((model): model is LlmModelRead => model !== null);

  const modelOptions: SearchableSelectOption[] = modelsForGateway.map((model) => ({
    value: model.id,
    label: modelOptionLabel(model),
  }));

  const hasUnsavedChanges = (() => {
    if (!agent) return false;
    return (
      baselinePrimaryModelId !== primaryModelId ||
      !stringListsMatch(baselineFallbackModelIds, fallbackModelIds)
    );
  })();

  const handleSave = () => {
    if (!agent) {
      setError("Agent not found.");
      return;
    }

    if (primaryModelId && !availableModelIds.has(primaryModelId)) {
      setError("Primary model must belong to this gateway catalog.");
      return;
    }

    setError(null);
    updateAgentMutation.mutate({
      agentId: agent.id,
      params: { force: true },
      data: {
        primary_model_id: primaryModelId || null,
        fallback_model_ids: fallbackModelIds.length > 0 ? fallbackModelIds : null,
      },
    });
  };

  const handleRevert = () => {
    setError(null);
    setPrimaryModelDraft(null);
    setFallbackModelDraft(null);
  };

  const requestedGateway = searchParams.get("gateway")?.trim() ?? "";
  const backGatewayId = agent?.gateway_id ?? requestedGateway;
  const gatewayName = agent?.gateway_id ? (gatewaysById.get(agent.gateway_id)?.name ?? null) : null;

  const pageError =
    agentsQuery.error?.message ??
    boardsQuery.error?.message ??
    gatewaysQuery.error?.message ??
    modelsQuery.error?.message ??
    null;

  const missingAgent =
    !agentsQuery.isLoading &&
    agentsQuery.data?.status === 200 &&
    !agent;

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to edit agent routing.",
        forceRedirectUrl: "/models/routing",
        signUpForceRedirectUrl: "/models/routing",
      }}
      title="Edit agent routing"
      description="Set primary override and fallback models for this agent."
      isAdmin={isAdmin}
      adminOnlyMessage="Only organization owners and admins can edit agent routing."
    >
      <div className="space-y-4">
        {missingAgent ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            Agent not found.
          </div>
        ) : (
          <div className="space-y-4">
            <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">Agent details</h2>
              {!agent ? (
                <p className="mt-3 text-sm text-slate-500">Loading agent...</p>
              ) : (
                <table className="mt-3 min-w-full border-collapse text-sm">
                  <tbody>
                    <tr className="border-t border-slate-200">
                      <th className="w-44 px-3 py-3 text-left font-medium text-slate-600">Agent</th>
                      <td className="px-3 py-3">
                        <Link
                          href={`/agents/${agent.id}`}
                          className="font-semibold text-blue-700 underline-offset-2 hover:underline"
                        >
                          {agent.name}
                        </Link>
                      </td>
                    </tr>
                    <tr className="border-t border-slate-200">
                      <th className="px-3 py-3 text-left font-medium text-slate-600">Role</th>
                      <td className="px-3 py-3 text-slate-700">{agentRoleLabel(agent) ?? "Unspecified"}</td>
                    </tr>
                    <tr className="border-t border-slate-200">
                      <th className="px-3 py-3 text-left font-medium text-slate-600">Board</th>
                      <td className="px-3 py-3 text-slate-700">
                        {agent.board_id ? (
                          <Link
                            href={`/boards/${agent.board_id}`}
                            className="text-blue-700 underline-offset-2 hover:underline"
                          >
                            {agentBoard?.name ?? "Open board"}
                          </Link>
                        ) : (
                          "Gateway main"
                        )}
                      </td>
                    </tr>
                    <tr className="border-t border-slate-200">
                      <th className="px-3 py-3 text-left font-medium text-slate-600">Gateway</th>
                      <td className="px-3 py-3 text-slate-700">
                        {gatewayName ? `${gatewayName} (${agent.gateway_id})` : (agent.gateway_id || "Unknown gateway")}
                      </td>
                    </tr>
                    <tr className="border-t border-slate-200">
                      <th className="px-3 py-3 text-left font-medium text-slate-600">Status</th>
                      <td className="px-3 py-3">
                        <Badge variant={routingStatusVariant(status)}>{routingStatusLabel(status)}</Badge>
                      </td>
                    </tr>
                    <tr className="border-t border-slate-200">
                      <th className="px-3 py-3 text-left font-medium text-slate-600">Effective primary</th>
                      <td className="px-3 py-3 text-slate-700">
                        {effectivePrimaryModel ? modelOptionLabel(effectivePrimaryModel) : "None"}
                        {!selectedPrimary && effectivePrimaryModel ? " (inherited from default)" : ""}
                      </td>
                    </tr>
                  </tbody>
                </table>
              )}
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-slate-900">Routing assignment</h2>
                {!agent ? (
                  <Badge variant="outline">Loading</Badge>
                ) : hasUnsavedChanges ? (
                  <Badge variant="warning">Unsaved changes</Badge>
                ) : (
                  <Badge variant="outline">Saved</Badge>
                )}
              </div>
              <p className="mt-1 text-xs text-slate-600">
                Primary override is optional. Empty primary inherits the gateway default.
              </p>

              <div className="mt-4 space-y-4">
                <div>
                  <p className="mb-2 text-sm font-medium text-slate-700">Primary model override</p>
                  <SearchableSelect
                    ariaLabel="Select primary model"
                    value={primaryModelId}
                    onValueChange={(value) => {
                      setPrimaryModelDraft(value);
                      setFallbackModelDraft((current) => {
                        const source = current ?? baselineFallbackModelIds;
                        return source.filter((item) => item !== value);
                      });
                    }}
                    options={modelOptions}
                    placeholder="Use gateway default (no override)"
                    searchPlaceholder="Search models..."
                    emptyMessage="No matching models."
                    triggerClassName="w-full"
                    disabled={!agent || updateAgentMutation.isPending || modelOptions.length === 0}
                  />
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-slate-700">
                      Fallback models ({fallbackModelIds.length})
                    </p>
                    {selectedFallbackModels.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {selectedFallbackModels.map((model) => (
                          <Badge key={model.id} variant="outline" className="normal-case tracking-normal">
                            {model.display_name}
                          </Badge>
                        ))}
                      </div>
                    ) : null}
                  </div>

                  {modelOptions.length === 0 ? (
                    <p className="text-sm text-slate-500">No catalog models available for this gateway yet.</p>
                  ) : (
                    <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                      {modelOptions.map((option) => {
                        const checked = fallbackModelIds.includes(option.value);
                        const disabled = option.value === primaryModelId || !agent;
                        const model = modelsById.get(option.value) ?? null;
                        return (
                          <label
                            key={option.value}
                            className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2"
                          >
                            <span className="flex min-w-0 items-center gap-2">
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={disabled || updateAgentMutation.isPending}
                                onChange={(event) => {
                                  if (event.target.checked) {
                                    setFallbackModelDraft((current) => {
                                      const source = current ?? baselineFallbackModelIds;
                                      return source.includes(option.value)
                                        ? source
                                        : [...source, option.value];
                                    });
                                    return;
                                  }
                                  setFallbackModelDraft((current) => {
                                    const source = current ?? baselineFallbackModelIds;
                                    return source.filter((value) => value !== option.value);
                                  });
                                }}
                              />
                              <span className="min-w-0 truncate text-sm text-slate-700">{option.label}</span>
                            </span>
                            {model ? <Badge variant="outline">{model.provider}</Badge> : null}
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-5 flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  onClick={handleSave}
                  disabled={!agent || updateAgentMutation.isPending || !hasUnsavedChanges}
                >
                  {updateAgentMutation.isPending ? "Saving..." : "Save routing"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleRevert}
                  disabled={!agent || updateAgentMutation.isPending || !hasUnsavedChanges}
                >
                  Revert
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setError(null);
                    setPrimaryModelDraft("");
                    setFallbackModelDraft([]);
                  }}
                  disabled={!agent || updateAgentMutation.isPending}
                >
                  Clear override
                </Button>
                <Link
                  href={withGatewayQuery("/models/routing", backGatewayId)}
                  className={buttonVariants({ variant: "outline", size: "md" })}
                >
                  Back to routing table
                </Link>
              </div>
            </section>
          </div>
        )}

        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {pageError ? <p className="text-sm text-red-600">{pageError}</p> : null}
      </div>
    </DashboardPageLayout>
  );
}
