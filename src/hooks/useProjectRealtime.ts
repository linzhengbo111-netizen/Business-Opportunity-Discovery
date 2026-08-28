/**
 * Supabase Realtime subscription hook for the projects table.
 * Returns a monotonically increasing version (triggers re-fetch on change)
 * and the current connection status for the LIVE indicator.
 *
 * Multiple components (Header, pages, useAllProjects) subscribe simultaneously —
 * the channel is a module-level singleton: one WebSocket channel, N listeners.
 * Per-instance channels with the same name would throw
 * "cannot add postgres_changes callbacks after subscribe()".
 */

import { useEffect, useState } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { supabase } from "@/db/supabase";

export type ConnectionStatus = "connected" | "disconnected";

interface UseProjectRealtimeResult {
  version: number;
  status: ConnectionStatus;
}

interface Listener {
  bump: () => void;
  setStatus: (s: ConnectionStatus) => void;
}

let channel: RealtimeChannel | null = null;
const listeners = new Set<Listener>();
let sharedStatus: ConnectionStatus = "disconnected";

function notifyStatus(status: ConnectionStatus) {
  sharedStatus = status;
  for (const l of listeners) l.setStatus(status);
}

function ensureChannel() {
  if (channel) return;

  console.log("[Realtime] Opening shared channel 'projects-changes'...");

  channel = supabase
    .channel("projects-changes", {
      config: { broadcast: { self: false } },
    })
    .on(
      "postgres_changes",
      { event: "INSERT", schema: "public", table: "projects" },
      (payload) => {
        console.log("[Realtime] INSERT on projects:", payload.new);
        for (const l of listeners) l.bump();
      },
    )
    .on(
      "postgres_changes",
      { event: "UPDATE", schema: "public", table: "projects" },
      (payload) => {
        console.log("[Realtime] UPDATE on projects:", payload.new);
        for (const l of listeners) l.bump();
      },
    )
    .subscribe((subscribeStatus, err) => {
      if (err) {
        console.error("[Realtime] Subscribe error:", err);
        notifyStatus("disconnected");
        return;
      }
      switch (subscribeStatus) {
        case "SUBSCRIBED":
          console.log("[Realtime] ✅ Channel SUBSCRIBED — live connection active.");
          notifyStatus("connected");
          break;
        case "TIMED_OUT":
          console.warn("[Realtime] ⚠️  Channel TIMED_OUT — connection lost.");
          notifyStatus("disconnected");
          break;
        case "CLOSED":
          console.log("[Realtime] Channel CLOSED by server.");
          notifyStatus("disconnected");
          break;
        case "CHANNEL_ERROR":
          console.error("[Realtime] ❌ CHANNEL_ERROR — unexpected failure.");
          notifyStatus("disconnected");
          break;
        default:
          console.log("[Realtime] Subscribe status:", subscribeStatus);
      }
    });
}

export function useProjectRealtime(): UseProjectRealtimeResult {
  const [version, setVersion] = useState(0);
  const [status, setStatus] = useState<ConnectionStatus>(sharedStatus);

  useEffect(() => {
    const listener: Listener = {
      bump: () => setVersion((v) => v + 1),
      setStatus,
    };
    listeners.add(listener);
    // Late subscribers immediately see the current shared status.
    setStatus(sharedStatus);
    ensureChannel();
    return () => {
      listeners.delete(listener);
    };
  }, []);

  return { version, status };
}
