import IngredientDetail from "@/components/IngredientDetail";

export const metadata = { title: "Faida - Raw material" };

export default async function MaterialPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <IngredientDetail ingredientId={id} />;
}
