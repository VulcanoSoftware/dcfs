import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  basePath: "/dcfs",
  assetPrefix: "/dcfs",
  images: {
    loader: "custom",
    loaderFile: "image-loader.js",
  },
};

export default nextConfig;
