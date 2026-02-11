"use client";

export const dynamic = "force-dynamic";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/auth/clerk";
import { ApiError, customFetch } from "@/api/mutator";
import {
  type listGatewaysApiV1GatewaysGetResponse,
  useListGatewaysApiV1GatewaysGet,
} from "@/api/generated/gateways/gateways";
import {
  type listAgentsApiV1AgentsGetResponse,
  getListAgentsApiV1AgentsGetQueryKey,
  useListAgentsApiV1AgentsGet,
} from "@/api/generated/agents/agents";
import {
  type listModelsApiV1ModelRegistryModelsGetResponse,
  type listProviderAuthApiV1ModelRegistryProviderAuthGetResponse,
  getListModelsApiV1ModelRegistryModelsGetQueryKey,
  getListProviderAuthApiV1ModelRegistryProviderAuthGetQueryKey,
  useListModelsApiV1ModelRegistryModelsGet,
  useListProviderAuthApiV1ModelRegistryProviderAuthGet,
  useSyncGatewayModelsApiV1ModelRegistryGatewaysGatewayIdSyncPost,
} from "@/api/generated/model-registry/model-registry";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import SearchableSelect, {
  type SearchableSelectOption,
} from "@/components/ui/searchable-select";
import { useOrganizationMembership } from "@/lib/use-organization-membership";

type GatewayModelPullResult = {
  gateway_id: string;
  provider_auth_imported: number;
  model_catalog_imported: number;
  agent_models_imported: number;
  errors?: string[];
};

const toGatewayOptions = (gateways: { id: string; name: string }[]): SearchableSelectOption[] =>
  gateways.map((gateway) => ({ value: gateway.id, label: gateway.name }));

