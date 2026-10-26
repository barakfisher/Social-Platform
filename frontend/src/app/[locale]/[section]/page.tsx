import { notFound } from "next/navigation";
import { Dashboard } from "@/components/dashboard";
import { locales, sections, type Locale } from "@/lib/i18n";
export default async function Page({
  params,
}: {
  params: Promise<{ locale: string; section: string }>;
}) {
  const { locale, section } = await params;
  if (
    !locales.includes(locale as Locale) ||
    !sections.includes(section as (typeof sections)[number])
  )
    notFound();
  return <Dashboard locale={locale as Locale} section={section} />;
}
