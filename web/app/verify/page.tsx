import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { VerifyClient } from "@/components/verify/VerifyClient";

export const metadata: Metadata = {
  title: "Verify · OATH",
  description: "Every oath OATH has ever taken, checked against Solana. Re-run the whole verification in your browser from a public RPC. No account, no trust.",
};

export default function VerifyPage() {
  return (
    <main className="subpage grain relative min-h-svh">
      <Nav active="/verify" />
      <VerifyClient />
    </main>
  );
}
