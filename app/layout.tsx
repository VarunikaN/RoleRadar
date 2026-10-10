import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RoleRadar",
  description: "Match a resume to live job listings in any field using only skills that appear in both the resume and the listing.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
