import { initOpenNextCloudflareForDev } from "@opennextjs/cloudflare";

// Lets `next dev` read Cloudflare bindings (none yet — this app talks to the
// API over plain fetch) without needing `wrangler dev` during local work.
initOpenNextCloudflareForDev();

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: false },
};

export default nextConfig;
