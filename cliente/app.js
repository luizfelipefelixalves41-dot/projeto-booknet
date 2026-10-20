"use strict";

/* =====================================================================
   BookNet · Cliente Web
   Conversa com três serviços por HTTP/REST (JSON) e WebSocket.
   - Login: o Serviço de Usuários devolve um token de sessão; ele vai em
     todas as requisições e cada serviço o confere sozinho.
   - Perfis: o aluno vê o acervo e os próprios empréstimos; o bibliotecário
     administra acervo, usuários e empréstimos.
   ===================================================================== */

// Execução local ou na rede do laboratório: serviços nas portas 8001-8003 da mesma
// máquina que serve o cliente. Na nuvem: endereços públicos de config.js.
const HOST = location.hostname || "127.0.0.1";
const EXECUCAO_LOCAL =
  location.protocol === "file:" ||
  HOST === "localhost" ||
  HOST === "[::1]" ||
  /^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(HOST);
const NUVEM = window.BOOKNET_NUVEM || {};

function servico(chave, nome, porta) {
  const url = EXECUCAO_LOCAL ? `http://${HOST}:${porta}` : NUVEM[chave];
  const onde = EXECUCAO_LOCAL ? `porta ${porta}` : new URL(url).hostname;
  return { chave, nome, url, porta, onde };
}

const SERVICOS = {
  catalogo: servico("catalogo", "Catálogo", 8001),
  usuarios: servico("usuarios", "Usuários", 8002),
  emprestimos: servico("emprestimos", "Empréstimos", 8003),
};

/** Cada rota pertence a um serviço, como no desenho da arquitetura. */
function servicoDaRota(caminho) {
  if (caminho.startsWith("/usuarios") || caminho.startsWith("/auth")) return SERVICOS.usuarios;
  if (caminho.startsWith("/emprestimos") || caminho.startsWith("/health/dependencias")) return SERVICOS.emprestimos;
  return SERVICOS.catalogo;
}

/* ---------------------------- utilidades ---------------------------- */

const $ = (seletor, raiz = document) => raiz.querySelector(seletor);
const $$ = (seletor, raiz = document) => [...raiz.querySelectorAll(seletor)];

/** Cria elementos sem innerHTML: textos vindos dos serviços nunca viram HTML. */
function el(tag, atributos = {}, ...filhos) {
  const elemento = document.createElement(tag);
  for (const [nome, valor] of Object.entries(atributos)) {
    if (nome === "class") elemento.className = valor;
    else if (nome === "style") elemento.setAttribute("style", valor);
    else if (nome.startsWith("on")) elemento.addEventListener(nome.slice(2), valor);
    else if (valor !== false && valor != null) elemento.setAttribute(nome, valor === true ? "" : valor);
  }
  for (const filho of filhos.flat()) {
    if (filho != null && filho !== false) elemento.append(filho);
  }
  return elemento;
}

function icone(nome) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "icone");
  const uso = document.createElementNS("http://www.w3.org/2000/svg", "use");
  uso.setAttribute("href", `#i-${nome}`);
  svg.append(uso);
  return svg;
}

function avisar(mensagem, erro = false, classe = "") {
  const toast = el("div", { class: `toast ${erro ? "erro" : classe}` }, mensagem);
  $("#toasts").append(toast);
  setTimeout(() => toast.remove(), erro ? 6000 : 3800);
}

function mensagemDeErro(corpo, status) {
  const detalhe = corpo && corpo.detail;
  if (typeof detalhe === "string") return detalhe;
  if (Array.isArray(detalhe) && detalhe.length) {
    const campo = detalhe[0].loc ? detalhe[0].loc.slice(1).join(".") : "";
    return `Dados inválidos${campo ? ` em "${campo}"` : ""}: ${detalhe[0].msg}`;
  }
  return `Erro HTTP ${status}.`;
}

const formatarData = (valor) =>
  valor ? new Date(valor.length === 10 ? `${valor}T12:00:00` : valor).toLocaleDateString("pt-BR") : "—";

const vazio = (texto) => el("div", { class: "vazio" }, texto);

function iniciais(texto) {
  return texto.split(/\s+/).filter((p) => p.length > 2 || /^[A-Z]/.test(p)).slice(0, 2).map((p) => p[0]).join("").toUpperCase() || "?";
}

/** Cor da "capa" do livro derivada do título: o mesmo livro tem sempre a mesma cor. */
function corDaCapa(texto) {
  let soma = 0;
  for (const letra of texto) soma = (soma * 31 + letra.charCodeAt(0)) % 360;
  return `hsl(${soma} 42% 36%)`;
}

const capa = (titulo) => el("div", { class: "capa", style: `background:${corDaCapa(titulo)}`, "aria-hidden": "true" }, iniciais(titulo));