export default function ModelsSyncPage() {
  const { isSignedIn } = useAuth();
  const queryClient = useQueryClient();
  const { isAdmin } = useOrganizationMembership(isSignedIn);

  const [activeGatewayDraft, setActiveGatewayDraft] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

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

  const syncMutation =
    useSyncGatewayModelsApiV1ModelRegistryGatewaysGatewayIdSyncPost<ApiError>({
      mutation: {
        onSuccess: async (response) => {
          if (response.status === 200) {
            const result = response.data;
            const syncErrors = result.errors ?? [];
            const suffix =
              syncErrors.length > 0
                ? ` Completed with ${syncErrors.length} warning(s).`
                : " Synced cleanly.";
            setSyncMessage(
              `Patched ${result.provider_auth_patched} provider auth, ${result.model_catalog_patched} catalog models, ${result.agent_models_patched} agent assignments, and ${result.sessions_patched} sessions.${suffix}`,
            );
          }
          await Promise.all([
            queryClient.invalidateQueries({ queryKey: modelsKey }),
            queryClient.invalidateQueries({ queryKey: providerAuthKey }),
            queryClient.invalidateQueries({ queryKey: agentsKey }),
          ]);
        },
        onError: (error) => {
          setSyncMessage(error.message || "Gateway sync failed.");
        },
      },
    });

  const pullMutation = useMutation<
    { data: GatewayModelPullResult; status: number; headers: Headers },
    ApiError,
    string
  >({
    mutationFn: async (gatewayId: string) =>
      customFetch<{ data: GatewayModelPullResult; status: number; headers: Headers }>(
        `/api/v1/model-registry/gateways/${gatewayId}/pull`,
        { method: "POST" },
      ),
    onSuccess: async (response) => {
      if (response.status === 200) {
        const result = response.data;
        const pullErrors = result.errors ?? [];
        const suffix =
          pullErrors.length > 0
            ? ` Imported with ${pullErrors.length} warning(s).`
            : " Imported cleanly.";
        setSyncMessage(
          `Imported ${result.provider_auth_imported} provider auth entries, ${result.model_catalog_imported} catalog models, and ${result.agent_models_imported} agent assignments.${suffix}`,
        );
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: modelsKey }),
        queryClient.invalidateQueries({ queryKey: providerAuthKey }),
        queryClient.invalidateQueries({ queryKey: agentsKey }),
      ]);
    },
    onError: (error) => {
      setSyncMessage(error.message || "Gateway pull failed.");
    },
  });

  const gateways =
    gatewaysQuery.data?.status === 200 ? (gatewaysQuery.data.data.items ?? []) : [];
  const models =
    modelsQuery.data?.status === 200 ? modelsQuery.data.data : [];
  const providerAuth =
    providerAuthQuery.data?.status === 200 ? providerAuthQuery.data.data : [];
  const agents =
    agentsQuery.data?.status === 200 ? (agentsQuery.data.data.items ?? []) : [];

  const activeGatewayId =
    activeGatewayDraft && gateways.some((gateway) => gateway.id === activeGatewayDraft)
      ? activeGatewayDraft
      : (gateways[0]?.id ?? "");

  const activeGateway = gateways.find((gateway) => gateway.id === activeGatewayId) ?? null;

  const providerCount = providerAuth.filter((item) => item.gateway_id === activeGatewayId).length;
  const modelCount = models.filter((item) => item.gateway_id === activeGatewayId).length;
  const agentCount = agents.filter((item) => item.gateway_id === activeGatewayId).length;
  const primaryOverrideCount = agents.filter(
    (item) => item.gateway_id === activeGatewayId && Boolean(item.primary_model_id),
  ).length;

  const isBusy = pullMutation.isPending || syncMutation.isPending;

  const pageError =
    gatewaysQuery.error?.message ??
    modelsQuery.error?.message ??
    providerAuthQuery.error?.message ??
    agentsQuery.error?.message ??
    null;

  const runGatewayPull = () => {
    if (!activeGatewayId) {
      setSyncMessage("Select a gateway first.");
      return;
    }
    setSyncMessage(null);
    pullMutation.mutate(activeGatewayId);
  };

  const runGatewaySync = () => {
    if (!activeGatewayId) {
      setSyncMessage("Select a gateway first.");
      return;
    }
    setSyncMessage(null);
    syncMutation.mutate({ gatewayId: activeGatewayId });
  };

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to sync models with a gateway.",
        forceRedirectUrl: "/models/sync",
        signUpForceRedirectUrl: "/models/sync",
      }}
      title="Gateway Sync"
      description="Pull and push provider auth, catalog models, and agent routing per gateway."
      isAdmin={isAdmin}
      adminOnlyMessage="Only organization owners and admins can sync models."
    >
      <div className="space-y-6">
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-full max-w-md">
              <p className="mb-2 text-sm font-medium text-slate-900">Gateway</p>
              <SearchableSelect
                ariaLabel="Select gateway"
                value={activeGatewayId}
                onValueChange={setActiveGatewayDraft}
                options={toGatewayOptions(gateways)}
                placeholder="Select gateway"
                searchPlaceholder="Search gateways..."
                emptyMessage="No matching gateways."
                triggerClassName="w-full"
                disabled={gateways.length === 0 || isBusy}
              />
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={runGatewayPull}
              disabled={!activeGatewayId || isBusy}
            >
              {pullMutation.isPending ? "Pulling..." : "Pull from gateway"}
            </Button>
            <Button
              type="button"
              onClick={runGatewaySync}
              disabled={!activeGatewayId || isBusy}
            >
              {syncMutation.isPending ? "Pushing..." : "Push to gateway"}
            </Button>
          </div>

          {syncMessage ? (
            <p className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
              {syncMessage}
            </p>
          ) : null}

          {pageError ? <p className="mt-4 text-sm text-red-500">{pageError}</p> : null}
        </section>

        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-slate-900">
                {activeGateway ? `${activeGateway.name} summary` : "Gateway summary"}
              </h3>
              <Badge variant="outline">{activeGatewayId ? "Selected" : "No gateway"}</Badge>
            </div>
          </div>

          <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <p className="text-xs uppercase tracking-wider text-slate-500">Provider auth</p>
              <p className="mt-1 text-xl font-semibold text-slate-900">{providerCount}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <p className="text-xs uppercase tracking-wider text-slate-500">Catalog models</p>
              <p className="mt-1 text-xl font-semibold text-slate-900">{modelCount}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <p className="text-xs uppercase tracking-wider text-slate-500">Agents</p>
              <p className="mt-1 text-xl font-semibold text-slate-900">{agentCount}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <p className="text-xs uppercase tracking-wider text-slate-500">Primary overrides</p>
              <p className="mt-1 text-xl font-semibold text-slate-900">{primaryOverrideCount}</p>
            </div>
          </div>
        </section>
      </div>
    </DashboardPageLayout>
  );
}
