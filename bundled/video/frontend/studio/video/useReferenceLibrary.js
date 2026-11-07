import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@lds/plugin-sdk';
import { createReferenceLibraryFeed } from './referenceLibrary';

export default function useReferenceLibrary({ kind, source, collection, query }) {
  const [state, setState] = useState({ items: [], sources: [], collections: [], loading: true, error: '', hasMore: false });
  const [search, setSearch] = useState(query);
  const [retry, setRetry] = useState(0);
  const feed = useRef(null);
  useEffect(() => { const timer = setTimeout(() => setSearch(query), 250); return () => clearTimeout(timer); }, [query]);
  useEffect(() => {
    const instance = createReferenceLibraryFeed(apiFetch, setState);
    feed.current = instance;
    return () => instance.dispose();
  }, []);
  useEffect(() => { feed.current?.query({ kind, source, collection, query: search }); }, [kind, source, collection, search, retry]);
  return { ...state, more: () => feed.current?.more(), retry: () => setRetry((n) => n + 1) };
}
