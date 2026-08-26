/**
 * FollowUpStatus Component (S7)
 * =============================
 *
 * Inline follow-up status selector with notes and corrections form.
 * Used in project detail panels and battle cards.
 *
 * Shows 5 status buttons. Current status is highlighted. Clicking a
 * status opens an inline form for optional notes and corrections.
 */

import { useState, useEffect, useCallback } from "react";
import { useFollowUp, FOLLOW_UP_STATUS_LABELS, FOLLOW_UP_STATUS_COLORS, type FollowUpStatus, type FollowUp, type FollowUpCorrections } from "@/hooks/useFollowUp";
import { useRequireLogin } from "@/hooks/useRequireLogin";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface FollowUpStatusProps {
  projectId: string;
  projectName?: string;
  /** If provided, show this follow-up state instead of fetching. */
  initialFollowUp?: FollowUp | null;
  /** Called after a successful save. */
  onSaved?: (followUp: FollowUp) => void;
  /** Show compact version (battle card footer). */
  compact?: boolean;
}

/* ------------------------------------------------------------------ */
/*  Status button group                                                */
/* ------------------------------------------------------------------ */

const ALL_STATUSES: FollowUpStatus[] = ["contacted", "valid", "inquiry", "invalid", "closed"];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function FollowUpStatus({
  projectId,
  projectName,
  initialFollowUp,
  onSaved,
  compact = false,
}: FollowUpStatusProps) {
  const { followUp, getFollowUp, loading, isAuthenticated } = useFollowUp();
  const requireLogin = useRequireLogin();

  const [current, setCurrent] = useState<FollowUp | null>(initialFollowUp ?? null);
  const [fetched, setFetched] = useState(!!initialFollowUp);

  // Editing state
  const [editing, setEditing] = useState(false);
  const [pendingStatus, setPendingStatus] = useState<FollowUpStatus | null>(null);
  const [notes, setNotes] = useState("");
  const [actualMaterial, setActualMaterial] = useState("");
  const [actualProcurementDate, setActualProcurementDate] = useState("");
  const [additionalNotes, setAdditionalNotes] = useState("");
  const [saving, setSaving] = useState(false);

  // Fetch existing follow-up on mount (unless initialFollowUp provided)
  useEffect(() => {
    if (initialFollowUp !== undefined) {
      setCurrent(initialFollowUp);
      setFetched(true);
      return;
    }
    if (!isAuthenticated || fetched) return;
    getFollowUp(projectId).then((fu) => {
      setCurrent(fu);
      setFetched(true);
    });
  }, [projectId, isAuthenticated, initialFollowUp, fetched, getFollowUp]);

  // Populate form when editing starts
  const startEdit = useCallback((status: FollowUpStatus) => {
    if (!requireLogin()) return;
    setPendingStatus(status);
    setNotes(current?.notes ?? "");
    setActualMaterial((current?.corrections as FollowUpCorrections | null)?.actualMaterial ?? "");
    setActualProcurementDate((current?.corrections as FollowUpCorrections | null)?.actualProcurementDate ?? "");
    setAdditionalNotes((current?.corrections as FollowUpCorrections | null)?.additionalNotes ?? "");
    setEditing(true);
  }, [current, requireLogin]);

  const cancelEdit = useCallback(() => {
    setEditing(false);
    setPendingStatus(null);
  }, []);

  const handleSave = useCallback(async () => {
    if (!pendingStatus) return;
    setSaving(true);

    const corrections: FollowUpCorrections = {};
    if (actualMaterial.trim()) corrections.actualMaterial = actualMaterial.trim();
    if (actualProcurementDate.trim()) corrections.actualProcurementDate = actualProcurementDate.trim();
    if (additionalNotes.trim()) corrections.additionalNotes = additionalNotes.trim();

    const result = await followUp(projectId, pendingStatus, notes.trim() || undefined, corrections);
    if (result) {
      setCurrent(result);
      onSaved?.(result);
    }
    setEditing(false);
    setPendingStatus(null);
    setSaving(false);
  }, [projectId, pendingStatus, notes, actualMaterial, actualProcurementDate, additionalNotes, followUp, onSaved]);

  // Helper: check if a status matches current
  const isActive = (s: FollowUpStatus) => current?.status === s;

  if (compact) {
    // Compact mode: just show the current status badge
    if (!current) return null;
    return (
      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium border ${FOLLOW_UP_STATUS_COLORS[current.status]}`}>
        {FOLLOW_UP_STATUS_LABELS[current.status]}
      </span>
    );
  }

  return (
    <div className="space-y-3">
      {/* Status label & current value */}
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-fpso-dim">
          Follow-up Status
        </h4>
        {current && (
          <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium border ${FOLLOW_UP_STATUS_COLORS[current.status]}`}>
            {FOLLOW_UP_STATUS_LABELS[current.status]}
          </span>
        )}
      </div>

      {!isAuthenticated && (
        <p className="text-[11px] text-fpso-dim">
          Log in with Feishu to save follow-up status.
        </p>
      )}

      {/* Status buttons */}
      <div className="flex flex-wrap gap-1.5">
        {ALL_STATUSES.map((s) => (
          <button
            key={s}
            type="button"
            disabled={loading || saving}
            onClick={() => {
              if (!requireLogin()) return;
              if (isActive(s) && !editing) {
                // Re-clicking active status opens edit
                startEdit(s);
              } else if (!isActive(s)) {
                // Clicking a different status: quick-set without notes
                followUp(projectId, s).then((result) => {
                  if (result) {
                    setCurrent(result);
                    onSaved?.(result);
                  }
                });
              }
            }}
            className={`inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-medium transition-all
              ${isActive(s)
                ? `${FOLLOW_UP_STATUS_COLORS[s]} ring-1 ring-offset-1 ring-offset-fpso-bg`
                : "border-fpso-border text-fpso-muted hover:border-fpso-blue/40 hover:text-fpso-fg hover:shadow-glow"
              }
              disabled:opacity-50 disabled:cursor-not-allowed
            `}
          >
            {FOLLOW_UP_STATUS_LABELS[s]}
          </button>
        ))}
        {/* Edit button for current status */}
        {current && !editing && (
          <button
            type="button"
            onClick={() => startEdit(current.status)}
            className="inline-flex items-center rounded-md border border-dashed border-fpso-border px-2 py-1 text-xs text-fpso-dim hover:border-fpso-blue/30 hover:text-fpso-blue transition-colors"
          >
            + Notes
          </button>
        )}
      </div>

      {/* Inline edit form */}
      {editing && pendingStatus && (
        <div className="space-y-3 rounded-lg border border-fpso-border bg-fpso-bg/60 p-4 shadow-card animate-fade-in">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-fpso-fg">
              {isActive(pendingStatus) ? "Edit" : "Set"} status:
            </span>
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium border ${FOLLOW_UP_STATUS_COLORS[pendingStatus]}`}>
              {FOLLOW_UP_STATUS_LABELS[pendingStatus]}
            </span>
          </div>

          {/* Notes */}
          <div className="space-y-1.5">
            <Label className="text-xs text-fpso-dim">备注 (Notes)</Label>
            <Textarea
              placeholder="销售备注... (可选)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="resize-none bg-white border-fpso-border text-fpso-fg text-xs placeholder:text-fpso-muted/50"
            />
          </div>

          {/* Corrections form */}
          <div className="space-y-3 border-t border-fpso-border pt-3">
            <p className="text-[11px] text-fpso-dim">
              Corrections — 修正系统推断 (all optional)
            </p>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-fpso-dim">实际材质</Label>
                <Input
                  placeholder="如: Duplex 2205"
                  value={actualMaterial}
                  onChange={(e) => setActualMaterial(e.target.value)}
                  className="h-8 bg-white border-fpso-border text-fpso-fg text-xs placeholder:text-fpso-muted/50"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-fpso-dim">实际采购时间</Label>
                <Input
                  type="date"
                  value={actualProcurementDate}
                  onChange={(e) => setActualProcurementDate(e.target.value)}
                  className="h-8 bg-white border-fpso-border text-fpso-fg text-xs"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs text-fpso-dim">补充说明</Label>
              <Input
                placeholder="补充说明... (可选)"
                value={additionalNotes}
                onChange={(e) => setAdditionalNotes(e.target.value)}
                className="h-8 bg-white border-fpso-border text-fpso-fg text-xs placeholder:text-fpso-muted/50"
              />
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 pt-1">
            <Button
              size="sm"
              onClick={handleSave}
              disabled={saving}
              className="h-7 bg-fpso-blue hover:bg-fpso-blue/80 text-primary-foreground text-xs"
            >
              {saving ? "Saving..." : "Save"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={cancelEdit}
              disabled={saving}
              className="h-7 border-fpso-border text-fpso-muted hover:text-fpso-fg text-xs"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Show notes if present (when not editing) */}
      {current?.notes && !editing && (
        <p className="text-xs text-fpso-dim italic border-l-2 border-fpso-blue/20 pl-2">
          {current.notes}
        </p>
      )}

      {/* Show corrections summary if present (when not editing) */}
      {current?.corrections && !editing && (() => {
        const c = current.corrections as FollowUpCorrections;
        if (!c.actualMaterial && !c.actualProcurementDate && !c.additionalNotes) return null;
        return (
          <div className="text-[11px] text-fpso-dim space-y-0.5 border-l-2 border-fpso-orange/20 pl-2">
            {c.actualMaterial && (
              <p>Actual material: <span className="text-fpso-orange">{c.actualMaterial}</span></p>
            )}
            {c.actualProcurementDate && (
              <p>Actual procurement: <span className="text-fpso-orange">{c.actualProcurementDate}</span></p>
            )}
            {c.additionalNotes && (
              <p className="text-fpso-muted/70">{c.additionalNotes}</p>
            )}
          </div>
        );
      })()}
    </div>
  );
}
