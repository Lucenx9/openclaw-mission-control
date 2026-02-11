"use client";

export const dynamic = "force-dynamic";

import { useParams } from "next/navigation";

import CatalogModelFormPage from "../../../_components/CatalogModelFormPage";

export default function ModelsCatalogEditPage() {
  const params = useParams();
  const modelIdParam = params?.modelId;
  const modelId = Array.isArray(modelIdParam) ? modelIdParam[0] : modelIdParam;

  return <CatalogModelFormPage mode="edit" modelId={modelId ?? ""} />;
}
