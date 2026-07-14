/**
 * Thin Web Speech API wrapper for voice-to-text.
 * Chrome / Edge work best; Safari is partial; Firefox often unsupported.
 */

export type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionResultEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type SpeechRecognitionResultEventLike = {
  resultIndex: number;
  results: ArrayLike<{
    isFinal: boolean;
    0: { transcript: string };
  }>;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

export type SpeechCallbacks = {
  onInterim?: (text: string) => void;
  onFinal?: (text: string) => void;
  onError?: (message: string) => void;
  onEnd?: () => void;
};

function getSpeechRecognitionConstructor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const w = window as Window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function isSpeechRecognitionSupported(): boolean {
  return getSpeechRecognitionConstructor() != null;
}

export function createSpeechRecognition(
  callbacks: SpeechCallbacks,
  options?: { lang?: string },
): SpeechRecognitionLike | null {
  const Ctor = getSpeechRecognitionConstructor();
  if (!Ctor) return null;

  const recognition = new Ctor();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = options?.lang ?? "en-US";

  recognition.onresult = (event) => {
    let interim = "";
    let finalText = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const piece = event.results[i][0]?.transcript ?? "";
      if (event.results[i].isFinal) {
        finalText += piece;
      } else {
        interim += piece;
      }
    }
    if (interim) callbacks.onInterim?.(interim.trim());
    if (finalText) callbacks.onFinal?.(finalText.trim());
  };

  recognition.onerror = (event) => {
    const code = event.error;
    if (code === "aborted" || code === "no-speech") {
      callbacks.onEnd?.();
      return;
    }
    const messages: Record<string, string> = {
      "not-allowed": "Microphone permission denied.",
      "service-not-allowed": "Speech service not allowed in this browser.",
      network: "Network error while using speech recognition.",
      "audio-capture": "No microphone found.",
    };
    callbacks.onError?.(messages[code] || `Speech error: ${code}`);
    callbacks.onEnd?.();
  };

  recognition.onend = () => {
    callbacks.onEnd?.();
  };

  return recognition;
}

export function isSpeechSynthesisSupported(): boolean {
  return typeof window !== "undefined" && typeof window.speechSynthesis !== "undefined";
}

export function speakText(text: string, options?: { lang?: string }): void {
  if (!isSpeechSynthesisSupported() || !text.trim()) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text.trim());
  utterance.lang = options?.lang ?? "en-US";
  utterance.rate = 1;
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking(): void {
  if (!isSpeechSynthesisSupported()) return;
  window.speechSynthesis.cancel();
}
