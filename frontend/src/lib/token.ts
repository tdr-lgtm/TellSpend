/**
 * Where the login token is kept between page loads.
 * The only code that touches localStorage for auth.
 */

const TOKEN_KEY = "tellspend.token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function saveToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}