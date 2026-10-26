import { redirect } from "next/navigation";
import { cookies } from "next/headers";
export default async function Home() {
  const locale = (await cookies()).get("locale")?.value === "he" ? "he" : "en";
  redirect(`/${locale}/brand`);
}
