import { Suspense } from "react";
import InvoiceList from "@/components/InvoiceList";

export const metadata = { title: "Faida - Invoices" };

export default function InvoicesPage() {
  return (
    <Suspense
      fallback={
        <div aria-busy="true" className="rounded-md border border-ink/10 bg-paper p-6">
          <p role="status" className="text-sm text-stone">
            Loading invoices
          </p>
        </div>
      }
    >
      <InvoiceList />
    </Suspense>
  );
}
