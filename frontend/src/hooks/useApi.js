import { useEffect, useState } from 'react';

export function useApi(load, deps = []) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    let active = true;
    setState({ loading: true, data: null, error: null });
    load().then((data) => active && setState({ loading: false, data, error: null }))
      .catch((error) => active && setState({ loading: false, data: null, error }));
    return () => { active = false; };
  // Callers explicitly provide dependencies for request parameters.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}
