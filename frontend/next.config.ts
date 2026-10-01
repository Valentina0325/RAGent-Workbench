import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: '/api/rag', destination: 'http://localhost:8000/rag' },
      { source: '/api/function', destination: 'http://localhost:8000/function' },
      { source: '/api/plan', destination: 'http://localhost:8000/plan' },
      { source: '/api/upload-doc', destination: 'http://localhost:8000/upload-doc' },
      { source: '/api/kb/:path*', destination: 'http://localhost:8000/kb/:path*' },
      { source: '/api/chat/stream', destination: 'http://localhost:8000/chat/stream' },
      { source: '/api/csv-analyze', destination: 'http://localhost:8000/csv-analyze' },
      { source: '/api/csv-report', destination: 'http://localhost:8000/csv-report' },
      { source: '/api/kb/:name/doc-content', destination: 'http://localhost:8000/kb/:name/doc-content' },
    ];
  },
};

export default nextConfig;
