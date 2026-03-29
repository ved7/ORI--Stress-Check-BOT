import "./SessionHistory.css";


function formatSessionTime(timestamp) {
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
  }).format(new Date(timestamp));
}


function sessionTitle(session) {
  if (session.report?.profile?.support_need) {
    return session.report.profile.support_need;
  }
  return "Ori stress check-in";
}


export default function SessionHistory({
  activeSessionId,
  history,
  isLoading,
  isSessionLoading,
  onClearHistory,
  onDeleteSession,
  onSelectSession,
}) {
  const completedHistory = history.filter((session) => session.status === "complete");

  return (
    <section className="session-history" aria-label="Past check-ins">
      <div className="session-history__header">
        <div>
          <span className="session-history__eyebrow">Saved history</span>
          <h2>Past check-ins</h2>
        </div>
        <button
          className="session-history__clear"
          disabled={isLoading || isSessionLoading || !completedHistory.length}
          type="button"
          onClick={onClearHistory}
        >
          Clear all
        </button>
      </div>

      {isLoading ? <p className="session-history__empty">Loading your recent sessions...</p> : null}
      {!isLoading && !completedHistory.length ? (
        <p className="session-history__empty">Completed check-ins will appear here once a reflection is finished.</p>
      ) : null}

      <div className="session-history__list">
        {completedHistory.map((session) => (
          <article
            key={session.session_id}
            className={`session-history__card${session.session_id === activeSessionId ? " is-active" : ""}`}
          >
            <button
              className="session-history__card-main"
              disabled={isSessionLoading}
              type="button"
              onClick={() => onSelectSession(session.session_id)}
            >
              <div className="session-history__meta">
                <span className="session-history__status session-history__status--complete">Complete</span>
                <time dateTime={session.updated_at}>{formatSessionTime(session.updated_at)}</time>
              </div>

              <p className="session-history__headline">{sessionTitle(session)}</p>
            </button>

            <button
              aria-label={`Delete ${sessionTitle(session)}`}
              className="session-history__delete"
              disabled={isSessionLoading}
              type="button"
              onClick={() => onDeleteSession(session.session_id)}
            >
              Delete
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
