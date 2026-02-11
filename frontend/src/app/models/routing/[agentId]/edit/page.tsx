"use client";

export const dynamic = "force-dynamic";

import { useParams } from "next/navigation";

import AgentRoutingEditPage from "../../../_components/AgentRoutingEditPage";

export default function ModelsRoutingEditPageWrapper() {
  const params = useParams();
  const agentIdParam = params?.agentId;
  const agentId = Array.isArray(agentIdParam) ? agentIdParam[0] : agentIdParam;

  return <AgentRoutingEditPage agentId={agentId ?? ""} />;
}
