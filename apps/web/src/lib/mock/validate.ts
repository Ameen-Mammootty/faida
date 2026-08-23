/**
 * Mock-side mirror of the server's deterministic checks (apps/api
 * extraction/validate.py, contract C4), so a PATCH in mock mode re-validates
 * exactly the way the real API will. Same tolerances, same result shapes,
 * same notes.
 *
 * One deliberate alignment with pipeline.py rather than validate.py: the
 * pipeline stamps `snapped` onto persisted checks without recomputing status
 * ("an unsnapped line keeps its green arithmetic" while the catalog
 * self-builds), so here status is green iff the arithmetic passed.
 */

import { abs, add, dec, fmt, lte, maxDec, mul, sub, ZERO, type Dec } from "./decimal";
import type { CheckStatus, Confidence, DocumentCheck, FieldStatus, LineCheck } from "../types";

const LINE_TOLERANCE_ABS = dec("0.05")!;
const LINE_TOLERANCE_PCT = dec("0.005")!;
const DOC_TOLERANCE_ABS = dec("0.10")!;

export interface CheckableLine {
  qty: string | null;
  unit_price: string | null;
  line_total: string | null;
  snapped: boolean | null;
}

export interface CheckableTotals {
  subtotal: string | null;
  tax: string | null;
  total: string | null;
}

function parse(value: string | null): Dec | null {
  return value === null ? null : dec(value);
}

export function checkLine(index: number, line: CheckableLine): LineCheck {
  const qty = parse(line.qty);
  const unitPrice = parse(line.unit_price);
  const lineTotal = parse(line.line_total);
  if (qty === null || unitPrice === null || lineTotal === null) {
    return {
      line_index: index,
      arith: "indeterminate",
      expected: null,
      extracted: null,
      snapped: line.snapped,
      status: "amber",
    };
  }
  const expected = mul(qty, unitPrice);
  const tolerance = maxDec(LINE_TOLERANCE_ABS, mul(LINE_TOLERANCE_PCT, abs(lineTotal)));
  if (lte(abs(sub(expected, lineTotal)), tolerance)) {
    return {
      line_index: index,
      arith: "passed",
      expected: null,
      extracted: null,
      snapped: line.snapped,
      status: "green",
    };
  }
  return {
    line_index: index,
    arith: "failed",
    expected: fmt(expected),
    extracted: line.line_total,
    snapped: line.snapped,
    status: "amber",
  };
}

export function checkDocument(
  lines: Pick<CheckableLine, "line_total">[],
  lineChecks: LineCheck[],
  totals: CheckableTotals,
): DocumentCheck {
  const notes: string[] = [];

  const missingTotals = lines.filter((line) => line.line_total === null).length;
  let lineSum: Dec | null = null;
  if (missingTotals > 0) {
    notes.push(`line_total missing on ${missingTotals} line(s); line sum unknown`);
  } else {
    lineSum = lines.reduce((sum, line) => add(sum, parse(line.line_total)!), ZERO);
  }

  let tax = parse(totals.tax);
  if (tax === null) {
    tax = ZERO;
    notes.push("tax missing; treated as 0");
  }

  const subtotal = parse(totals.subtotal);
  let subtotalCheck: CheckStatus;
  if (subtotal === null || lineSum === null) {
    subtotalCheck = "indeterminate";
  } else if (lte(abs(sub(subtotal, lineSum)), DOC_TOLERANCE_ABS)) {
    subtotalCheck = "passed";
  } else {
    subtotalCheck = "failed";
  }

  const total = parse(totals.total);
  let arith: CheckStatus;
  let expected: string | null = null;
  let extracted: string | null = null;
  if (total === null || lineSum === null) {
    arith = "indeterminate";
  } else if (lte(abs(sub(add(lineSum, tax), total)), DOC_TOLERANCE_ABS)) {
    arith = "passed";
  } else {
    arith = "failed";
    expected = fmt(add(lineSum, tax));
    extracted = totals.total;
  }

  const failedLines = lineChecks.filter((check) => check.arith === "failed").length;
  if (failedLines > 0 && arith === "passed") {
    notes.push(`${failedLines} line check(s) failed; totals stay amber`);
  }

  const green = arith === "passed" && subtotalCheck !== "failed" && failedLines === 0;
  const status: FieldStatus = green ? "green" : "amber";
  return {
    arith,
    subtotal_check: subtotalCheck,
    line_sum: lineSum === null ? null : fmt(lineSum),
    expected,
    extracted,
    notes,
    status,
  };
}

export function deriveConfidence(document: DocumentCheck, lineChecks: LineCheck[]): Confidence {
  return { document, lines: lineChecks.map((check) => check.status) };
}
