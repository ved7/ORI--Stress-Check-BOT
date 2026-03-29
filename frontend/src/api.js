import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});


function parseEventBlock(block) {
  const lines = block.split("\n").filter(Boolean);
  const eventName = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
  const dataLines = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim());
  if (!eventName || dataLines.length === 0) {
    return null;
  }
  return { event: eventName, data: JSON.parse(dataLines.join("")) };
}


function logJsonParseError(error) {
  console.error("Unable to parse API response payload.", error);
}


function flushBufferedEvents(buffer, onEvent) {
  const normalizedBuffer = buffer.replace(/\r/g, "");
  const chunks = normalizedBuffer.split("\n\n");
  chunks.slice(0, -1).forEach((chunk) => {
    const parsedEvent = parseEventBlock(chunk);
    if (parsedEvent) {
      onEvent(parsedEvent);
    }
  });
  return chunks.at(-1) ?? "";
}


async function readSseStream(stream, onEvent) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer = flushBufferedEvents(buffer + decoder.decode(value, { stream: true }), onEvent);
  }
  flushBufferedEvents(`${buffer}\n\n`, onEvent);
}


function buildFetchError(response, payload) {
  return new Error(payload?.detail || `Request failed with status ${response.status}`);
}


async function readErrorPayload(response) {
  try {
    return await response.json();
  } catch (error) {
    logJsonParseError(error);
    return null;
  }
}


export async function streamChat({ clientId, sessionId, messages, step, onEvent, signal }) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: clientId, session_id: sessionId, messages, step }),
    signal,
  });
  if (!response.ok) {
    const payload = await readErrorPayload(response);
    throw buildFetchError(response, payload);
  }
  await readSseStream(response.body, onEvent);
}


export async function createReport({ clientId, sessionId, messages }) {
  const response = await apiClient.post("/report", {
    client_id: clientId,
    session_id: sessionId,
    messages,
  });
  return response.data;
}


export async function fetchSessionHistory(clientId) {
  const response = await apiClient.get(`/history/${clientId}`);
  return response.data;
}


export async function fetchSessionDetail(clientId, sessionId) {
  const response = await apiClient.get(`/history/${clientId}/${sessionId}`);
  return response.data;
}


export async function deleteSessionHistory(clientId, sessionId) {
  const response = await apiClient.delete(`/history/${clientId}/${sessionId}`);
  return response.data;
}


export async function clearSessionHistory(clientId) {
  const response = await apiClient.delete(`/history/${clientId}`);
  return response.data;
}


export async function checkHealth() {
  const response = await apiClient.get("/health");
  return response.data;
}
