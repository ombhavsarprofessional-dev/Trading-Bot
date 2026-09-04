/**
 * Cloudflare Worker: Reverse Proxy & API Gateway for NSE Swing Bot
 *
 * This Worker sits on your Cloudflare edge domain and seamlessly proxies
 * /api/* requests to your Python backend (VPS or Cloudflare Tunnel),
 * preventing CORS issues and securing your backend IP address.
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Set this environment variable in Cloudflare Worker settings:
    // BACKEND_URL = "https://api.your-vps-domain.com" or "https://your-tunnel.cfargotunnel.com"
    const BACKEND_URL = env.BACKEND_URL || "http://127.0.0.1:5000";

    // Route API requests to the Python backend
    if (url.pathname.startsWith("/api/")) {
      const targetUrl = `${BACKEND_URL}${url.pathname}${url.search}`;
      
      const newRequest = new Request(targetUrl, {
        method: request.method,
        headers: request.headers,
        body: request.body,
        redirect: "follow",
      });

      // Forward request to backend
      const response = await fetch(newRequest);
      
      // Inject standard CORS headers
      const corsHeaders = new Headers(response.headers);
      corsHeaders.set("Access-Control-Allow-Origin", "*");
      corsHeaders.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
      corsHeaders.set("Access-Control-Allow-Headers", "Content-Type, Authorization");

      if (request.method === "OPTIONS") {
        return new Response(null, { headers: corsHeaders });
      }

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: corsHeaders,
      });
    }

    // Pass through non-API requests (or static assets)
    return fetch(request);
  },
};
