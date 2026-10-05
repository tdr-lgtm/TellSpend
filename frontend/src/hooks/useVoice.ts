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

    let finals = "";
    const waitForSilence = () => {
      window.clearTimeout(silence.current);
      silence.current = window.setTimeout(() => recognizer.stop(), SILENCE_MS);
    };

    recognizer.onresult = (event: RecognitionEvent) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) {
          finals = joinText(finals, result[0].transcript);
        } else {
          interim = joinText(interim, result[0].transcript);
        }
      }
      onTextRef.current(joinText(finals, interim));
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
