"use strict";

// Cliente Web do BookNet: conversa com a API FastAPI por HTTP/REST (JSON).
// A API fica na mesma máquina que serve o cliente, na porta 8000. Assim, abrindo
// http://IP_DO_SERVIDOR:8080 em outro computador, o navegador fala com IP_DO_SERVIDOR:8000.
const API = `http://${location.hostname || "127.0.0.1"}:8000`;

const $ = (seletor, raiz = document) => raiz.querySelector(seletor);
const $$ = (seletor, raiz = document) => [...raiz.querySelectorAll(seletor)];

/** Cria elementos sem innerHTML: textos da API nunca são interpretados como HTML. */
function el(tag, atributos = {}, ...filhos) {
  const elemento = document.createElement(tag);
  for (const [nome, valor] of Object.entries(atributos)) {
    if (nome === "class") elemento.className = valor;
    else if (nome.startsWith("on")) elemento.addEventListener(nome.slice(2), valor);
    else if (valor !== false && valor != null) elemento.setAttribute(nome, valor === true ? "" : valor);
  }
  for (const filho of filhos.flat()) {
    if (filho != null && filho !== false) elemento.append(filho);
  }
  return elemento;
}

function avisar(mensagem, erro = false, classe = "") {
  const toast = el("div", { class: `toast ${erro ? "erro" : classe}` }, mensagem);
  $("#toasts").append(toast);
  setTimeout(() => toast.remove(), erro ? 6000 : 3500);
}

function mensagemDeErro(corpo, status) {
  const detalhe = corpo && corpo.detail;
  if (typeof detalhe === "string") return detalhe;
  if (Array.isArray(detalhe) && detalhe.length) {
    // Erro 422 de validação: mostra o campo e a mensagem do primeiro problema.
    const campo = detalhe[0].loc ? detalhe[0].loc.slice(1).join(".") : "";
    return `Dados inválidos${campo ? ` em "${campo}"` : ""}: ${detalhe[0].msg}`;
  }
  return `Erro HTTP ${status}.`;
}

async function api(metodo, caminho, dados) {
  let resposta;
  try {
    resposta = await fetch(API + caminho, {
      method: metodo,
      headers: dados ? { "Content-Type": "application/json" } : {},
      body: dados ? JSON.stringify(dados) : undefined,
    });
  } catch {
    throw new Error("Não foi possível falar com a API. Ela está em execução na porta 8000?");
  }
  const corpo = await resposta.json().catch(() => null);
  if (!resposta.ok) throw new Error(mensagemDeErro(corpo, resposta.status));
  return corpo;
}

const formatarData = (valor) =>
  valor ? new Date(valor.length === 10 ? `${valor}T12:00:00` : valor).toLocaleDateString("pt-BR") : "—";

function vazio(texto) {
  return el("div", { class: "empty" }, texto);
}

/* ---------- Estado da API ---------- */

async function verificarStatus() {
  const caixa = $("#status-api");
  const texto = $(".status-text", caixa);
  try {
    const banco = await fetch(`${API}/health/database`).then((r) => r.json());
    const online = banco.database === "online";
    caixa.className = `status ${online ? "ok" : "erro"}`;
    texto.textContent = online ? "API e banco online" : "API online · banco offline";
  } catch {
    caixa.className = "status erro";
    texto.textContent = "API offline";
  }
}

/* ---------- Tempo real (V2): WebSocket de eventos ---------- */

const WS_URL = `${API.replace(/^http/, "ws")}/ws/eventos`;
const acoesProprias = new Set(); // eventos causados por esta tela: atualiza, mas não repete o aviso

function marcarPropria(tipo, id) {
  acoesProprias.add(`${tipo}:${id}`);
}

const DESCRICOES = {
  "emprestimo.criado": (d) => `${d.usuario_nome} pegou “${d.livro_titulo}” (exemplar ${d.codigo_tombo}).`,
  "emprestimo.devolvido": (d) => `${d.usuario_nome} devolveu “${d.livro_titulo}” (exemplar ${d.codigo_tombo}).`,
  "livro.criado": (d) => `Novo livro no acervo: “${d.titulo}”.`,
  "livro.atualizado": (d) => `Livro atualizado: “${d.titulo}”.`,
  "exemplar.criado": (d) => `Novo exemplar cadastrado: ${d.codigo_tombo}.`,
  "usuario.criado": (d) => `Novo usuário: ${d.nome}.`,
  "usuario.atualizado": (d) => `Usuário atualizado: ${d.nome}.`,
};

