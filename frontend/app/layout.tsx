import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MemBridge — Mémoire partagée pour agents IA",
  description:
    "Serveur MCP de mémoire : −75 % de tokens, qualité maintenue. Benchmark live naïf vs MemBridge.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
