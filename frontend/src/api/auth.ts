import {
  clearAuthentication,
  requestJson,
  restoreAccessTokenOnce,
  setAccessToken,
} from "./client";
import type {
  AuthenticatedUser,
  ChangePasswordInput,
  LoginInput,
  RegistrationInput,
  TokenResponse,
} from "../types/auth";

let bootstrapPromise: Promise<AuthenticatedUser> | null = null;

export async function login(input: LoginInput): Promise<AuthenticatedUser> {
  const session = await requestJson<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
    retryOnUnauthorized: false,
  });
  setAccessToken(session.access_token);
  bootstrapPromise = Promise.resolve(session.user);
  return session.user;
}

export async function register(
  input: RegistrationInput,
): Promise<AuthenticatedUser> {
  await requestJson<{user: AuthenticatedUser}>("/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
    retryOnUnauthorized: false,
  });
  return login({identifier: input.email, password: input.password});
}

export function restoreCurrentUser(): Promise<AuthenticatedUser> {
  if (!bootstrapPromise) {
    bootstrapPromise = restoreAccessTokenOnce().then(() => getCurrentUser());
  }
  return bootstrapPromise;
}

export async function getCurrentUser(): Promise<AuthenticatedUser> {
  const response = await requestJson<{user: AuthenticatedUser}>("/auth/me", {
    authenticated: true,
  });
  return response.user;
}

export async function logout(): Promise<void> {
  try {
    await requestJson<void>("/auth/logout", {
      method: "POST",
      authenticated: true,
      retryOnUnauthorized: false,
    });
  } finally {
    clearAuthentication();
    bootstrapPromise = null;
  }
}

export async function logoutAllDevices(): Promise<void> {
  try {
    await requestJson<void>("/auth/logout-all", {
      method: "POST",
      authenticated: true,
      retryOnUnauthorized: false,
    });
  } finally {
    clearAuthentication();
    bootstrapPromise = null;
  }
}

export async function changePassword(
  input: ChangePasswordInput,
): Promise<void> {
  await requestJson<void>("/auth/change-password", {
    method: "POST",
    authenticated: true,
    body: JSON.stringify(input),
  });
  clearAuthentication();
  bootstrapPromise = null;
}
