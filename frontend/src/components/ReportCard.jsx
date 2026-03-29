import "./ReportCard.css";


function toLabel(value) {
  return value.replaceAll("_", " ");
}


export default function ReportCard({ report, onRestart }) {
  const profileEntries = Object.entries(report.profile).filter(([key]) => key !== "support_need");

  return (
    <section className="report-card" aria-label="Stress profile summary">
      <div className="report-card__block">
        <span className="report-card__eyebrow">Ori’s read</span>
        <h2>Your stress profile</h2>
        <p>A grounded summary of the pattern Ori heard across your five answers.</p>
      </div>

      <div className="report-card__block">
        <section className="report-card__summary">
          <article className="report-card__spotlight">
            <span>Support need</span>
            <strong>{report.profile.support_need}</strong>
            <p>This is the kind of care or structure that would likely feel most helpful right now.</p>
          </article>

          <div className="report-card__profile">
            {profileEntries.map(([key, value]) => (
              <article key={key} className="report-card__tile">
                <span>{toLabel(key)}</span>
                <strong>{value}</strong>
              </article>
            ))}
          </div>
        </section>
      </div>

      <div className="report-card__block">
        <section className="report-card__plan" aria-label="Three grounded next steps">
          <div className="report-card__plan-copy">
            <span className="report-card__plan-eyebrow">Action plan</span>
            <h3>Three grounded next steps</h3>
            <p>Start with the one that feels easiest to follow through on today.</p>
          </div>
          <div className="report-card__actions">
            {report.actions.map((action, index) => (
              <article key={action} className="report-card__action">
                <span className="report-card__action-number">0{index + 1}</span>
                <p>{action}</p>
              </article>
            ))}
          </div>
        </section>
      </div>

      <div className="report-card__block">
        <button className="report-card__button" type="button" onClick={onRestart}>
          Start another check-in
        </button>
      </div>
    </section>
  );
}
