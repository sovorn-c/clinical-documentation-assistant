// Minimal line-level diff (LCS) for the AI-draft vs human-edit view.
// Dependency-free; sufficient for short SOAP notes.

export type DiffLine = {
  type: "same" | "add" | "remove";
  text: string;
};

export function diffLines(a: string, b: string): DiffLine[] {
  const la = a.split("\n");
  const lb = b.split("\n");
  const m = la.length;
  const n = lb.length;

  // LCS length table
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      dp[i][j] = la[i] === lb[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (la[i] === lb[j]) {
      out.push({ type: "same", text: la[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ type: "remove", text: la[i] });
      i++;
    } else {
      out.push({ type: "add", text: lb[j] });
      j++;
    }
  }
  while (i < m) out.push({ type: "remove", text: la[i++] });
  while (j < n) out.push({ type: "add", text: lb[j++] });
  return out;
}

export function flattenNote(note: {
  subjective: { text: string }[];
  objective: { text: string }[];
  assessment: { text: string }[];
  plan: { text: string }[];
}): string {
  const sections: Array<[string, { text: string }[]]> = [
    ["SUBJECTIVE", note.subjective],
    ["OBJECTIVE", note.objective],
    ["ASSESSMENT", note.assessment],
    ["PLAN", note.plan],
  ];
  const lines: string[] = [];
  for (const [heading, claims] of sections) {
    lines.push(heading + ":");
    for (const c of claims) lines.push(`- ${c.text}`);
  }
  return lines.join("\n");
}