function atualizarIndicadorTempoReal(conectado, telas) {
  const caixa = $("#status-ws");
  caixa.className = `status ${conectado ? "ok" : "erro"}`;
  $(".status-text", caixa).textContent = conectado
    ? `Ao vivo · ${telas} ${telas === 1 ? "tela" : "telas"}`
    : "Tempo real desconectado · tentando de novo…";
}

function registrarNoFeed(evento, texto) {
  const feed = $("#feed-eventos");
  if (feed.firstElementChild && !feed.firstElementChild.querySelector("time")) feed.replaceChildren();
  const hora = new Date(evento.momento).toLocaleTimeString("pt-BR");
  feed.prepend(
    el("li", { class: evento.tipo === "emprestimo.devolvido" ? "devolucao" : "" }, el("time", {}, hora), texto)
  );
  while (feed.children.length > 15) feed.lastElementChild.remove();
}

function recarregarAbaAtual() {
  const ativa = $(".tab.is-active").dataset.tab;
  if (ativa === "acervo") carregarLivros();
  if (ativa === "usuarios") carregarUsuarios();
  if (ativa === "emprestimos") {
    carregarOpcoesUsuarios();
    carregarEmprestimos();
  }
}

function tratarEvento(evento) {
  if (evento.tipo === "conectado" || evento.tipo === "conexoes.alteradas") {
    atualizarIndicadorTempoReal(true, evento.dados.conexoes);
    return;
  }
  const descrever = DESCRICOES[evento.tipo];
  if (!descrever) return;
  const texto = descrever(evento.dados);
  registrarNoFeed(evento, texto);
  const chave = `${evento.tipo}:${evento.dados.id}`;
  if (acoesProprias.has(chave)) acoesProprias.delete(chave);
  else avisar(texto, false, "ao-vivo");
  recarregarAbaAtual();
}

function conectarEventos(tentativa = 0) {
  const ws = new WebSocket(WS_URL);
  let aberto = false;
  ws.addEventListener("open", () => {
    aberto = true;
  });
  ws.addEventListener("message", (mensagem) => tratarEvento(JSON.parse(mensagem.data)));
  ws.addEventListener("close", () => {
    atualizarIndicadorTempoReal(false);
    // Reconexão com espera crescente (1s, 2s, 4s… até 30s) para não sobrecarregar a API.
    const proxima = aberto ? 0 : tentativa + 1;
    setTimeout(() => conectarEventos(proxima), Math.min(30000, 1000 * 2 ** proxima));
  });
}

/* ---------- Abas ---------- */

function abrirAba(nome) {
  for (const aba of $$(".tab")) aba.classList.toggle("is-active", aba.dataset.tab === nome);
  for (const painel of $$(".panel")) painel.hidden = painel.id !== `tab-${nome}`;
  if (nome === "acervo") carregarLivros();
  if (nome === "usuarios") carregarUsuarios();
  if (nome === "emprestimos") {
    carregarOpcoesUsuarios();
    carregarEmprestimos();
  }
}

/* ---------- Acervo ---------- */

async function carregarLivros() {
  const lista = $("#lista-livros");
  const q = $("#busca-livros").q.value.trim();
  try {
    const livros = await api("GET", `/livros?limit=50${q ? `&q=${encodeURIComponent(q)}` : ""}`);
    const exemplares = await Promise.all(livros.map((l) => api("GET", `/livros/${l.id}/exemplares`)));
    lista.replaceChildren(
      ...(livros.length ? livros.map((livro, i) => cartaoLivro(livro, exemplares[i])) : [vazio("Nenhum livro encontrado.")])
    );
  } catch (erro) {
    lista.replaceChildren(vazio(erro.message));
  }
}

