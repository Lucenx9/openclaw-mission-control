"use client";

import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { useAuth } from "@/auth/clerk";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/mutator";
import {
  type listGatewaysApiV1GatewaysGetResponse,
  useListGatewaysApiV1GatewaysGet,
} from "@/api/generated/gateways/gateways";
import type { GatewayRead, LlmModelRead } from "@/api/generated/model";
import {
  type listModelsApiV1ModelRegistryModelsGetResponse,
  getListModelsApiV1ModelRegistryModelsGetQueryKey,
  useCreateModelApiV1ModelRegistryModelsPost,
  useListModelsApiV1ModelRegistryModelsGet,
  useUpdateModelApiV1ModelRegistryModelsModelIdPatch,
} from "@/api/generated/model-registry/model-registry";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import SearchableSelect, {
  type SearchableSelectOption,
} from "@/components/ui/searchable-select";
import { Textarea } from "@/components/ui/textarea";
import { useOrganizationMembership } from "@/lib/use-organization-membership";

type CatalogModelFormPageProps =
  | { mode: "create" }
  | { mode: "edit"; modelId: string };

const toGatewayOptions = (gateways: GatewayRead[]): SearchableSelectOption[] =>
  gateways.map((gateway) => ({ value: gateway.id, label: gateway.name }));

const withGatewayQuery = (path: string, gatewayId: string): string => {
  if (!gatewayId) return path;
  return `${path}?gateway=${encodeURIComponent(gatewayId)}`;
};

