import { RootProvider } from 'fumadocs-ui/provider/next';
import './global.css';
import { Inter, JetBrains_Mono } from 'next/font/google';
import type { Metadata } from 'next';
import { siteUrl } from '@/lib/shared';

const inter = Inter({ subsets: ['latin'], variable: '--font-sans' });
const mono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono' });

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: 'Evalstone — the evals layer for LLM products',
    template: '%s · Evalstone',
  },
  description:
    'Open-source evals for any LLM-based project: a Python library, a learning center, a check center, an API and an MCP server. Learn what evals are, then ship with them.',
  openGraph: {
    siteName: 'Evalstone',
    type: 'website',
    url: siteUrl,
  },
};

export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable} ${inter.className}`} suppressHydrationWarning>
      <body className="flex flex-col min-h-screen">
        <RootProvider>{children}</RootProvider>
      </body>
    </html>
  );
}
