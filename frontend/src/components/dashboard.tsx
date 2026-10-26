"use client";
import Link from "next/link";
import { History as DraftHistory } from "@/components/history";
import { CreatePost } from "@/components/create-post";
import { KnowledgeBase } from "@/components/knowledge-base";
import { BrandEditor } from "@/components/brand-editor";
import { useEffect } from "react";
import {
  Fingerprint,
  BookOpen,
  PenLine,
  History,
  Sprout,
  ArrowUpRight,
  Languages,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { copy, sections, type Locale } from "@/lib/i18n";
import { cn } from "@/lib/utils";
const icons = [Fingerprint, BookOpen, PenLine, History];
export function Dashboard({
  locale,
  section,
}: {
  locale: Locale;
  section: string;
}) {
  const t = copy[locale];
  const index = sections.indexOf(section as (typeof sections)[number]);
  const titles = [
    t.brandTitle,
    t.knowledgeTitle,
    t.createTitle,
    t.historyTitle,
  ];
  const descriptions = [
    t.brandBody,
    t.knowledgeBody,
    t.createBody,
    t.historyBody,
  ];
  const Icon = icons[index];
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === "he" ? "rtl" : "ltr";
    document.cookie = `locale=${locale};path=/;max-age=31536000;SameSite=Lax`;
  }, [locale]);
  return (
    <div dir={locale === "he" ? "rtl" : "ltr"} className="min-h-screen lg:flex">
      <aside className="flex flex-col border-b border-border bg-card p-6 lg:min-h-screen lg:w-64 lg:shrink-0 lg:border-b-0 lg:border-e">
        <Link
          href={`/${locale}/brand`}
          className="flex items-center gap-3 font-semibold"
        >
          <span className="rounded-xl bg-primary p-2 text-white">
            <Sprout size={22} />
          </span>
          {t.product}
        </Link>
        <p className="mb-8 mt-7 text-xs font-medium text-muted-foreground">
          {t.workspace}
        </p>
        <nav
          aria-label={locale === "he" ? "ניווט ראשי" : "Main navigation"}
          className="grid grid-cols-2 gap-2 lg:grid-cols-1"
        >
          {sections.map((s, i) => {
            const NavIcon = icons[i];
            return (
              <Link
                key={s}
                href={`/${locale}/${s}`}
                aria-current={s === section ? "page" : undefined}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-3 text-sm transition-colors hover:bg-muted",
                  s === section
                    ? "bg-primary/10 font-semibold text-primary"
                    : "text-muted-foreground",
                )}
              >
                <NavIcon size={18} />
                {t.nav[i]}
              </Link>
            );
          })}
        </nav>
        <p className="mt-auto hidden pt-16 text-xs leading-5 text-muted-foreground lg:block">
          {t.help}
        </p>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex items-center justify-between gap-4 border-b border-border bg-card px-6 py-4 lg:px-10">
          <span className="text-sm font-medium">{t.nav[index]}</span>
          <Button variant="outline" size="sm" asChild>
            <Link
              href={`/${locale === "en" ? "he" : "en"}/${section}`}
              aria-label={t.language}
            >
              <Languages size={16} />
              {locale === "en" ? "עברית" : "English"}
            </Link>
          </Button>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-10 lg:px-12 lg:py-14">
          <p className="text-xs font-semibold tracking-widest text-primary">
            {t.eyebrow}
          </p>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">
            {t.title}
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">
            {t.subtitle}
          </p>
          <div className="mt-7 inline-flex rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground">
            {t.phase}
          </div>
          {section === "brand" ? (
            <BrandEditor locale={locale} />
          ) : section === "knowledge" ? (
            <KnowledgeBase locale={locale} />
          ) : section === "create" ? (
            <CreatePost locale={locale} />
          ) : section === "history" ? (
            <DraftHistory locale={locale} />
          ) : (
            <section
              aria-labelledby="section-title"
              className="mt-10 rounded-2xl border border-border bg-card p-7 sm:p-10"
            >
              <div className="mb-6 inline-flex rounded-xl bg-primary/10 p-3 text-primary">
                <Icon size={26} />
              </div>
              <h2 id="section-title" className="text-2xl font-semibold">
                {titles[index]}
              </h2>
              <p className="mt-3 max-w-xl leading-7 text-muted-foreground">
                {descriptions[index]}
              </p>
              <p className="mt-7 text-sm text-muted-foreground">{t.upcoming}</p>
            </section>
          )}
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            {sections.slice(0, 3).map((s, i) => {
              const CardIcon = icons[i];
              return (
                <Link
                  key={s}
                  href={`/${locale}/${s}`}
                  className="group rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/50"
                >
                  <div className="flex items-center justify-between">
                    <CardIcon size={19} className="text-primary" />
                    <ArrowUpRight
                      size={16}
                      className="text-muted-foreground rtl:-scale-x-100"
                    />
                  </div>
                  <h3 className="mt-5 font-medium">{t.nav[i]}</h3>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">
                    {descriptions[i]}
                  </p>
                </Link>
              );
            })}
          </div>
        </main>
      </div>
    </div>
  );
}
