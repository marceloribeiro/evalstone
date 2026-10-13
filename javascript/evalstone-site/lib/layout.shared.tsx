import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { Logo } from '@/components/common/logo';
import { githubUrl } from './shared';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: <Logo />,
      url: '/',
    },
    // One-page navigation: every link is a section of the homepage, plus one entry into
    // the docs. On the homepage they sit in the header (and in the phone menu); on docs
    // pages fumadocs lists them at the top of the sidebar, above the docs tree.
    links: [
      { text: 'The problem', url: '/#problem', active: 'none' },
      { text: 'What evals are', url: '/#what-are-evals', active: 'none' },
      { text: 'How it helps', url: '/#how-it-helps', active: 'none' },
      { text: 'How it works', url: '/#how-it-works', active: 'none' },
      { text: 'The model', url: '/#model-or-not', active: 'none' },
      { text: 'Learn', url: '/#learn', active: 'none' },
      { text: 'Docs', url: '/docs', active: 'nested-url' },
    ],
    githubUrl,
  };
}