function cartaoLivro(livro, exemplares) {
  const disponiveis = exemplares.filter((e) => e.status === "DISPONIVEL").length;
  const areaExemplares = el("div", { class: "exemplares", hidden: true },
    exemplares.length
      ? exemplares.map((exemplar) =>
          el("div", { class: "exemplar" },
            el("span", {}, el("strong", {}, exemplar.codigo_tombo), ` · id ${exemplar.id}`),
            el("span", { class: "item-actions" },
              el("span", { class: exemplar.status === "DISPONIVEL" ? "badge" : "badge warn" }, exemplar.status),
              exemplar.status === "DISPONIVEL"
                ? el("button", { class: "small accent", type: "button", onclick: () => prepararEmprestimo(exemplar, livro) }, "Emprestar")
                : null
            )
          )
        )
      : el("p", { class: "item-meta" }, "Nenhum exemplar cadastrado."),
    el("form", { class: "novo-exemplar", onsubmit: (evento) => criarExemplar(evento, livro.id) },
      el("input", { name: "codigo_tombo", placeholder: "Código de tombo do novo exemplar", required: true, maxlength: 50 }),
      el("button", { class: "small", type: "submit" }, "Adicionar")
    )
  );
  const alternar = el("button", { class: "small", type: "button" }, "Exemplares");
  alternar.addEventListener("click", () => {
    areaExemplares.hidden = !areaExemplares.hidden;
  });

  return el("article", { class: "card item" },
    el("div", { class: "item-row" },
      el("div", {},
        el("h3", {}, livro.titulo),
        el("p", { class: "item-meta" }, `${livro.autor} · ISBN ${livro.isbn}`)
      ),
      el("div", { class: "item-actions" },
        el("span", { class: disponiveis ? "badge" : exemplares.length ? "badge warn" : "badge neutral" },
          `${disponiveis}/${exemplares.length} disponíveis`),
        alternar,
        el("button", { class: "small", type: "button", onclick: () => editarLivro(livro) }, "Editar")
      )
    ),
    areaExemplares
  );
}

async function criarExemplar(evento, livroId) {
  evento.preventDefault();
  const formulario = evento.target;
  try {
    const exemplar = await api("POST", `/livros/${livroId}/exemplares`, { codigo_tombo: formulario.codigo_tombo.value });
    marcarPropria("exemplar.criado", exemplar.id);
    avisar(`Exemplar ${exemplar.codigo_tombo} cadastrado.`);
    carregarLivros();
  } catch (erro) {
    avisar(erro.message, true);
  }
}

function editarLivro(livro) {
  const formulario = $("#form-livro");
  formulario.registro_id.value = livro.id;
  formulario.titulo.value = livro.titulo;
  formulario.autor.value = livro.autor;
  formulario.isbn.value = livro.isbn;
  formulario.ativo.checked = livro.ativo;
  $("#titulo-form-livro").textContent = `Editar livro #${livro.id}`;
  $("#cancelar-livro").hidden = false;
  formulario.titulo.focus();
}

function limparFormLivro() {
  const formulario = $("#form-livro");
  formulario.reset();
  formulario.registro_id.value = "";
  $("#titulo-form-livro").textContent = "Novo livro";
  $("#cancelar-livro").hidden = true;
}

async function salvarLivro(evento) {
  evento.preventDefault();
  const f = evento.target;
  const dados = { titulo: f.titulo.value, autor: f.autor.value, isbn: f.isbn.value, ativo: f.ativo.checked };
  try {
    const livro = f.registro_id.value ? await api("PUT", `/livros/${f.registro_id.value}`, dados) : await api("POST", "/livros", dados);
    marcarPropria(f.registro_id.value ? "livro.atualizado" : "livro.criado", livro.id);
    avisar(`Livro "${livro.titulo}" salvo.`);
    limparFormLivro();
    carregarLivros();
  } catch (erro) {
    avisar(erro.message, true);
  }
}

function prepararEmprestimo(exemplar, livro) {
  abrirAba("emprestimos");
  const formulario = $("#form-emprestimo");
  formulario.exemplar_id.value = exemplar.id;
  $("#info-exemplar").textContent = `Exemplar ${exemplar.codigo_tombo} — ${livro.titulo}`;
  formulario.usuario_id.focus();
}

/* ---------- Usuários ---------- */

