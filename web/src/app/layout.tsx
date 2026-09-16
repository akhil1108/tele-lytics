import type { Metadata } from "next";

import "@/styles/globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Tele-lytics",
  description:
    "Call recording insight for contact centres: transcripts, tone, sentiment, tasks and satisfaction.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
