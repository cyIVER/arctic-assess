import { fileURLToPath } from "node:url";

// Static export: `NEXT_EXPORT=1 next build` writes static files to web/out for serving
// from an nginx web root. Leave unset for development (next dev) to retain /api proxying and hot reload.
const isExport = process.env.NEXT_EXPORT === "1";
// Vercel demo: the entire site uses mocks, with no backend or /api proxy required.
const isMock = process.env.NEXT_PUBLIC_MOCK === "1";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Prevent parent lockfiles from affecting root inference and asset paths.
  turbopack: { root: fileURLToPath(new URL(".", import.meta.url)) },
  reactCompiler: true,
  // Allow LAN IPs to access development resources (HMR); adjust as needed.
  // During development, allow any IPv4 origin to access /_next/* and HMR, including changing LAN IPs.
  // Note: Next disallows a bare "*" for security; use segment wildcards. "*.*.*.*" matches any IPv4 address.
  allowedDevOrigins: ["*.*.*.*"],
  compiler: {
    removeConsole: process.env.NODE_ENV === "production",
  },
  ...(isExport
    ? {
        // Static export: no Node runtime or image optimization; each route produces <route>/index.html.
        output: "export",
        images: { unoptimized: true },
        trailingSlash: true,
      }
    : isMock
      ? {
          // Vercel mock demo: no backend or /api proxy required.
          images: { unoptimized: true },
        }
      : {
          // Development: proxy /api/* to the Go backend (default :8787; override with AUTOPENTEST_API).
          async rewrites() {
            const backend = process.env.AUTOPENTEST_API ?? "http://localhost:8787";
            return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
          },
        }),
};

export default nextConfig;
