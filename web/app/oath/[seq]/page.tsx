import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { OathDetail } from "@/components/live/OathDetail";
import { Nav } from "@/components/Nav";

export async function generateMetadata({ params }: PageProps<"/oath/[seq]">): Promise<Metadata> {
  const { seq } = await params;
  return { title: `Oath #${seq} · OATH`, description: `Commit, trade, close and reveal of OATH's oath #${seq}, each linked to Solana.` };
}

export default async function OathPage({ params }: PageProps<"/oath/[seq]">) {
  const { seq } = await params;
  if (!/^[1-9][0-9]{0,8}$/.test(seq)) notFound();
  return (
    <main className="subpage grain relative min-h-svh">
      <Nav active="/live" />
      <OathDetail seq={Number(seq)} />
    </main>
  );
}
