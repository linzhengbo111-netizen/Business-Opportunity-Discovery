/**
 * Event type classification shared by the timeline views
 * (ProjectTimelinePage and the Dashboard project modal).
 *
 * Timelines show ALL accepted event types — regulatory filings, permits,
 * EIA submissions included — sorted by publication date ascending.
 * The single exception: DELIVERED events always go last, regardless of
 * date; multiple DELIVERED events sort by date among themselves.
 */

/**
 * Timeline ordering — ascending by publication date.
 * No-date events ("日期未披露") sort absolutely last, after every dated
 * event; DELIVERED stays last among dated events. Ties keep input order.
 */
export function sortTimelineEvents<T extends { eventType: string; publicationDate: string }>(
  events: T[],
): T[] {
  return [...events].sort((a, b) => {
    const aEmpty = !a.publicationDate;
    const bEmpty = !b.publicationDate;
    if (aEmpty !== bEmpty) return aEmpty ? 1 : -1;
    const aDelivered = a.eventType.toUpperCase() === "DELIVERED";
    const bDelivered = b.eventType.toUpperCase() === "DELIVERED";
    if (aDelivered !== bDelivered) return aDelivered ? 1 : -1;
    return (a.publicationDate || "").localeCompare(b.publicationDate || "");
  });
}
