export type UserRole = "user" | "station_admin" | "system_admin";

export type AuthenticatedUser = {
  id: string;
  email: string;
  username: string;
  full_name: string;
  phone: string | null;
  role: UserRole;
  created_at: string;
};

export type LoginInput = {
  identifier: string;
  password: string;
};

export type ChangePasswordInput = {
  current_password: string;
  new_password: string;
};

export type RegistrationInput = {
  email: string;
  username: string;
  password: string;
  full_name: string;
  phone: string | null;
};

export type TokenResponse = {
  access_token: string;
  token_type: "Bearer";
  expires_in: number;
  user: AuthenticatedUser;
};
