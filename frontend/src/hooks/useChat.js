import { startTransition, useEffect, useRef, useState } from "react";

import {
  clearSessionHistory,
  createReport,
  deleteSessionHistory,
  fetchSessionDetail,
  fetchSessionHistory,
  streamChat,
} from "../api";

const STORAGE_KEY = "ori-stress-check-in";
const CLIENT_ID_KEY = "ori-stress-client-id";
const START_TYPING_DELAY_MS = 90;
const STREAM_TICK_MS = 24;
const PERSIST_DELAY_MS = 220;


function loadStoredState() {
  const storedValue = localStorage.getItem(STORAGE_KEY);
  if (!storedValue) {
    return null;
  }
  try {
    return JSON.parse(storedValue);
  } catch (error) {
    console.error("Stored chat state could not be restored.", error);
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}


function ensureClientId() {
  const existingValue = localStorage.getItem(CLIENT_ID_KEY);
  if (existingValue) {
    return existingValue;
  }
  const generatedValue = crypto.randomUUID();
  localStorage.setItem(CLIENT_ID_KEY, generatedValue);
  return generatedValue;
}


function sanitizeMessages(messages = []) {
  return messages.map((message) => ({ ...message, pending: false }));
}


function createMessage(role, content) {
  return { id: crypto.randomUUID(), role, content, pending: false };
}


function hydrateMessages(messages = []) {
  return messages.map((message) => ({ ...message, id: crypto.randomUUID(), pending: false }));
}


function createAssistantPlaceholder() {
  return { id: crypto.randomUUID(), role: "assistant", content: "", pending: true };
}


function appendChunk(messages, textChunk) {
  return messages.map((message, index) => {
    const isLastAssistant = index === messages.length - 1 && message.role === "assistant";
    return isLastAssistant ? { ...message, content: `${message.content}${textChunk}` } : message;
  });
}


function finishAssistant(messages) {
  return messages.map((message, index) => {
    const isLastAssistant = index === messages.length - 1 && message.role === "assistant";
    return isLastAssistant ? { ...message, pending: false } : message;
  });
}


function assistantTurns(messages) {
  return messages.filter((message) => message.role === "assistant").length;
}


function nextDrainSize(bufferLength) {
  if (bufferLength > 180) {
    return 6;
  }
  if (bufferLength > 90) {
    return 4;
  }
  if (bufferLength > 36) {
    return 2;
  }
  return 1;
}


function initialState() {
  const storedState = loadStoredState();
  return {
    clientId: storedState?.clientId ?? ensureClientId(),
    sessionId: storedState?.sessionId ?? crypto.randomUUID(),
    // messages: sanitizeMessages(storedState?.messages),
    messages: sanitizeMessages(storedState?.messages),
    step: storedState?.step ?? 1,
    report: storedState?.report ?? null,
    isComplete: storedState?.isComplete ?? false,
  };
}


export function useChat() {
  const persistedState = useRef(initialState()).current;
  const [clientId] = useState(persistedState.clientId);
  const [sessionId, setSessionId] = useState(persistedState.sessionId);
  const [messages, setMessages] = useState(persistedState.messages);
  const [step, setStep] = useState(persistedState.step);
  const [report, setReport] = useState(persistedState.report);
  const [history, setHistory] = useState([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [activeHistorySessionId, setActiveHistorySessionId] = useState(persistedState.sessionId);
  const [isComplete, setIsComplete] = useState(persistedState.isComplete);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isSessionLoading, setIsSessionLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const bootstrappedRef = useRef(false);
  const queueRef = useRef("");
  const streamFinishedRef = useRef(false);
  const drainTimerRef = useRef(null);
  const drainStartTimerRef = useRef(null);
  const persistTimerRef = useRef(null);
  const streamAbortRef = useRef(null);
  const streamGenerationRef = useRef(0);

  function abortActiveStream() {
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
  }

  function isAbortError(error) {
    return error?.name === "AbortError";
  }

  useEffect(() => {
    const payload = JSON.stringify({ clientId, sessionId, messages, step, report, isComplete });
    if (persistTimerRef.current) {
      window.clearTimeout(persistTimerRef.current);
      persistTimerRef.current = null;
    }
    if (!isStreaming) {
      localStorage.setItem(STORAGE_KEY, payload);
      return;
    }
    persistTimerRef.current = window.setTimeout(() => {
      localStorage.setItem(STORAGE_KEY, payload);
      persistTimerRef.current = null;
    }, PERSIST_DELAY_MS);
  }, [clientId, isComplete, isStreaming, messages, report, sessionId, step]);

  useEffect(() => {
    if (bootstrappedRef.current) {
      return;
    }
    bootstrappedRef.current = true;
    if (messages.length || isComplete) {
      return;
    }
    void beginCheckIn(sessionId);
  }, [isComplete, messages.length, sessionId]);

  useEffect(() => {
    void refreshHistory();
  }, [clientId]);

  useEffect(() => () => {
    abortActiveStream();
    stopDrainer();
    stopPersistTimer();
  }, []);

  function stopDrainer() {
    if (drainStartTimerRef.current) {
      window.clearTimeout(drainStartTimerRef.current);
      drainStartTimerRef.current = null;
    }
    if (!drainTimerRef.current) {
      return;
    }
    window.clearInterval(drainTimerRef.current);
    drainTimerRef.current = null;
  }

  function stopPersistTimer() {
    if (!persistTimerRef.current) {
      return;
    }
    window.clearTimeout(persistTimerRef.current);
    persistTimerRef.current = null;
  }

  function resetConversation(nextSessionId) {
    queueRef.current = "";
    streamFinishedRef.current = false;
    setSessionId(nextSessionId);
    setActiveHistorySessionId(nextSessionId);
    setMessages([]);
    setStep(1);
    setReport(null);
    setIsComplete(false);
    setIsGeneratingReport(false);
    setErrorMessage("");
  }

  async function activateFreshSession(nextSessionId = crypto.randomUUID()) {
    abortActiveStream();
    stopDrainer();
    stopPersistTimer();
    resetConversation(nextSessionId);
    await beginCheckIn(nextSessionId);
  }

  function finalizeStreamingMessage() {
    stopDrainer();
    streamFinishedRef.current = false;
    setIsStreaming(false);
    startTransition(() => setMessages((currentMessages) => finishAssistant(currentMessages)));
  }

  function tickQueue() {
    if (!queueRef.current) {
      if (streamFinishedRef.current) {
        finalizeStreamingMessage();
      }
      return;
    }
    const nextChunk = queueRef.current.slice(0, nextDrainSize(queueRef.current.length));
    queueRef.current = queueRef.current.slice(nextChunk.length);
    startTransition(() => {
      setMessages((currentMessages) => appendChunk(currentMessages, nextChunk));
    });
  }

  function startDrainer() {
    if (drainTimerRef.current || drainStartTimerRef.current) {
      return;
    }
    drainStartTimerRef.current = window.setTimeout(() => {
      drainStartTimerRef.current = null;
      tickQueue();
      drainTimerRef.current = window.setInterval(tickQueue, STREAM_TICK_MS);
    }, START_TYPING_DELAY_MS);
  }

  async function refreshHistory() {
    setIsHistoryLoading(true);
    try {
      const historyPayload = await fetchSessionHistory(clientId);
      setHistory(historyPayload.sessions);
    } catch (error) {
      console.error("Past session history could not be loaded.", error);
    } finally {
      setIsHistoryLoading(false);
    }
  }

  async function openHistorySession(nextSessionId) {
    if (isStreaming || isSessionLoading) {
      return;
    }
    setErrorMessage("");
    setIsSessionLoading(true);
    try {
      const sessionDetail = await fetchSessionDetail(clientId, nextSessionId);
      stopDrainer();
      stopPersistTimer();
      queueRef.current = "";
      streamFinishedRef.current = false;
      setSessionId(sessionDetail.session_id);
      setMessages(hydrateMessages(sessionDetail.messages));
      setStep(sessionDetail.current_step);
      setReport(sessionDetail.report);
      setIsComplete(sessionDetail.status === "complete");
      setActiveHistorySessionId(sessionDetail.session_id);
      setIsStreaming(false);
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsSessionLoading(false);
    }
  }

  async function beginCheckIn(activeSessionId) {
    const generation = ++streamGenerationRef.current;
    abortActiveStream();
    const controller = new AbortController();
    streamAbortRef.current = controller;

    setErrorMessage("");
    setIsStreaming(true);
    setActiveHistorySessionId(activeSessionId);
    setMessages([createAssistantPlaceholder()]);
    queueRef.current = "";
    streamFinishedRef.current = false;
    startDrainer();
    try {
      await streamChat({
        clientId,
        sessionId: activeSessionId,
        messages: [],
        step,
        onEvent: handleStreamEvent,
        signal: controller.signal,
      });
      if (generation !== streamGenerationRef.current) {
        return;
      }
      void refreshHistory();
    } catch (error) {
      if (isAbortError(error) || generation !== streamGenerationRef.current) {
        return;
      }
      setErrorMessage(error.message);
      stopDrainer();
      setIsStreaming(false);
      setMessages([]);
    }
  }

  function handleStreamEvent({ event, data }) {
    if (event === "meta") {
      setStep(data.step);
      return;
    }
    if (event === "token") {
      queueRef.current += data.text;
      return;
    }
    if (event === "done") {
      streamFinishedRef.current = true;
      setStep(data.step);
    }
  }

  async function continueCheckIn(nextMessages) {
    const generation = ++streamGenerationRef.current;
    abortActiveStream();
    const controller = new AbortController();
    streamAbortRef.current = controller;

    setErrorMessage("");
    setIsStreaming(true);
    queueRef.current = "";
    streamFinishedRef.current = false;
    startTransition(() => {
      setMessages([...nextMessages, createAssistantPlaceholder()]);
    });
    startDrainer();
    try {
      await streamChat({
        clientId,
        sessionId,
        messages: nextMessages,
        step,
        onEvent: handleStreamEvent,
        signal: controller.signal,
      });
      if (generation !== streamGenerationRef.current) {
        return false;
      }
      void refreshHistory();
    } catch (error) {
      if (isAbortError(error) || generation !== streamGenerationRef.current) {
        return false;
      }
      stopDrainer();
      setIsStreaming(false);
      setErrorMessage(error.message);
      setMessages(messages);
      return false;
    }
    return true;
  }

  async function completeCheckIn(nextMessages) {
    setErrorMessage("");
    setIsStreaming(true);
    setIsGeneratingReport(true);
    setMessages(nextMessages);
    try {
      const reportData = await createReport({ clientId, sessionId, messages: nextMessages });
      setReport(reportData);
      setIsComplete(true);
      void refreshHistory();
      return true;
    } catch (error) {
      setErrorMessage(error.message);
      setMessages(messages);
      return false;
    } finally {
      setIsGeneratingReport(false);
      setIsStreaming(false);
    }
  }

  async function submitResponse(rawInput) {
    const trimmedInput = rawInput.trim();
    if (!trimmedInput || isStreaming) {
      return false;
    }
    const nextMessages = [...messages, createMessage("user", trimmedInput)];
    const isLastStepAnswer = step === 5 && assistantTurns(messages) >= 5;
    if (isLastStepAnswer) {
      return completeCheckIn(nextMessages);
    }
    return continueCheckIn(nextMessages);
  }

  async function restartSession() {
    await activateFreshSession();
  }

  async function removeHistorySession(targetSessionId) {
    if (isStreaming || isSessionLoading) {
      return;
    }
    if (!window.confirm("Delete this saved check-in from your history?")) {
      return;
    }
    setErrorMessage("");
    setIsSessionLoading(true);
    const shouldStartFresh = targetSessionId === sessionId;
    try {
      await deleteSessionHistory(clientId, targetSessionId);
      await refreshHistory();
    } catch (error) {
      setErrorMessage(error.message);
      setIsSessionLoading(false);
      return;
    }
    setIsSessionLoading(false);
    if (shouldStartFresh) {
      await activateFreshSession();
    }
  }

  async function removeAllHistory() {
    if (isStreaming || isSessionLoading) {
      return;
    }
    if (!history.some((session) => session.status === "complete")) {
      return;
    }
    if (!window.confirm("Delete all saved check-ins from your history?")) {
      return;
    }
    setErrorMessage("");
    setIsSessionLoading(true);
    const shouldStartFresh = isComplete && history.some((session) => session.session_id === sessionId);
    try {
      await clearSessionHistory(clientId);
      await refreshHistory();
    } catch (error) {
      setErrorMessage(error.message);
      setIsSessionLoading(false);
      return;
    }
    setIsSessionLoading(false);
    if (shouldStartFresh) {
      await activateFreshSession();
    }
  }

  return {
    activeHistorySessionId,
    errorMessage,
    history,
    isComplete,
    isGeneratingReport,
    isHistoryLoading,
    isStreaming,
    isSessionLoading,
    messages,
    removeAllHistory,
    removeHistorySession,
    openHistorySession,
    report,
    restartSession,
    sessionId,
    step,
    submitResponse,
  };
}
