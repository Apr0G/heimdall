import type { Metadata } from "next";
import { JetBrains_Mono, Public_Sans } from "next/font/google";
import { cookies, headers } from "next/headers";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { ThemeFavicon } from "@/components/theme-favicon";
import { Providers } from "@/lib/query-provider";
import { OG_IMAGE, SITE_URL } from "@/lib/site";
import {
  FAVICON_SIZES,
  THEME_COOKIE,
  THEME_KEY,
  faviconHref,
} from "@/lib/theme";

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

export async function generateMetadata(): Promise<Metadata> {
  // The tab icon follows the site theme, not the OS one. Safari only honours
  // the icon in the initial HTML, so the server picks the set from the theme
  // cookie (dark is the site default); ThemeFavicon keeps it in step after.
  const theme =
    (await cookies()).get(THEME_COOKIE)?.value === "light" ? "light" : "dark";
  return {
    // Absolute URLs for the share card; without this Next falls back to the
    // *.vercel.app deployment host.
    metadataBase: new URL(SITE_URL),
    title: "Heimdall Claims",
    description:
      "AI-assisted claim pre-checks and insurance appeal automation for small practices",
    icons: {
      icon: FAVICON_SIZES.map((size) => ({
        url: faviconHref(theme, size),
        type: "image/png",
        sizes: `${size}x${size}`,
      })),
      // The dark tile matches the app's default theme.
      apple: "/apple-touch-icon.png",
    },
    openGraph: { images: [OG_IMAGE] },
  };
}

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
            __html: `try{if(localStorage.getItem('${THEME_KEY}')!=='light'){document.documentElement.classList.add('dark')}}catch(e){document.documentElement.classList.add('dark')}`,
          }}
        />
        <ThemeFavicon />
        <Providers>
          <AuthProvider>{children}</AuthProvider>
        </Providers>
      </body>
    </html>
  );
}
