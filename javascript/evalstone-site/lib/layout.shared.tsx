import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { Logo } from '@/components/common/logo';
import { githubUrl } from './shared';

const SECTIONS = [
  ['Problem', 'problem'],
  ['Evals', 'what-are-evals'],
  ['How it helps', 'how-it-helps'],
  ['How it works', 'how-it-works'],
  ['Model', 'model-or-not'],
  ['Learn', 'learn'],
] as const;

/**
 * The homepage header walks the page's own sections (one-page navigation) and offers
 * one entry into the docs. Docs pages get the sections as one "Home" menu, plus the
 * docs areas with their active state, so the sidebar is not seven anchors deep.
 */
export function baseOptions(layout: 'home' | 'docs' = 'home'): BaseLayoutProps {
  const sections = SECTIONS.map(([text, id]) => ({ text, url: `/#${id}`, active: 'none' as const }));
  return {
    nav: {
      title: <Logo />,
      url: '/',
    },
    links:
      layout === 'home'
        ? [...sections, { text: 'Docs', url: '/docs', active: 'nested-url' }]
        : [
            { type: 'menu', text: 'Home', items: sections },
            { text: 'Learn evals', url: '/docs/learn', active: 'nested-url' },
            { text: 'Evalstone', url: '/docs/evalstone', active: 'nested-url' },
            { text: 'Guides', url: '/docs/guides/quickstart', active: 'nested-url' },
            { text: 'Reference', url: '/docs/reference/cli', active: 'nested-url' },
          ],
    githubUrl,
  };
}