async function carregarUsuarios() {
  const lista = $("#lista-usuarios");
  const busca = $("#busca-usuarios");
  const parametros = new URLSearchParams({ limit: "100" });
  if (busca.q.value.trim()) parametros.set("q", busca.q.value.trim());
  if (busca.tipo.value) parametros.set("tipo", busca.tipo.value);
  try {
    const usuarios = await api("GET", `/usuarios?${parametros}`);
    lista.replaceChildren(
      ...(usuarios.length ? usuarios.map(cartaoUsuario) : [vazio("Nenhum usuário encontrado.")])
    );
  } catch (erro) {
    lista.replaceChildren(vazio(erro.message));
  }
}

function cartaoUsuario(usuario) {
  return el("article", { class: "card item" },
    el("div", { class: "item-row" },
      el("div", {},
        el("h3", {}, usuario.nome),
        el("p", { class: "item-meta" }, `${usuario.email} · matrícula ${usuario.matricula}`)
      ),
      el("div", { class: "item-actions" },
        el("span", { class: usuario.tipo === "ALUNO" ? "badge" : "badge neutral" }, usuario.tipo),
        el("button", { class: "small", type: "button", onclick: () => verEmprestimosDe(usuario) }, "Empréstimos"),
        el("button", { class: "small", type: "button", onclick: () => editarUsuario(usuario) }, "Editar")
      )
    )
  );
}

function editarUsuario(usuario) {
  const f = $("#form-usuario");
  f.registro_id.value = usuario.id;
  f.nome.value = usuario.nome;
  f.email.value = usuario.email;
  f.matricula.value = usuario.matricula;
  f.tipo.value = usuario.tipo;
  f.ativo.checked = usuario.ativo;
  $("#titulo-form-usuario").textContent = `Editar usuário #${usuario.id}`;
  $("#cancelar-usuario").hidden = false;
  f.nome.focus();
}

function limparFormUsuario() {
  const f = $("#form-usuario");
  f.reset();
  f.registro_id.value = "";
  $("#titulo-form-usuario").textContent = "Novo usuário";
  $("#cancelar-usuario").hidden = true;
}

async function salvarUsuario(evento) {
  evento.preventDefault();
  const f = evento.target;
  const dados = { nome: f.nome.value, email: f.email.value, matricula: f.matricula.value, tipo: f.tipo.value, ativo: f.ativo.checked };
  try {
    const usuario = f.registro_id.value ? await api("PUT", `/usuarios/${f.registro_id.value}`, dados) : await api("POST", "/usuarios", dados);
    marcarPropria(f.registro_id.value ? "usuario.atualizado" : "usuario.criado", usuario.id);
    avisar(`Usuário "${usuario.nome}" salvo.`);
    limparFormUsuario();
    carregarUsuarios();
  } catch (erro) {
    avisar(erro.message, true);
  }
}

/* ---------- Empréstimos ---------- */

let filtroEmprestimos = "";
let usuarioFiltrado = null;

async function carregarOpcoesUsuarios() {
  const select = $("#select-usuario");
  const atual = select.value;
  try {
    const usuarios = await api("GET", "/usuarios?limit=100");
    select.replaceChildren(
      el("option", { value: "" }, "Selecione…"),
      ...usuarios.map((u) => el("option", { value: u.id }, `${u.nome} (${u.matricula})`))
    );
    select.value = atual;
  } catch (erro) {
    avisar(erro.message, true);
  }
}

function verEmprestimosDe(usuario) {
  usuarioFiltrado = usuario;
  abrirAba("emprestimos");
}

async function carregarEmprestimos() {
  const lista = $("#lista-emprestimos");
  const parametros = new URLSearchParams(filtroEmprestimos);
  parametros.set("limit", "100");
  if (usuarioFiltrado) parametros.set("usuario_id", usuarioFiltrado.id);
  try {
    const emprestimos = await api("GET", `/emprestimos?${parametros}`);
    const aviso = usuarioFiltrado
      ? el("div", { class: "item-row card" },
          el("span", {}, "Mostrando empréstimos de ", el("strong", {}, usuarioFiltrado.nome)),
          el("button", { class: "small", type: "button", onclick: () => { usuarioFiltrado = null; carregarEmprestimos(); } }, "Mostrar todos"))
      : null;
    lista.replaceChildren(
      ...[aviso].filter(Boolean),
      ...(emprestimos.length ? emprestimos.map(cartaoEmprestimo) : [vazio("Nenhum empréstimo encontrado.")])
    );
  } catch (erro) {
    lista.replaceChildren(vazio(erro.message));
  }
}

