// Authentication API client

const API_BASE = 'http://localhost:8080';

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: number;
  email: string;
  is_active: boolean;
  created_at: string;
}

class AuthApi {
  private tokenKey = 'redbook_token';

  getToken(): string | null {
    return localStorage.getItem(this.tokenKey);
  }

  setToken(token: string): void {
    localStorage.setItem(this.tokenKey, token);
  }

  removeToken(): void {
    localStorage.removeItem(this.tokenKey);
  }

  async login(request: LoginRequest): Promise<AuthResponse> {
    const formData = new URLSearchParams();
    formData.append('username', request.username);
    formData.append('password', request.password);

    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData,
    });

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Login failed');
    }

    const data = await res.json();
    this.setToken(data.access_token);
    return data;
  }

  async register(request: RegisterRequest): Promise<User> {
    const res = await fetch(`${API_BASE}/api/auth/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Registration failed');
    }

    return res.json();
  }

  async getMe(): Promise<User> {
    const token = this.getToken();
    if (!token) {
      throw new Error('Not logged in');
    }

    const res = await fetch(`${API_BASE}/api/auth/me`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });

    if (!res.ok) {
      this.removeToken();
      throw new Error('Failed to get user info');
    }

    return res.json();
  }

  logout(): void {
    this.removeToken();
  }

  isLoggedIn(): boolean {
    return !!this.getToken();
  }
}

export const authApi = new AuthApi();