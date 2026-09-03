import { afterEach, describe, expect, it, vi } from 'vitest';
import viteConfig from '../../vite.config.js';
import { request } from '../services/api';

describe('separate Vite/frontend runtime', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('runs on port 5173 and proxies relative API paths to FastAPI', () => {
    expect(viteConfig.server).toMatchObject({
      host: '127.0.0.1', port: 5173, strictPort: true,
      proxy: { '/api': 'http://127.0.0.1:8000' },
    });
  });

  it('uses a relative API URL so Vite can proxy authenticated requests', async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ ok: true }),
    });
    vi.stubGlobal('fetch', fetch);

    await expect(request('/student/dashboard', { token: 'token' }))
      .resolves.toEqual({ ok: true });
    expect(fetch).toHaveBeenCalledWith('/api/student/dashboard', expect.objectContaining({
      headers: { Authorization: 'Bearer token' },
    }));
  });
});