function cartaoEmprestimo(emp) {
  const badge = emp.status === "DEVOLVIDO"
    ? el("span", { class: "badge neutral" }, "DEVOLVIDO")
    : emp.atrasado
      ? el("span", { class: "badge danger" }, "ATRASADO")
      : el("span", { class: "badge" }, "ATIVO");
  const datas = emp.status === "DEVOLVIDO"
    ? `Emprestado em ${formatarData(emp.data_emprestimo)} · devolvido em ${formatarData(emp.data_devolucao)}`
    : `Emprestado em ${formatarData(emp.data_emprestimo)} · devolver até ${formatarData(emp.data_prevista_devolucao)}`;

  return el("article", { class: "card item" },
    el("div", { class: "item-row" },
      el("div", {},
        el("h3", {}, emp.livro_titulo),
        el("p", { class: "item-meta" }, `#${emp.id} · ${emp.usuario_nome} · exemplar ${emp.codigo_tombo}`),
        el("p", { class: "item-meta" }, datas)
      ),
      el("div", { class: "item-actions" },
        badge,
        emp.status === "ATIVO"
          ? el("button", { class: "small accent", type: "button", onclick: (e) => devolver(emp, e.currentTarget) }, "Registrar devolução")
          : null
      )
    )
  );
}

async function criarEmprestimo(evento) {
  evento.preventDefault();
  const f = evento.target;
  const botao = $("button[type=submit]", f);
  botao.disabled = true;
  try {
    const emp = await api("POST", "/emprestimos", {
      usuario_id: Number(f.usuario_id.value),
      exemplar_id: Number(f.exemplar_id.value),
      prazo_dias: Number(f.prazo_dias.value),
    });
    marcarPropria("emprestimo.criado", emp.id);
    avisar(`Empréstimo #${emp.id} registrado: devolver até ${formatarData(emp.data_prevista_devolucao)}.`);
    f.exemplar_id.value = "";
    $("#info-exemplar").textContent = "Dica: use o botão “Emprestar” no Acervo.";
    carregarEmprestimos();
  } catch (erro) {
    avisar(erro.message, true);
  } finally {
    botao.disabled = false;
  }
}

async function devolver(emp, botao) {
  botao.disabled = true;
  try {
    await api("POST", `/emprestimos/${emp.id}/devolucao`);
    marcarPropria("emprestimo.devolvido", emp.id);
    avisar(`Devolução do exemplar ${emp.codigo_tombo} registrada.`);
    carregarEmprestimos();
  } catch (erro) {
    avisar(erro.message, true);
    botao.disabled = false;
  }
}

/* ---------- Inicialização ---------- */

document.addEventListener("DOMContentLoaded", () => {
  for (const aba of $$(".tab")) aba.addEventListener("click", () => abrirAba(aba.dataset.tab));
  for (const chip of $$(".chip")) {
    chip.addEventListener("click", () => {
      for (const outro of $$(".chip")) outro.classList.toggle("is-active", outro === chip);
      filtroEmprestimos = chip.dataset.filtro;
      carregarEmprestimos();
    });
  }
  $("#busca-livros").addEventListener("submit", (e) => { e.preventDefault(); carregarLivros(); });
  $("#busca-usuarios").addEventListener("submit", (e) => { e.preventDefault(); carregarUsuarios(); });
  $("#form-livro").addEventListener("submit", salvarLivro);
  $("#cancelar-livro").addEventListener("click", limparFormLivro);
  $("#form-usuario").addEventListener("submit", salvarUsuario);
  $("#cancelar-usuario").addEventListener("click", limparFormUsuario);
  $("#form-emprestimo").addEventListener("submit", criarEmprestimo);

  verificarStatus();
  setInterval(verificarStatus, 15000);
  conectarEventos();
  const abaInicial = location.hash.slice(1);
  abrirAba(["acervo", "usuarios", "emprestimos"].includes(abaInicial) ? abaInicial : "acervo");
});
