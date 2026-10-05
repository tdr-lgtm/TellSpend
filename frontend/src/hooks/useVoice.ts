/**
 * Voice input: speak into a text box. Words arrive live, and it stops on
 * its own after a pause (or when stopped).
 */

import { useEffect, useRef, useState } from "react";

import {
  createRecognition,
  joinText,
  speechErrorMessage,
  type Recognition,
  type RecognitionEvent,
} from "../lib/speech";

// Stop dictating after this long without new words.
const SILENCE_MS = 2200;

export function useDictation(onText: (spoken: string) => void) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const silence = useRef<number | undefined>(undefined);
  const onTextRef = useRef(onText);

  useEffect(() => {
    onTextRef.current = onText;
  }, [onText]);

  function stop() {
    window.clearTimeout(silence.current);
    recognition.current?.stop();
  }

  function start() {
    if (recognition.current) {
      return;
    }
    const recognizer = createRecognition(true);
    if (!recognizer) {
      return;
    }

    const waitForSilence = () => {
      window.clearTimeout(silence.current);
      silence.current = window.setTimeout(() => recognizer.stop(), SILENCE_MS);
    };

    // The whole text, rebuilt from every result each time rather than
    // added to, so a result sent again never doubles words.
    recognizer.onresult = (event: RecognitionEvent) => {
      const parts: string[] = [];
      for (let i = 0; i < event.results.length; i += 1) {
        parts.push(event.results[i][0].transcript);
      }
      onTextRef.current(joinText(...parts));
      waitForSilence();
    };
    recognizer.onerror = (event) => setError(speechErrorMessage(event.error));
    recognizer.onend = () => {
      window.clearTimeout(silence.current);
      recognition.current = null;
      setListening(false);
    };

    setError(null);
    recognition.current = recognizer;
    recognizer.start();
    setListening(true);
    waitForSilence();
  }

  // Leaving the page stops listening.
  useEffect(
    () => () => {
      window.clearTimeout(silence.current);
      recognition.current?.abort();
    },
    [],
  );

  return { listening, error, start, stop };
}
