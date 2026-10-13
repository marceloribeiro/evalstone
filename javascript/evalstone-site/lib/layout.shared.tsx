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
      { text: 'Evalstone', url: '/docs/evalstone', active: 'nested-url' },
    ],
    githubUrl,
  };
}
