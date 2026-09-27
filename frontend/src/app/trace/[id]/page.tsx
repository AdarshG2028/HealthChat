import type { Metadata } from "next";

import { TraceView } from "@/components/decision-trace/trace-view";
import { SiteHeader } from "@/components/layout/site-header";

export const metadata: Metadata = { title: "Decision Trace — Carewise", robots: { index: false } };

export default async function TracePage(props: PageProps<"/trace/[id]">) {
  const { id } = await props.params;
  return (
    <>
      <SiteHeader compact />
      <main>
        <TraceView id={id} />
      </main>
    </>
  );
}
