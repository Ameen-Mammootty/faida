"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { parseCsv, type CsvResult } from "@/lib/csv";

/**
 * The file-choose-and-read phase both loaders share (M8 WP-83, lifted out of
 * `MenuLoader`): the hidden input, the re-pick fix, reading the bytes,
 * `parseCsv`, and the one file-level sentence when it refuses. The grids stay
 * in their own components - this owns nothing about what the rows mean.
 *
 * The re-pick fix is the loop itself: a consultant fixes two cells in the
 * sheet, saves over it, and uploads the same filename again. A file input
 * fires no change event for the same filename twice, so its value is cleared
 * on every pick.
 */

export type ParsedCsv = Extract<CsvResult, { ok: true }>;

export interface UseCsvFileOptions {
  /** Runs the moment a file is picked, before its bytes are read - the place
   * to clear the previous grid so a stale one is never shown under
   * "Reading the file". */
  onPick?: (file: File) => void;
  /** Runs with the parsed rows. Throwing an Error puts its message on the
   * file, exactly like a `parseCsv` refusal - one place for every sentence a
   * file can be refused with. */
  onParsed: (file: File, parsed: ParsedCsv) => Promise<void> | void;
}

export function useCsvFile({ onPick, onParsed }: UseCsvFileOptions) {
  const [fileName, setFileName] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function pick(file: File | null) {
    if (!file) return;
    setFileName(file.name);
    setFileError(null);
    setReading(true);
    onPick?.(file);
    try {
      const parsed = parseCsv(await file.text());
      if (!parsed.ok) {
        setFileError(parsed.error);
        return;
      }
      await onParsed(file, parsed);
    } catch (error) {
      setFileError(
        error instanceof Error ? error.message : "That file could not be read as a CSV.",
      );
    } finally {
      setReading(false);
    }
  }

  const inputProps = {
    ref: inputRef,
    type: "file" as const,
    accept: ".csv,text/csv",
    className: "sr-only",
    onChange: (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0] ?? null;
      event.target.value = "";
      void pick(file);
    },
  };

  return { fileName, fileError, setFileError, reading, inputProps, pick };
}
