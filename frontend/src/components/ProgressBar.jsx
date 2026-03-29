import { CHECK_IN_STEPS } from "../stepContent";
import "./ProgressBar.css";


export default function ProgressBar({ step, isComplete }) {
  const activeStep = isComplete ? 5 : step;
  const fillClassName = `progress-card__fill progress-card__fill--${activeStep}`;
  const cardClassName = `progress-card${isComplete ? " progress-card--complete" : ""}`;

  return (
    <section className={cardClassName} aria-label="Stress check-in progress">
      <div className="progress-card__copy">
        <span className="progress-card__eyebrow">{isComplete ? "Check-in complete" : "5-step check-in"}</span>
        <strong>{isComplete ? "Ready to review" : `Step ${activeStep} of 5`}</strong>
      </div>
      <div className="progress-card__track" aria-hidden="true">
        <div className={fillClassName} />
      </div>
      {isComplete ? (
        <p className="progress-card__note">All five reflections are captured in your summary.</p>
      ) : (
        <>
          <div className="progress-card__steps">
            {[1, 2, 3, 4, 5].map((marker) => {
              const markerClassName = marker <= activeStep ? "progress-card__dot is-active" : "progress-card__dot";
              return <span key={marker} className={markerClassName} />;
            })}
          </div>
          <div className="progress-card__labels" aria-hidden="true">
            {CHECK_IN_STEPS.map((item) => {
              const labelClassName = item.number === activeStep ? "progress-card__label is-current" : "progress-card__label";
              return (
                <span key={item.number} className={labelClassName}>
                  {item.shortTitle}
                </span>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}
