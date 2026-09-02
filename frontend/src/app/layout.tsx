import type { Metadata } from "next";
import { JetBrains_Mono, Public_Sans } from "next/font/google";
import { headers } from "next/headers";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { Providers } from "@/lib/query-provider";
import { OG_IMAGE, SITE_URL } from "@/lib/site";

const publicSans = Public_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  // Absolute URLs for the share card; without this Next falls back to the
  // *.vercel.app deployment host.
  metadataBase: new URL(SITE_URL),
  title: "Heimdall Claims",
  description:
    "AI-assisted claim pre-checks and insurance appeal automation for small practices",
  // The favicon sits on the browser's tab strip, which follows the OS colour
  // scheme rather than the in-app theme toggle, so the media query keys on
  // prefers-color-scheme. Three sizes per theme let the browser pick the
  // one matching its pixel density instead of resampling.
  icons: {
    icon: (["light", "dark"] as const).flatMap((theme) =>
      [16, 32, 48].map((size) => ({
        url: `/favicon-${theme}-${size}.png`,
        type: "image/png",
        sizes: `${size}x${size}`,
        media: `(prefers-color-scheme: ${theme})`,
      })),
    ),
    // iOS ignores prefers-color-scheme for home-screen icons; the dark tile
    // matches the app's default theme.
    apple: "/apple-touch-icon.png",
  },
  openGraph: { images: [OG_IMAGE] },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Set by src/proxy.ts; the inline theme script below must carry it or the
  // nonce-based CSP blocks it.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${publicSans.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* Apply the theme before paint to avoid a flash. Dark is the default
            for everyone — including first-time visitors and browsers that ask
            for light — unless this visitor has explicitly toggled to light. */}
        <script
          nonce={nonce}
          dangerouslySetInnerHTML={{
            __html: `try{if(localStorage.getItem('heimdall_theme')!=='light'){document.documentElement.classList.add('dark')}}catch(e){document.documentElement.classList.add('dark')}`,
          }}
        />
        <Providers>
          <AuthProvider>{children}</AuthProvider>
        </Providers>
      </body>
    </html>
  );
}
