const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function req(path, { method = "GET", body, headers = {} } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Erro ${res.status}`);
  return data;
}

export const api = {
  config: () => req("/config"),
  products: () => req("/products"),
  orders: () => req("/orders"),
  order: (id) => req(`/orders/${id}`),
  createOrder: (items) => req("/orders", { method: "POST", body: { items } }),
  pay: (id, key) => req(`/orders/${id}/pay`, { method: "POST", headers: { "Idempotency-Key": key } }),
  ship: (id) => req(`/orders/${id}/ship`, { method: "POST" }),
};
