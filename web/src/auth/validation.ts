import { errorText } from "./api";

export type AuthFields = { username: string; password: string; display_name: string };
export type AuthField = keyof AuthFields;
export type AuthFieldErrors = Partial<Record<AuthField, string>>;

// Mirrors app/auth/passwords.py. Server validation remains authoritative.
// Python len() counts Unicode code points; HTML maxLength counts UTF-16 units.
export function validateAuth(fields: AuthFields, register: boolean): AuthFieldErrors {
  const errors: AuthFieldErrors = {};
  if (/\p{C}/u.test(fields.username) || !/^[A-Za-z0-9_-]{3,32}$/.test(fields.username.trim()))
    errors.username = errorText.invalid_username;
  const length = Array.from(fields.password).length;
  if (length < 10 || length > 128 || /\p{Cs}/u.test(fields.password) || new TextEncoder().encode(fields.password).length > 512)
    errors.password = errorText.invalid_password;
  if (register && (Array.from(fields.display_name.trim()).length < 1 || Array.from(fields.display_name.trim()).length > 32
      || /\p{C}/u.test(fields.display_name))) errors.display_name = errorText.invalid_display_name;
  return errors;
}

export function authErrorField(code: string): AuthField | undefined {
  if (code === "invalid_username" || code === "username_taken") return "username";
  if (code === "invalid_display_name") return "display_name";
  if (code === "invalid_password") return "password";
}
