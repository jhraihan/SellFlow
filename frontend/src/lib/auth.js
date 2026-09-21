import { create } from "zustand";
import { api, readStoreId, readTokens, writeStoreId, writeTokens } from "./api";

export const useAuth = create((set, get) => ({
  user: null,
  stores: [],
  storeId: readStoreId() ? Number(readStoreId()) : null,
  capabilities: [],
  role: null,
  ready: false,

  async bootstrap() {
    if (!readTokens()?.access) {
      set({ ready: true });
      return;
    }
    try {
      const { data } = await api.get("/auth/me/");
      const stores = data.stores || [];
      const current =
        stores.find((s) => s.store_id === get().storeId) || stores[0] || null;

      if (current) writeStoreId(current.store_id);

      set({
        user: data.user,
        stores,
        storeId: current?.store_id ?? null,
        capabilities: current?.capabilities ?? [],
        role: current?.role ?? null,
        ready: true,
      });
    } catch {
      writeTokens(null);
      writeStoreId(null);
      set({ user: null, stores: [], storeId: null, ready: true });
    }
  },

  async login(email, password) {
    const { data } = await api.post("/auth/login/", { email, password });
    writeTokens({ access: data.access, refresh: data.refresh });

    const stores = data.stores || [];
    const current = stores[0] || null;
    if (current) writeStoreId(current.store_id);

    set({
      user: data.user,
      stores,
      storeId: current?.store_id ?? null,
      capabilities: current?.capabilities ?? [],
      role: current?.role ?? null,
      ready: true,
    });
    return { hasStore: Boolean(current) };
  },

  async register(payload) {
    const { data } = await api.post("/auth/register/", payload);
    writeTokens({ access: data.access, refresh: data.refresh });
    set({ user: data.user, stores: [], storeId: null, ready: true });
  },

  selectStore(storeId) {
    const membership = get().stores.find((s) => s.store_id === storeId);
    if (!membership) return;
    writeStoreId(storeId);
    set({
      storeId,
      capabilities: membership.capabilities || [],
      role: membership.role,
    });
  },

  setStores(stores) {
    const current =
      stores.find((s) => s.store_id === get().storeId) || stores[0] || null;
    if (current) writeStoreId(current.store_id);
    set({
      stores,
      storeId: current?.store_id ?? null,
      capabilities: current?.capabilities ?? [],
      role: current?.role ?? null,
    });
  },

  async logout() {
    const tokens = readTokens();
    try {
      if (tokens?.refresh) {
        await api.post("/auth/logout/", { refresh: tokens.refresh });
      }
    } catch {
      /* logging out locally is what matters */
    }
    writeTokens(null);
    writeStoreId(null);
    set({ user: null, stores: [], storeId: null, capabilities: [], role: null });
  },

  can(capability) {
    return get().capabilities.includes(capability);
  },
}));
