import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { COOPERATIVE_NAME } from "@/lib/branding";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  applicationName: COOPERATIVE_NAME,
  title: {
    default: `${COOPERATIVE_NAME} Manager`,
    template: `%s · ${COOPERATIVE_NAME} Manager`,
  },
  description: "Cooperative society member, loan, and deduction management",
  icons: {
    icon: [
      { url: "/icons/favicon.svg", type: "image/svg+xml" },
      { url: "/icons/favicon-64.png", sizes: "64x64", type: "image/png" },
    ],
    apple: "/icons/koperra-app-icon-1024.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#082b59",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}
