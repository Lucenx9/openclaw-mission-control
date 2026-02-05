"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "@clerk/nextjs";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { getApiBaseUrl } from "@/lib/api-base";
import { cn } from "@/lib/utils";

const apiBase = getApiBaseUrl();

type Approval = {
  id: string;
  action_type: string;
  payload?: Record<string, unknown> | null;
  confidence: number;
  rubric_scores?: Record<string, number> | null;
  status: string;
  created_at: string;
  resolved_at?: string | null;
};

type BoardApprovalsPanelProps = {
  boardId: string;
  approvals?: Approval[];
  isLoading?: boolean;
  error?: string | null;
  onRefresh?: () => void;
  onDecision?: (approvalId: string, status: "approved" | "rejected") => void;
  scrollable?: boolean;
};

const formatTimestamp = (value?: string | null) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const statusBadgeVariant = (status: string) => {
  if (status === "approved") return "success";
  if (status === "rejected") return "danger";
  return "outline";
};

const confidenceVariant = (confidence: number) => {
  if (confidence >= 90) return "success";
  if (confidence >= 80) return "accent";
  return "warning";
};

const humanizeAction = (value: string) =>
  value
    .split(".")
    .map((part) =>
      part
        .replace(/_/g, " ")
        .replace(/\b\w/g, (char) => char.toUpperCase())
    )
    .join(" · ");

const payloadValue = (payload: Approval["payload"], key: string) => {
  if (!payload) return null;
  const value = payload[key as keyof typeof payload];
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  return null;
};

const approvalSummary = (approval: Approval) => {
  const payload = approval.payload ?? {};
  const taskId =
    payloadValue(payload, "task_id") ??
    payloadValue(payload, "taskId") ??
    payloadValue(payload, "taskID");
  const assignedAgentId =
    payloadValue(payload, "assigned_agent_id") ??
    payloadValue(payload, "assignedAgentId");
  const reason = payloadValue(payload, "reason");
  const title = payloadValue(payload, "title");
  const role = payloadValue(payload, "role");
  const isAssign = approval.action_type.includes("assign");
  const rows: Array<{ label: string; value: string }> = [];
  if (taskId) rows.push({ label: "Task", value: taskId });
  if (isAssign) {
    rows.push({
      label: "Assignee",
      value: assignedAgentId ?? "Unassigned",
    });
  }
  if (title) rows.push({ label: "Title", value: title });
  if (role) rows.push({ label: "Role", value: role });
  return { taskId, reason, rows };
};

