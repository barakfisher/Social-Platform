import "./globals.css";
import { headers } from "next/headers";
export const metadata = {
  title: "Social Platform",
  description: "Your brand content studio",
};
export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = (await headers()).get("x-locale") === "he" ? "he" : "en";
  return (
    <html lang={locale} dir={locale === "he" ? "rtl" : "ltr"}>
      <body>{children}</body>
    </html>
  );
}
