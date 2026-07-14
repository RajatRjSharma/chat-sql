"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSpeechRecognition,
  isSpeechRecognitionSupported,
  type SpeechRecognitionLike,
} from "@/lib/speech";

type UseSpeechToTextOptions = {
  lang?: string;
  disabled?: boolean;
  onTranscript: (text: string, meta: { interim: boolean }) => void;
};

export function useSpeechToText({
  lang = "en-US",
  disabled = false,
  onTranscript,
}: UseSpeechToTextOptions) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  useEffect(() => {
    setSupported(isSpeechRecognitionSupported());
  }, []);

  const stop = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      setListening(false);
      return;
    }
    try {
      recognition.stop();
    } catch {
      try {
        recognition.abort();
      } catch {
        /* ignore */
      }
    }
    recognitionRef.current = null;
    setListening(false);
  }, []);

  const start = useCallback(() => {
    if (disabled) return;
    setError(null);

    if (recognitionRef.current) {
      stop();
    }

    const recognition = createSpeechRecognition(
      {
        onInterim: (text) => {
          if (text) onTranscriptRef.current(text, { interim: true });
        },
        onFinal: (text) => {
          if (text) onTranscriptRef.current(text, { interim: false });
        },
        onError: (message) => {
          setError(message);
          setListening(false);
          recognitionRef.current = null;
        },
        onEnd: () => {
          setListening(false);
          recognitionRef.current = null;
        },
      },
      { lang },
    );

    if (!recognition) {
      setError("Voice input is not supported in this browser.");
      setSupported(false);
      return;
    }

    recognitionRef.current = recognition;
    try {
      recognition.start();
      setListening(true);
    } catch {
      setError("Could not start the microphone.");
      recognitionRef.current = null;
      setListening(false);
    }
  }, [disabled, lang, stop]);

  const toggle = useCallback(() => {
    if (listening) stop();
    else start();
  }, [listening, start, stop]);

  useEffect(() => {
    if (disabled && listening) stop();
  }, [disabled, listening, stop]);

  useEffect(() => {
    return () => {
      const recognition = recognitionRef.current;
      if (!recognition) return;
      try {
        recognition.abort();
      } catch {
        /* ignore */
      }
      recognitionRef.current = null;
    };
  }, []);

  return {
    supported,
    listening,
    error,
    start,
    stop,
    toggle,
  };
}
