/**
 * Review Page — candidate_events 人工审核面板
 * 深色数据终端风格，支持筛选、审核确认、一键 Promote
 */

import { useEffect, useMemo, useState } from "react";
import Header from "@/components/common/Header";
import PageMeta from "@/components/common/PageMeta";
import { supabase } from "@/db/supabase";
import { normalizeProjectName, getDisplayName } from "@/data/project_aliases";

/* ------------------------------------------------------------------ */
/*  types                                                              */
/* ------------------------------------------------------------------ */

interface CandidateEvent {
  id: string;
  project_name_raw: string;
  event_type: string;
  country: string;
  summary: string;
  evidence_quote: string;
  source_name: string;
  source_url: string;
  publication_date: string;
  review_status: string;
  canonical_project_id: string | null;
  fetched_at: string;
}

/* ------------------------------------------------------------------ */
/*  helpers                                                             */
/* ------------------------------------------------------------------ */

function truncate(text: string, max: number) {
  if (!text) return "";
  return text.length > max ? text.slice(0, max) + "…" : text;
}

function statusBadge(status: string) {
  switch (status) {
    case "accepted":
      return "bg-fpso-green/15 text-fpso-green";
    case "rejected":
      return "bg-red-500/15 text-red-400";
    case "auto_accepted":
      return "bg-fpso-blue/15 text-fpso-blue";
    case "auto_rejected":
      return "bg-amber-500/15 text-amber-400";
    default:
      return "bg-fpso-orange/15 text-fpso-orange";
  }
}

function statusLabel(status: string) {
  switch (status) {
    case "auto_accepted":
      return "AI Suggested ✓";
    case "auto_rejected":
      return "AI Suggested ✗";
    case "accepted":
      return "accepted";
    case "rejected":
      return "rejected";
    default:
      return status || "pending";
  }
}

/** Extract AI classification reason from evidence_quote trail marker. */
function extractAiReason(evidenceQuote: string): string | null {
  if (!evidenceQuote) return null;
  const match = evidenceQuote.match(/\[Auto-(?:accepted|rejected):\s*(.+?)\]/);
  return match ? match[1] : null;
}

function formatDate(d: string | null) {
  if (!d) return "—";
  return d.slice(0, 10);
}

/* ------------------------------------------------------------------ */
/*  main page                                                          */
/* ------------------------------------------------------------------ */

