import InvoiceReview from "@/components/InvoiceReview";

export const metadata = { title: "Faida - Invoice review" };

export default async function InvoiceReviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <InvoiceReview id={id} />;
}
