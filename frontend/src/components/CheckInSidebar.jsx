import ProgressBar from "./ProgressBar";
import SessionHistory from "./SessionHistory";
import { CHECK_IN_STEPS } from "../stepContent";
import "./CheckInSidebar.css";


function getStepState(number, activeStep, isComplete) {
  if (isComplete || number < activeStep) {
    return "done";
  }
  if (number === activeStep) {
    return "current";
  }
  return "upcoming";
}


export default function CheckInSidebar({
  activeHistorySessionId,
  history,
  isComplete,
  isHistoryLoading,
  isSessionLoading,
  onClearHistory,
  onDeleteHistorySession,
  onSelectHistorySession,
  step,
}) {
  const activeStep = isComplete ? 5 : step;

  return (
    <aside className="checkin-sidebar" aria-label="Check-in overview">
      <section className="checkin-sidebar__hero">
        <h1>Ori stress check-in</h1>
      </section>

      <ProgressBar step={step} isComplete={isComplete} />

      <div className="checkin-sidebar__content">
        <section className="checkin-sidebar__steps" aria-label="Check-in steps">
          {CHECK_IN_STEPS.map((item) => {
            const stepState = getStepState(item.number, activeStep, isComplete);
            const itemClassName = `checkin-sidebar__step checkin-sidebar__step--${stepState}`;

            return (
              <article key={item.number} className={itemClassName}>
                <span className="checkin-sidebar__step-number">0{item.number}</span>
                <div className="checkin-sidebar__step-copy">
                  <strong>{item.title}</strong>
                  <p>{item.helper}</p>
                </div>
              </article>
            );
          })}
        </section>

        <SessionHistory
          activeSessionId={activeHistorySessionId}
          history={history}
          isLoading={isHistoryLoading}
          isSessionLoading={isSessionLoading}
          onClearHistory={onClearHistory}
          onDeleteSession={onDeleteHistorySession}
          onSelectSession={onSelectHistorySession}
        />
      </div>
    </aside>
  );
}
