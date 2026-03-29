import "./QuickReplyChips.css";


export default function QuickReplyChips({ disabled, onSelect, options }) {
  const visibleOptions = options.slice(0, 2);

  if (!visibleOptions.length) {
    return null;
  }

  return (
    <section className="quick-replies" aria-label="Suggested response starters">
      <div className="quick-replies__list">
        {visibleOptions.map((option) => (
          <button key={option} className="quick-replies__chip" disabled={disabled} type="button" onClick={() => onSelect(option)}>
            {option}
          </button>
        ))}
      </div>
    </section>
  );
}
