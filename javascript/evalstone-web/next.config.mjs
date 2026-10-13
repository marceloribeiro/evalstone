/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  // Self-contained server bundle for the self-hosted deploy (rsync + systemd).
  output: "standalone",
};

export default config;
