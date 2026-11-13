import { useEffect, useMemo, useRef, useState } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { Elements, PaymentElement, useElements, useStripe } from "@stripe/react-stripe-js";
import { api } from "./api";
import "./styles.css";

const brl = (c) => (c / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const ROTULO = { pendente: "Pendente", pago: "Pago", enviado: "Enviado", recusado: "Recusado", estornado: "Estornado" };

function Selo({ status }) {
  return <span className={`selo selo-${status}`}>{ROTULO[status] ?? status}</span>;
}

export default function App() {
  const [config, setConfig] = useState(null);
  const [produtos, setProdutos] = useState([]);
  const [carrinho, setCarrinho] = useState({});
  const [pedidoId, setPedidoId] = useState(null);
  const [lista, setLista] = useState([]);
  const [erro, setErro] = useState("");
  const [criando, setCriando] = useState(false);
  const trava = useRef(false);

  useEffect(() => {
    api.config().then(setConfig).catch((e) => setErro(e.message));
    api.products().then(setProdutos).catch((e) => setErro(`API fora do ar? ${e.message}`));
  }, []);
  useEffect(() => {
    if (!pedidoId) api.orders().then(setLista).catch(() => {});
  }, [pedidoId]);

  const linhas = produtos.filter((p) => carrinho[p.id]);
  const total = linhas.reduce((s, p) => s + p.price_cents * carrinho[p.id], 0);
  const mudar = (id, d) =>
    setCarrinho((c) => {
      const q = Math.max(0, (c[id] ?? 0) + d);
      const { [id]: _, ...resto } = c;
      return q ? { ...resto, [id]: q } : resto;
    });

  async function finalizar() {
    if (trava.current) return;
    trava.current = true;
    setCriando(true);
    setErro("");
    try {
      const itens = linhas.map((p) => ({ product_id: p.id, quantity: carrinho[p.id] }));
      const pedido = await api.createOrder(itens);
      setCarrinho({});
      setPedidoId(pedido.id);
    } catch (e) {
      setErro(e.message);
    } finally {
      trava.current = false;
      setCriando(false);
    }
  }

  return (
    <main>
      <header>
        <h1>Loja</h1>
        <span className="modo">Stripe · modo de teste</span>
      </header>
      {erro && <p className="erro">{erro}</p>}

      {pedidoId ? (
        <Pedido id={pedidoId} config={config} voltar={() => setPedidoId(null)} />
      ) : (
        <>
          <div className="vitrine">
            <section>
              <h2>Produtos</h2>
              <ul className="lista">
                {produtos.map((p) => (
                  <li key={p.id}>
                    <span>{p.name}</span>
                    <span className="preco">{brl(p.price_cents)}</span>
                    <button onClick={() => mudar(p.id, 1)}>Adicionar</button>
                  </li>
                ))}
              </ul>
            </section>

            <section>
              <h2>Carrinho</h2>
              {linhas.length === 0 ? (
                <p className="suave">Seu carrinho está vazio. Adicione um produto para começar.</p>
              ) : (
                <>
                  <ul className="lista">
                    {linhas.map((p) => (
                      <li key={p.id}>
                        <span>{p.name}</span>
                        <span className="qtd">
                          <button aria-label={`Remover um ${p.name}`} onClick={() => mudar(p.id, -1)}>−</button>
                          <b>{carrinho[p.id]}</b>
                          <button aria-label={`Adicionar um ${p.name}`} onClick={() => mudar(p.id, 1)}>+</button>
                        </span>
                        <span className="preco">{brl(p.price_cents * carrinho[p.id])}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="total">
                    <span>Total</span>
                    <span>{brl(total)}</span>
                  </p>
                  <button className="primario" disabled={criando} onClick={finalizar}>
                    {criando ? "Criando pedido…" : "Finalizar pedido"}
                  </button>
                </>
              )}
            </section>
          </div>

          <section>
            <h2>Pedidos recentes</h2>
            {lista.length === 0 && <p className="suave">Nenhum pedido ainda.</p>}
            <ul className="lista">
              {lista.map((o) => (
                <li key={o.id}>
                  <button className="link id" onClick={() => setPedidoId(o.id)}>{o.id}</button>
                  <Selo status={o.status} />
                  <span className="preco">{brl(o.total_cents)}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}

function Pedido({ id, config, voltar }) {
  const [pedido, setPedido] = useState(null);
  const [erro, setErro] = useState("");

  const carregar = () => api.order(id).then(setPedido).catch((e) => setErro(e.message));
  useEffect(() => {
    carregar();
    const t = setInterval(carregar, 2000);
    return () => clearInterval(t);
  }, [id]);

  if (!pedido) return <p className="suave">{erro || "Carregando…"}</p>;
  const pagavel = pedido.status === "pendente" || pedido.status === "recusado";

  return (
    <section className="recibo">
      <button className="link" onClick={voltar}>← Voltar à loja</button>
      <h2>
        Pedido <span className="id">{pedido.id}</span> <Selo status={pedido.status} />
      </h2>
      <ul className="lista">
        {pedido.items.map((i) => (
          <li key={i.product_id}>
            <span>{i.quantity}× {i.name}</span>
            <span className="preco">{brl(i.unit_price_cents * i.quantity)}</span>
          </li>
        ))}
      </ul>
      <p className="total">
        <span>Total</span>
        <span>{brl(pedido.total_cents)}</span>
      </p>

      {pagavel && <Pagamento pedido={pedido} config={config} aoMudar={carregar} />}
      {pedido.status === "pago" && (
        <button className="primario" onClick={() => api.ship(id).then(carregar).catch((e) => setErro(e.message))}>
          Marcar como enviado
        </button>
      )}
      {erro && <p className="erro">{erro}</p>}

      <h3>Histórico (auditoria)</h3>
      <ol className="historico">
        {pedido.history.map((h, i) => (
          <li key={i}>
            <Selo status={h.to_status} /> <small>{h.cause}{h.event_id ? ` · ${h.event_id}` : ""}</small>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Pagamento({ pedido, config, aoMudar }) {
  const chave = useRef(crypto.randomUUID());
  const trava = useRef(false);
  const [segredo, setSegredo] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");
  const stripePromise = useMemo(
    () => (config?.publishable_key ? loadStripe(config.publishable_key) : null),
    [config]
  );

  async function iniciar() {
    if (trava.current) return;
    trava.current = true;
    setOcupado(true);
    setErro("");
    try {
      const r = await api.pay(pedido.id, chave.current);
      setSegredo(r.client_secret);
      aoMudar();
    } catch (e) {
      setErro(e.message);
    } finally {
      trava.current = false;
      setOcupado(false);
    }
  }

  return (
    <div className="caixa">
      <h3>Pagamento</h3>
      {!segredo && (
        <button className="primario" disabled={ocupado || !stripePromise} onClick={iniciar}>
          {ocupado ? "Processando…" : "Pagar"}
        </button>
      )}
      {!stripePromise && <p className="erro">Chave pública do Stripe ausente: confira STRIPE_PUBLISHABLE_KEY no .env.</p>}
      {segredo && stripePromise && (
        <Elements
          stripe={stripePromise}
          options={{
            clientSecret: segredo,
            appearance: {
              theme: "stripe",
              variables: { colorPrimary: "#0f5c4d", colorText: "#14211f", borderRadius: "10px", fontFamily: "Figtree, system-ui, sans-serif" },
            },
          }}
        >
          <FormularioStripe aoMudar={aoMudar} />
        </Elements>
      )}
      {erro && <p className="erro">{erro}</p>}
    </div>
  );
}

function FormularioStripe({ aoMudar }) {
  const stripe = useStripe();
  const elements = useElements();
  const trava = useRef(false);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");

  async function pagar(e) {
    e.preventDefault();
    if (!stripe || !elements || trava.current) return;
    trava.current = true;
    setOcupado(true);
    setErro("");
    const { error } = await stripe.confirmPayment({
      elements,
      redirect: "if_required",
      confirmParams: { return_url: window.location.href },
    });
    if (error) {
      setErro(error.message);
      trava.current = false;
    }
    setOcupado(false);
    aoMudar();
  }

  return (
    <form onSubmit={pagar}>
      <p className="suave">Cartão de teste: 4242 4242 4242 4242 (aprovado) · 4000 0000 0000 0002 (recusado)</p>
      <PaymentElement />
      <button className="primario" disabled={!stripe || ocupado}>{ocupado ? "Confirmando…" : "Confirmar pagamento"}</button>
      {erro && <p className="erro">{erro}</p>}
    </form>
  );
}