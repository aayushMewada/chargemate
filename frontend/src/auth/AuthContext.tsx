import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  changePassword as changePasswordRequest,
  login as loginRequest,
  logout as logoutRequest,
  logoutAllDevices as logoutAllDevicesRequest,
  register as registerRequest,
  restoreCurrentUser,
} from "../api/auth";
import type {
  AuthenticatedUser,
  ChangePasswordInput,
  LoginInput,
  RegistrationInput,
} from "../types/auth";

type AuthStatus = "loading" | "authenticated" | "anonymous";

type AuthContextValue = {
  status: AuthStatus;
  user: AuthenticatedUser | null;
  login: (input: LoginInput) => Promise<void>;
  register: (input: RegistrationInput) => Promise<void>;
  logout: () => Promise<void>;
  logoutAllDevices: () => Promise<void>;
  changePassword: (input: ChangePasswordInput) => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({children}: {children: ReactNode}) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthenticatedUser | null>(null);

  useEffect(() => {
    let active = true;

    restoreCurrentUser()
      .then((restoredUser) => {
        if (!active) return;
        setUser(restoredUser);
        setStatus("authenticated");
      })
      .catch(() => {
        if (!active) return;
        setUser(null);
        setStatus("anonymous");
      });

    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      login: async (input) => {
        const authenticatedUser = await loginRequest(input);
        setUser(authenticatedUser);
        setStatus("authenticated");
      },
      register: async (input) => {
        const authenticatedUser = await registerRequest(input);
        setUser(authenticatedUser);
        setStatus("authenticated");
      },
      logout: async () => {
        try {
          await logoutRequest();
        } finally {
          setUser(null);
          setStatus("anonymous");
        }
      },
      logoutAllDevices: async () => {
        try {
          await logoutAllDevicesRequest();
        } finally {
          setUser(null);
          setStatus("anonymous");
        }
      },
      changePassword: async (input) => {
        await changePasswordRequest(input);
        setUser(null);
        setStatus("anonymous");
      },
    }),
    [status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return context;
}
