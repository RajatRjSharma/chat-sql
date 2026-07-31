"use client";

import { Volume2, VolumeX, Loader2 } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  getPlayingSpeakId,
  stopSpeakPlayback,
  subscribeSpeakPlayback,
  toggleSpeakText,
} from "@/lib/speak-playback";
import { cn } from "@/lib/cn";

type SpeakButtonProps = {
  text: string;
  className?: string;
  /** Stable id so only one summary plays at a time; defaults to React useId. */
  speakId?: string;
};

export function SpeakButton({ text, className, speakId }: SpeakButtonProps) {
  const autoId = useId();
  const id = speakId ?? autoId;
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    return subscribeSpeakPlayback((activeId) => {
      setPlaying(activeId === id);
      if (activeId === id) {
        setLoading(false);
      }
    });
  }, [id]);

  useEffect(() => {
    return () => {
      if (getPlayingSpeakId() === id) {
        stopSpeakPlayback();
      }
    };
  }, [id]);

  if (!text.trim()) return null;

  async function handleClick() {
    setError(null);
    if (playing) {
      stopSpeakPlayback();
      return;
    }
    setLoading(true);
    try {
      await toggleSpeakText(text, id);
    } catch {
      setError("Could not play audio");
      setPlaying(false);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className={cn("h-11 min-w-11 px-2 sm:h-8 sm:min-w-0", className)}
      onClick={() => {
        void handleClick();
      }}
      disabled={loading}
      aria-label={playing ? "Stop reading answer" : "Play answer aloud"}
      title={error ?? (playing ? "Stop" : "Play summary")}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : playing ? (
        <VolumeX className="h-4 w-4" />
      ) : (
        <Volume2 className="h-4 w-4" />
      )}
    </Button>
  );
}
