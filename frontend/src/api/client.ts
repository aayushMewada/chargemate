type ValidationDetail = {
  field?: string;
  location?: Array<string | number>;
  message?: string;
};

type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    details?: ValidationDetail[];
  };
};

type TokenEnvelope = {
  access_token: string;
};

type RequestOptions = RequestInit & {
  authenticated?: boolean;
  retryOnUnauthorized?: boolean;
};

let accessToken: string | null = null;
let refreshPromise: Promise<TokenEnvelope> | null = null;
let initialRestorePromise: Promise<TokenEnvelope> | null = null;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ValidationDetail[];

  constructor(
    status: number,
    code: string,
    message: string,
    details: ValidationDetail[] = [],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function clearAuthentication(): void {
  accessToken = null;
  initialRestorePromise = null;
}

export async function requestJson<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    authenticated = false,
    retryOnUnauthorized = true,
    headers: suppliedHeaders,
    ...fetchOptions
  } = options;
  const headers = new Headers(suppliedHeaders);
  headers.set("Accept", "application/json");

  if (fetchOptions.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (authenticated && accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`/api${path}`, {
    ...fetchOptions,
    credentials: "include",
    headers,
  });

  if (response.status === 401 && authenticated && retryOnUnauthorized) {
    await refreshAccessToken();
    return requestJson<T>(path, {
      ...options,
      retryOnUnauthorized: false,
    });
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return requestJson<T>(path, {signal});
}

export function restoreAccessTokenOnce(): Promise<TokenEnvelope> {
  if (!initialRestorePromise) {
    initialRestorePromise = refreshAccessToken();
  }
  return initialRestorePromise;
}

export async function refreshAccessToken(): Promise<TokenEnvelope> {
  if (!refreshPromise) {
    refreshPromise = requestJson<TokenEnvelope>("/auth/refresh", {
      method: "POST",
      retryOnUnauthorized: false,
    })
      .then((tokens) => {
        setAccessToken(tokens.access_token);
        return tokens;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

async function toApiError(response: Response): Promise<ApiError> {
  const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
  return new ApiError(
    response.status,
    body.error?.code ?? "request_failed",
    body.error?.message ?? "ChargeMate could not complete the request.",
    body.error?.details ?? [],
  );
}
