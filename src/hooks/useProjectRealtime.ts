/**
 * Supabase Realtime subscription hook for the projects table.
 * Returns a monotonically increasing version (triggers re-fetch on change)
 * and the current connection status for the LIVE indicator.
 */

import { useEffect, useRef, useState } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { supabase } from "@/db/supabase";

export type ConnectionStatus = "connected" | "disconnected";

interface UseProjectRealtimeResult {
  version: number;
  status: ConnectionStatus;
}

export function useProjectRealtime(): UseProjectRealtimeResult {
  const [version, setVersion] = useState(0);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const channelRef = useRef<RealtimeChannel | null>(null);

  useEffect(() => {
    console.log("[Realtime] Opening channel 'projects-changes'...");

    const channel = supabase
      .channel("projects-changes", {
        config: { broadcast: { self: false } },
      })
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "projects" },
        (payload) => {
          console.log("[Realtime] INSERT on projects:", payload.new);
          setVersion((v) => v + 1);
        },
      )
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "projects" },
        (payload) => {
          console.log("[Realtime] UPDATE on projects:", payload.new);
          setVersion((v) => v + 1);
        },
      )
      .subscribe((subscribeStatus, err) => {
        if (err) {
          console.error("[Realtime] Subscribe error:", err);
          setStatus("disconnected");
          return;
        }
        switch (subscribeStatus) {
          case "SUBSCRIBED":
            console.log("[Realtime] ✅ Channel SUBSCRIBED — live connection active.");
            setStatus("connected");
            break;
          case "TIMED_OUT":
            console.warn("[Realtime] ⚠️  Channel TIMED_OUT — connection lost.");
            setStatus("disconnected");
            break;
          case "CLOSED":
            console.log("[Realtime] Channel CLOSED by server.");
            setStatus("disconnected");
            break;
          case "CHANNEL_ERROR":
            console.error("[Realtime] ❌ CHANNEL_ERROR — unexpected failure.");
            setStatus("disconnected");
            break;
          default:
            console.log("[Realtime] Subscribe status:", subscribeStatus);
        }
      });

    channelRef.current = channel;

    return () => {
      console.log("[Realtime] Cleaning up channel 'projects-changes' — unsubscribing.");
      supabase.removeChannel(channel);
    };
  }, []);

  return { version, status };
}
