import type { Metadata } from "next";
import "./globals.css";
import { Banner } from "@/components/Banner";

export const metadata: Metadata = {
  title: "Clinical Documentation Assistant",
  description: "Audio to FHIR, clinician in the loop. Synthetic data only.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Banner />
        {children}
      </body>
    </html>
  );
}
