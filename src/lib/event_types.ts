/**
 * Event type classification shared by the timeline views
 * (ProjectTimelinePage and the Dashboard project modal).
 *
 * Timelines show ONLY key milestone events. Regulatory filings, permits,
 * EIA submissions and the like stay in the database but are not rendered —
 * they flood the timeline without adding procurement signal.
 */

/** Key milestone whitelist — the only event types rendered on timelines. */
export const MILESTONE_EVENT_TYPES: ReadonlySet<string> = new Set([
  "CONTRACT_AWARDED",
  "FPSO_CONTRACT_AWARDED",
  "FID_CONFIRMED",
  "FIRST_OIL",
  "PRODUCTION_START",
  "CONSTRUCTION_UPDATE",
  "DELIVERED",
]);

/** Contract awards, FID, first oil, production start, delivery, construction. */
export function isMilestoneEvent(eventType: string): boolean {
  return MILESTONE_EVENT_TYPES.has(eventType.toUpperCase());
}
