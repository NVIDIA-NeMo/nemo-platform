// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  initGetRequest,
  initPostRequest,
  addCsrfToRequestHeaders,
  extractCsrfFromResponseHeaders,
  setLastCsrfToken,
  CSRF_HEADER_NAME,
} from '@studio/util/csrf';

let testCount: number = 1;
let token: number = 0;

async function mockCsrfMiddleware(request: RequestInit): Promise<Response> {
  // CSRF Middleware skips validation on GET requests
  if (request.method !== 'GET') {
    // validate token
    const requestHeaders = new Headers(request.headers);
    if (requestHeaders.get(CSRF_HEADER_NAME) == null) {
      const response: Response = new Response(null, {
        status: 403,
        statusText: `No CSRF Token found in '${CSRF_HEADER_NAME}' header`,
      });
      // CSRF Middleware sends back new token on error also
      response.headers.append(CSRF_HEADER_NAME, `${token++}`);
      return response;
    }
    if (requestHeaders.get(CSRF_HEADER_NAME) !== `${token - 1}`) {
      const response: Response = new Response(null, {
        status: 403,
        statusText: `Invalid CSRF Token found in '${CSRF_HEADER_NAME}' header`,
      });
      // CSRF Middleware sends back new token on error also
      response.headers.append(CSRF_HEADER_NAME, `${token++}`);
      return response;
    }
  }

  const response: Response = new Response(null, {
    status: 200,
    statusText: 'OK',
  });
  response.headers.append(CSRF_HEADER_NAME, `${token++}`);

  return response;
}

// mocks helpers#fetchWithCsrf
async function fetchWithCsrfMock(request: RequestInit): Promise<Response> {
  const reqHeaders = addCsrfToRequestHeaders(request?.headers);
  const response: Response = await mockCsrfMiddleware({
    ...request,
    headers: reqHeaders,
  });
  extractCsrfFromResponseHeaders(response.headers);
  return response;
}

describe('fetchWithCSRF', () => {
  it(`Test fetch with csrf utils #${testCount++}`, async () => {
    // First request is not GET - should get invalidated
    await expect(fetchWithCsrfMock(initPostRequest())).resolves.toHaveProperty('status', 403);
  });

  it(`Test fetch with csrf utils #${testCount++}`, async () => {
    // second request is not GET - should get validated, since got a new token from last http error
    await expect(fetchWithCsrfMock(initPostRequest())).resolves.toHaveProperty('status', 200);
  });

  it(`Test fetch with csrf utils #${testCount++}`, async () => {
    await expect(fetchWithCsrfMock(initGetRequest())).resolves.toHaveProperty('status', 200);
  });

  it(`Test fetch with csrf utils #${testCount++}`, async () => {
    await expect(fetchWithCsrfMock(initPostRequest())).resolves.toHaveProperty('status', 200);
  });

  it(`Test fetch with csrf utils #${testCount++}`, async () => {
    setLastCsrfToken('');
    // Test with invalid CSRF token value in GET request - CSRF skips GET requests
    await expect(fetchWithCsrfMock(initGetRequest())).resolves.toHaveProperty('status', 200);
  });

  it('Uses custom CORS options if provided', async () => {
    const requestWithCustomOptions: RequestInit = {
      ...initPostRequest(),
      mode: 'no-cors',
    };

    await expect(fetchWithCsrfMock(requestWithCustomOptions)).resolves.toHaveProperty(
      'status',
      200
    );
  });
});

describe('getLastCsrfToken', () => {
  it('returns the current CSRF token value', async () => {
    const { getLastCsrfToken, setLastCsrfToken } = await import('@studio/util/csrf');
    setLastCsrfToken('test-token-123');
    expect(getLastCsrfToken()).toBe('test-token-123');
  });

  it('returns empty string when no token has been set', async () => {
    const { getLastCsrfToken, setLastCsrfToken } = await import('@studio/util/csrf');
    setLastCsrfToken('');
    expect(getLastCsrfToken()).toBe('');
  });
});

describe('fetchWithCsrf', () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch);
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends CSRF header in request', async () => {
    const { fetchWithCsrf, setLastCsrfToken, CSRF_HEADER_NAME } = await import('@studio/util/csrf');
    setLastCsrfToken('my-csrf-token');

    const responseHeaders = new Headers();
    responseHeaders.set(CSRF_HEADER_NAME, 'new-token');
    mockFetch.mockResolvedValue(new Response(null, { status: 200, headers: responseHeaders }));

    await fetchWithCsrf('/api/test');

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit;
    expect((calledOptions.headers as Record<string, string>)[CSRF_HEADER_NAME]).toBe(
      'my-csrf-token'
    );
  });

  it('extracts CSRF token from response headers', async () => {
    const { fetchWithCsrf, setLastCsrfToken, getLastCsrfToken, CSRF_HEADER_NAME } =
      await import('@studio/util/csrf');
    setLastCsrfToken('old-token');

    const responseHeaders = new Headers();
    responseHeaders.set(CSRF_HEADER_NAME, 'response-token-456');
    mockFetch.mockResolvedValue(new Response(null, { status: 200, headers: responseHeaders }));

    await fetchWithCsrf('/api/test');

    expect(getLastCsrfToken()).toBe('response-token-456');
  });

  it('uses GET method by default', async () => {
    const { fetchWithCsrf, setLastCsrfToken, CSRF_HEADER_NAME } = await import('@studio/util/csrf');
    setLastCsrfToken('');

    const responseHeaders = new Headers();
    responseHeaders.set(CSRF_HEADER_NAME, 'token');
    mockFetch.mockResolvedValue(new Response(null, { status: 200, headers: responseHeaders }));

    await fetchWithCsrf('/api/test');

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit;
    expect(calledOptions.method).toBe('GET');
  });

  it('returns the response from fetch', async () => {
    const { fetchWithCsrf, setLastCsrfToken, CSRF_HEADER_NAME } = await import('@studio/util/csrf');
    setLastCsrfToken('');

    const responseHeaders = new Headers();
    responseHeaders.set(CSRF_HEADER_NAME, 'token');
    mockFetch.mockResolvedValue(new Response('body', { status: 201, headers: responseHeaders }));

    const response = await fetchWithCsrf('/api/test');
    expect(response.status).toBe(201);
  });
});
