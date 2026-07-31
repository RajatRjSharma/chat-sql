import { deriveChart } from "@/lib/chart";
import type { ChatTurn } from "@/lib/types";

export type SessionBrief = {
  /** Spoken / copyable plain text */
  text: string;
  questionCount: number;
  okCount: number;
  failedCount: number;
  bullets: string[];
};

const MAX_BULLETS = 6;
const MAX_ANSWER_CHARS = 140;

function firstSentence(text: string): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  const match = cleaned.match(/^(.+?[.!?])(\s|$)/);
  const sentence = match ? match[1] : cleaned;
  if (sentence.length <= MAX_ANSWER_CHARS) return sentence;
  return `${sentence.slice(0, MAX_ANSWER_CHARS - 1).trimEnd()}…`;
}

function truncateQuestion(question: string, max = 56): string {
  const q = question.replace(/\s+/g, " ").trim();
  if (q.length <= max) return q;
  return `${q.slice(0, max - 1).trimEnd()}…`;
}

/**
 * Build a short session digest from existing turn answers (no extra LLM call).
 */
export function buildSessionBrief(turns: ChatTurn[]): SessionBrief {
  const questionCount = turns.length;
  const ok = turns.filter((t) => t.status === "ok" && t.answer.trim());
  const failedCount = turns.filter((t) => t.status === "failed").length;
  const okCount = ok.length;

  const bullets = ok.slice(-MAX_BULLETS).map((turn) => {
    const answer = firstSentence(turn.answer);
    const q = truncateQuestion(turn.question);
    return answer ? `${q} → ${answer}` : q;
  });

  const headerParts = [
    `${questionCount} question${questionCount === 1 ? "" : "s"}`,
    `${okCount} answered`,
  ];
  if (failedCount > 0) {
    headerParts.push(`${failedCount} failed`);
  }

  const lines: string[] = [];
  if (questionCount === 0) {
    lines.push("No questions in this session yet.");
  } else {
    lines.push(`Session so far: ${headerParts.join(" · ")}.`);
    for (const bullet of bullets) {
      lines.push(`• ${bullet}`);
    }
    if (okCount > MAX_BULLETS) {
      const extra = okCount - MAX_BULLETS;
      lines.push(`• …and ${extra} earlier answer${extra === 1 ? "" : "s"}.`);
    }
  }

  return {
    text: lines.join("\n"),
    questionCount,
    okCount,
    failedCount,
    bullets,
  };
}

export type ChartableTurn = {
  turn: ChatTurn;
  index: number;
};

export function listChartableTurns(turns: ChatTurn[]): ChartableTurn[] {
  const out: ChartableTurn[] = [];
  turns.forEach((turn, index) => {
    if (turn.status !== "ok" || turn.rows.length === 0) return;
    if (deriveChart(turn.columns, turn.rows).kind === "none") return;
    out.push({ turn, index });
  });
  return out;
}

/** Stable id so the carousel can reset when the chart set changes. */
export function chartCarouselIdentity(items: ChartableTurn[]): string {
  return items.map((item) => item.turn.id).join("|");
}
