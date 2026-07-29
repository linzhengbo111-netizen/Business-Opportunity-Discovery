/**
 * Review Page — candidate_events 人工审核面板
 * 深色数据终端风格，支持筛选、审核确认、一键 Promote
 */

import { useEffect, useMemo, useState } from "react";
import Header from "@/components/common/Header";
import PageMeta from "@/components/common/PageMeta";
import { supabase } from "@/db/supabase";

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
    default:
      return "bg-fpso-orange/15 text-fpso-orange";
  }
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
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterEventType, setFilterEventType] = useState("all");
  const [filterCountry, setFilterCountry] = useState("all");
  const [filterSource, setFilterSource] = useState("all");
  const [searchName, setSearchName] = useState("");

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

  /* ---- filter ---- */
  const filtered = useMemo(() => {
    let list = events;

    if (filterStatus !== "all") {
      list = list.filter((e) => e.review_status === filterStatus);
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
  }, [events, filterStatus, filterEventType, filterCountry, filterSource, searchName]);

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

    let inserted = 0;
    let updated = 0;
    let errors = 0;

    for (const ev of accepted) {
      try {
        const projectName = ev.project_name_raw || "Unknown Project";
        const country = ev.country || "Unknown";
        const summary = ev.summary || "";
        const sourceName = ev.source_name || "";
        const sourceUrl = ev.source_url || "";
        const pubDate = ev.publication_date ? ev.publication_date.slice(0, 10) : "";

        // Check if project already exists by name
        const { data: existing } = await supabase
          .from("projects")
          .select("id, name")
          .eq("name", projectName)
          .maybeSingle();

        if (existing) {
          // Update: merge summary if new info
          const { error: updateErr } = await supabase
            .from("projects")
            .update({
              summary: summary || undefined,
              source_name: sourceName || undefined,
              source_url: sourceUrl || undefined,
              source_date: pubDate || undefined,
            })
            .eq("id", existing.id);

          if (updateErr) {
            errors++;
          } else {
            updated++;
          }
        } else {
          // Insert new project
          const { error: insertErr } = await supabase
            .from("projects")
            .insert({
              name: projectName,
              country,
              flag: "",
              status: "Unknown",
              summary,
              source_name: sourceName,
              source_url: sourceUrl,
              source_date: pubDate,
              stainless_steel: "",
              application: "",
            });

          if (insertErr) {
            errors++;
          } else {
            inserted++;
          }
        }
      } catch {
        errors++;
      }
    }

    const parts = [];
    if (inserted > 0) parts.push(`${inserted} inserted`);
    if (updated > 0) parts.push(`${updated} updated`);
    if (errors > 0) parts.push(`${errors} errors`);
    setPromoteResult(`Promote complete: ${parts.join(", ")}.`);
    setPromoting(false);
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
              {filtered.length} of {events.length} events
            </p>
          </div>

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
        </section>

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
              className="h-8 min-w-[120px] rounded-md bg-fpso-bg/70 px-2.5 py-1 text-sm text-fpso-fg outline-none border border-fpso-border focus:ring-2 focus:ring-fpso-blue/50"
            >
              <option value="all">All</option>
              <option value="pending">Pending</option>
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
                        {ev.review_status || "pending"}
                      </span>
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
    </>
  );
}