export function BoardApprovalsPanel({
  boardId,
  approvals: externalApprovals,
  isLoading: externalLoading,
  error: externalError,
  onRefresh,
  onDecision,
  scrollable = false,
}: BoardApprovalsPanelProps) {
  const { getToken, isSignedIn } = useAuth();
  const [internalApprovals, setInternalApprovals] = useState<Approval[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const usingExternal = Array.isArray(externalApprovals);
  const approvals = usingExternal ? externalApprovals ?? [] : internalApprovals;
  const loadingState = usingExternal ? externalLoading ?? false : isLoading;
  const errorState = usingExternal ? externalError ?? null : error;

  const loadApprovals = useCallback(async () => {
    if (usingExternal) return;
    if (!isSignedIn || !boardId) return;
    setIsLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const res = await fetch(`${apiBase}/api/v1/boards/${boardId}/approvals`, {
        headers: {
          Authorization: token ? `Bearer ${token}` : "",
        },
      });
      if (!res.ok) throw new Error("Unable to load approvals.");
      const data = (await res.json()) as Approval[];
      setInternalApprovals(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load approvals.");
    } finally {
      setIsLoading(false);
    }
  }, [boardId, getToken, isSignedIn, usingExternal]);

  useEffect(() => {
    if (usingExternal) return;
    loadApprovals();
    if (!isSignedIn || !boardId) return;
    const interval = setInterval(loadApprovals, 15000);
    return () => clearInterval(interval);
  }, [boardId, isSignedIn, loadApprovals, usingExternal]);

  const handleDecision = useCallback(
    async (approvalId: string, status: "approved" | "rejected") => {
      if (onDecision) {
        onDecision(approvalId, status);
        return;
      }
      if (usingExternal) return;
      if (!isSignedIn || !boardId) return;
      setUpdatingId(approvalId);
      setError(null);
      try {
        const token = await getToken();
        const res = await fetch(
          `${apiBase}/api/v1/boards/${boardId}/approvals/${approvalId}`,
          {
            method: "PATCH",
            headers: {
              "Content-Type": "application/json",
              Authorization: token ? `Bearer ${token}` : "",
            },
            body: JSON.stringify({ status }),
          }
        );
        if (!res.ok) throw new Error("Unable to update approval.");
        const updated = (await res.json()) as Approval;
        setInternalApprovals((prev) =>
          prev.map((item) => (item.id === approvalId ? updated : item))
        );
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Unable to update approval."
        );
      } finally {
        setUpdatingId(null);
      }
    },
    [boardId, getToken, isSignedIn, onDecision, usingExternal]
  );

  const sortedApprovals = useMemo(() => {
    const sortByTime = (items: Approval[]) =>
      [...items].sort((a, b) => {
        const aTime = new Date(a.created_at).getTime();
        const bTime = new Date(b.created_at).getTime();
        return bTime - aTime;
      });
    const pending = sortByTime(
      approvals.filter((item) => item.status === "pending")
    );
    const resolved = sortByTime(
      approvals.filter((item) => item.status !== "pending")
    );
    return { pending, resolved };
  }, [approvals]);

  const toggleExpanded = useCallback((approvalId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(approvalId)) {
        next.delete(approvalId);
      } else {
        next.add(approvalId);
      }
      return next;
    });
  }, []);

  return (
    <Card className={scrollable ? "flex h-full flex-col" : undefined}>
      <CardHeader className="flex flex-col gap-4 border-b border-[color:var(--border)] pb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-muted">
              Approvals
            </p>
            <p className="mt-1 text-lg font-semibold text-strong">
              {sortedApprovals.pending.length} pending
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={onRefresh ?? loadApprovals}
          >
            Refresh
          </Button>
        </div>
        <p className="text-sm text-muted">
          Review lead-agent decisions that require human approval.
        </p>
      </CardHeader>
      <CardContent
        className={cn(
          "space-y-4 pt-5",
          scrollable && "flex-1 overflow-y-auto"
        )}
      >
        {errorState ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {errorState}
          </div>
        ) : null}
        {loadingState ? (
          <p className="text-sm text-muted">Loading approvals…</p>
        ) : sortedApprovals.pending.length === 0 &&
          sortedApprovals.resolved.length === 0 ? (
          <p className="text-sm text-muted">No approvals yet.</p>
        ) : (
          <div className="space-y-6">
            {sortedApprovals.pending.length > 0 ? (
              <div className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Pending
                </p>
                <div className="divide-y divide-[color:var(--border)] rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface)]">
                  {sortedApprovals.pending.map((approval) => {
                    const summary = approvalSummary(approval);
                    const summaryLine = summary.rows
                      .map((row) => `${row.label}: ${row.value}`)
                      .join(" • ");
                    const detailsPayload = JSON.stringify(
                      {
                        payload: approval.payload ?? null,
                        rubric_scores: approval.rubric_scores ?? null,
                      },
                      null,
                      2
                    );
                    const isExpanded = expandedIds.has(approval.id);
                    return (
                      <div key={approval.id} className="space-y-3 px-5 py-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="space-y-1">
                            <p className="text-sm font-semibold text-strong">
                              {humanizeAction(approval.action_type)}
                            </p>
                            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                              <span>
                                Requested {formatTimestamp(approval.created_at)}
                              </span>
                              {summaryLine ? (
                                <>
                                  <span className="text-slate-300">•</span>
                                  <span className="truncate">{summaryLine}</span>
                                </>
                              ) : null}
                            </div>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant={confidenceVariant(approval.confidence)}>
                              {approval.confidence}% confidence
                            </Badge>
                            <Badge variant={statusBadgeVariant(approval.status)}>
                              {approval.status}
                            </Badge>
                          </div>
                        </div>
                        {summary.reason ? (
                          <p className="text-sm text-muted">{summary.reason}</p>
                        ) : null}
                        {summary.rows.length > 0 ? (
                          <dl className="grid gap-2 text-xs text-muted sm:grid-cols-2">
                            {summary.rows.map((row) => (
                              <div key={`${approval.id}-${row.label}`}>
                                <dt className="font-semibold uppercase tracking-wide text-slate-500">
                                  {row.label}
                                </dt>
                                <dd className="mt-1 text-sm text-strong">
                                  {row.value}
                                </dd>
                              </div>
                            ))}
                          </dl>
                        ) : null}
                        <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
                          <button
                            type="button"
                            className="font-semibold text-slate-700 hover:text-slate-900"
                            onClick={() => toggleExpanded(approval.id)}
                          >
                            {isExpanded ? "Hide raw" : "View raw"}
                          </button>
                          <span>JSON payload + rubric</span>
                        </div>
                        {isExpanded ? (
                          <pre className="max-h-40 overflow-auto rounded-xl bg-slate-950 px-3 py-3 text-[11px] text-slate-100">
                            {detailsPayload}
                          </pre>
                        ) : null}
                        <div className="flex flex-wrap gap-2">
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => handleDecision(approval.id, "approved")}
                            disabled={updatingId === approval.id}
                          >
                            Approve
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleDecision(approval.id, "rejected")}
                            disabled={updatingId === approval.id}
                            className={cn(
                              "border-[color:var(--danger)] text-[color:var(--danger)] hover:text-[color:var(--danger)]"
                            )}
                          >
                            Reject
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
            {sortedApprovals.resolved.length > 0 ? (
              <div className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Resolved
                </p>
                <div className="divide-y divide-[color:var(--border)] rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface)]">
                  {sortedApprovals.resolved.map((approval) => {
                    const summary = approvalSummary(approval);
                    const summaryLine = summary.rows
                      .map((row) => `${row.label}: ${row.value}`)
                      .join(" • ");
                    const detailsPayload = JSON.stringify(
                      {
                        payload: approval.payload ?? null,
                        rubric_scores: approval.rubric_scores ?? null,
                      },
                      null,
                      2
                    );
                    const isExpanded = expandedIds.has(approval.id);
                    return (
                      <div key={approval.id} className="space-y-3 px-5 py-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="space-y-1">
                            <p className="text-sm font-semibold text-strong">
                              {humanizeAction(approval.action_type)}
                            </p>
                            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                              <span>
                                Requested {formatTimestamp(approval.created_at)}
                              </span>
                              {summaryLine ? (
                                <>
                                  <span className="text-slate-300">•</span>
                                  <span className="truncate">{summaryLine}</span>
                                </>
                              ) : null}
                            </div>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant={confidenceVariant(approval.confidence)}>
                              {approval.confidence}% confidence
                            </Badge>
                            <Badge variant={statusBadgeVariant(approval.status)}>
                              {approval.status}
                            </Badge>
                          </div>
                        </div>
                        {summary.reason ? (
                          <p className="text-sm text-muted">{summary.reason}</p>
                        ) : null}
                        {summary.rows.length > 0 ? (
                          <dl className="grid gap-2 text-xs text-muted sm:grid-cols-2">
                            {summary.rows.map((row) => (
                              <div key={`${approval.id}-${row.label}`}>
                                <dt className="font-semibold uppercase tracking-wide text-slate-500">
                                  {row.label}
                                </dt>
                                <dd className="mt-1 text-sm text-strong">
                                  {row.value}
                                </dd>
                              </div>
                            ))}
                          </dl>
                        ) : null}
                        <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
                          <button
                            type="button"
                            className="font-semibold text-slate-700 hover:text-slate-900"
                            onClick={() => toggleExpanded(approval.id)}
                          >
                            {isExpanded ? "Hide raw" : "View raw"}
                          </button>
                          <span>JSON payload + rubric</span>
                        </div>
                        {isExpanded ? (
                          <pre className="max-h-40 overflow-auto rounded-xl bg-slate-950 px-3 py-3 text-[11px] text-slate-100">
                            {detailsPayload}
                          </pre>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default BoardApprovalsPanel;