export default function CatalogModelFormPage(props: CatalogModelFormPageProps) {
  const { isSignedIn } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { isAdmin } = useOrganizationMembership(isSignedIn);

  const modelIdParam = props.mode === "edit" ? props.modelId : null;

  const [gatewayDraft, setGatewayDraft] = useState<string | null>(null);
  const [providerDraft, setProviderDraft] = useState<string | null>(null);
  const [modelIdDraft, setModelIdDraft] = useState<string | null>(null);
  const [displayNameDraft, setDisplayNameDraft] = useState<string | null>(null);
  const [settingsDraft, setSettingsDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const modelsKey = getListModelsApiV1ModelRegistryModelsGetQueryKey();

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

  const createMutation = useCreateModelApiV1ModelRegistryModelsPost<ApiError>({
    mutation: {
      onSuccess: async () => {
        await queryClient.invalidateQueries({ queryKey: modelsKey });
        router.push(withGatewayQuery("/models/catalog", gatewayId));
      },
      onError: (err) => {
        setError(err.message || "Unable to create model.");
      },
    },
  });

  const updateMutation = useUpdateModelApiV1ModelRegistryModelsModelIdPatch<ApiError>({
    mutation: {
      onSuccess: async () => {
        await queryClient.invalidateQueries({ queryKey: modelsKey });
        router.push(withGatewayQuery("/models/catalog", gatewayId));
      },
      onError: (err) => {
        setError(err.message || "Unable to update model.");
      },
    },
  });

  const gateways = useMemo(() => {
    if (gatewaysQuery.data?.status !== 200) return [];
    return gatewaysQuery.data.data.items ?? [];
  }, [gatewaysQuery.data]);

  const models = useMemo<LlmModelRead[]>(() => {
    if (modelsQuery.data?.status !== 200) return [];
    return modelsQuery.data.data;
  }, [modelsQuery.data]);

  const currentItem = useMemo(() => {
    if (props.mode !== "edit" || !modelIdParam) return null;
    return models.find((item) => item.id === modelIdParam) ?? null;
  }, [modelIdParam, models, props.mode]);

  const gatewayOptions = useMemo(() => toGatewayOptions(gateways), [gateways]);
  const requestedGateway = searchParams.get("gateway")?.trim() ?? "";
  const gatewayId = (() => {
    if (gateways.length === 0) return "";
    if (props.mode === "edit" && currentItem?.gateway_id) {
      return currentItem.gateway_id;
    }
    if (gatewayDraft && gateways.some((gateway) => gateway.id === gatewayDraft)) {
      return gatewayDraft;
    }
    if (requestedGateway && gateways.some((gateway) => gateway.id === requestedGateway)) {
      return requestedGateway;
    }
    return gateways[0].id;
  })();

  const provider = providerDraft ?? (props.mode === "edit" ? (currentItem?.provider ?? "") : "");
  const modelId = modelIdDraft ?? (props.mode === "edit" ? (currentItem?.model_id ?? "") : "");
  const displayName =
    displayNameDraft ?? (props.mode === "edit" ? (currentItem?.display_name ?? "") : "");
  const settingsText =
    settingsDraft ??
    (props.mode === "edit" && currentItem?.settings
      ? JSON.stringify(currentItem.settings, null, 2)
      : "");

  const isBusy = createMutation.isPending || updateMutation.isPending;
  const pageError = gatewaysQuery.error?.message ?? modelsQuery.error?.message ?? null;

  const title = props.mode === "create" ? "Add catalog model" : "Edit catalog model";
  const description =
    props.mode === "create"
      ? "Create a gateway model catalog entry for agent routing."
      : "Update model metadata and settings for this catalog entry.";

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!gatewayId) {
      setError("Select a gateway first.");
      return;
    }

    const normalizedProvider = provider.trim().toLowerCase();
    const normalizedModelId = modelId.trim();
    const normalizedDisplayName = displayName.trim();

    if (!normalizedProvider || !normalizedModelId || !normalizedDisplayName) {
      setError("Provider, model ID, and display name are required.");
      return;
    }

    let settings: Record<string, unknown> | undefined;
    const normalizedSettings = settingsText.trim();
    if (normalizedSettings) {
      try {
        const parsed = JSON.parse(normalizedSettings) as unknown;
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("settings must be an object");
        }
        settings = parsed as Record<string, unknown>;
      } catch {
        setError("Settings must be a valid JSON object.");
        return;
      }
    } else if (props.mode === "edit") {
      settings = {};
    }

    setError(null);

    if (props.mode === "create") {
      createMutation.mutate({
        data: {
          gateway_id: gatewayId,
          provider: normalizedProvider,
          model_id: normalizedModelId,
          display_name: normalizedDisplayName,
          settings,
        },
      });
      return;
    }

    if (!modelIdParam) {
      setError("Missing model identifier.");
      return;
    }

    updateMutation.mutate({
      modelId: modelIdParam,
      data: {
        provider: normalizedProvider,
        model_id: normalizedModelId,
        display_name: normalizedDisplayName,
        settings,
      },
    });
  };

  const missingEditItem =
    props.mode === "edit" &&
    !modelsQuery.isLoading &&
    modelsQuery.data?.status === 200 &&
    !currentItem;

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to manage catalog models.",
        forceRedirectUrl: "/models/catalog",
        signUpForceRedirectUrl: "/models/catalog",
      }}
      title={title}
      description={description}
      isAdmin={isAdmin}
      adminOnlyMessage="Only organization owners and admins can manage model catalog entries."
    >
      <div className="space-y-4">
        {missingEditItem ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            Catalog model entry not found.
          </div>
        ) : (
          <form
            onSubmit={handleSubmit}
            className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
          >
            <div className="space-y-4">
              <h2 className="text-sm font-semibold text-slate-900">Model details</h2>

              <div className="grid gap-4 md:grid-cols-2">
                <label className="space-y-2 text-sm text-slate-700">
                  <span className="font-medium text-slate-900">
                    Gateway <span className="text-red-500">*</span>
                  </span>
                  <SearchableSelect
                    ariaLabel="Select gateway"
                    value={gatewayId}
                    onValueChange={setGatewayDraft}
                    options={gatewayOptions}
                    placeholder="Select gateway"
                    searchPlaceholder="Search gateways..."
                    emptyMessage="No matching gateways."
                    triggerClassName="w-full"
                    disabled={props.mode === "edit" || isBusy}
                  />
                </label>

                <label className="space-y-2 text-sm text-slate-700">
                  <span className="font-medium text-slate-900">
                    Provider <span className="text-red-500">*</span>
                  </span>
                  <Input
                    value={provider}
                    onChange={(event) => setProviderDraft(event.target.value)}
                    placeholder="openai"
                    disabled={isBusy}
                  />
                </label>

                <label className="space-y-2 text-sm text-slate-700">
                  <span className="font-medium text-slate-900">
                    Model ID <span className="text-red-500">*</span>
                  </span>
                  <Input
                    value={modelId}
                    onChange={(event) => setModelIdDraft(event.target.value)}
                    placeholder="openai-codex/gpt-5.3"
                    disabled={isBusy}
                  />
                </label>

                <label className="space-y-2 text-sm text-slate-700">
                  <span className="font-medium text-slate-900">
                    Display name <span className="text-red-500">*</span>
                  </span>
                  <Input
                    value={displayName}
                    onChange={(event) => setDisplayNameDraft(event.target.value)}
                    placeholder="GPT-5.3 (Codex)"
                    disabled={isBusy}
                  />
                </label>

                <label className="space-y-2 text-sm text-slate-700 md:col-span-2">
                  <span>Settings JSON (optional)</span>
                  <Textarea
                    value={settingsText}
                    onChange={(event) => setSettingsDraft(event.target.value)}
                    rows={8}
                    placeholder='{"temperature": 0.2}'
                    disabled={isBusy}
                  />
                </label>
              </div>
            </div>

            {error ? <p className="text-sm text-red-500">{error}</p> : null}
            {pageError ? <p className="text-sm text-red-500">{pageError}</p> : null}

            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={isBusy || missingEditItem}>
                {props.mode === "create"
                  ? createMutation.isPending
                    ? "Creating..."
                    : "Create model"
                  : updateMutation.isPending
                    ? "Saving..."
                    : "Save changes"}
              </Button>
              <Link
                href={withGatewayQuery("/models/catalog", gatewayId || requestedGateway)}
                className={buttonVariants({ variant: "outline", size: "md" })}
              >
                Back to model catalog
              </Link>
            </div>
          </form>
        )}
      </div>
    </DashboardPageLayout>
  );
}
