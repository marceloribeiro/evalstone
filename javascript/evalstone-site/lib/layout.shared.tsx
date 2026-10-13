import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { Logo } from '@/components/common/logo';
import { githubUrl } from './shared';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: <Logo />,
      url: '/',
    },
    links: [
      { text: 'Learn evals', url: '/docs/learn', active: 'nested-url' },
      { text: 'How it works', url: '/docs/evalstone/how-it-works', active: 'url', on: 'nav' },
      { text: 'Evalstone', url: '/docs/evalstone', active: 'url' },
      { text: 'Guides', url: '/docs/guides/quickstart', active: 'nested-url', on: 'nav' },
      { text: 'Reference', url: '/docs/reference/cli', active: 'nested-url', on: 'nav' },
    ],
    githubUrl,
  };
}
