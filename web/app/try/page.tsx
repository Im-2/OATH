import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { TryClient } from "@/components/try/TryClient";

export const metadata: Metadata = {
  title: "Try · OATH",
  description: "Try to fake an oath and watch the hash break, or ask OATH about a trade idea in a sandbox where no money moves.",
};

export default function TryPage() {
  return (
    <main className="subpage grain relative min-h-svh">
      <Nav active="/try" />
      <TryClient />
    </main>
  );
}
