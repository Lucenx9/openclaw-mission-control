"use client";

export const dynamic = "force-dynamic";

import { useParams } from "next/navigation";

import ProviderAuthFormPage from "../../../_components/ProviderAuthFormPage";

export default function ModelsProviderAuthEditPage() {
  const params = useParams();
  const providerAuthIdParam = params?.providerAuthId;
  const providerAuthId = Array.isArray(providerAuthIdParam)
    ? providerAuthIdParam[0]
    : providerAuthIdParam;

  return <ProviderAuthFormPage mode="edit" providerAuthId={providerAuthId ?? ""} />;
}
