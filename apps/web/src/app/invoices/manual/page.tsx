import { Suspense } from "react";
import ManualEntryForm from "@/components/ManualEntryForm";

export const metadata = { title: "Faida - Enter invoice" };

export default function ManualEntryPage() {
  return (
    <Suspense
      fallback={
        <div aria-busy="true" className="rounded-md border border-ink/10 bg-paper p-6">
          <p role="status" className="text-sm text-stone">
            Loading
          </p>
        </div>
      }
    >
      <ManualEntryForm />
    </Suspense>
  );
}
