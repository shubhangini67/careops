import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";
import { DashboardProvider } from "@/context/DashboardContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { ChatSessionProvider } from "@/context/ChatSessionContext";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";
import FloatingChatWidget from "@/components/chat/FloatingChatWidget";

export const metadata: Metadata = {
  title: "CareOps AI — Hospital Operations Copilot",
  description: "Agentic hospital operations and policy copilot for capacity, staffing, and supply planning",
};

// Runs before React hydrates so the correct theme class is on <html> for the
// very first paint -- without this, the page would flash the wrong theme
// every load while ThemeProvider's effect catches up.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("careops-theme");
    var dark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (dark) document.documentElement.classList.add("dark");
  } catch (e) {}
})();
`;

// suppressHydrationWarning below: THEME_INIT_SCRIPT intentionally mutates
// <html>'s class before React hydrates, so server and client legitimately
// disagree on className for one frame -- the standard, safe pattern for
// avoiding a theme flash.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="flex min-h-screen">
        {/* next/script with beforeInteractive, placed in <body> per Next's
            own documented pattern -- Next hoists it into the real document
            <head> and guarantees it runs before hydration regardless of
            where it's written in JSX. Placing it inside a manually-authored
            <head> (App Router's <head> is otherwise reserved for the
            Metadata API) is what triggered React's "encountered a script
            tag" dev warning -- <body> is the documented placement. */}
        <Script id="theme-init" strategy="beforeInteractive">
          {THEME_INIT_SCRIPT}
        </Script>
        <ThemeProvider>
          <AuthProvider>
            <DashboardProvider>
              <ChatSessionProvider>
                <Sidebar />
                <div className="flex min-w-0 flex-1 flex-col">
                  <TopBar />
                  <main className="flex-1">{children}</main>
                </div>
                <FloatingChatWidget />
              </ChatSessionProvider>
            </DashboardProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
