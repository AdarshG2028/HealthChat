import type { Metadata } from "next";
import { Suspense } from "react";

import { ChatExperience } from "@/components/chat/chat-experience";
import { SiteHeader } from "@/components/layout/site-header";

export const metadata: Metadata = { title: "Your check — Carewise" };

export default function ChatPage() {
  return (
    <>
      <SiteHeader compact />
      <main>
        <h1 className="sr-only">Health check conversation</h1>
        <Suspense>
          <ChatExperience />
        </Suspense>
      </main>
    </>
  );
}