/* ------------------------------ sessão ------------------------------ */

const CHAVE_SESSAO = "booknet.sessao";
let sessao = null; // { token, usuario, expira }

function lerSessaoSalva() {
  try {
    const salva = JSON.parse(sessionStorage.getItem(CHAVE_SESSAO));
    if (salva && salva.token && salva.expira > Date.now()) return salva;
  } catch {
    // armazenamento indisponível: segue sem sessão salva
  }
  return null;
}

function salvarSessao() {
  try {
    if (sessao) sessionStorage.setItem(CHAVE_SESSAO, JSON.stringify(sessao));
    else sessionStorage.removeItem(CHAVE_SESSAO);
  } catch {
    // ignora: a sessão continua valendo nesta aba
  }
}

const ehBibliotecario = () => sessao && sessao.usuario.tipo === "BIBLIOTECARIO";

async function api(metodo, caminho, dados, { semSessao = false } = {}) {
  const destino = servicoDaRota(caminho);
  const cabecalhos = {};
  if (dados) cabecalhos["Content-Type"] = "application/json";
  if (sessao && !semSessao) cabecalhos.Authorization = `Bearer ${sessao.token}`;
  let resposta;
  try {
    resposta = await fetch(destino.url + caminho, {
      method: metodo,
      headers: cabecalhos,
      body: dados ? JSON.stringify(dados) : undefined,
    });
  } catch {
    throw new Error(
      EXECUCAO_LOCAL
        ? `Serviço de ${destino.nome} fora do ar (porta ${destino.porta}).`
        : `Serviço de ${destino.nome} indisponível. Na nuvem gratuita ele pode estar acordando: aguarde até 1 minuto.`
    );
  }
  const corpo = await resposta.json().catch(() => null);
  if (resposta.status === 401 && !semSessao) {
    encerrarSessao("Sua sessão expirou. Entre novamente.");
    throw new Error("Sessão expirada.");
  }
  if (!resposta.ok) throw new Error(mensagemDeErro(corpo, resposta.status));
  return corpo;
}

/* ------------------------- estado dos serviços ------------------------- */

let acordando = false;
const estadoServicos = {};

async function verificarStatus() {
  const resultados = await Promise.all(
    Object.values(SERVICOS).map(async (s) => {
      let estado = "erro";
      let detalhe = "fora do ar";
      try {
        const banco = await fetch(`${s.url}/health/database`).then((r) => r.json());
        estado = banco.database === "online" ? "ok" : "erro";
        detalhe = banco.database === "online" ? "online" : "sem banco";
      } catch {
        // serviço desligado ou dormindo
      }
      estadoServicos[s.chave] = { ...s, estado, detalhe };
      return { ok: estado === "ok", s, estado, detalhe };
    })
  );
  const indicador = (r) =>
    el("span", { class: `status ${r.estado}`, title: `${r.s.nome} (${r.s.onde}): ${r.detalhe}` },
      el("span", { class: "ponto" }), el("span", { class: "status-texto" }, r.s.nome));
  $("#status-servicos").replaceChildren(...resultados.map(indicador));
  $("#login-servicos").replaceChildren(...resultados.map(indicador));

  // Nuvem gratuita: serviços sem uso dormem e levam até 1 minuto para acordar.
  const todosOk = resultados.every((r) => r.ok);
  if (!EXECUCAO_LOCAL && !todosOk) {
    acordando = true;
    $("#aviso-nuvem").hidden = false;
  } else if (acordando && todosOk) {
    acordando = false;
    $("#aviso-nuvem").hidden = true;
    if (sessao) {
      avisar("Todos os serviços estão no ar.");
      recarregarAbaAtual();
    }
  }
  if (abaAtual === "painel") desenharSaude();
  setTimeout(verificarStatus, todosOk ? 15000 : 5000);
}

/* --------------------- tempo real (V2): WebSocket --------------------- */

const acoesProprias = new Set(); // eventos causados por esta tela: atualiza sem repetir o aviso
const emAndamento = {}; // tipo de evento → ações desta tela ainda aguardando resposta
const canais = {}; // { conectado, telas, jaConectou }
const sockets = {};

function marcarPropria(tipo, id) {
  acoesProprias.add(`${tipo}:${id}`);
}

/** Executa uma ação desta tela. O WebSocket pode avisar ANTES de a resposta HTTP
 *  chegar; por isso a ação é anotada como "em andamento" antes do pedido. */
