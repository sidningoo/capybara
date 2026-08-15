import type { Metadata } from "next";
import "./globals.css";
import { ToastProvider } from "@/components/Toaster";

export const metadata: Metadata = {
  title: "Capybara · Trading Dashboard",
  description: "Monitoring and control UI for the Capybara autonomous paper-trading bot.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
