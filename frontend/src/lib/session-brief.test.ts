import { describe, expect, it } from "vitest";
import {
  buildSessionBrief,
  chartCarouselIdentity,
  listChartableTurns,
} from "@/lib/session-brief";
import type { ChatTurn } from "@/lib/types";

function turn(
  partial: Partial<ChatTurn> & Pick<ChatTurn, "id" | "question" | "answer" | "status">,
): ChatTurn {
  return {
    columns: [],
    rows: [],
    sql: null,
    attempts: 1,
    source_metadata: null,
    ...partial,
  };
}

describe("buildSessionBrief", () => {
  it("describes an empty session", () => {
    const brief = buildSessionBrief([]);
    expect(brief.questionCount).toBe(0);
    expect(brief.text).toContain("No questions");
  });

  it("summarizes successful turns into brief bullets", () => {
    const brief = buildSessionBrief([
      turn({
        id: "1",
        question: "What is total revenue?",
        answer: "Total revenue is $1.2M this quarter. More detail follows.",
        status: "ok",
      }),
      turn({
        id: "2",
        question: "Top region?",
        answer: "North leads with 42% of sales.",
        status: "ok",
      }),
    ]);
    expect(brief.okCount).toBe(2);
    expect(brief.bullets).toHaveLength(2);
    expect(brief.text).toContain("2 questions");
    expect(brief.text).toContain("Total revenue is $1.2M this quarter.");
    expect(brief.text).toContain("North leads");
  });

  it("counts failures and caps bullets", () => {
    const turns = Array.from({ length: 8 }, (_, i) =>
      turn({
        id: String(i),
        question: `Q${i}?`,
        answer: `Answer ${i} is ready.`,
        status: "ok",
      }),
    );
    turns.push(
      turn({
        id: "fail",
        question: "Broken?",
        answer: "Could not run SQL",
        status: "failed",
      }),
    );
    const brief = buildSessionBrief(turns);
    expect(brief.failedCount).toBe(1);
    expect(brief.bullets).toHaveLength(6);
    expect(brief.text).toContain("earlier answer");
  });
});

describe("listChartableTurns", () => {
  it("keeps only turns that can chart", () => {
    const items = listChartableTurns([
      turn({
        id: "a",
        question: "By region",
        answer: "North is ahead.",
        status: "ok",
        columns: ["region", "revenue"],
        rows: [
          { region: "North", revenue: 10 },
          { region: "South", revenue: 5 },
        ],
      }),
      turn({
        id: "b",
        question: "Empty",
        answer: "No rows",
        status: "ok",
        columns: ["x"],
        rows: [],
      }),
    ]);
    expect(items).toHaveLength(1);
    expect(items[0].turn.id).toBe("a");
    expect(chartCarouselIdentity(items)).toBe("a");
  });
});
