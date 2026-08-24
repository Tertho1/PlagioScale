import PropTypes from 'prop-types';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export function RequireAuth({ children }) {
  const { isLoggedIn, loading } = useAuth();

  if (loading) return null;
  if (!isLoggedIn) return <Navigate to="/auth" replace />;
  return children;
}

export function RequireRole({ role, children }) {
  const { role: userRole, isLoggedIn, loading } = useAuth();

  if (loading) return null;
  if (!isLoggedIn) return <Navigate to="/auth" replace />;
  if (userRole !== role) return <Navigate to="/dashboard" replace />;
  return children;
}

RequireAuth.propTypes = {
  children: PropTypes.node,
};

RequireRole.propTypes = {
  role: PropTypes.string.isRequired,
  children: PropTypes.node,
};
