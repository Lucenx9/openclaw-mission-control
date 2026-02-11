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
import type { GatewayRead, LlmProviderAuthRead } from "@/api/generated/model";
import {
  type listProviderAuthApiV1ModelRegistryProviderAuthGetResponse,
  getListProviderAuthApiV1ModelRegistryProviderAuthGetQueryKey,
  useCreateProviderAuthApiV1ModelRegistryProviderAuthPost,
  useListProviderAuthApiV1ModelRegistryProviderAuthGet,
  useUpdateProviderAuthApiV1ModelRegistryProviderAuthProviderAuthIdPatch,
} from "@/api/generated/model-registry/model-registry";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import SearchableSelect, {
  type SearchableSelectOption,
} from "@/components/ui/searchable-select";
import { useOrganizationMembership } from "@/lib/use-organization-membership";

const PROVIDER_PLACEHOLDER = "openai";

type ProviderAuthFormPageProps =
  | { mode: "create" }
  | { mode: "edit"; providerAuthId: string };

const toGatewayOptions = (gateways: GatewayRead[]): SearchableSelectOption[] =>
  gateways.map((gateway) => ({ value: gateway.id, label: gateway.name }));

const withGatewayQuery = (path: string, gatewayId: string): string => {
  if (!gatewayId) return path;
  return `${path}?gateway=${encodeURIComponent(gatewayId)}`;
};

export default function ProviderAuthFormPage(props: ProviderAuthFormPageProps) {
  const { isSignedIn } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { isAdmin } = useOrganizationMembership(isSignedIn);

  const providerAuthId = props.mode === "edit" ? props.providerAuthId : null;

  const [gatewayDraft, setGatewayDraft] = useState<string | null>(null);
  const [providerDraft, setProviderDraft] = useState<string | null>(null);
  const [configPathDraft, setConfigPathDraft] = useState<string | null>(null);
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);

  const providerAuthKey = getListProviderAuthApiV1ModelRegistryProviderAuthGetQueryKey();

  const gatewaysQuery = useListGatewaysApiV1GatewaysGet<
    listGatewaysApiV1GatewaysGetResponse,
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
      enabled: Boolean(isSignedIn && isAdmin && props.mode === "edit"),
      refetchOnMount: "always",
    },
  });

  const createMutation = useCreateProviderAuthApiV1ModelRegistryProviderAuthPost<ApiError>({
    mutation: {
      onSuccess: async () => {
        await queryClient.invalidateQueries({ queryKey: providerAuthKey });
        router.push(withGatewayQuery("/models/provider-auth", gatewayId));
      },
      onError: (err) => {
        setError(err.message || "Unable to create provider auth entry.");
      },
    },
  });

  const updateMutation =
    useUpdateProviderAuthApiV1ModelRegistryProviderAuthProviderAuthIdPatch<ApiError>({
      mutation: {
        onSuccess: async () => {
          await queryClient.invalidateQueries({ queryKey: providerAuthKey });
          router.push(withGatewayQuery("/models/provider-auth", gatewayId));
        },
        onError: (err) => {
          setError(err.message || "Unable to update provider auth entry.");
        },
      },
    });

  const gateways = useMemo(() => {
    if (gatewaysQuery.data?.status !== 200) return [];
    return gatewaysQuery.data.data.items ?? [];
  }, [gatewaysQuery.data]);

  const providerAuthItems = useMemo<LlmProviderAuthRead[]>(() => {
    if (providerAuthQuery.data?.status !== 200) return [];
    return providerAuthQuery.data.data;
  }, [providerAuthQuery.data]);

  const currentItem = useMemo(() => {
    if (props.mode !== "edit" || !providerAuthId) return null;
    return providerAuthItems.find((item) => item.id === providerAuthId) ?? null;
  }, [props.mode, providerAuthId, providerAuthItems]);

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
  const configPath =
    configPathDraft ?? (props.mode === "edit" ? (currentItem?.config_path ?? "") : "");

  const isBusy = createMutation.isPending || updateMutation.isPending;
  const pageError =
    gatewaysQuery.error?.message ??
    (props.mode === "edit" ? providerAuthQuery.error?.message : null) ??
    null;

  const title = props.mode === "create" ? "Add provider auth" : "Edit provider auth";
  const description =
    props.mode === "create"
      ? "Create provider credentials for a gateway config path."
      : "Update provider credentials and config path for this gateway entry.";

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!gatewayId) {
      setError("Select a gateway first.");
      return;
    }

    const normalizedProvider = provider.trim().toLowerCase();
    const normalizedConfigPath = configPath.trim() || `providers.${normalizedProvider}.apiKey`;

    if (!normalizedProvider) {
      setError("Provider is required.");
      return;
    }

    if (props.mode === "create") {
      const normalizedSecret = secret.trim();
      if (!normalizedSecret) {
        setError("Secret is required.");
        return;
      }
      setError(null);
      createMutation.mutate({
        data: {
          gateway_id: gatewayId,
          provider: normalizedProvider,
          config_path: normalizedConfigPath,
          secret: normalizedSecret,
        },
      });
      return;
    }

    if (!providerAuthId) {
      setError("Missing provider auth identifier.");
      return;
    }

    setError(null);
    updateMutation.mutate({
      providerAuthId,
      data: {
        provider: normalizedProvider,
        config_path: normalizedConfigPath,
        secret: secret.trim() ? secret.trim() : undefined,
      },
    });
  };

  const missingEditItem =
    props.mode === "edit" &&
    !providerAuthQuery.isLoading &&
    providerAuthQuery.data?.status === 200 &&
    !currentItem;

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to manage provider auth.",
        forceRedirectUrl: "/models/provider-auth",
        signUpForceRedirectUrl: "/models/provider-auth",
      }}
      title={title}
      description={description}
      isAdmin={isAdmin}
      adminOnlyMessage="Only organization owners and admins can manage provider auth."
    >
      <div className="space-y-4">
        {missingEditItem ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            Provider auth entry not found.
          </div>
        ) : (
          <form
            onSubmit={handleSubmit}
            className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
          >
            <div className="space-y-4">
              <h2 className="text-sm font-semibold text-slate-900">Credentials</h2>

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
                    placeholder={PROVIDER_PLACEHOLDER}
                    disabled={isBusy}
                  />
                </label>

                <label className="space-y-2 text-sm text-slate-700 md:col-span-2">
                  <span className="font-medium text-slate-900">Config path</span>
                  <Input
                    value={configPath}
                    onChange={(event) => setConfigPathDraft(event.target.value)}
                    placeholder="providers.openai.apiKey"
                    disabled={isBusy}
                  />
                </label>

                <label className="space-y-2 text-sm text-slate-700 md:col-span-2">
                  <span className="font-medium text-slate-900">
                    {props.mode === "create" ? (
                      <>
                        Secret <span className="text-red-500">*</span>
                      </>
                    ) : (
                      "Secret (leave blank to keep current)"
                    )}
                  </span>
                  <Input
                    value={secret}
                    onChange={(event) => setSecret(event.target.value)}
                    type="password"
                    placeholder="sk-..."
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
                    : "Create provider auth"
                  : updateMutation.isPending
                    ? "Saving..."
                    : "Save changes"}
              </Button>
              <Link
                href={withGatewayQuery("/models/provider-auth", gatewayId || requestedGateway)}
                className={buttonVariants({ variant: "outline", size: "md" })}
              >
                Back to provider auth
              </Link>
            </div>
          </form>
        )}
      </div>
    </DashboardPageLayout>
  );
}
