/**
 * Server TTS playback (Piper via /api/voice/speak) with optional browser fallback.
 * Only one utterance plays at a time across the app.
 */

import { ApiError, api } from "@/lib/api";
import {
  isSpeechSynthesisSupported,
  speakText,
  stopSpeaking as stopBrowserSpeaking,
} from "@/lib/speech";

type Listener = (playingId: string | null) => void;

let currentAudio: HTMLAudioElement | null = null;
let currentObjectUrl: string | null = null;
let currentId: string | null = null;
let playGeneration = 0;
const listeners = new Set<Listener>();

function notify(playingId: string | null) {
  currentId = playingId;
  for (const listener of listeners) {
    listener(playingId);
  }
}

function releaseAudio() {
  if (currentAudio) {
    currentAudio.onended = null;
    currentAudio.onerror = null;
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }
  if (currentObjectUrl) {
    URL.revokeObjectURL(currentObjectUrl);
    currentObjectUrl = null;
  }
}

export function subscribeSpeakPlayback(listener: Listener): () => void {
  listeners.add(listener);
  listener(currentId);
  return () => {
    listeners.delete(listener);
  };
}

export function getPlayingSpeakId(): string | null {
  return currentId;
}

export function stopSpeakPlayback(): void {
  playGeneration += 1;
  stopBrowserSpeaking();
  releaseAudio();
  notify(null);
}

function playBrowserFallback(text: string, id: string): void {
  if (!isSpeechSynthesisSupported()) {
    notify(null);
    return;
  }
  speakText(text);
  notify(id);
  const check = window.setInterval(() => {
    if (!window.speechSynthesis.speaking) {
      window.clearInterval(check);
      if (currentId === id) {
        notify(null);
      }
    }
  }, 250);
}

/**
 * Play text aloud. Uses Piper on the API; falls back to browser TTS on failure.
 */
export async function playSpeakText(text: string, id: string): Promise<void> {
  const trimmed = text.trim();
  if (!trimmed) return;

  stopSpeakPlayback();
  const generation = playGeneration;
  notify(id);

  try {
    const blob = await api.speak(trimmed);
    if (generation !== playGeneration) return;

    const url = URL.createObjectURL(blob);
    currentObjectUrl = url;
    const audio = new Audio(url);
    currentAudio = audio;

    audio.onended = () => {
      if (generation !== playGeneration) return;
      releaseAudio();
      notify(null);
    };
    audio.onerror = () => {
      if (generation !== playGeneration) return;
      releaseAudio();
      playBrowserFallback(trimmed, id);
    };

    await audio.play();
  } catch (err) {
    if (generation !== playGeneration) return;
    releaseAudio();
    // Auth / hard failures: still try local browser TTS so Play stays useful offline-client.
    if (err instanceof ApiError && err.status === 401) {
      notify(null);
      throw err;
    }
    playBrowserFallback(trimmed, id);
  }
}

export function toggleSpeakText(text: string, id: string): Promise<void> {
  if (currentId === id) {
    stopSpeakPlayback();
    return Promise.resolve();
  }
  return playSpeakText(text, id);
}
