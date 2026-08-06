/**
 * Server TTS playback via Piper sentence stream (/api/voice/speak-stream).
 * Prefetch when an answer arrives so Play can start with buffered audio.
 * Browser TTS only if the API fails (not for slowness).
 */

import { ApiError, api } from "@/lib/api";
import {
  isSpeechSynthesisSupported,
  speakText,
  stopSpeaking as stopBrowserSpeaking,
} from "@/lib/speech";

type Listener = (playingId: string | null) => void;

type PrefetchState = {
  text: string;
  blobs: Blob[];
  done: boolean;
  error: unknown;
};

let currentAudio: HTMLAudioElement | null = null;
let currentObjectUrl: string | null = null;
let currentId: string | null = null;
let playGeneration = 0;
const listeners = new Set<Listener>();

const pendingBlobs: Blob[] = [];
let drainRunning = false;
let prefetch: PrefetchState | null = null;

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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
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

/**
 * Start synthesizing when a chat answer arrives so Play has less wait.
 * Does not start playback — the user must press Speak.
 */
export function prefetchSpeakText(text: string): void {
  const trimmed = text.trim();
  if (!trimmed) return;
  if (prefetch?.text === trimmed) return;

  if (prefetch) {
    prefetch.blobs.length = 0;
  }

  const state: PrefetchState = {
    text: trimmed,
    blobs: [],
    done: false,
    error: null,
  };
  prefetch = state;

  void api
    .speakStream(trimmed, (blob) => {
      if (prefetch !== state) return;
      state.blobs.push(blob);
    })
    .then(() => {
      if (prefetch === state) state.done = true;
    })
    .catch((err) => {
      if (prefetch !== state) return;
      state.error = err;
      state.done = true;
    });
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

async function waitForPlaybackDrain(generation: number): Promise<void> {
  while (
    generation === playGeneration &&
    (drainRunning || pendingBlobs.length > 0 || currentAudio)
  ) {
    await sleep(80);
  }
}

async function playFromPrefetch(
  state: PrefetchState,
  generation: number,
  id: string,
): Promise<void> {
  let idx = 0;
  let received = 0;

  while (generation === playGeneration && (!state.done || idx < state.blobs.length)) {
    if (idx < state.blobs.length) {
      enqueueBlob(state.blobs[idx], generation, id);
      idx += 1;
      received += 1;
      continue;
    }
    await sleep(40);
  }

  if (generation !== playGeneration) return;

  if (received === 0) {
    if (state.error) throw state.error;
    throw new ApiError(502, "TTS stream returned no audio");
  }

  await waitForPlaybackDrain(generation);
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
    if (prefetch?.text === trimmed) {
      await playFromPrefetch(prefetch, generation, id);
      return;
    }

    let received = 0;
    await api.speakStream(trimmed, (blob) => {
      received += 1;
      enqueueBlob(blob, generation, id);
    });

    if (generation !== playGeneration) return;

    if (received === 0) {
      throw new ApiError(502, "TTS stream returned no audio");
    }

    await waitForPlaybackDrain(generation);
  } catch (err) {
    if (generation !== playGeneration) return;
    clearQueue();
    releaseAudio();
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
