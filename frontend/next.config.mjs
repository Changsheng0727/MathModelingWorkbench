/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  assetPrefix: "/static",
  images: {
    unoptimized: true,
  },
  reactStrictMode: false,
  generateBuildId: async () => "modeling-workbench-static",
};

export default nextConfig;
