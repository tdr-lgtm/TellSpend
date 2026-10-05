/**
 * Speech to text with the browser's own recognizer (the Web Speech API:
 * Chrome, Edge, Safari; not Firefox). Nothing goes to our server: the
 * browser turns speech into text (Chrome does it on Google's servers).
 */

// The small part of the API we use (TypeScript's DOM types don't have it).
type Alternative = { transcript: string };
type ResultItem = { isFinal: boolean; 0: Alternative };
export type RecognitionEvent = { resultIndex: number; results: ArrayLike<ResultItem> };

export type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: RecognitionEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
};

type RecognitionConstructor = new () => Recognition;

function recognitionClass(): RecognitionConstructor | undefined {
  const scope = window as unknown as {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition;
}

export const speechSupported = typeof window !== "undefined" && recognitionClass() !== undefined;

export function createRecognition(continuous: boolean): Recognition | null {
  const Recognizer = recognitionClass();
  if (!Recognizer) {
    return null;
  }
  const recognition = new Recognizer();
  // The device's language (e.g. en-IN), so local names and numbers work.
  recognition.lang = navigator.language || "en-US";
  recognition.continuous = continuous;
  recognition.interimResults = true;
  return recognition;
}

// What the recognizer's errors mean for the user; others are passing.
export function speechErrorMessage(error: string): string | null {
  if (error === "not-allowed" || error === "service-not-allowed") {
    return "Microphone access is blocked. Allow it in the browser's site settings.";
  }
  if (error === "audio-capture") {
    return "No microphone was found.";
  }
  return null;
}

// Two spaces never; used when adding spoken words to typed ones.
export function joinText(...parts: string[]): string {
  return parts.map((part) => part.trim()).filter(Boolean).join(" ");
}
