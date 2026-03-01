/** @type {import('next').NextConfig} */

/**
 * PageTutor AI - Next.js Configuration
 * Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
 *
 * Features:
 * - Image optimization (WebP conversion)
 * - Security headers
 * - API proxy to FastAPI backend
 * - SEO: sitemap, robots
 */

const nextConfig = {
  reactStrictMode: true,

  // Image optimization: convert to WebP, reduce bandwidth
  images: {
    domains: ['cdn.pagetutor.ai', 'localhost'],
    formats: ['image/webp', 'image/avif'],
    deviceSizes: [640, 750, 828, 1080, 1200, 1920],
    imageSizes: [16, 32, 48, 64, 96, 128, 256, 384],
    minimumCacheTTL: 60 * 60 * 24 * 30, // 30 days
  },

  // Experimental features
  experimental: {
    serverComponentsExternalPackages: [],
  },

  // Security headers (additional to backend CSP)
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          {
            key: 'Permissions-Policy',
            value: 'geolocation=(), microphone=(), camera=()',
          },
        ],
      },
    ];
  },

  // API proxy: forward /api calls to FastAPI backend
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/:path*`,
      },
    ];
  },

  // SEO: generate sitemap
  // Using next-sitemap (add to package.json if needed)
  
  // Compression
  compress: true,

  // Power by header removal
  poweredByHeader: false,

  // Output for Docker
  output: 'standalone',
};

module.exports = nextConfig;
