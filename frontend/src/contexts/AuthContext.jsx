import PropTypes from 'prop-types';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { getToken, getStoredEmail, setToken, clearToken, fetchMe, refreshToken } from '../utils/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setTokenState] = useState(() => getToken());
  const [email, setEmail] = useState(() => getStoredEmail());
  const [role, setRole] = useState(null);
  const [roll, setRoll] = useState(null);
  const [name, setName] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const user = await fetchMe();
      if (cancelled) return;
      if (user) {
        setRole(user.role || 'user');
        if (user.email) setEmail(user.email);
        if (user.roll) setRoll(user.roll); else setRoll(null);
        if (user.name) setName(user.name); else setName(null);
      }
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const onStorage = (e) => {
      if (e.key === 'plagioscale_access_token') {
        setTokenState(getToken());
      }
      if (e.key === 'plagioscale_user_email') {
        setEmail(getStoredEmail());
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const login = useCallback((newToken, newEmail) => {
    setToken(newToken, newEmail);
    setTokenState(newToken);
    setEmail(newEmail);
  }, []);

  // Re-fetch profile (role/roll/name) — call right after login/signup so the
  // whole app sees fresh identity without a page reload.
  const refreshProfile = useCallback(async () => {
    const user = await fetchMe();
    if (user) {
      setRole(user.role || 'user');
      if (user.email) setEmail(user.email);
      if (user.roll) setRoll(user.roll); else setRoll(null);
      if (user.name) setName(user.name); else setName(null);
    }
    return user;
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setTokenState('');
    setEmail('');
    setRole(null);
    setRoll(null);
    setName(null);
  }, []);

  const refresh = useCallback(async () => {
    const newToken = await refreshToken();
    if (newToken) {
      setTokenState(newToken);
    }
    return newToken;
  }, []);

  const value = {
    token,
    email,
    role,
    roll,
    name,
    loading,
    isLoggedIn: !!token,
    login,
    logout,
    refresh,
    refreshProfile,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

AuthProvider.propTypes = {
  children: PropTypes.node,
};
