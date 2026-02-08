import type { Metadata } from "next";
import { Noto_Sans_SC, Noto_Serif_SC } from "next/font/google";
import { Agentation } from "agentation";

import "./globals.css";

import { Providers } from "@/app/providers";
import { TopNav } from "@/components/shell/TopNav";

const sans = Noto_Sans_SC({
  weight: ["300", "400", "600"],
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap"
});

const serif = Noto_Serif_SC({
  weight: ["600", "900"],
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap"
});

export const metadata: Metadata = {
  title: "永久投资组合",
  description: "Permanent Portfolio Tracker"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className={`${sans.variable} ${serif.variable}`}>
        <Providers>
          <div className="pp-page">
            <TopNav />
            <main className="mx-auto w-full max-w-[1120px] px-3 pb-12 pt-4">{children}</main>
            <footer className="mx-auto w-full max-w-[1120px] px-3 pb-8 text-xs text-ink/55">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>永久投资组合追踪</div>
                <div className="pp-mono">/health · /api/v2/*</div>
              </div>
            </footer>
            {process.env.NODE_ENV === "development" && (
              <Agentation endpoint={process.env.NEXT_PUBLIC_AGENTATION_ENDPOINT ?? "http://127.0.0.1:4747"} />
            )}
          </div>
        </Providers>
      </body>
    </html>
  );
}