async function acaoPropria(tipo, executar) {
  emAndamento[tipo] = (emAndamento[tipo] || 0) + 1;
  try {
    const resultado = await executar();
    marcarPropria(tipo, resultado.id);
    return resultado;
  } finally {
    setTimeout(() => { emAndamento[tipo] -= 1; }, 3000);
  }
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

function atualizarIndicadorTempoReal() {
  const total = Object.keys(SERVICOS).length;
  const ativos = Object.values(canais).filter((c) => c.conectado);
  const telas = Math.max(0, ...ativos.map((c) => c.telas));
  const caixa = $("#status-ws");
  caixa.className = `status ${ativos.length === total ? "ok" : ativos.length ? "parcial" : "erro"}`;
  $(".status-texto", caixa).textContent = ativos.length
    ? `Ao vivo ${ativos.length}/${total} · ${telas} ${telas === 1 ? "tela" : "telas"}`
    : "Tempo real desconectado";
}

function registrarNoFeed(evento, texto) {
  const feed = $("#feed-eventos");
  if (feed.firstElementChild && feed.firstElementChild.classList.contains("vazio-feed")) feed.replaceChildren();
  const hora = new Date(evento.momento).toLocaleTimeString("pt-BR");
  feed.prepend(el("li", { class: evento.tipo === "emprestimo.devolvido" ? "devolucao" : "" }, el("time", {}, hora), texto));
  while (feed.children.length > 20) feed.lastElementChild.remove();
}

function tratarEvento(chave, evento) {
  if (evento.tipo === "conectado" || evento.tipo === "conexoes.alteradas") {
    canais[chave] = { ...canais[chave], conectado: true, telas: evento.dados.conexoes };
    atualizarIndicadorTempoReal();
    return;
  }
  const descrever = DESCRICOES[evento.tipo];
  if (!descrever) return;
  const texto = descrever(evento.dados);
  registrarNoFeed(evento, texto);
  const identificador = `${evento.tipo}:${evento.dados.id}`;
  const propria = acoesProprias.delete(identificador) || emAndamento[evento.tipo] > 0;
  if (!propria) avisar(texto, false, "ao-vivo");
  recarregarAbaAtual();
}

function conectarEventos(chave, tentativa = 0) {
  if (!sessao) return;
  const token = encodeURIComponent(sessao.token);
  const ws = new WebSocket(`${SERVICOS[chave].url.replace(/^http/, "ws")}/ws/eventos?token=${token}`);
  sockets[chave] = ws;
  let aberto = false;
  ws.addEventListener("open", () => {
    aberto = true;
    // V5: ao voltar de uma queda, recarrega a tela para não perder o que mudou nesse meio-tempo.
    if (canais[chave] && canais[chave].jaConectou) recarregarAbaAtual();
    canais[chave] = { ...canais[chave], jaConectou: true };
  });
  ws.addEventListener("message", (mensagem) => tratarEvento(chave, JSON.parse(mensagem.data)));
  ws.addEventListener("close", () => {
    canais[chave] = { ...canais[chave], conectado: false, telas: 0 };
    atualizarIndicadorTempoReal();
    if (!sessao || sockets[chave] !== ws) return; // saiu do sistema: não reconecta
    const proxima = aberto ? 0 : tentativa + 1;
    setTimeout(() => conectarEventos(chave, proxima), Math.min(30000, 1000 * 2 ** proxima));
  });
}

function fecharEventos() {
  for (const [chave, ws] of Object.entries(sockets)) {
    delete sockets[chave];
    ws.close();
  }
  for (const chave of Object.keys(canais)) delete canais[chave];
}

/* --------------------------- login e saída --------------------------- */

let perfilEscolhido = "ALUNO";
const TEXTOS_PERFIL = {
  ALUNO: { botao: "Entrar como aluno", ajuda: "Ainda não tem senha? Procure a biblioteca para ativar o seu acesso." },
  BIBLIOTECARIO: { botao: "Entrar como bibliotecário", ajuda: "Acesso de administração do acervo, dos usuários e dos empréstimos." },
};

function escolherPerfil(perfil) {
  perfilEscolhido = perfil;
  for (const botao of $$(".perfil")) {
    const ativo = botao.dataset.perfil === perfil;
    botao.classList.toggle("is-ativo", ativo);
    botao.setAttribute("aria-selected", String(ativo));
  }
  $("#botao-entrar").textContent = TEXTOS_PERFIL[perfil].botao;
  $("#login-ajuda").textContent = TEXTOS_PERFIL[perfil].ajuda;
  $("#erro-login").hidden = true;
}

function mostrarLogin(mensagem) {
  $("#tela-app").hidden = true;
  $("#tela-login").hidden = false;
  const erro = $("#erro-login");
  erro.textContent = mensagem || "";
  erro.hidden = !mensagem;
  $("#form-login").matricula.focus();
}

async function entrar(evento) {
  evento.preventDefault();
  const formulario = evento.target;
  const botao = $("#botao-entrar");
  const erro = $("#erro-login");
  if (!formulario.matricula.value.trim() || !formulario.senha.value) {
    erro.textContent = "Informe a matrícula e a senha.";
    erro.hidden = false;
    return;
  }
  botao.disabled = true;
  botao.textContent = "Entrando…";
  try {
    const resposta = await api("POST", "/auth/login", {
      matricula: formulario.matricula.value.trim(),
      senha: formulario.senha.value,
      perfil: perfilEscolhido,
    }, { semSessao: true });
    sessao = { token: resposta.token, usuario: resposta.usuario, expira: Date.now() + resposta.expira_em_segundos * 1000 };
    salvarSessao();
    formulario.reset();
    iniciarApp();
  } catch (falha) {
    erro.textContent = falha.message;
    erro.hidden = false;
  } finally {
    botao.disabled = false;
    botao.textContent = TEXTOS_PERFIL[perfilEscolhido].botao;
  }
}

function encerrarSessao(mensagem) {
  sessao = null;
  salvarSessao();
  fecharEventos();
  history.replaceState(null, "", location.pathname);
  mostrarLogin(mensagem);
}

/* ---------------------------- navegação ---------------------------- */

const ABAS = {
  ALUNO: [["acervo", "Acervo"], ["meus", "Meus empréstimos"]],
  BIBLIOTECARIO: [["painel", "Painel"], ["acervo", "Acervo"], ["usuarios", "Usuários"], ["emprestimos", "Empréstimos"]],
};
let abaAtual = null;

function iniciarApp() {
  const { usuario } = sessao;
  $("#tela-login").hidden = true;
  $("#tela-app").hidden = false;
  $("#avatar").textContent = iniciais(usuario.nome);
  $("#usuario-nome").textContent = usuario.nome.split(" ")[0];
  $("#usuario-papel").textContent = ehBibliotecario() ? "Bibliotecário(a)" : `Aluno · ${usuario.matricula}`;
  $("#marca-perfil").textContent = ehBibliotecario() ? "ADMINISTRAÇÃO" : "ÁREA DO ALUNO";
  $("#saudacao").textContent = `Olá, ${usuario.nome.split(" ")[0]}`;
  $("#acervo-sub").textContent = ehBibliotecario()
    ? "Cadastre livros e exemplares e acompanhe a disponibilidade."
    : "Encontre um livro e pegue emprestado com um clique.";
  for (const elemento of $$(".somente-biblio")) elemento.hidden = !ehBibliotecario();
  document.body.classList.toggle("perfil-aluno", !ehBibliotecario());

  const abas = ABAS[usuario.tipo];
  $("#abas").replaceChildren(
    ...abas.map(([chave, nome]) => el("button", { class: "aba", type: "button", "data-aba": chave, onclick: () => abrirAba(chave) }, nome))
  );
  for (const chave of Object.keys(SERVICOS)) conectarEventos(chave);
  const pedida = location.hash.slice(1);
  abrirAba(abas.some(([chave]) => chave === pedida) ? pedida : abas[0][0]);
}

function abrirAba(nome) {
  abaAtual = nome;
  for (const aba of $$(".aba")) aba.classList.toggle("is-ativo", aba.dataset.aba === nome);
  for (const painel of $$(".painel")) painel.hidden = painel.id !== `aba-${nome}`;
  history.replaceState(null, "", `#${nome}`);
  recarregarAbaAtual();
}

function recarregarAbaAtual() {
  if (!sessao) return;
  if (abaAtual === "painel") carregarPainel();
  if (abaAtual === "acervo") carregarLivros();
  if (abaAtual === "meus") carregarMeus();
  if (abaAtual === "usuarios") carregarUsuarios();
  if (abaAtual === "emprestimos") {
    carregarOpcoesUsuarios();
    carregarEmprestimos();
  }
}

/* ------------------------ painel (bibliotecário) ------------------------ */

const kpi = (titulo, valor, detalhe, classe = "") =>
  el("div", { class: `kpi ${classe}` }, el("small", {}, titulo), el("strong", {}, String(valor)), el("span", {}, detalhe));

async function carregarPainel() {
  if (!$("#kpis").children.length) {
    $("#kpis").replaceChildren(
      ...["Livros no acervo", "Exemplares disponíveis", "Empréstimos ativos", "Atrasados"].map((titulo, i) =>
        kpi(titulo, "…", "carregando", i === 0 ? "destaque" : "")));
  }
  desenharSaude(); // em paralelo com os números
  try {
    const [livros, ativos, atrasados] = await Promise.all([
      api("GET", "/livros?limit=100"),
      api("GET", "/emprestimos?status=ATIVO&limit=100"),
      api("GET", "/emprestimos?atrasados=true&limit=100"),
    ]);
    const exemplares = (await Promise.all(livros.map((l) => api("GET", `/livros/${l.id}/exemplares`)))).flat();
    const disponiveis = exemplares.filter((e) => e.status === "DISPONIVEL").length;
    $("#kpis").replaceChildren(
      kpi("Livros no acervo", livros.length, "títulos ativos", "destaque"),
      kpi("Exemplares disponíveis", `${disponiveis}/${exemplares.length}`, "prontos para emprestar"),
      kpi("Empréstimos ativos", ativos.length, "livros fora da biblioteca"),
      kpi("Atrasados", atrasados.length, atrasados.length ? "precisam de atenção" : "tudo em dia", atrasados.length ? "alerta" : "")
    );
  } catch (erro) {
    $("#kpis").replaceChildren(vazio(erro.message));
  }
}

let dependencias = null;

async function desenharSaude() {
  desenharLinhasSaude(); // mostra já o que se sabe; os disjuntores chegam em seguida
  try {
    dependencias = await api("GET", "/health/dependencias");
  } catch {
    dependencias = null;
  }
  desenharLinhasSaude();
}

function desenharLinhasSaude() {
  const linhas = Object.values(SERVICOS).map((s) => {
    const estado = estadoServicos[s.chave];
    return el("div", { class: "saude-linha" },
      el("span", {}, el("b", {}, `Serviço de ${s.nome}`), el("span", { class: "dica" }, ` · ${s.onde}`)),
      el("span", { class: `selo ${!estado ? "neutro" : estado.estado === "ok" ? "" : "perigo"}` }, estado ? estado.detalhe : "verificando…"));
  });
  if (dependencias) {
    for (const [nome, d] of Object.entries(dependencias.disjuntores)) {
      const classe = d.estado === "FECHADO" ? "" : d.estado === "ABERTO" ? "perigo" : "aviso";
      const texto = d.estado === "FECHADO" ? "fechado (normal)" : d.estado === "ABERTO" ? `aberto · ${d.nova_tentativa_em_segundos}s` : "meio-aberto (testando)";
      linhas.push(el("div", { class: "saude-linha" },
        el("span", {}, el("b", {}, `Disjuntor → ${nome}`), el("span", { class: "dica" }, " · visto pelo Empréstimos")),
        el("span", { class: `selo ${classe}` }, texto)));
    }
    const ultima = dependencias.ultima_reconciliacao;
    $("#resultado-reconciliacao").textContent = ultima
      ? `Última verificação: ${new Date(ultima.momento).toLocaleTimeString("pt-BR")} · ${ultima.verificados} emprestado(s) conferido(s) · ${ultima.liberados.length} preso(s) liberado(s).`
      : "A verificação automática roda a cada 5 minutos.";
  }
  $("#saude-sistema").replaceChildren(...linhas);
}

async function executarReconciliacao() {
  const botao = $("#botao-reconciliar");
  botao.disabled = true;
  try {
    const resultado = await api("POST", "/emprestimos/reconciliacao");
    avisar(resultado.liberados.length
      ? `Exemplares liberados: ${resultado.liberados.join(", ")}.`
      : `Tudo consistente: ${resultado.verificados} exemplar(es) emprestado(s) conferido(s).`);
    desenharSaude();
  } catch (erro) {
    avisar(erro.message, true);
  } finally {
    botao.disabled = false;
  }
}

/* ------------------------------- acervo ------------------------------- */

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

function seloDisponibilidade(disponiveis, total) {
  if (!total) return el("span", { class: "selo neutro" }, "sem exemplares");
  if (!disponiveis) return el("span", { class: "selo aviso" }, "todos emprestados");
  return el("span", { class: "selo" }, `${disponiveis} de ${total} disponíveis`);
}

function cartaoLivro(livro, exemplares) {
  const disponiveis = exemplares.filter((e) => e.status === "DISPONIVEL");
  const acoes = [];
  let detalhes = null;

  if (ehBibliotecario()) {
    detalhes = el("div", { class: "exemplares", hidden: true },
      exemplares.length
        ? exemplares.map((exemplar) =>
            el("div", { class: "exemplar" },
              el("span", {}, el("strong", {}, exemplar.codigo_tombo), ` · id ${exemplar.id}`),
              el("span", { class: "item-acoes" },
                el("span", { class: exemplar.status === "DISPONIVEL" ? "selo" : "selo aviso" }, exemplar.status),
                exemplar.status === "DISPONIVEL"
                  ? el("button", { class: "botao pequeno primario", type: "button", onclick: () => prepararEmprestimo(exemplar, livro) }, "Emprestar")
                  : null)))
        : el("p", { class: "item-meta" }, "Nenhum exemplar cadastrado."),
      el("form", { class: "novo-exemplar", onsubmit: (evento) => criarExemplar(evento, livro.id) },
        el("input", { name: "codigo_tombo", placeholder: "Código de tombo do novo exemplar", required: true, maxlength: 50 }),
        el("button", { class: "botao pequeno", type: "submit" }, "Adicionar")));
    acoes.push(
      el("button", { class: "botao pequeno", type: "button", onclick: () => { detalhes.hidden = !detalhes.hidden; } }, `Exemplares (${exemplares.length})`),
      el("button", { class: "botao pequeno", type: "button", onclick: () => editarLivro(livro) }, "Editar"));
  } else {
    acoes.push(el("button", {
      class: "botao pequeno primario", type: "button", disabled: !disponiveis.length,
      onclick: (evento) => pegarEmprestado(livro, disponiveis, evento.currentTarget),
    }, disponiveis.length ? "Pegar emprestado" : "Indisponível"));
  }

  return el("article", { class: "cartao item" },
    capa(livro.titulo),
    el("div", { class: "item-corpo" },
      el("div", { class: "item-linha" },
        el("div", {}, el("h3", {}, livro.titulo), el("p", { class: "item-meta" }, `${livro.autor} · ISBN ${livro.isbn}`)),
        el("div", { class: "item-acoes" }, seloDisponibilidade(disponiveis.length, exemplares.length), ...acoes)),
      detalhes));
}

/** Aluno: tenta os exemplares disponíveis em ordem; se outro aluno pegar antes, tenta o próximo. */
async function pegarEmprestado(livro, disponiveis, botao) {
  botao.disabled = true;
  botao.textContent = "Reservando…";
  for (const exemplar of disponiveis) {
    try {
      const emp = await acaoPropria("emprestimo.criado", () =>
        api("POST", "/emprestimos", { usuario_id: sessao.usuario.id, exemplar_id: exemplar.id, prazo_dias: 14 }));
      avisar(`“${livro.titulo}” é seu! Devolva até ${formatarData(emp.data_prevista_devolucao)}.`);
      recarregarAbaAtual();
      return;
    } catch (erro) {
      if (erro.message !== "Exemplar não está disponível.") {
        avisar(erro.message, true);
        break;
      }
    }
  }
  if (botao.isConnected) {
    botao.disabled = false;
    botao.textContent = "Pegar emprestado";
  }
  recarregarAbaAtual();
}

async function criarExemplar(evento, livroId) {
  evento.preventDefault();
  try {
    const exemplar = await acaoPropria("exemplar.criado", () =>
      api("POST", `/livros/${livroId}/exemplares`, { codigo_tombo: evento.target.codigo_tombo.value }));
    avisar(`Exemplar ${exemplar.codigo_tombo} cadastrado.`);
    carregarLivros();
  } catch (erro) {
    avisar(erro.message, true);
  }
}

function editarLivro(livro) {
  const f = $("#form-livro");
  f.registro_id.value = livro.id;
  f.titulo.value = livro.titulo;
  f.autor.value = livro.autor;
  f.isbn.value = livro.isbn;
  f.ativo.checked = livro.ativo;
  $("#titulo-form-livro").textContent = `Editar livro #${livro.id}`;
  $("#cancelar-livro").hidden = false;
  f.titulo.focus();
}

function limparFormLivro() {
  const f = $("#form-livro");
  f.reset();
  f.registro_id.value = "";
  $("#titulo-form-livro").textContent = "Novo livro";
  $("#cancelar-livro").hidden = true;
}

async function salvarLivro(evento) {
  evento.preventDefault();
  const f = evento.target;
  const dados = { titulo: f.titulo.value, autor: f.autor.value, isbn: f.isbn.value, ativo: f.ativo.checked };
  try {
    const livro = await acaoPropria(f.registro_id.value ? "livro.atualizado" : "livro.criado", () =>
      f.registro_id.value ? api("PUT", `/livros/${f.registro_id.value}`, dados) : api("POST", "/livros", dados));
    avisar(`Livro “${livro.titulo}” salvo.`);
    limparFormLivro();
    carregarLivros();
  } catch (erro) {
    avisar(erro.message, true);
  }
}

function prepararEmprestimo(exemplar, livro) {
  abrirAba("emprestimos");
  $("#form-emprestimo").exemplar_id.value = exemplar.id;
  $("#info-exemplar").textContent = `Exemplar ${exemplar.codigo_tombo} — ${livro.titulo}`;
  $("#form-emprestimo").usuario_id.focus();
}

/* ------------------------ meus empréstimos (aluno) ------------------------ */

function cartaoEmprestimo(emp, { mostrarUsuario }) {
  const selo = emp.status === "DEVOLVIDO"
    ? el("span", { class: "selo neutro" }, "Devolvido")
    : emp.atrasado ? el("span", { class: "selo perigo" }, "Atrasado") : el("span", { class: "selo" }, "Com você");
  const datas = emp.status === "DEVOLVIDO"
    ? `Emprestado em ${formatarData(emp.data_emprestimo)} · devolvido em ${formatarData(emp.data_devolucao)}`
    : `Emprestado em ${formatarData(emp.data_emprestimo)} · devolver até ${formatarData(emp.data_prevista_devolucao)}`;
  if (mostrarUsuario && emp.status === "ATIVO" && !emp.atrasado) selo.textContent = "Ativo";
  return el("article", { class: "cartao item emprestimo" },
    capa(emp.livro_titulo),
    el("div", { class: "item-corpo" },
      el("div", { class: "item-linha" },
        el("div", {},
          el("h3", {}, emp.livro_titulo),
          el("p", { class: "item-meta" }, mostrarUsuario ? `#${emp.id} · ${emp.usuario_nome} · exemplar ${emp.codigo_tombo}` : `Exemplar ${emp.codigo_tombo}`),
          el("p", { class: "item-meta prazo" }, icone("relogio"), datas)),
        el("div", { class: "item-acoes" },
          selo,
          emp.status === "ATIVO"
            ? el("button", { class: "botao pequeno primario", type: "button", onclick: (e) => devolver(emp, e.currentTarget) }, mostrarUsuario ? "Registrar devolução" : "Devolver")
            : null))));
}

async function carregarMeus() {
  const lista = $("#lista-meus");
  try {
    const emprestimos = await api("GET", "/emprestimos?limit=100");
    const ativos = emprestimos.filter((e) => e.status === "ATIVO");
    const atrasados = ativos.filter((e) => e.atrasado);
    $("#kpis-aluno").replaceChildren(
      kpi("Com você agora", `${ativos.length}/3`, ativos.length >= 3 ? "limite atingido" : `pode pegar mais ${3 - ativos.length}`, "destaque"),
      kpi("Atrasados", atrasados.length, atrasados.length ? "devolva para liberar novos empréstimos" : "tudo em dia", atrasados.length ? "alerta" : ""),
      kpi("Já lidos", emprestimos.length - ativos.length, "empréstimos devolvidos"));
    lista.replaceChildren(
      ...(emprestimos.length
        ? emprestimos.map((emp) => cartaoEmprestimo(emp, { mostrarUsuario: false }))
        : [vazio("Você ainda não pegou nenhum livro. Que tal começar pelo Acervo?")]));
  } catch (erro) {
    lista.replaceChildren(vazio(erro.message));
  }
}

async function devolver(emp, botao) {
  botao.disabled = true;
  try {
    await acaoPropria("emprestimo.devolvido", () => api("POST", `/emprestimos/${emp.id}/devolucao`));
    avisar(`Devolução de “${emp.livro_titulo}” registrada.`);
    recarregarAbaAtual();
  } catch (erro) {
    avisar(erro.message, true);
    botao.disabled = false;
  }
}

/* --------------------------- usuários (bibliotecário) --------------------------- */

async function carregarUsuarios() {
  const lista = $("#lista-usuarios");
  const busca = $("#busca-usuarios");
  const parametros = new URLSearchParams({ limit: "100" });
  if (busca.q.value.trim()) parametros.set("q", busca.q.value.trim());
  if (busca.tipo.value) parametros.set("tipo", busca.tipo.value);
  try {
    const usuarios = await api("GET", `/usuarios?${parametros}`);
    lista.replaceChildren(...(usuarios.length ? usuarios.map(cartaoUsuario) : [vazio("Nenhum usuário encontrado.")]));
  } catch (erro) {
    lista.replaceChildren(vazio(erro.message));
  }
}

function cartaoUsuario(usuario) {
  return el("article", { class: "cartao item" },
    el("span", { class: "avatar", "aria-hidden": "true", style: `background:${corDaCapa(usuario.nome)}` }, iniciais(usuario.nome)),
    el("div", { class: "item-corpo" },
      el("div", { class: "item-linha" },
        el("div", {}, el("h3", {}, usuario.nome), el("p", { class: "item-meta" }, `${usuario.email} · matrícula ${usuario.matricula}`)),
        el("div", { class: "item-acoes" },
          el("span", { class: usuario.tipo === "ALUNO" ? "selo" : "selo neutro" }, usuario.tipo === "ALUNO" ? "Aluno" : "Bibliotecário"),
          usuario.tem_senha ? null : el("span", { class: "selo aviso", title: "Defina uma senha para liberar o login" }, "sem senha"),
          el("button", { class: "botao pequeno", type: "button", onclick: () => verEmprestimosDe(usuario) }, "Empréstimos"),
          el("button", { class: "botao pequeno", type: "button", onclick: () => editarUsuario(usuario) }, "Editar")))));
}

function editarUsuario(usuario) {
  const f = $("#form-usuario");
  f.registro_id.value = usuario.id;
  f.nome.value = usuario.nome;
  f.email.value = usuario.email;
  f.matricula.value = usuario.matricula;
  f.tipo.value = usuario.tipo;
  f.ativo.checked = usuario.ativo;
  f.senha.value = "";
  $("#dica-senha").textContent = usuario.tem_senha ? "(deixe em branco para manter a atual)" : "(defina para liberar o login)";
  $("#titulo-form-usuario").textContent = `Editar usuário #${usuario.id}`;
  $("#cancelar-usuario").hidden = false;
  f.nome.focus();
}

function limparFormUsuario() {
  const f = $("#form-usuario");
  f.reset();
  f.registro_id.value = "";
  $("#dica-senha").textContent = "(mínimo de 6 caracteres)";
  $("#titulo-form-usuario").textContent = "Novo usuário";
  $("#cancelar-usuario").hidden = true;
}

async function salvarUsuario(evento) {
  evento.preventDefault();
  const f = evento.target;
  const dados = { nome: f.nome.value, email: f.email.value, matricula: f.matricula.value, tipo: f.tipo.value, ativo: f.ativo.checked };
  if (f.senha.value) dados.senha = f.senha.value;
  try {
    const usuario = await acaoPropria(f.registro_id.value ? "usuario.atualizado" : "usuario.criado", () =>
      f.registro_id.value ? api("PUT", `/usuarios/${f.registro_id.value}`, dados) : api("POST", "/usuarios", dados));
    avisar(`Usuário “${usuario.nome}” salvo.`);
    limparFormUsuario();
    carregarUsuarios();
  } catch (erro) {
    avisar(erro.message, true);
  }
}

/* -------------------------- empréstimos (bibliotecário) -------------------------- */

let filtroEmprestimos = "";
let usuarioFiltrado = null;

async function carregarOpcoesUsuarios() {
  const select = $("#select-usuario");
  const atual = select.value;
  try {
    const usuarios = await api("GET", "/usuarios?limit=100");
    select.replaceChildren(
      el("option", { value: "" }, "Selecione…"),
      ...usuarios.map((u) => el("option", { value: u.id }, `${u.nome} (${u.matricula})`)));
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
      ? el("div", { class: "cartao item-linha" },
          el("span", {}, "Mostrando empréstimos de ", el("strong", {}, usuarioFiltrado.nome)),
          el("button", { class: "botao pequeno", type: "button", onclick: () => { usuarioFiltrado = null; carregarEmprestimos(); } }, "Mostrar todos"))
      : null;
    lista.replaceChildren(
      ...[aviso].filter(Boolean),
      ...(emprestimos.length ? emprestimos.map((emp) => cartaoEmprestimo(emp, { mostrarUsuario: true })) : [vazio("Nenhum empréstimo encontrado.")]));
  } catch (erro) {
    lista.replaceChildren(vazio(erro.message));
  }
}

async function criarEmprestimo(evento) {
  evento.preventDefault();
  const f = evento.target;
  const botao = $("button[type=submit]", f);
  botao.disabled = true;
  try {
    const emp = await acaoPropria("emprestimo.criado", () => api("POST", "/emprestimos", {
      usuario_id: Number(f.usuario_id.value),
      exemplar_id: Number(f.exemplar_id.value),
      prazo_dias: Number(f.prazo_dias.value),
    }));
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

/* ---------------------------- inicialização ---------------------------- */

document.addEventListener("DOMContentLoaded", () => {
  for (const botao of $$(".perfil")) botao.addEventListener("click", () => escolherPerfil(botao.dataset.perfil));
  $("#form-login").addEventListener("submit", entrar);
  $(".mostrar-senha").addEventListener("click", () => {
    const campo = $("#form-login").senha;
    campo.type = campo.type === "password" ? "text" : "password";
  });
  $("#botao-sair").addEventListener("click", () => encerrarSessao());
  for (const chip of $$(".chip")) {
    chip.addEventListener("click", () => {
      for (const outro of $$(".chip")) outro.classList.toggle("is-ativo", outro === chip);
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
  $("#botao-reconciliar").addEventListener("click", executarReconciliacao);

  escolherPerfil("ALUNO");
  sessao = lerSessaoSalva();
  if (sessao) iniciarApp();
  else mostrarLogin();
  verificarStatus();
});
