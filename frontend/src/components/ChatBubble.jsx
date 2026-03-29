import { memo } from "react";

import "./ChatBubble.css";


function ChatBubble({ message }) {
  const bubbleClassName = `chat-bubble chat-bubble--${message.role}`;
  const showTypingIndicator = message.pending && !message.content;
  const showCursor = message.pending && Boolean(message.content);
  const avatarLabel = message.role === "assistant" ? "Ori" : "You";
  const authorLabel = message.role === "assistant" ? "Ori" : "You";
  const surfaceClassName = `chat-bubble__surface${showTypingIndicator ? " chat-bubble__surface--pending" : ""}`;

  return (
    <article className={bubbleClassName}>
      <span className="chat-bubble__avatar" aria-hidden="true">{avatarLabel}</span>
      <div className={surfaceClassName}>
        <span className="chat-bubble__author">{authorLabel}</span>
        <div className="chat-bubble__content">
          {showTypingIndicator ? (
            <span className="chat-bubble__typing" aria-label="Ori is typing">
              <span className="chat-bubble__typing-dot" />
              <span className="chat-bubble__typing-dot" />
              <span className="chat-bubble__typing-dot" />
            </span>
          ) : (
            message.content
          )}
          {showCursor ? <span className="chat-bubble__cursor" aria-hidden="true" /> : null}
        </div>
      </div>
    </article>
  );
}


export default memo(ChatBubble);