export default function ReviewPage() {
  /* ---- state ---- */
  const [events, setEvents] = useState<CandidateEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadProgress, setLoadProgress] = useState("");
  const [promoting, setPromoting] = useState(false);
  const [promoteResult, setPromoteResult] = useState<string | null>(null);

  // filters
  const [filterStatus, setFilterStatus] = useState("all-except-ai");
  const [filterEventType, setFilterEventType] = useState("all");
  const [filterCountry, setFilterCountry] = useState("all");
  const [filterSource, setFilterSource] = useState("all");
  const [searchName, setSearchName] = useState("");
  const [showAiSuggestions, setShowAiSuggestions] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  /* ---- fetch (paginated: loops until all rows loaded) ---- */
  async function fetchEvents() {
    setLoading(true);
    setLoadProgress("Counting rows...");
    const start = performance.now();
    console.log("[Review] Fetching candidate_events (paginated)...");

    const PAGE_SIZE = 1000;
    const all: CandidateEvent[] = [];

    // First, get total count
    const { count, error: countErr } = await supabase
      .from("candidate_events")
      .select("*", { count: "exact", head: true });

    const total = count ?? 0;

    if (countErr) {
      console.error("[Review] Count FAILED:", countErr.message, countErr);
      setEvents([]);
      setLoading(false);
      setLoadProgress("");
      return;
    }

    console.log(`[Review] Total rows: ${total}`);

    // Loop until all rows fetched
    let rangeStart = 0;
    while (rangeStart < total) {
      const rangeEnd = Math.min(rangeStart + PAGE_SIZE - 1, total - 1);
      setLoadProgress(`Loading events: ${all.length}/${total}...`);

      const { data, error, status } = await supabase
        .from("candidate_events")
        .select("*")
        .order("fetched_at", { ascending: false })
        .range(rangeStart, rangeEnd);

      if (error) {
        console.error(`[Review] Page fetch FAILED (HTTP ${status}):`, error.message, error);
        setEvents([]);
        setLoading(false);
        setLoadProgress("");
        return;
      }

      if (data && data.length > 0) {
        all.push(...(data as CandidateEvent[]));
      }

      rangeStart += PAGE_SIZE;
    }

    const elapsed = (performance.now() - start).toFixed(0);
    console.log(`[Review] Fetch OK (${elapsed}ms): ${all.length} rows total`);
    setEvents(all);
    setLoading(false);
    setLoadProgress("");
  }

  useEffect(() => {
    fetchEvents();
  }, []);

  /* ---- derive filters ---- */
  const eventTypes = useMemo(() => {
    const set = new Set<string>();
    for (const e of events) if (e.event_type) set.add(e.event_type);
    return Array.from(set).sort();
  }, [events]);

  const countries = useMemo(() => {
    const set = new Set<string>();
    for (const e of events) if (e.country) set.add(e.country.trim());
    return Array.from(set).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  }, [events]);

  const sources = useMemo(() => {
    const set = new Set<string>();
    for (const e of events) if (e.source_name) set.add(e.source_name);
    return Array.from(set).sort();
  }, [events]);

  /* ---- stats ---- */
  const stats = useMemo(() => {
    let autoAccepted = 0, autoRejected = 0, pending = 0, accepted = 0, rejected = 0;
    for (const e of events) {
      switch (e.review_status) {
        case "auto_accepted": autoAccepted++; break;
        case "auto_rejected": autoRejected++; break;
        case "pending": pending++; break;
        case "accepted": accepted++; break;
        case "rejected": rejected++; break;
      }
    }
    return { autoAccepted, autoRejected, pending, accepted, rejected };
  }, [events]);

  /* ---- filter ---- */
  const filtered = useMemo(() => {
    let list = events;

    // Status filter: "all-except-ai" = default, hides auto_accepted + auto_rejected
    if (filterStatus === "all-except-ai") {
      list = list.filter((e) =>
        e.review_status !== "auto_accepted" && e.review_status !== "auto_rejected"
      );
    } else if (filterStatus !== "all") {
      list = list.filter((e) => e.review_status === filterStatus);
    }

    // AI suggestions toggle: when on, shows auto_* records regardless of status filter
    if (showAiSuggestions && filterStatus === "all-except-ai") {
      list = events; // override: show everything
      // Re-apply non-status filters below
    }

    if (filterEventType !== "all") {
      list = list.filter((e) => e.event_type === filterEventType);
    }
    if (filterCountry !== "all") {
      list = list.filter((e) => e.country?.trim() === filterCountry);
    }
    if (filterSource !== "all") {
      list = list.filter((e) => e.source_name === filterSource);
    }
    if (searchName.trim()) {
      const q = searchName.trim().toLowerCase();
      list = list.filter((e) => (e.project_name_raw ?? "").toLowerCase().includes(q));
    }

    return list;
  }, [events, filterStatus, filterEventType, filterCountry, filterSource, searchName, showAiSuggestions]);

  /* ---- actions ---- */
  async function updateStatus(id: string, status: "accepted" | "rejected") {
    const { error } = await supabase
      .from("candidate_events")
      .update({ review_status: status })
      .eq("id", id);

    if (error) {
      console.error("Update error:", error.message);
      return;
    }

    // refresh local state
    setEvents((prev) =>
      prev.map((e) => (e.id === id ? { ...e, review_status: status } : e)),
    );
  }

  async function handlePromote() {
    setPromoting(true);
    setPromoteResult(null);

    const accepted = events.filter((e) => e.review_status === "accepted");
    if (accepted.length === 0) {
      setPromoteResult("No accepted events to promote.");
      setPromoting(false);
      return;
    }

    // ---- Step 1: normalize and group by canonical project ID ----
    // Map key: canonical ID string, or "__raw__<project_name_raw>" fallback
    const groups = new Map<string, CandidateEvent[]>();

    for (const ev of accepted) {
      const canonicalId = normalizeProjectName(ev.project_name_raw);
      const key = canonicalId ?? `__raw__${ev.project_name_raw || "Unknown Project"}`;

      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key)!.push(ev);
    }

    // ---- Step 2: write canonical_project_id back to candidate_events ----
    for (const ev of accepted) {
      const canonicalId = normalizeProjectName(ev.project_name_raw);
      if (canonicalId && ev.canonical_project_id !== canonicalId) {
        supabase
          .from("candidate_events")
          .update({ canonical_project_id: canonicalId })
          .eq("id", ev.id)
          .then(({ error }) => {
            if (error) console.warn("[Promote] backfill canonical_project_id failed:", ev.id, error.message);
          });
      }
    }

    // ---- Step 3: merge each group and upsert into projects ----
    let inserted = 0;
    let updated = 0;
    let errors = 0;

    for (const [key, group] of groups) {
      try {
        const canonicalId = key.startsWith("__raw__") ? null : key;
        const projectName = canonicalId
          ? getDisplayName(canonicalId)
          : (group[0].project_name_raw || "Unknown Project");

        // --- Merge logic (mirrors Python promote_accepted_candidates) ---

        // Summary: longest first, then append distinct summaries not already contained
        const summaries = group
          .map((e) => (e.summary || "").trim())
          .filter((s) => s.length > 0);
        let mergedSummary = summaries.length > 0
          ? summaries.reduce((a, b) => (b.length > a.length ? b : a))
          : "";
        const seenSummaries = new Set<string>([mergedSummary]);
        for (const s of summaries) {
          if (!seenSummaries.has(s) && s.length > 20 && !mergedSummary.includes(s)) {
            mergedSummary += " | " + s;
            seenSummaries.add(s);
          }
        }

        // Evidence quote: collect dedup, join with separator
        const quotes = new Set<string>();
        for (const ev of group) {
          if (ev.evidence_quote && ev.evidence_quote.trim()) {
            quotes.add(ev.evidence_quote.trim());
          }
        }
        const mergedEvidenceQuote = Array.from(quotes).join(" | ");

        // Append unique evidence quotes to summary so evidence is preserved
        for (const q of quotes) {
          if (!mergedSummary.includes(q)) {
            mergedSummary += " | " + q;
          }
        }

        // Source name: dedup join
        const sourceNames = new Set<string>();
        for (const ev of group) {
          if (ev.source_name && ev.source_name.trim()) {
            sourceNames.add(ev.source_name.trim());
          }
        }
        const mergedSourceName = Array.from(sourceNames).join(", ");

        // Source URL: from the event with latest publication_date
        const dated = group
          .filter((e) => e.publication_date)
          .sort((a, b) => b.publication_date.localeCompare(a.publication_date));
        const best = dated.length > 0 ? dated[0] : group[0];
        const mergedSourceUrl = best.source_url || "";

        // Publication date: latest across group
        const pubDate = best.publication_date
          ? best.publication_date.slice(0, 10)
          : "";

        // Country: most common value in group
        const countryCounts = new Map<string, number>();
        for (const ev of group) {
          if (ev.country && ev.country.trim()) {
            const c = ev.country.trim();
            countryCounts.set(c, (countryCounts.get(c) || 0) + 1);
          }
        }
        let mergedCountry = "Unknown";
        let maxCount = 0;
        for (const [c, n] of countryCounts) {
          if (n > maxCount) {
            mergedCountry = c;
            maxCount = n;
          }
        }

        // Status: prioritize Delivered > Under Construction > Planned > Unknown
        const statusPriority: Record<string, number> = {
          "Delivered": 0,
          "Under Construction": 1,
          "Planned": 2,
          "Unknown": 3,
        };
        const statuses = group.map((e) => (e as any).status || "Unknown");
        const mergedStatus = statuses.sort(
          (a, b) => (statusPriority[a] ?? 99) - (statusPriority[b] ?? 99)
        )[0];

        // --- Upsert: check if project already exists by name ---
        const { data: existing } = await supabase
          .from("projects")
          .select("id, name")
          .eq("name", projectName)
          .maybeSingle();

        if (existing) {
          const { error: updateErr } = await supabase
            .from("projects")
            .update({
              summary: mergedSummary || undefined,
              source_name: mergedSourceName || undefined,
              source_url: mergedSourceUrl || undefined,
              source_date: pubDate || undefined,
              country: mergedCountry,
              status: mergedStatus,
            })
            .eq("id", existing.id);

          if (updateErr) {
            console.error("[Promote] update error:", updateErr.message);
            errors++;
          } else {
            updated++;
          }
        } else {
          const { error: insertErr } = await supabase
            .from("projects")
            .insert({
              name: projectName,
              country: mergedCountry,
              flag: "",
              status: mergedStatus,
              summary: mergedSummary,
              source_name: mergedSourceName,
              source_url: mergedSourceUrl,
              source_date: pubDate,
              stainless_steel: "",
              application: "",
            });

          if (insertErr) {
            console.error("[Promote] insert error:", insertErr.message);
            errors++;
          } else {
            inserted++;
          }
        }
      } catch (err) {
        console.error("[Promote] unexpected error:", err);
        errors++;
      }
    }

    // ---- Step 4: report ----
    console.log(
      `Promote: ${accepted.length} accepted events merged into ${groups.size} unique projects`,
    );

    const parts = [];
    if (inserted > 0) parts.push(`${inserted} inserted`);
    if (updated > 0) parts.push(`${updated} updated`);
    if (errors > 0) parts.push(`${errors} errors`);
    setPromoteResult(`Promote complete: ${parts.join(", ")}.`);
    setPromoting(false);
  }

  /** Batch-apply all AI suggestions: auto_accepted → accepted, auto_rejected → rejected. */
  async function handleAcceptAllAi() {
    setShowConfirmDialog(false);

    const autoAccepted = events.filter((e) => e.review_status === "auto_accepted");
    const autoRejected = events.filter((e) => e.review_status === "auto_rejected");

    if (autoAccepted.length === 0 && autoRejected.length === 0) {
      return;
    }

    let done = 0;
    let errs = 0;

    // Accept all auto_accepted
    for (const ev of autoAccepted) {
      const { error } = await supabase
        .from("candidate_events")
        .update({ review_status: "accepted" })
        .eq("id", ev.id);
      if (error) { errs++; console.error("Accept AI error:", error.message); }
      else { done++; }
    }

    // Reject all auto_rejected
    for (const ev of autoRejected) {
      const { error } = await supabase
        .from("candidate_events")
        .update({ review_status: "rejected" })
        .eq("id", ev.id);
      if (error) { errs++; console.error("Reject AI error:", error.message); }
      else { done++; }
    }

    // Refresh local state
    setEvents((prev) =>
      prev.map((e) => {
        if (e.review_status === "auto_accepted") return { ...e, review_status: "accepted" };
        if (e.review_status === "auto_rejected") return { ...e, review_status: "rejected" };
        return e;
      }),
    );

    console.log(`Accept All AI: ${done} applied, ${errs} errors`);
  }

  /* ---- render ---- */
  return (
    <>
      <PageMeta title="Review — Candidate Events" description="人工审核 candidate_events 数据" />
      <Header />

      <main className="mx-auto w-full max-w-7xl px-6 py-8">
        {/* page title + promote */}
        <section className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-fpso-fg md:text-3xl">
              Candidate Events Review
            </h1>
            <p className="mt-1 text-sm text-fpso-muted">
              {filtered.length} of {events.length} events shown
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handlePromote}
              disabled={promoting}
              className="inline-flex items-center gap-2 rounded-lg bg-fpso-blue px-5 py-2.5 text-sm font-semibold text-black transition-all hover:bg-fpso-blue/80 hover:shadow-[0_0_20px_rgba(0,212,255,0.4)] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {promoting ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-black/30 border-t-black" />
                  Promoting…
                </>
              ) : (
                "Promote to Projects"
              )}
            </button>
          </div>
        </section>

        {/* AI stats bar */}
        {(stats.autoAccepted > 0 || stats.autoRejected > 0) && (
          <section className="mb-6 rounded-lg border border-fpso-blue/20 bg-fpso-card px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex flex-wrap items-center gap-5 text-sm">
                <span className="text-fpso-muted font-medium">AI Pre-Screening:</span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-fpso-blue" />
                  <span className="text-fpso-fg font-semibold">{stats.autoAccepted}</span>
                  <span className="text-fpso-muted">Auto-Accepted</span>
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-amber-400" />
                  <span className="text-fpso-fg font-semibold">{stats.autoRejected}</span>
                  <span className="text-fpso-muted">Auto-Rejected</span>
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-fpso-orange" />
                  <span className="text-fpso-fg font-semibold">{stats.pending}</span>
                  <span className="text-fpso-muted">Pending</span>
                </span>
              </div>

              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-xs text-fpso-muted cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={showAiSuggestions}
                    onChange={(e) => setShowAiSuggestions(e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-fpso-border bg-fpso-bg accent-fpso-blue"
                  />
                  Show AI suggestions
                </label>

                {(stats.autoAccepted > 0 || stats.autoRejected > 0) && (
                  <button
                    onClick={() => setShowConfirmDialog(true)}
                    className="inline-flex items-center gap-1.5 rounded-md bg-fpso-blue/80 px-3.5 py-2 text-xs font-semibold text-black transition-all hover:bg-fpso-blue hover:shadow-[0_0_16px_rgba(0,212,255,0.4)]"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    Accept All AI Suggestions
                  </button>
                )}
              </div>
            </div>
          </section>
        )}

        {/* promote result toast */}
        {promoteResult && (
          <section className="mb-6 rounded-lg border border-fpso-border bg-fpso-card px-5 py-3 text-sm text-fpso-fg">
            {promoteResult}
          </section>
        )}

        {/* filters */}
        <section className="mb-6 flex flex-wrap items-center gap-4 rounded-lg border border-fpso-border bg-fpso-card px-5 py-3">
          {/* review_status */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Status</label>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="h-8 min-w-[140px] rounded-md bg-fpso-bg/70 px-2.5 py-1 text-sm text-fpso-fg outline-none border border-fpso-border focus:ring-2 focus:ring-fpso-blue/50"
            >
              <option value="all-except-ai">All (excl. AI)</option>
              <option value="all">All</option>
              <option value="pending">Pending</option>
              <option value="auto_accepted">Auto-Accepted</option>
              <option value="auto_rejected">Auto-Rejected</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>

          {/* event_type */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Event Type</label>
            <select
              value={filterEventType}
              onChange={(e) => setFilterEventType(e.target.value)}
              className="h-8 min-w-[140px] rounded-md bg-fpso-bg/70 px-2.5 py-1 text-sm text-fpso-fg outline-none border border-fpso-border focus:ring-2 focus:ring-fpso-blue/50"
            >
              <option value="all">All Types</option>
              {eventTypes.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>

          {/* country */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Country</label>
            <select
              value={filterCountry}
              onChange={(e) => setFilterCountry(e.target.value)}
              className="h-8 min-w-[140px] rounded-md bg-fpso-bg/70 px-2.5 py-1 text-sm text-fpso-fg outline-none border border-fpso-border focus:ring-2 focus:ring-fpso-blue/50"
            >
              <option value="all">All Countries</option>
              {countries.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          {/* source_name */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Source</label>
            <select
              value={filterSource}
              onChange={(e) => setFilterSource(e.target.value)}
              className="h-8 min-w-[140px] rounded-md bg-fpso-bg/70 px-2.5 py-1 text-sm text-fpso-fg outline-none border border-fpso-border focus:ring-2 focus:ring-fpso-blue/50"
            >
              <option value="all">All Sources</option>
              {sources.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {/* project_name_raw search */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Search</label>
            <input
              type="text"
              value={searchName}
              onChange={(e) => setSearchName(e.target.value)}
              placeholder="Project name…"
              className="h-8 w-48 rounded-md bg-fpso-bg/70 px-2.5 py-1 text-sm text-fpso-fg outline-none border border-fpso-border focus:ring-2 focus:ring-fpso-blue/50 placeholder:text-fpso-dim"
            />
          </div>
        </section>

        {/* card list */}
        <section className="space-y-4">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-fpso-blue/30 border-t-fpso-blue" />
              {loadProgress && (
                <p className="text-sm text-fpso-muted font-mono">{loadProgress}</p>
              )}
            </div>
          ) : events.length === 0 ? (
            <div className="rounded-lg border border-fpso-border bg-fpso-card px-6 py-16 text-center">
              <p className="text-fpso-muted text-sm">No data in candidate_events table.</p>
              <p className="text-fpso-dim text-xs mt-1">
                Open browser console for request details. DashboardPage also reads this table — check its log for comparison.
              </p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="rounded-lg border border-fpso-border bg-fpso-card px-6 py-16 text-center text-fpso-muted">
              No events match the current filters ({events.length} total in table).
            </div>
          ) : (
            filtered.map((ev) => (
              <div
                key={ev.id}
                className="rounded-lg border border-fpso-border bg-fpso-card p-5 transition-all hover:border-fpso-blue/30"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  {/* info */}
                  <div className="flex-1 min-w-0 space-y-2">
                    {/* header row */}
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-base font-semibold text-fpso-fg">
                        {ev.project_name_raw || "Unnamed"}
                      </h3>
                      <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${statusBadge(ev.review_status)}`}>
                        {statusLabel(ev.review_status)}
                      </span>
                      {/* AI reasoning badge */}
                      {(ev.review_status === "auto_accepted" || ev.review_status === "auto_rejected") &&
                        extractAiReason(ev.evidence_quote) && (
                          <span className="inline-block rounded-full bg-fpso-blue/10 px-2.5 py-0.5 text-xs text-fpso-blue/80"
                            title={extractAiReason(ev.evidence_quote) ?? undefined}>
                            {extractAiReason(ev.evidence_quote)}
                          </span>
                      )}
                      {ev.event_type && (
                        <span className="inline-block rounded-full bg-fpso-blue/10 px-2.5 py-0.5 text-xs font-medium text-fpso-blue">
                          {ev.event_type}
                        </span>
                      )}
                    </div>

                    {/* country + date */}
                    <div className="flex flex-wrap items-center gap-3 text-xs text-fpso-muted">
                      {ev.country && <span>Country: {ev.country}</span>}
                      {ev.publication_date && <span>Published: {formatDate(ev.publication_date)}</span>}
                      {ev.source_name && (
                        <span>
                          Source:{" "}
                          {ev.source_url ? (
                            <a
                              href={ev.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-fpso-blue underline-offset-2 hover:underline"
                            >
                              {ev.source_name}
                            </a>
                          ) : (
                            ev.source_name
                          )}
                        </span>
                      )}
                    </div>

                    {/* summary */}
                    {ev.summary && (
                      <p className="text-sm text-fpso-fg leading-relaxed">
                        {truncate(ev.summary, 100)}
                      </p>
                    )}

                    {/* evidence quote */}
                    {ev.evidence_quote && (
                      <blockquote className="border-l-2 border-fpso-blue/30 pl-3 text-xs text-fpso-muted italic">
                        {truncate(ev.evidence_quote, 200)}
                      </blockquote>
                    )}
                  </div>

                  {/* actions */}
                  <div className="flex items-center gap-2 lg:flex-shrink-0">
                    {ev.review_status !== "accepted" && (
                      <button
                        onClick={() => updateStatus(ev.id, "accepted")}
                        className="inline-flex items-center gap-1 rounded-md bg-fpso-green/15 px-3 py-1.5 text-xs font-semibold text-fpso-green transition-all hover:bg-fpso-green/25 hover:shadow-[0_0_12px_rgba(16,185,129,0.3)]"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                        Accept
                      </button>
                    )}
                    {ev.review_status !== "rejected" && (
                      <button
                        onClick={() => updateStatus(ev.id, "rejected")}
                        className="inline-flex items-center gap-1 rounded-md bg-red-500/15 px-3 py-1.5 text-xs font-semibold text-red-400 transition-all hover:bg-red-500/25 hover:shadow-[0_0_12px_rgba(239,68,68,0.3)]"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                        Reject
                      </button>
                    )}
                    {ev.review_status === "accepted" && (
                      <span className="rounded-md bg-fpso-green/10 px-3 py-1.5 text-xs font-medium text-fpso-green">
                        ✓ Accepted
                      </span>
                    )}
                    {ev.review_status === "rejected" && (
                      <span className="rounded-md bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-400">
                        ✗ Rejected
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </section>
      </main>

      {/* Confirmation dialog for "Accept All AI Suggestions" */}
      {showConfirmDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="mx-4 w-full max-w-md rounded-xl border border-fpso-border bg-fpso-card p-6 shadow-2xl">
            <h2 className="text-lg font-semibold text-fpso-fg">
              Accept All AI Suggestions
            </h2>
            <p className="mt-3 text-sm text-fpso-fg leading-relaxed">
              This will <strong className="text-fpso-green">accept {stats.autoAccepted} events</strong>{" "}
              (auto_accepted → accepted) and{" "}
              <strong className="text-red-400">reject {stats.autoRejected} events</strong>{" "}
              (auto_rejected → rejected).
            </p>
            <p className="mt-2 text-xs text-fpso-muted">
              You can manually override any individual decision afterwards. This action
              cannot be bulk-undone, but individual events can be corrected one by one.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setShowConfirmDialog(false)}
                className="rounded-lg border border-fpso-border px-4 py-2 text-sm font-medium text-fpso-muted transition-all hover:bg-fpso-bg/50 hover:text-fpso-fg"
              >
                Cancel
              </button>
              <button
                onClick={handleAcceptAllAi}
                className="rounded-lg bg-fpso-blue/80 px-5 py-2 text-sm font-semibold text-black transition-all hover:bg-fpso-blue hover:shadow-[0_0_16px_rgba(0,212,255,0.4)]"
              >
                Confirm — Accept {stats.autoAccepted} / Reject {stats.autoRejected}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
