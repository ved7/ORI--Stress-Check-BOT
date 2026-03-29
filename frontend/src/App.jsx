import { useEffect, useRef, useState } from "react";

import CheckInSidebar from "./components/CheckInSidebar";
import ChatBubble from "./components/ChatBubble";
import QuickReplyChips from "./components/QuickReplyChips";
import ReportCard from "./components/ReportCard";
import { useChat } from "./hooks/useChat";
import { getStepContent } from "./stepContent";
import "./App.css";


export default function App() {
  const [draft, setDraft] = useState("");
  const chatLogRef = useRef(null);
  const inputRef = useRef(null);
  const reportStartRef = useRef(null);
  const {
    activeHistorySessionId,
    errorMessage,
    history,
    isComplete,
    isGeneratingReport,
    isHistoryLoading,
    isSessionLoading,
    isStreaming,
    messages,
    openHistorySession,
    removeAllHistory,
    removeHistorySession,
    report,
    restartSession,
    sessionId,
    step,
    submitResponse,
  } = useChat();
  const stepContent = getStepContent(step);
  const showQuickReplies = !isComplete && !isStreaming && !isGeneratingReport && !draft.trim();
  const lastMessage = messages[messages.length - 1];
  const lastMessageSignature = lastMessage
    ? `${lastMessage.id}:${lastMessage.content.length}:${lastMessage.pending ? "pending" : "ready"}`
    : "empty";

  useEffect(() => {
    setDraft("");
  }, [sessionId]);

  useEffect(() => {
    const chatLogElement = chatLogRef.current;
    if (!chatLogElement) {
      return;
    }
    if (report && reportStartRef.current) {
      chatLogElement.scrollTo({
        top: Math.max(reportStartRef.current.offsetTop - 12, 0),
        behavior: "smooth",
      });
      return;
    }
    chatLogElement.scrollTo({
      top: chatLogElement.scrollHeight,
      behavior: isStreaming ? "auto" : "smooth",
    });
  }, [isStreaming, lastMessageSignature, report]);

  useEffect(() => {
    if (isStreaming || isComplete) {
      return;
    }
    inputRef.current?.focus();
  }, [isComplete, isStreaming, step]);

  function handleQuickReply(option) {
    setDraft(option);
    inputRef.current?.focus();
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const nextDraft = draft;
    const wasSubmitted = await submitResponse(nextDraft);
    if (wasSubmitted) {
      setDraft("");
    }
  }

  function handleKeyDown(event) {
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }
    event.preventDefault();
    void handleSubmit(event);
  }

  function renderHeaderText() {
    if (isComplete) {
      return {
        eyebrow: "Complete",
        title: "Reflection complete",
        body: "",
      };
    }
    return {
      eyebrow: `Step ${stepContent.number} of 5`,
      title: stepContent.title,
      body: stepContent.description,
    };
  }

  const headerText = renderHeaderText();
  const headerClassName = `conversation-panel__header${isComplete ? " conversation-panel__header--complete" : ""}`;
  const statusClassName = `conversation-panel__status${isComplete ? " conversation-panel__status--complete" : ""}`;

  return (
    <div className="app-shell">
      <main className="experience-layout">
        <CheckInSidebar
          activeHistorySessionId={activeHistorySessionId}
          history={history}
          isComplete={isComplete}
          isHistoryLoading={isHistoryLoading}
          isSessionLoading={isSessionLoading}
          onClearHistory={removeAllHistory}
          onDeleteHistorySession={removeHistorySession}
          onSelectHistorySession={openHistorySession}
          step={step}
        />

        <section className="conversation-panel">
          <header className={headerClassName}>
            <div className="conversation-panel__copy">
              <span className="conversation-panel__eyebrow">{headerText.eyebrow}</span>
              <h2>{headerText.title}</h2>
              {headerText.body ? <p>{headerText.body}</p> : null}
            </div>
            <div className={statusClassName}>
              <span className={`status-pill ${isStreaming ? "is-busy" : ""}`}>
                {isSessionLoading
                  ? "Loading saved session"
                  : isComplete
                    ? "Profile ready"
                    : isGeneratingReport
                      ? "Generating profile"
                    : isStreaming
                      ? "Ori is typing"
                      : "Ready for your response"}
              </span>
              <button className="conversation-panel__restart" disabled={isStreaming} type="button" onClick={restartSession}>
                Start over
              </button>
            </div>
          </header>

          {errorMessage ? <p className="app-error">{errorMessage}</p> : null}

          <section className="conversation-card">
            {isGeneratingReport ? (
              <div className="profile-alert" role="status" aria-live="polite">
                <span className="profile-alert__spinner" aria-hidden="true" />
                <div className="profile-alert__copy">
                  <strong>Generating your stress profile</strong>
                  <p>Ori is pulling together your five answers into one grounded read.</p>
                </div>
              </div>
            ) : null}

            <section ref={chatLogRef} className="chat-log" aria-live="polite">
              {messages.map((message) => (
                <ChatBubble key={message.id} message={message} />
              ))}
              {report ? (
                <div ref={reportStartRef}>
                  <ReportCard report={report} onRestart={restartSession} />
                </div>
              ) : null}
            </section>

            {isComplete ? null : (
              <>
                {showQuickReplies ? (
                  <QuickReplyChips disabled={isStreaming} onSelect={handleQuickReply} options={stepContent.starters} />
                ) : null}

                <form className="chat-composer" onSubmit={handleSubmit}>
                  <div className="chat-composer__heading">
                    <label className="chat-composer__label" htmlFor="stress-response">
                      Your response
                    </label>
                  </div>
                  <textarea
                    id="stress-response"
                    className="chat-composer__input"
                    value={draft}
                    ref={inputRef}
                    rows={4}
                    placeholder={stepContent.placeholder}
                    disabled={isStreaming}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={handleKeyDown}
                  />
                  <div className="chat-composer__footer">
                    <span>{isGeneratingReport ? "Building your profile..." : isStreaming ? "Ori is responding..." : ""}</span>
                    <button className="chat-composer__button" disabled={isStreaming || !draft.trim()} type="submit">
                      {isGeneratingReport ? "Generating..." : isStreaming ? "Listening..." : stepContent.buttonLabel}
                    </button>
                  </div>
                </form>
              </>
            )}
          </section>
        </section>
      </main>
    </div>
  );
}
