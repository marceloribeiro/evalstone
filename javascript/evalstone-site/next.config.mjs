import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  // Self-contained server bundle for the self-hosted deploy (rsync + systemd).
  output: 'standalone',
};

export default withMDX(config);
