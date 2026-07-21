"use client";

import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";

type UploadFormProps = {
  onUploaded: (payload: {
    dataSourceId: string;
    dataSourceName: string;
    chunksEmbedded: number;
  }) => void;
};

type Phase = "idle" | "uploading" | "embedding" | "done";

const ACCEPT = ".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

export function UploadForm({ onUploaded }: UploadFormProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);

  function pickFile(next: File | null) {
    setError(null);
    setFile(next);
    if (next && !displayName.trim()) {
      setDisplayName(next.name.replace(/\.(csv|xlsx)$/i, ""));
    }
  }

  function onFileInput(event: ChangeEvent<HTMLInputElement>) {
    pickFile(event.target.files?.[0] ?? null);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    const dropped = event.dataTransfer.files?.[0] ?? null;
    if (dropped) pickFile(dropped);
  }

  async function handleUpload() {
    if (!file) {
      setError("Choose a CSV or Excel (.xlsx) file first.");
      return;
    }

    setError(null);
    setPhase("uploading");

    try {
      const uploaded = await api.uploadFile(file, displayName || undefined);
      setPhase("embedding");
      const embedded = await api.embedSchema(uploaded.data_source_id);
      setPhase("done");
      onUploaded({
        dataSourceId: uploaded.data_source_id,
        dataSourceName: uploaded.name,
        chunksEmbedded: embedded.chunks_embedded,
      });
    } catch (err) {
      setPhase("idle");
      setError(err instanceof ApiError ? err.detail : "Upload failed");
    }
  }

  const busy = phase === "uploading" || phase === "embedding";

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-[var(--bg-shell-elevated)]/80 p-8 shadow-[0_40px_80px_-40px_rgba(0,0,0,0.7)] backdrop-blur-sm animate-rise">
      <div
        aria-hidden
        className="pointer-events-none absolute -left-12 bottom-0 h-40 w-40 rounded-full bg-[#1d4ed8]/20 blur-3xl"
      />
      <div className="relative">
        <p className="font-[family-name:var(--font-display)] text-2xl tracking-tight text-[var(--text-on-dark)]">
          Upload CSV / Excel
        </p>
        <p className="mt-2 max-w-md text-sm leading-relaxed text-[var(--text-muted-dark)]">
          Load a spreadsheet into an isolated warehouse schema, index it for RAG,
          then ask questions like any connected source.
        </p>

        <div className="mt-8 space-y-5">
          <div>
            <Label className="text-[var(--text-muted-dark)]">Display name (optional)</Label>
            <Input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              disabled={busy}
              placeholder="Q1 sales export"
              className="border-white/10 bg-[var(--bg-shell)] text-[var(--text-on-dark)] placeholder:text-[var(--text-muted-dark)] focus:ring-[var(--accent)]/30"
            />
          </div>

          <div
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                inputRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => !busy && inputRef.current?.click()}
            className={cn(
              "cursor-pointer rounded-xl border border-dashed px-5 py-8 text-center transition-colors",
              dragOver
                ? "border-[var(--accent)] bg-[var(--accent)]/10"
                : "border-white/15 bg-[var(--bg-shell)]/60 hover:border-white/25",
              busy && "pointer-events-none opacity-50",
            )}
          >
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              className="hidden"
              disabled={busy}
              onChange={onFileInput}
            />
            <p className="text-sm text-[var(--text-on-dark)]">
              {file ? file.name : "Drop a file here, or click to browse"}
            </p>
            <p className="mt-2 text-xs text-[var(--text-muted-dark)]">
              {file
                ? `${(file.size / 1024).toFixed(1)} KB · .csv or .xlsx`
                : "Max 10 MB · first Excel sheet only"}
            </p>
          </div>

          {error ? (
            <p
              role="alert"
              className="rounded-md border border-[var(--error)]/30 bg-[var(--error)]/10 px-3 py-2 text-sm text-[#fecaca]"
            >
              {error}
            </p>
          ) : null}

          <div className="flex flex-col gap-3 pt-1 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-[var(--text-muted-dark)]">
              {phase === "uploading" && "Loading rows into the warehouse…"}
              {phase === "embedding" && "Indexing schema for RAG…"}
              {phase === "idle" && "Creates a read-only analytics source for chat."}
              {phase === "done" && "Ready."}
            </p>
            <Button
              type="button"
              size="lg"
              disabled={busy || !file}
              className="min-w-[180px]"
              onClick={() => void handleUpload()}
            >
              {busy ? "Working…" : "Upload & index"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
