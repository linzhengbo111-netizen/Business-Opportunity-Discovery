/**
 * Event type classification helpers shared by the timeline views
 * (ProjectTimelinePage and the Dashboard project modal).
 *
 * Milestone events get visually promoted (big dot + glow); regulatory
 * filings stay small and muted — they are the bulk of most timelines,
 * not the highlights.
 */

/** Contract awards, FID, first oil, production start, delivery, construction. */
export function isMilestoneEvent(eventType: string): boolean {
  const et = eventType.toUpperCase();
  return /CONTRACT_AWARDED|FID|FIRST_OIL|PRODUCTION_START|DELIVERED|CONSTRUCTION_UPDATE/.test(et);
}

/** Regulatory filings, permits, licenses, consent, EIA and plan submissions. */
export function isRegulatoryEvent(eventType: string): boolean {
  const et = eventType.toUpperCase();
  return (
    /REGULATORY|CONSENT|PERMIT|LICENSE|EIA_SUBMITTED|PUBLIC_NOTICE/.test(et) ||
    /DEVELOPMENT_PLAN|FIELD_DEVELOPMENT_PLAN/.test(et)
  );
}
