/**
 * Minimal History-API router.
 *
 * CCMS needs a handful of routes, protected-route redirects and query-string
 * state. A small in-house router avoids adding a dependency (react-router v6
 * currently carries an open-redirect advisory, GHSA-wrjc-x8rr-h8h6) and only
 * ever navigates to same-origin, app-internal paths.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

export interface RouterLocation {
  pathname: string;
  search: string;
  state: unknown;
}

export interface NavigateOptions {
  replace?: boolean;
  state?: unknown;
}

type NavigateFn = (to: string, options?: NavigateOptions) => void;

interface RouterContextValue {
  location: RouterLocation;
  navigate: NavigateFn;
}

const RouterContext = createContext<RouterContextValue | null>(null);

/**
 * Accepts only app-internal paths such as "/complaints?page=2".
 * Rejects protocol-relative ("//evil"), backslash ("/\\evil") and absolute URLs.
 */
export function isSafeInternalPath(value: unknown): value is string {
  if (typeof value !== 'string' || value.length === 0 || value.length > 2048) return false;
  if (!value.startsWith('/')) return false;
  if (value.startsWith('//') || value.startsWith('/\\')) return false;
  if (/[\u0000-\u001f\\]/.test(value)) return false;
  return true;
}

function readLocation(): RouterLocation {
  return {
    pathname: window.location.pathname || '/',
    search: window.location.search,
    state: window.history.state?.usr ?? null,
  };
}

export function RouterProvider({ children }: { children: React.ReactNode }) {
  const [location, setLocation] = useState<RouterLocation>(readLocation);

  useEffect(() => {
    const onPop = () => setLocation(readLocation());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const navigate = useCallback<NavigateFn>((to, options = {}) => {
    const target = isSafeInternalPath(to) ? to : '/';
    const historyState = { usr: options.state ?? null };
    if (options.replace) {
      window.history.replaceState(historyState, '', target);
    } else {
      window.history.pushState(historyState, '', target);
    }
    setLocation(readLocation());
    // New page: move to top unless only the query string changed.
    if (!options.replace) window.scrollTo({ top: 0 });
  }, []);

  const value = useMemo(() => ({ location, navigate }), [location, navigate]);
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

function useRouter(): RouterContextValue {
  const ctx = useContext(RouterContext);
  if (!ctx) throw new Error('Router hooks must be used inside <RouterProvider>');
  return ctx;
}

export function useLocation(): RouterLocation {
  return useRouter().location;
}

export function useNavigate(): NavigateFn {
  return useRouter().navigate;
}

/** Match "/complaints/:id" style patterns. Returns params or null. */
export function matchPath(pattern: string, pathname: string): Record<string, string> | null {
  const clean = (p: string) => (p.length > 1 ? p.replace(/\/+$/, '') : p);
  const patternParts = clean(pattern).split('/');
  const pathParts = clean(pathname).split('/');
  if (patternParts.length !== pathParts.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < patternParts.length; i++) {
    const pp = patternParts[i];
    const segment = pathParts[i];
    if (pp.startsWith(':')) {
      if (!segment) return null;
      try {
        params[pp.slice(1)] = decodeURIComponent(segment);
      } catch {
        return null;
      }
    } else if (pp !== segment) {
      return null;
    }
  }
  return params;
}

export function Navigate({ to, replace = true, state }: { to: string; replace?: boolean; state?: unknown }) {
  const navigate = useNavigate();
  useEffect(() => {
    navigate(to, { replace, state });
  }, [navigate, to, replace, state]);
  return null;
}

type LinkProps = Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & {
  to: string;
  replace?: boolean;
  state?: unknown;
};

export const Link = React.forwardRef<HTMLAnchorElement, LinkProps>(function Link(
  { to, replace, state, onClick, ...rest },
  ref,
) {
  const navigate = useNavigate();
  const href = isSafeInternalPath(to) ? to : '/';
  const handleClick = (event: React.MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      rest.target === '_blank'
    ) {
      return;
    }
    event.preventDefault();
    navigate(href, { replace, state });
  };
  return <a ref={ref} href={href} onClick={handleClick} {...rest} />;
});

/** Read and update URL query parameters (used to keep list filters across refresh). */
export function useSearchParams(): [URLSearchParams, (next: Record<string, string | null>) => void] {
  const { location, navigate } = useRouter();
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const update = useCallback(
    (next: Record<string, string | null>) => {
      const merged = new URLSearchParams(location.search);
      for (const [key, value] of Object.entries(next)) {
        if (value === null || value === '') merged.delete(key);
        else merged.set(key, value);
      }
      const qs = merged.toString();
      navigate(`${location.pathname}${qs ? `?${qs}` : ''}`, { replace: true });
    },
    [location.pathname, location.search, navigate],
  );
  return [params, update];
}
