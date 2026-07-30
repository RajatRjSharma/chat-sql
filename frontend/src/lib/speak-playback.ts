/**
 * Server TTS playback via Piper sentence stream (/api/voice/speak-stream).
 * Plays the first sentence as soon as it arrives; queues the rest.
 * Browser TTS only if the API fails (not for slowness).
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

const pendingBlobs: Blob[] = [];
let drainRunning = false;

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

function clearQueue() {
  pendingBlobs.length = 0;
  drainRunning = false;
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
  clearQueue();
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

function playBlob(blob: Blob, generation: number, id: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (generation !== playGeneration) {
      resolve();
      return;
    }
    releaseAudio();
    const url = URL.createObjectURL(blob);
    currentObjectUrl = url;
    const audio = new Audio(url);
    currentAudio = audio;
    notify(id);

    audio.onended = () => {
      releaseAudio();
      resolve();
    };
    audio.onerror = () => {
      releaseAudio();
      reject(new Error("Audio playback failed"));
    };

    void audio.play().catch(reject);
  });
}

async function drainQueue(generation: number, id: string): Promise<void> {
  if (drainRunning) return;
  drainRunning = true;
  try {
    while (generation === playGeneration) {
      const next = pendingBlobs.shift();
      if (!next) break;
      await playBlob(next, generation, id);
    }
  } finally {
    drainRunning = false;
    if (
      generation === playGeneration &&
      pendingBlobs.length === 0 &&
      !currentAudio
    ) {
      notify(null);
    }
  }
}

function enqueueBlob(blob: Blob, generation: number, id: string): void {
  if (generation !== playGeneration) return;
  pendingBlobs.push(blob);
  void drainQueue(generation, id).catch(() => {
    /* next chunk or stop handles recovery */
  });
}

/**
 * Play text aloud via Piper sentence stream. Browser TTS only on API failure.
 */
export async function playSpeakText(text: string, id: string): Promise<void> {
  const trimmed = text.trim();
  if (!trimmed) return;

  stopSpeakPlayback();
  const generation = playGeneration;
  notify(id);

  try {
    let received = 0;
    await api.speakStream(trimmed, (blob) => {
      received += 1;
      enqueueBlob(blob, generation, id);
    });

    if (generation !== playGeneration) return;

    if (received === 0) {
      throw new ApiError(502, "TTS stream returned no audio");
    }

    // Wait until the queue finishes playing (drain may still be running).
    while (
      generation === playGeneration &&
      (drainRunning || pendingBlobs.length > 0 || currentAudio)
    ) {
      await new Promise((r) => window.setTimeout(r, 100));
    }
  } catch (err) {
    if (generation !== playGeneration) return;
    clearQueue();
    releaseAudio();
    if (err instanceof ApiError && err.status === 401) {
      notify(null);
      throw err;
    }
    // Fail-only browser fallback — not used for slowness.
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
