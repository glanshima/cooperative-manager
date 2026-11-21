import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import BrandingProvider from "@/components/branding/BrandingProvider";
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
    // Resolved per request so the tab follows the logo uploaded in Settings;
    // the route falls back to the static Koperra icon.
    icon: [{ url: "/api/favicon" }],
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
      <body>
        <BrandingProvider>{children}</BrandingProvider>
      </body>
    </html>
  );
}
