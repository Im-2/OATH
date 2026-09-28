import type { Metadata } from "next";
import { LiveClient } from "@/components/live/LiveClient";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "Live · OATH",
  description: "Every oath OATH takes, as it happens: sealed commitments, trades, blocks, stand-asides and reveals, read from Solana.",
};

export default function LivePage() {
  return (
    <main className="subpage grain relative min-h-svh">
      <Nav active="/live" />
      <LiveClient />
    </main>
  );
}
