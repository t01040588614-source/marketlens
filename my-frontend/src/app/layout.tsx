import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ReactQueryProvider } from "@/lib/queryClient";
import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import AppShell from "@/components/layout/AppShell";
import AuthSessionLayer from "@/components/auth/AuthSessionLayer";
import { CRITICAL_LAYOUT_CSS } from "@/lib/criticalStyles";
import { brand } from "@/config/brand";
import { getSiteUrl } from "@/lib/siteUrl";
import { pageTitle, rootSiteDescription } from "@/lib/seo";
import {
  buildRenderPublicApiBaseFromEnv,
  buildRenderPublicWsFromEnv,
} from "@/lib/apiBase";

export const metadata: Metadata = {
  metadataBase: new URL(getSiteUrl()),
  applicationName: brand.name,
  title: {
    default: pageTitle(brand.tagline),
    template: "%s",
  },
  description: rootSiteDescription,
  keywords: [
    "주식",
    "실시간 시세",
    "KOSPI",
    "KOSDAQ",
    "미국 주식",
    "차트",
    "금융 뉴스",
    "경제 캘린더",
    "포트폴리오",
    brand.name,
  ],
  authors: [{ name: brand.name }],
  creator: brand.name,
  formatDetection: {
    email: false,
    telephone: false,
  },
  appleWebApp: {
    capable: true,
    title: brand.name,
    statusBarStyle: "black-translucent",
  },
  openGraph: {
    type: "website",
    locale: "ko_KR",
    siteName: brand.name,
    title: pageTitle(brand.tagline),
    description: rootSiteDescription,
    images: [
      {
        url: "/og-marketlens.svg",
        width: 1200,
        height: 630,
        alt: pageTitle(brand.tagline),
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: pageTitle(brand.tagline),
    description: rootSiteDescription,
    images: ["/og-marketlens.svg"],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1419" },
  ],
};

const themeInitScript = `(function(){try{var flag='investing-ui-20260929';if(!localStorage.getItem(flag)){localStorage.setItem('stock-dashboard-theme','light');localStorage.setItem(flag,'1');}var k='stock-dashboard-theme';var m=localStorage.getItem(k);var t=m==='dark'?'dark':'light';document.documentElement.setAttribute('data-theme',t);document.documentElement.style.colorScheme=t;}catch(e){document.documentElement.setAttribute('data-theme','light');}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const renderApiBase = buildRenderPublicApiBaseFromEnv();
  const renderWsUrl = buildRenderPublicWsFromEnv();
  /* Render 배포일 때만 값이 생김 — 빌드 때 굳은 NEXT_PUBLIC_* 대신 서버 env 로 API 주소를 브라우저에 알려 줌 */
  const toScriptJson = (v: string) => JSON.stringify(v).replace(/</g, "\\u003c");
  const renderRuntimeScript =
    renderApiBase && renderWsUrl
      ? `(function(){window.__ML_API_BASE=${toScriptJson(renderApiBase)};window.__ML_WS_URL=${toScriptJson(renderWsUrl)};})();`
      : "";

  return (
    <html lang="ko" suppressHydrationWarning>
      <head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
          crossOrigin="anonymous"
        />
        <style id="critical-layout" dangerouslySetInnerHTML={{ __html: CRITICAL_LAYOUT_CSS }} />
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        {renderRuntimeScript ? (
          <script dangerouslySetInnerHTML={{ __html: renderRuntimeScript }} />
        ) : null}
      </head>
      <body>
        <ReactQueryProvider>
          <ThemeProvider>
            <AuthProvider>
              <AuthSessionLayer>
                <AppShell>{children}</AppShell>
              </AuthSessionLayer>
            </AuthProvider>
          </ThemeProvider>
        </ReactQueryProvider>
      </body>
    </html>
  );
}
