# BookNet

**Sistema Distribuído de Gerenciamento de Biblioteca Universitária**  
Disciplina: Sistemas Distribuídos  
Etapa atual: **V5 — Falhas e recuperação concluída**

Entregas concluídas: **V0 (Ideia e arquitetura)**, **V1 (Cliente-servidor)**, **V2 (Sockets / mensagens)**, **V3 (Serviços separados)**, **V4 (Docker)** e **V5 (Falhas e recuperação)**

## Integrantes

- André
- João Henrique
- Luiz Felipe

## Sobre o projeto

O BookNet é um projeto acadêmico da disciplina de Sistemas Distribuídos voltado ao gerenciamento de uma biblioteca universitária. O desenvolvimento é incremental ao longo do semestre, e cada versão se relaciona aos conceitos estudados em aula.

- **V0** reuniu a proposta, a arquitetura conceitual e um dashboard estático de apresentação.
- **V1** entregou a primeira implementação cliente-servidor: uma API FastAPI com catálogo, usuários, empréstimos e devoluções, persistida em PostgreSQL no Neon, e um **Cliente Web funcional**. A falha de concorrência da V0 (dois usuários disputando o mesmo exemplar) foi resolvida no banco.
- **V2** acrescentou **mensagens em tempo real por WebSocket**: quando alguém empresta ou devolve um livro, todas as telas abertas são avisadas na hora.
- **V3** transformou a aplicação única nos **três serviços independentes do desenho da V0**: Catálogo, Usuários e Empréstimos, cada um em seu processo e porta. O Serviço de Empréstimos consulta os outros dois **pela rede**, com tempo limite e compensação em caso de falha.
- **V4** empacotou cada parte em um **contêiner Docker**: um único `docker compose up` sobe a migração, os três serviços e o Cliente Web em qualquer computador com Docker, sem instalar Python.
- **V5** fez o sistema **se recuperar** de falhas: novas tentativas seguras, disjuntor, reconciliação de exemplares presos e reinício automático dos contêineres.

A orquestração continua planejada (V6).

## Problema

Uma biblioteca universitária precisa manter informações coerentes sobre seus usuários, acervo e circulação de exemplares. Esse gerenciamento envolve:

- Identificar os usuários e distinguir alunos de bibliotecários.
- Organizar os dados dos livros, como título, autor e ISBN.
- Diferenciar cada livro de seus exemplares físicos e acompanhar a disponibilidade de cada exemplar.
- Relacionar empréstimos a usuários e exemplares, registrando datas e previsão de devolução.
- Registrar devoluções e refletir a disponibilidade do exemplar para novos empréstimos.

Ao distribuir essas responsabilidades, o projeto também precisa considerar a comunicação pela rede e situações em que os componentes recebem solicitações simultâneas ou deixam de responder.

## Objetivo

O objetivo geral é desenvolver um sistema de gerenciamento de biblioteca universitária que organize usuários, livros, exemplares, empréstimos e devoluções em componentes com responsabilidades definidas.

O objetivo acadêmico é estudar comunicação entre processos e distribuição de responsabilidades, observando seus efeitos sobre concorrência, consistência, disponibilidade, escalabilidade e tolerância a falhas.

## Usuários

| Perfil | Funcionalidades | Situação |
| --- | --- | --- |
| **Aluno** | Pesquisar livros, verificar disponibilidade, solicitar empréstimos, realizar devoluções e consultar seus empréstimos. | Implementado, com login: o aluno só pega livros para si e só vê os próprios empréstimos. |
| **Bibliotecário** | Cadastrar e alterar livros e exemplares, consultar usuários e acompanhar empréstimos. | Implementado, com login de administrador e painel da biblioteca. |

Cada perfil entra com matrícula e senha e vê apenas o que lhe cabe. As permissões são conferidas pelos próprios serviços (veja "Login e perfis").

## Fora do escopo inicial

- Pagamentos.
- Multas complexas.
- Recomendação com IA.
- Aplicativo mobile.
- Reconhecimento facial.
- Integrações externas.

## Arquitetura

![Arquitetura conceitual do BookNet: Cliente Web envia solicitações aos serviços de Usuários, Catálogo e Empréstimos; os três acessam o Banco de Dados. Empréstimos consulta diretamente Usuários e Catálogo.](docs/arquitetura.svg)

A arquitetura possui cinco componentes: **Cliente Web**, **Serviço de Usuários**, **Serviço de Catálogo**, **Serviço de Empréstimos** e **Banco de Dados**. A [documentação da arquitetura](docs/arquitetura.md) preserva o registro da V0. Desde a V3, o código segue esse desenho.

### Arquitetura implementada (V3)

```text
                       Navegador · Cliente Web (porta 8080)
                 │ HTTP/REST + WebSocket          │                      │
                 ▼                                ▼                      ▼
   ┌──────────────────────────┐   ┌─────────────────────────┐   ┌──────────────────────┐
   │ Serviço de Catálogo 8001 │   │ Serviço de Usuários 8002│   │ Serviço de           │
   │ livros, exemplares       │   │ alunos, bibliotecários  │   │ Empréstimos 8003     │
   └────────────▲─────────────┘   └───────────▲─────────────┘   │ empréstimos,         │
                │ POST /interno/exemplares/…   │ GET /usuarios/{id}│ devoluções          │
                │ (retirada / liberação)       │                   └──┬───────────────────┘
                └──────────────────────────────┴───── HTTP, timeout 3s ┘
                                    │ cada serviço acessa só as próprias tabelas
                                    ▼
             PostgreSQL no Neon: livros, exemplares │ usuarios │ emprestimos
```

| Serviço | Porta | Dono de | Código | Detalhes |
| --- | --- | --- | --- | --- |
| Catálogo | 8001 | `livros`, `exemplares` | `backend/servicos/catalogo.py` | [servico-catalogo/](servico-catalogo/README.md) |
| Usuários | 8002 | `usuarios` | `backend/servicos/usuarios.py` | [servico-usuarios/](servico-usuarios/README.md) |
| Empréstimos | 8003 | `emprestimos` | `backend/servicos/emprestimos.py` | [servico-emprestimos/](servico-emprestimos/README.md) |

Cada serviço é um **processo separado**, com sua própria documentação (`/docs`), verificações de saúde (`/health` e `/health/database`) e canal de eventos (`/ws/eventos`). Se um deles cair, os outros continuam no ar.

O banco continua sendo um único PostgreSQL compartilhado, como no desenho da V0. A regra, porém, é que **cada serviço só lê e escreve as próprias tabelas**. O que pertence a outro serviço é pedido pela rede. As chaves estrangeiras entre as tabelas foram mantidas como proteção extra. Elas são um ponto de acoplamento conhecido: uma separação completa daria um banco a cada serviço.

## Modelos implementados

| Modelo / tabela | Serviço | Campos | Regras principais |
| --- | --- | --- | --- |
| `Livro` / `livros` | Catálogo | `id`, `titulo`, `autor`, `isbn`, `ativo`, `criado_em`, `atualizado_em` | ISBN único (string até 20); título e autor obrigatórios até 255; `ativo` padrão `true`. |
| `Exemplar` / `exemplares` | Catálogo | `id`, `livro_id`, `codigo_tombo`, `status`, `criado_em` | Livro obrigatório (FK `RESTRICT`); código de tombo único; status `DISPONIVEL` ou `EMPRESTADO`. Todo exemplar nasce `DISPONIVEL`. |
| `Usuario` / `usuarios` | Usuários | `id`, `nome`, `email`, `matricula`, `tipo`, `ativo`, `criado_em`, `atualizado_em` | E-mail e matrícula únicos; e-mail normalizado em minúsculas; tipo `ALUNO` ou `BIBLIOTECARIO`. |
| `Emprestimo` / `emprestimos` | Empréstimos | `id`, `usuario_id`, `exemplar_id`, `data_emprestimo`, `data_prevista_devolucao`, `data_devolucao`, `status`, `usuario_nome`, `codigo_tombo`, `livro_id`, `livro_titulo` | Status `ATIVO` ou `DEVOLVIDO`; `data_devolucao` vazia se e somente se `ATIVO`; **no máximo um empréstimo ATIVO por exemplar** (índice único parcial). |

As regras são garantidas em duas camadas. Os schemas Pydantic validam a entrada (respondendo `422`), e as constraints do banco (`UNIQUE`, `CHECK`, `FOREIGN KEY`) protegem os dados mesmo contra escritas que não passem pelos serviços. Nenhum registro é excluído: livros e usuários são desativados com `ativo = false`.

**Por que o empréstimo guarda `usuario_nome`, `codigo_tombo` e `livro_titulo`?** Desde a V3, o Serviço de Empréstimos não consulta as tabelas dos outros serviços. Ele guarda uma **cópia** desses dados no momento do empréstimo (migration `0003`). Com isso, a lista de empréstimos funciona mesmo com Usuários e Catálogo fora do ar. A contrapartida é que, se o usuário mudar de nome depois, os empréstimos antigos continuam com o nome da época. É um registro histórico, como um recibo.

## Endpoints

| Serviço | Método | Rota | Comportamento |
| --- | --- | --- | --- |
| todos | `GET` | `/` | Identificação, ex.: `{"projeto":"BookNet","servico":"catalogo","status":"online","versao":"V3"}`. |
| todos | `GET` | `/health` | Serviço respondendo: `{"status":"ok","servico":"…"}`. |
| todos | `GET` | `/health/database` | `SELECT 1` no banco: `200 online` ou `503 offline`. |
| todos | `WS` | `/ws/eventos?token=…` | Canal de eventos do serviço (V2); exige login. |
| Usuários | `POST` | `/auth/login` | Entrar: `{"matricula", "senha", "perfil"}` → token de sessão. |
| Usuários | `GET` | `/auth/eu` | Dados de quem está logado. |
| Empréstimos | `GET` | `/health/dependencias` | Estado dos disjuntores e da última reconciliação (V5). |
| Empréstimos | `POST` | `/emprestimos/reconciliacao` | Libera exemplares presos (V5, bibliotecário). |
| Catálogo | `GET` | `/livros` | Lista livros ativos; `q` pesquisa título, autor e ISBN; paginação `skip`/`limit`. |
| Catálogo | `GET` | `/livros/{id}` | Consulta um livro (inclusive inativo). |
| Catálogo | `POST` | `/livros` | Cadastra livro (`201`; `409` se o ISBN já existe). |
| Catálogo | `PUT` | `/livros/{id}` | Substitui os dados do livro (também usado para desativar). |
| Catálogo | `GET` | `/livros/{id}/exemplares` | Lista os exemplares do livro e seus status. |
| Catálogo | `POST` | `/livros/{id}/exemplares` | Cadastra exemplar (`409` se o tombo já existe). |
| Catálogo | `GET` | `/exemplares/{id}` | Consulta a disponibilidade de um exemplar. |
| Catálogo (interno) | `POST` | `/interno/exemplares/{id}/retirada` | Reserva atômica do exemplar para um empréstimo. Exige `X-Servico-Token`. |
| Catálogo (interno) | `POST` | `/interno/exemplares/{id}/liberacao` | Devolve o exemplar ao acervo; idempotente. Exige `X-Servico-Token`. |
| Usuários | `GET` | `/usuarios` | Lista usuários ativos; `q` pesquisa nome, e-mail e matrícula; filtro `tipo`. |
| Usuários | `GET` | `/usuarios/{id}` | Consulta um usuário. |
| Usuários | `POST` | `/usuarios` | Cadastra usuário (`409` para e-mail ou matrícula repetidos). |
| Usuários | `PUT` | `/usuarios/{id}` | Substitui os dados do usuário (também usado para desativar). |
| Empréstimos | `GET` | `/emprestimos` | Lista empréstimos, mais recentes primeiro; filtros `usuario_id`, `status` e `atrasados=true`. |
| Empréstimos | `GET` | `/emprestimos/{id}` | Consulta um empréstimo. |
| Empréstimos | `POST` | `/emprestimos` | Registra empréstimo: `{"usuario_id":1,"exemplar_id":4,"prazo_dias":14}`. |
| Empréstimos | `POST` | `/emprestimos/{id}/devolucao` | Registra a devolução e libera o exemplar no Catálogo. |

Exceto `/`, `/health`, `/health/database` e `/auth/login`, todas as rotas exigem o cabeçalho `Authorization: Bearer <token>`. As rotas de cadastro e alteração (livros, exemplares, usuários) e a reconciliação exigem perfil de **bibliotecário**. O aluno só acessa os próprios dados e empréstimos.

Documentação interativa de cada serviço: [8001/docs](http://127.0.0.1:8001/docs), [8002/docs](http://127.0.0.1:8002/docs) e [8003/docs](http://127.0.0.1:8003/docs).

### Regras de empréstimo

Um empréstimo é aprovado somente se:

1. O usuário existe (`404`) e está ativo (`409`). *Verificado pelo Serviço de Usuários.*
2. O usuário tem menos de **3 empréstimos ativos** (`409`). *Verificado pelo Serviço de Empréstimos.*
3. O usuário **não tem empréstimo em atraso** (`409`). *Verificado pelo Serviço de Empréstimos.*
4. O exemplar existe (`404`), pertence a um livro ativo (`409`) e está **disponível** (`409`). *Verificado pelo Serviço de Catálogo.*

O prazo padrão é de 14 dias, configurável de 1 a 60 em `prazo_dias`. Devolver duas vezes retorna `409`.

### Erros e segurança

| Situação | Resposta |
| --- | --- |
| Entrada inválida | `422` (validação padrão do FastAPI). |
| Recurso inexistente | `404`. |
| Duplicidade ou regra de negócio violada | `409` com mensagem clara (ex.: `E-mail já cadastrado.`). |
| Outras violações de integridade | `400`. |
| Sem login ou com sessão expirada | `401`. |
| Sem permissão (ex.: aluno cadastrando livro) ou rota interna sem o token | `403`. |
| Muitas senhas erradas | `429`. |
| Banco ou outro serviço indisponível | `503`. |
| Outro serviço não respondeu no prazo | `504`. |
| Erro inesperado | `500` com mensagem genérica. |

Respostas e logs nunca incluem SQL, traceback, connection string, host, usuário, senha ou token. Cada serviço usa uma sessão de banco por requisição (`get_db()`), com rollback automático em caso de falha.

## Cliente Web

A pasta `cliente/` contém a interface funcional em HTML, CSS e JavaScript puro, sem dependências. Ela começa pela **tela de login** e depois mostra a área do **aluno** (Acervo e Meus empréstimos) ou do **bibliotecário** (Painel, Acervo, Usuários e Empréstimos). Veja "Login e perfis". Desde a V3, ela conversa com **três endereços** e escolhe o serviço pelo início da rota: `/usuarios` vai para a porta 8002, `/emprestimos` para a 8003 e o resto para a 8001.

| Aba | O que faz |
| --- | --- |
| **Acervo** | Pesquisa livros, mostra quantos exemplares estão disponíveis, lista exemplares e seus status, cadastra e edita livros e exemplares, e tem o botão **Emprestar** em cada exemplar disponível. |
| **Usuários** | Pesquisa e filtra por tipo, cadastra e edita alunos e bibliotecários, e dá acesso aos empréstimos de cada usuário. |
| **Empréstimos** | Registra empréstimos, lista com filtros (todos, ativos, atrasados, devolvidos), registra devoluções e mostra o painel **Ao vivo**. |

O cabeçalho mostra um indicador por serviço (**Catálogo**, **Usuários**, **Empréstimos**), verde ou vermelho, e o estado do tempo real (**Ao vivo 3/3 · N telas**). Se um serviço estiver fora do ar, a aba correspondente mostra *"Serviço de Empréstimos fora do ar (porta 8003)"*, e as demais continuam funcionando. Os textos vindos dos serviços são inseridos com `textContent`, nunca como HTML.

O `dashboard/` continua sendo a apresentação acadêmica estática da V0.

## V2: Sockets e mensagens em tempo real

Na V1, toda comunicação segue o modelo **requisição → resposta**: o cliente pergunta e o servidor responde. Se o André empresta um livro no computador dele, a tela do João só fica sabendo quando o João recarrega a página.

A V2 acrescenta um **canal de mensagens por WebSocket**: uma conexão de socket que fica aberta entre cada cliente e o servidor. Quando algo muda, **o servidor toma a iniciativa** e envia uma mensagem a todos os clientes conectados (*broadcast*).

```text
 Computador do André                 Serviço (Computador A)             Computador do João
 ───────────────────                 ──────────────────────             ──────────────────
 POST /emprestimos ───── HTTP ─────▶ grava no banco (commit)
        ◀────────────── 201 ──────── responde
                                     publica "emprestimo.criado" ──WS──▶ aviso "AO VIVO" +
                                     (para todas as conexões)            lista atualizada
```

Na V3, cada serviço tem o seu canal e avisa sobre o próprio domínio. O cliente se conecta aos três.

### Formato das mensagens

Cada mensagem é um JSON com três campos:

```json
{
  "tipo": "emprestimo.criado",
  "dados": {"id": 8, "usuario_nome": "Bibliotecária BookNet", "livro_titulo": "Projeto de Banco de Dados", "codigo_tombo": "3828-01", "status": "ATIVO"},
  "momento": "2026-10-19T18:23:12.524Z"
}
```

| Tipo | Canal (V3) | Quando é enviada |
| --- | --- | --- |
| `conectado` | todos | Só para quem acabou de conectar, com o número de conexões abertas. |
| `conexoes.alteradas` | todos | Para todos, quando alguém conecta ou desconecta. |
| `emprestimo.criado` / `emprestimo.devolvido` | Empréstimos | Depois de um empréstimo ou de uma devolução confirmados no banco. |
| `livro.criado` / `livro.atualizado` | Catálogo | Cadastro ou alteração de livro. |
| `exemplar.criado` | Catálogo | Cadastro de exemplar. |
| `usuario.criado` / `usuario.atualizado` | Usuários | Cadastro ou alteração de usuário. |
| `pong` | todos | Resposta a uma mensagem `ping` enviada pelo cliente, para verificar se o canal está vivo. |

### Decisões de projeto

- **O aviso só sai depois do commit.** A publicação roda como tarefa em segundo plano, depois que a transação foi confirmada e a resposta HTTP enviada. Uma operação recusada (`404`, `409`) ou desfeita não gera mensagem, então nenhum cliente recebe aviso de algo que não aconteceu.
- **Conexões quebradas não travam as outras.** Se o envio para um cliente falhar (por exemplo, o Wi-Fi dele caiu), a conexão é removida e as demais continuam recebendo.
- **Reconexão automática.** Se um serviço cair, o cliente tenta de novo após 1s, 2s, 4s… (até 30s) e volta sozinho quando ele retorna.
- **Segurança.** O CORS não protege WebSockets, então cada serviço confere a origem de cada conexão com as mesmas regras do HTTP. Uma página de outro site recebe código `1008` e é recusada.
- **Mensagens não substituem o banco.** Elas só avisam: quem perder uma mensagem (por exemplo, com a página fechada) continua vendo os dados corretos ao consultar os serviços. Garantia de entrega fica para a V5.

### Como demonstrar

1. Inicie os serviços e o Cliente Web (veja "Como executar") e abra o cliente em **dois computadores** ou em duas janelas.
2. Em uma delas, empreste ou devolva um exemplar.
3. A outra mostra o aviso **AO VIVO**, registra o evento no painel "Ao vivo" da aba Empréstimos e atualiza a lista sozinha.

Também há um cliente de terminal, que escuta os três canais e mostra que eles não dependem do navegador:

```powershell
.\.venv\Scripts\python.exe scripts\monitor_eventos.py                 # mesma máquina
.\.venv\Scripts\python.exe scripts\monitor_eventos.py 192.168.0.101   # serviços em outro computador
```

## V3: Serviços separados

Até a V2, Catálogo, Usuários e Empréstimos eram partes de **um único programa**. Se ele caísse, tudo caía junto. Para Empréstimos saber se um exemplar estava disponível, bastava olhar a tabela do lado.

Na V3, cada um virou um **processo independente**, e a pergunta "o exemplar está disponível?" passou a ser uma **mensagem pela rede**. É exatamente o fluxo planejado no Checkpoint 01:

```text
Cliente Web
    │ POST /emprestimos {"usuario_id": 2, "exemplar_id": 5}
    ▼
Serviço de Empréstimos (8003)
    ├─1─▶ Serviço de Usuários (8002):   GET /usuarios/2               "existe e está ativo?"
    ├─2── regras locais: menos de 3 ativos? nenhum atrasado?
    ├─3─▶ Serviço de Catálogo (8001):   POST /interno/exemplares/5/retirada   "reserve para mim"
    └─4── grava o empréstimo na tabela emprestimos
              │ falhou? ──▶ compensação: POST /interno/exemplares/5/liberacao
              ▼
         201 Created + evento "emprestimo.criado"
```

### Decisões de projeto

- **Quem é dono do dado decide sobre ele.** A retirada atômica do exemplar (`UPDATE … WHERE status='DISPONIVEL'`) mudou do Empréstimos para o **Catálogo**, que é o dono dos exemplares. Com pedidos simultâneos, só um recebe `200`; os outros recebem `409`. A falha 2 continua resolvida, agora entre serviços (veja o teste abaixo).
- **Saga com compensação.** Não existe uma transação única que abranja dois serviços. Se o passo 4 falhar depois de o Catálogo já ter reservado o exemplar (passo 3), o Empréstimos **desfaz** o passo 3 pedindo a liberação. Se até a compensação falhar, o problema fica registrado no log; a V5 vai tratar isso com novas tentativas.
- **Tempo limite em toda chamada.** Cada chamada a outro serviço espera no máximo 3 segundos (`BOOKNET_TIMEOUT_SERVICOS`). O usuário recebe uma resposta clara em vez de uma tela travada: **503** quando o serviço está desligado e **504** quando não respondeu a tempo (falha 3).
- **Devolução segura.** A devolução só é gravada se o Catálogo confirmar a liberação do exemplar. Se ele estiver fora do ar, nada muda e a devolução pode ser repetida depois. A liberação é **idempotente** (repetir não causa efeito extra), o que permite tentar de novo com segurança.
- **Rotas internas protegidas.** Retirada e liberação ficam em `/interno/…` e exigem o cabeçalho `X-Servico-Token`, um segredo compartilhado entre os serviços (`BOOKNET_TOKEN_INTERNO` no `.env`). Sem ele, a resposta é `403`. O navegador nunca chama essas rotas.
- **Cópia dos dados no empréstimo.** O Empréstimos guarda nome do usuário, título e tombo no próprio registro (veja "Modelos implementados"), então a lista de empréstimos funciona sem os outros serviços.
- **Limite de 3 por usuário.** Na V1 era garantido com `SELECT … FOR UPDATE` na tabela de usuários. Essa tabela agora pertence a outro serviço, então o Empréstimos usa uma *trava consultiva* do PostgreSQL (`pg_advisory_xact_lock`) identificada pelo número do usuário.

### Concorrência entre serviços (falha 2)

`scripts/teste_concorrencia.py` dispara pedidos **simultâneos** de todos os usuários para o mesmo exemplar. Cada pedido atravessa Empréstimos → Usuários → Catálogo. Saída registrada no Neon com os três serviços rodando (3 execuções, sempre 1 aprovado):

```text
Exemplar disputado: id=15 tombo=CONC-1792440399
  Bibliotecária BookNet     HTTP 201  empréstimo 12
  André                     HTTP 409  Exemplar não está disponível.
  Luiz Felipe               HTTP 409  Exemplar não está disponível.
  João Henrique             HTTP 409  Exemplar não está disponível.
Pedidos simultâneos: 4 | aprovados: 1
RESULTADO: OK - apenas um empréstimo registrado.
```

### Demonstrando as falhas 1 e 3

O iniciador permite subir o sistema sem algum serviço (`--sem`):

```powershell
.\.venv\Scripts\python.exe scripts\iniciar_servicos.py --sem emprestimos   # falha 1
.\.venv\Scripts\python.exe scripts\iniciar_servicos.py --sem catalogo      # falha 3
```

| Cenário | O que acontece (verificado contra o Neon) |
| --- | --- |
| **Empréstimos fora do ar** (falha 1) | O indicador **Empréstimos** fica vermelho e o tempo real cai para 2/3. **O Acervo e os Usuários continuam funcionando normalmente.** A aba Empréstimos mostra "Serviço de Empréstimos fora do ar (porta 8003)". |
| **Catálogo fora do ar** (falha 3) | Um pedido de empréstimo recebe na hora `503 Serviço de Catálogo indisponível no momento.`, sem travar. A lista de empréstimos e o Serviço de Usuários continuam respondendo. |
| **Catálogo lento** (falha 3) | Depois de 3 segundos, `504 O Serviço de Catálogo não respondeu a tempo.` (coberto pelos testes automatizados). |

## V4: Docker

Até a V3, para rodar o BookNet era preciso ter o Python certo instalado, criar o `.venv`, instalar as dependências e abrir quatro programas. Funcionava "na minha máquina", mas cada computador novo era uma nova instalação.

Na V4, cada parte do sistema vira um **contêiner**: um pacote isolado que leva junto o próprio Python, as bibliotecas e o código. Em qualquer computador com Docker, **um único comando** sobe o sistema inteiro, sempre do mesmo jeito.

```text
                                 docker compose up
                                        │
       ┌───────────────┬───────────────┼────────────────┬────────────────┐
       ▼               ▼               ▼                ▼                ▼
   migracao        catalogo        usuarios        emprestimos        cliente
 (alembic, roda    :8001           :8002           :8003              nginx :8080
  e termina)           ▲               ▲               │
                       └── http://catalogo:8001 ───────┤   rede interna do compose:
                                   http://usuarios:8002┘   cada contêiner é achado pelo nome
       │               │               │                │
       └───────────────┴───────────────┴────────────────┘──▶ PostgreSQL no Neon (internet)
```

| Arquivo | Para que serve |
| --- | --- |
| `Dockerfile` | Receita da imagem dos serviços: parte de `python:3.13-slim`, instala o `requirements.txt` e copia `backend/` e `migrations/`. **A mesma imagem** vira os três serviços; só muda o comando de cada contêiner. |
| `cliente/Dockerfile` | Imagem do Cliente Web servido pelo **nginx**, um servidor web leve para arquivos estáticos. |
| `docker-compose.yml` | Descreve o sistema inteiro: quais contêineres existem, as portas, a ordem de subida e os endereços entre eles. |
| `.dockerignore` | Lista o que **nunca** entra numa imagem, a começar pelo `.env`. |

### Decisões de projeto

- **Uma imagem, três serviços.** Catálogo, Usuários e Empréstimos usam o mesmo código-base, então compartilham a imagem `booknet-servicos:v4` (274 MB). O compose escolhe qual `uvicorn backend.servicos.X:app` cada contêiner executa.
- **Endereços pelo nome do serviço.** Dentro do compose, o Empréstimos chama `http://catalogo:8001` e `http://usuarios:8002`. O Docker tem um DNS interno que resolve esses nomes. Por isso os endereços vêm de variáveis de ambiente (`BOOKNET_URL_*`) desde a V3: o código não muda, só a configuração.
- **Migração antes de tudo.** O contêiner `migracao` roda `alembic upgrade head` e termina. Os serviços só sobem depois que ele termina **com sucesso** (`service_completed_successfully`). Se o banco estiver com estrutura antiga, ela é atualizada automaticamente; se já estiver em dia, nada muda.
- **Segredos fora da imagem.** O `.env` está no `.dockerignore` e só chega aos contêineres em tempo de execução, pelo `env_file`. Verificado: a imagem não contém o arquivo. Uma imagem pode ser compartilhada sem expor a senha do banco.
- **Sem administrador dentro do contêiner.** Os serviços rodam como o usuário `booknet` (uid 10001), não como `root`. Se alguém explorar uma falha no serviço, terá menos poder dentro do contêiner.
- **Camadas em cache.** O `Dockerfile` instala as dependências **antes** de copiar o código. Mudar só o código não reinstala as bibliotecas, então a reconstrução leva segundos.

### Como usar

Pré-requisitos: **Docker Desktop** instalado e com "Engine running", e o arquivo `.env` na raiz `booknet/` (veja "Como executar"). Não é preciso ter Python instalado.

```powershell
docker compose up --build          # sobe tudo e mostra os logs (Ctrl+C encerra)
docker compose up --build -d       # sobe em segundo plano
docker compose ps                  # lista os contêineres e seus estados
docker compose logs -f emprestimos # acompanha os logs de um serviço
docker compose stop emprestimos    # derruba um serviço (falha 1)
docker compose start emprestimos   # religa
docker compose down                # remove os contêineres (os dados ficam no Neon)
```

Acesse **http://localhost:8080**. As portas 8001 a 8003 e 8080 ficam abertas também para a rede, então a demonstração em duas máquinas funciona da mesma forma: o Computador B abre `http://IP_DO_COMPUTADOR_A:8080`.

### Verificado nesta entrega

| Verificação | Resultado |
| --- | --- |
| `docker compose up --build -d` | `migracao` terminou com código 0; `catalogo`, `usuarios`, `emprestimos` e `cliente` em execução. |
| Saúde dos serviços | Os três responderam `banco online` (Neon) a partir dos contêineres. |
| Rede interna | De dentro do contêiner `emprestimos`, `http://catalogo:8001` e `http://usuarios:8002` responderam. |
| Concorrência (falha 2) | `teste_concorrencia.py` contra os contêineres: 2 execuções, sempre 1 aprovado. |
| Falha 1 | Com `docker compose stop emprestimos`, o indicador ficou vermelho e o Acervo continuou funcionando no navegador. |
| Segurança da imagem | Usuário `booknet` (não `root`); `/app` contém só `alembic.ini`, `backend`, `migrations` e `requirements.txt`, sem `.env`. |

## Login e perfis

O sistema abre numa **tela de login** com duas abas, **Aluno** e **Bibliotecário**. A pessoa entra com a **matrícula** e a **senha**, e cada perfil vê um sistema diferente:

| | Aluno | Bibliotecário (administrador) |
| --- | --- | --- |
| Abas | Acervo · Meus empréstimos | Painel · Acervo · Usuários · Empréstimos |
| Acervo | Pesquisa e **"Pegar emprestado"** com um clique (o sistema escolhe um exemplar disponível) | Cadastra e edita livros e exemplares |
| Empréstimos | Vê e devolve **só os próprios** | Vê todos, registra para qualquer usuário, registra devoluções |
| Usuários | Vê só os próprios dados | Cadastra alunos e bibliotecários e define senhas |
| Painel | — | Números do acervo, eventos ao vivo, saúde dos serviços e disjuntores, reconciliação |
| Avisos ao vivo | Acervo e os próprios empréstimos | Tudo |

### Como funciona (e por que isso é distribuído)

```text
 1. Navegador ── POST /auth/login {matrícula, senha} ──▶ Serviço de Usuários
                                                         confere a senha (hash PBKDF2)
              ◀──────────────── token de sessão (JWT) ── assina com o segredo compartilhado
 2. Navegador ── GET /livros   + "Authorization: Bearer <token>" ──▶ Catálogo     ┐ cada serviço
    Navegador ── POST /emprestimos + "Authorization: Bearer <token>" ──▶ Empréstimos ┘ confere sozinho
```

- **Senhas nunca são guardadas.** O banco guarda só o resultado do **PBKDF2-SHA256** com um *sal* aleatório por usuário e 600 mil repetições: rápido para um login, lento demais para quem tentasse adivinhar milhões de senhas. A comparação é feita em tempo constante.
- **Token de sessão assinado (JWT HS256).** Leva o número do usuário, o nome, o perfil e a validade (8 horas), assinados com `BOOKNET_SEGREDO_SESSAO`. Trocar qualquer letra, por exemplo `ALUNO` por `BIBLIOTECARIO`, invalida a assinatura. Tokens sem assinatura (`"alg": "none"`) também são recusados.
- **Autenticação sem ponto central.** Os três serviços têm o mesmo segredo, então **cada um confere o token sozinho**, sem perguntar ao Serviço de Usuários a cada pedido. Mesmo com o Serviço de Usuários fora do ar, quem já entrou continua usando o Catálogo e os Empréstimos.
- **As regras valem nos serviços, não só na tela.** Um aluno que chamar a API direto para cadastrar um livro recebe `403`. Sem login, a resposta é `401`. Só `/health`, `/` e `/auth/login` são públicos.
- **Freio contra adivinhação.** 5 senhas erradas em 5 minutos bloqueiam aquela matrícula temporariamente (`429`). A mensagem é sempre a mesma ("Matrícula ou senha incorretos"), para não revelar quais matrículas existem.
- **WebSocket com login.** O canal `/ws/eventos?token=...` recusa conexões sem token válido (código `1008`) e filtra as mensagens: um aluno não recebe os empréstimos dos outros.
- **Chamadas internas** entre serviços continuam usando o `X-Servico-Token` da V3.

### Primeiro acesso e senhas

Usuários sem senha existem, mas ainda não conseguem entrar (aparecem com o selo **"sem senha"** na aba Usuários). O bibliotecário define ou troca senhas pela tela de Usuários. Para criar o **primeiro** bibliotecário, use o script, que pede a senha sem mostrá-la:

```powershell
.\.venv\Scripts\python.exe scripts\definir_senha.py BIB-001
```

As senhas de demonstração **não ficam no repositório**: foram combinadas com o grupo fora do GitHub.

## V5: Falhas e recuperação

Até a V4, o BookNet **detectava** falhas: respondia `503` ou `504` e mostrava que um serviço tinha caído. Na V5 ele passa a **se recuperar** sozinho. Em sistemas distribuídos, falhas não são exceção, são rotina: a rede oscila, um serviço reinicia, na nuvem gratuita um serviço dorme. O sistema precisa sobreviver a elas.

| Mecanismo | Problema que resolve | Onde está |
| --- | --- | --- |
| **Novas tentativas** com espera crescente | Falha passageira (o serviço piscou, a conexão caiu por um instante) | `backend/servicos_remotos.py` |
| **Disjuntor** (*circuit breaker*) | Serviço caído de vez: evita que todos fiquem esperando e dá tempo para ele se recuperar | `backend/resiliencia.py` |
| **Reconciliação** | Exemplar "preso" como emprestado sem empréstimo, quando até a compensação falhou | `backend/reconciliacao.py` |
| **Reinício automático** | O processo de um serviço morreu | `restart: unless-stopped` no `docker-compose.yml` |

### Novas tentativas: só quando repetir é seguro

Quando a chamada a outro serviço falha, o Empréstimos tenta de novo até 3 vezes, esperando cada vez mais (0,3 s, 0,6 s, 1,2 s…), com um pouco de aleatoriedade para que vários clientes não tentem todos no mesmo instante. **Mas nem toda operação pode ser repetida:**

| Situação | Repete? | Por quê |
| --- | --- | --- |
| Falha de conexão (pedido nem chegou) | Sim, qualquer operação | O outro serviço não fez nada. |
| Erro 5xx ao **consultar usuário** ou **liberar exemplar** | Sim | Operações **idempotentes**: repetir não muda o resultado. |
| Erro 5xx ou tempo esgotado na **retirada de exemplar** | **Não** | A retirada pode ter acontecido. Repetir poderia reservar o exemplar duas vezes, e quem corrige isso é a reconciliação. |

### Disjuntor

```text
 FECHADO ──3 falhas seguidas──▶ ABERTO ──30 s──▶ MEIO_ABERTO ──sucesso──▶ FECHADO
                                   ▲                  │
                                   └──── falha ───────┘
```

Com o circuito **aberto**, as chamadas àquele serviço falham **na hora**, com `503 Serviço de Catálogo indisponível no momento. Nova tentativa em 27 s.`, em vez de cada usuário esperar o tempo limite. Passados 30 segundos, uma chamada de teste é liberada: se der certo, tudo volta ao normal. O estado dos disjuntores fica em `GET /health/dependencias`, no Serviço de Empréstimos.

### Reconciliação

A saga da V3 compensa falhas, mas e se **a própria compensação falhar**, por exemplo com o Catálogo caindo exatamente naquele segundo? O exemplar ficaria marcado como emprestado para sempre. A reconciliação compara as duas visões e corrige a diferença:

```text
Catálogo:     exemplares EMPRESTADO há mais de 2 minutos   {4, 7, 9}
Empréstimos:  exemplares com empréstimo ATIVO               {4, 9}
                                                            ──────
presos → liberar no Catálogo                                {7}
```

- Roda **sozinha a cada 5 minutos** e também pode ser disparada em `POST /emprestimos/reconciliacao`.
- Ignora exemplares que mudaram há menos de **2 minutos**, porque eles podem pertencer a um empréstimo que ainda está sendo gravado. Para isso, o Catálogo registra em `exemplares.alterado_em` o momento de cada mudança (migration `0004`).
- Se o Catálogo estiver fora do ar, a rodada é adiada para o próximo ciclo, sem alterar nada.

### Verificado nesta entrega

| Verificação | Resultado |
| --- | --- |
| Testes automáticos da V5 (`tests/test_resiliencia.py`) | 11 testes: transições do disjuntor; falha passageira superada na 2ª e 3ª tentativas com espera crescente; retirada não repetida após erro 5xx; liberação repetida; disjuntor aberto respondendo sem chamar o serviço e fechando quando ele volta; reconciliação liberando só o exemplar preso fora da carência; reconciliação adiada com o Catálogo fora do ar; execução periódica que continua após uma falha. |
| Reinício automático (Docker) | O processo do Empréstimos foi encerrado dentro do contêiner; o Docker o reiniciou sozinho (contador de reinícios 0 → 1) e o serviço voltou a responder em menos de 1 segundo. |
| Reconciliação no Neon | `POST /emprestimos/reconciliacao`: 0 exemplares presos (dados consistentes). |

## BookNet na nuvem (Render)

Para usar o BookNet de qualquer lugar (faculdade, celular, casa de um colega) sem depender de um computador ligado, o sistema roda no **Render** (render.com), no plano gratuito, sem cartão de crédito. O banco continua no Neon.

```text
        Qualquer navegador ──HTTPS──▶ booknet-luizfelipe.onrender.com (Cliente Web)
                                        │            │              │
                                        ▼            ▼              ▼
                                   Catálogo      Usuários      Empréstimos   ← três máquinas no Render
                                        ▲            ▲              │
                                        └────── HTTPS ──────────────┘
                                                     ▼
                                           PostgreSQL no Neon
```

| Componente | Endereço | Tipo no Render |
| --- | --- | --- |
| Cliente Web | https://booknet-luizfelipe.onrender.com | Static Site (gratuito) |
| Serviço de Catálogo | https://booknet-luizfelipe-catalogo.onrender.com | Web Service Docker (gratuito) |
| Serviço de Usuários | https://booknet-luizfelipe-usuarios.onrender.com | Web Service Docker (gratuito) |
| Serviço de Empréstimos | https://booknet-luizfelipe-emprestimos.onrender.com | Web Service Docker (gratuito) |

Tudo é descrito no arquivo [`render.yaml`](render.yaml) (um *Blueprint*). Os serviços usam o mesmo `Dockerfile` da V4. Cada um roda em uma máquina diferente, e o Empréstimos chama os outros pelo endereço público, com HTTPS e o token interno. O cliente detecta que está na nuvem e usa os endereços de [`cliente/config.js`](cliente/config.js).

### Limitação do plano gratuito

Um serviço sem acessos por **15 minutos "dorme"**. O primeiro acesso depois disso leva **cerca de 1 minuto** enquanto ele acorda. O Cliente Web trata isso:

- mostra a faixa **"Acordando os serviços na nuvem…"** e o indicador do serviço em vermelho;
- verifica de novo a cada 5 segundos e, quando todos estão no ar, avisa e carrega os dados sozinho.

Na nuvem, o Empréstimos espera até 60 segundos por outro serviço (`BOOKNET_TIMEOUT_SERVICOS`), tempo suficiente para ele acordar. **Antes de uma apresentação, abra o site uns 2 minutos antes.**

O plano gratuito oferece 750 horas de uso por mês, somando todos os serviços. Como eles dormem quando ninguém usa, isso sobra para o trabalho. Não use serviços para mantê-los acordados 24 horas por dia.

**Publicado e verificado em 20/10/2026:** os quatro componentes ficaram *Live* no Render, e o site abriu com "Ao vivo 3/3". Pela internet, os três serviços responderam "banco online"; o CORS liberou o site; a rota interna sem token respondeu `403`; e o teste de concorrência com 4 pedidos simultâneos teve **1 aprovado e 3 recusados**, com a devolução funcionando. Isso confirma o Empréstimos falando com Catálogo e Usuários entre máquinas diferentes do Render.

Esse comportamento foi simulado localmente antes da publicação: com o cliente servido num domínio "de internet" e o Catálogo parado, a faixa apareceu; ao religar o Catálogo, a página se recuperou sozinha e um empréstimo completo funcionou.

### Como publicar (uma vez só)

1. Acesse https://render.com e clique em **Get Started**. Entre com **GitHub** (*Sign up with GitHub*) usando a conta dona do repositório.
2. No painel do Render, clique em **New +** → **Blueprint**.
3. Conecte o GitHub quando for pedido e escolha o repositório **projeto-booknet**. O Render encontra o `render.yaml` sozinho.
4. Dê um nome ao Blueprint (ex.: `booknet`). Ele mostra os quatro componentes e pede o valor de **`DATABASE_URL`** para cada serviço. Cole a **connection string do Neon**, a mesma do seu `.env`, nos três campos.
5. Clique em **Apply** (ou **Deploy Blueprint**) e aguarde. A primeira publicação leva de 5 a 10 minutos, porque o Render constrói a imagem Docker.
6. Quando os quatro estiverem **Live** (verde), abra https://booknet-luizfelipe.onrender.com.

**Se algum endereço sair diferente** (por exemplo `booknet-luizfelipe-catalogo-ab12.onrender.com`, porque o nome já existia), troque-o em `render.yaml` (`BOOKNET_URL_*` e `BOOKNET_ORIGENS_EXTRAS`) e em `cliente/config.js`, e envie ao GitHub. O Render publica de novo sozinho.

### Atualizações

A cada `git push` na branch `main`, o Render reconstrói e publica a nova versão automaticamente. Se a mudança incluir uma nova migration, aplique-a antes no Neon, com `alembic upgrade head` ou com `docker compose up`, que roda a migração sozinho.

## Como executar

Além da versão na nuvem (seção anterior), há dois jeitos de rodar o BookNet no seu computador. Os dois usam o mesmo `.env` e o mesmo banco no Neon.

| | **Com Docker (V4, recomendado)** | **Com Python (V3)** |
| --- | --- | --- |
| Precisa instalar | Docker Desktop | Python 3.13 e as dependências |
| Comando | `docker compose up --build` | `.\.venv\Scripts\python.exe scripts\iniciar_servicos.py` |
| Bom para | apresentar, rodar no PC dos colegas | desenvolver e rodar os testes |

Os dois usam as mesmas portas, então **não rode os dois ao mesmo tempo**. Para trocar, encerre um antes (`docker compose down` ou Ctrl+C no iniciador).

Execute os comandos **na raiz `booknet/`**, no PowerShell. Os passos 1 e 2 abaixo são para o jeito com Python. No jeito com Docker basta criar o `.env` (passo 1) e seguir a seção "V4: Docker"; a migration roda sozinha.

### 1. Preparar o ambiente (somente na primeira vez)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Crie o arquivo `.env` na raiz `booknet/` com:

```env
DATABASE_URL=<connection string do Neon>
BOOKNET_TOKEN_INTERNO=<um texto secreto qualquer, igual para os três serviços>
BOOKNET_SEGREDO_SESSAO=<outro texto secreto longo, que assina os logins>
```

Esse arquivo é ignorado pelo Git e nunca deve ser enviado ao GitHub. Sem `BOOKNET_TOKEN_INTERNO`, os serviços usam um token padrão de desenvolvimento e mostram um aviso.

### 2. Criar ou atualizar as tabelas (migrations)

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

O banco do projeto no Neon já está na revisão `0004_recuperacao_e_login (head)`. Rodar `upgrade head` novamente não altera nada.

### 3. Iniciar tudo com um comando

```powershell
.\.venv\Scripts\python.exe scripts\iniciar_servicos.py
```

O iniciador sobe os **três serviços** (8001, 8002, 8003) e o **Cliente Web** (8080), cada um em um processo, e mostra os logs identificados por serviço. Se um serviço cair, os outros continuam. **Ctrl+C** encerra todos.

Acesse **[http://127.0.0.1:8080/](http://127.0.0.1:8080/)**. É preciso abrir pelo servidor HTTP, e não com duplo clique no `index.html`, por causa das regras de CORS dos serviços.

<details>
<summary>Alternativa: cada serviço em um terminal separado</summary>

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.servicos.catalogo:app --port 8001      # terminal 1
.\.venv\Scripts\python.exe -m uvicorn backend.servicos.usuarios:app --port 8002      # terminal 2
.\.venv\Scripts\python.exe -m uvicorn backend.servicos.emprestimos:app --port 8003   # terminal 3
.\.venv\Scripts\python.exe -m http.server 8080 --bind 127.0.0.1 --directory cliente # terminal 4
```

Fechar um dos terminais é a forma mais visual de mostrar um serviço caindo durante a apresentação.
</details>

### Demonstração em duas máquinas (rede do laboratório)

É a versão do BookNet do aquecimento da Aula 2 ("Computador A servidor, Computador B cliente"). O Computador A roda os serviços e o Cliente Web, e o Computador B usa a biblioteca só pelo navegador, através da rede.

**Computador A (servidor)**, na raiz `booknet/`:

```powershell
ipconfig                                                       # anote o IPv4, ex.: 192.168.0.101
.\.venv\Scripts\python.exe scripts\iniciar_servicos.py --rede
```

**Computador B (cliente)**:

```powershell
ping 192.168.0.101
```

No navegador, abra `http://192.168.0.101:8080`.

```text
Computador B (navegador) ──HTTP :8080─────────────▶ Computador A: arquivos do cliente
Computador B (navegador) ──HTTP/WS :8001/8002/8003─▶ Computador A: serviços ──▶ PostgreSQL no Neon
```

O cliente descobre sozinho o endereço dos serviços: ele usa o mesmo IP pelo qual foi aberto, nas portas 8001 a 8003. Os serviços aceitam origens de redes privadas (`10.x`, `172.16–31.x`, `192.168.x`) nas portas 8080 e 5500, e continuam recusando origens da internet.

Cuidados:

- Na primeira execução, o Windows pode perguntar se permite o Python na rede. Permita em **rede privada**. Se o `ping` funcionar mas a página não abrir, o bloqueio é do firewall.
- O iniciador serve **somente a pasta `cliente/`** na porta 8080. Nunca sirva a raiz `booknet/`, que contém o `.env`.
- Para a demonstração de concorrência, cada integrante pode clicar em **Emprestar** no mesmo exemplar, cada um no seu computador. Só um recebe o empréstimo.

### 4. Dados de demonstração e scripts (opcional)

Com os serviços rodando:

```powershell
.\.venv\Scripts\python.exe scripts\popular_dados.py       # 5 livros, 9 exemplares, 4 usuários
.\.venv\Scripts\python.exe scripts\teste_concorrencia.py  # pedidos simultâneos pelo mesmo exemplar
.\.venv\Scripts\python.exe scripts\monitor_eventos.py     # painel de eventos dos três serviços
```

Desde o login, os scripts entram como bibliotecário e pedem a senha (ou leem `BOOKNET_SENHA`). Os três aceitam o IP do Computador A como argumento (ex.: `scripts\monitor_eventos.py 192.168.0.101`). `popular_dados.py` pode ser executado várias vezes, porque ignora registros que já existem. Cada execução de `teste_concorrencia.py` cria um exemplar novo (tombo `CONC-...`) no primeiro livro e, ao final, devolve o empréstimo.

## Testes automatizados

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

**106 testes passando.** Eles usam SQLite em memória e não acessam o `.env` nem o Neon, porque qualquer tentativa de conexão PostgreSQL é bloqueada. Os três serviços rodam dentro do processo de teste. As chamadas entre eles usam o cliente `httpx` real, com um transporte simulado que entrega cada pedido ao serviço de destino. Isso permite simular **serviço fora do ar** e **timeout** de forma controlada.

| Arquivo | Cobertura |
| --- | --- |
| `tests/apoio.py` | Infraestrutura: banco isolado por teste, os três serviços ASGI e o transporte simulado entre eles. |
| `tests/test_catalogo.py` | Rotas de sistema, CORS, livros, exemplares, busca, paginação, erros seguros e constraints. |
| `tests/test_circulacao.py` | Usuários, fluxo completo de empréstimo e devolução, indisponibilidade, limite de 3, atraso, usuário e livro inativos, índice único parcial com **compensação**, filtros e constraints. |
| `tests/test_eventos.py` | WebSocket (V2): boas-vindas e ping/pong, origem recusada (`1008`), broadcast para várias telas, ausência de evento em operação recusada, **um canal por serviço** e remoção de conexão quebrada. |
| `tests/test_autenticacao.py` | Login: hash de senha, token adulterado/expirado/sem assinatura, mensagem genérica, aba errada, conta desativada, bloqueio após 5 erros, troca de senha, `401` sem login, `403` de aluno em rotas de bibliotecário, aluno só empresta e vê para si, WebSocket com token e filtrado por perfil. |
| `tests/test_resiliencia.py` | V5: disjuntor, novas tentativas (seguras e proibidas), reconciliação e execução periódica. |
| `tests/test_servicos.py` | V3: cada serviço expõe só as próprias rotas, token das rotas internas, retirada e liberação idempotente, Usuários fora do ar (`503`), Catálogo lento (`504`), devolução desfeita e repetida, compensação que falha, lista de empréstimos com os outros serviços fora do ar, cópia dos dados do momento e erro `500` remoto virando `503`. |

Validações feitas contra o Neon, com os serviços reais:

- Migrations `0001` a `0003` aplicadas; `alembic check` não detectou diferenças entre os modelos e o banco. Os 10 empréstimos existentes receberam a cópia dos dados na migration `0003`.
- `teste_concorrencia.py`: 4 execuções na V1 e 3 na V3 (atravessando os três serviços), sempre com exatamente 1 empréstimo aprovado.
- V2: o navegador e o `monitor_eventos.py`, conectados pelo IP da rede local (`192.168.0.101`), receberam os eventos de empréstimos feitos por outro cliente.
- V3: com o Catálogo desligado, o empréstimo respondeu `503` na hora; com o Empréstimos desligado, o Acervo continuou funcionando no navegador.
- V4: o sistema inteiro subiu com `docker compose up --build -d` e repetiu as verificações acima dentro dos contêineres (veja "V4: Docker").

## Estrutura do projeto

```text
booknet/
├── README.md
├── requirements.txt
├── alembic.ini
├── Dockerfile                  # V4: imagem dos três serviços
├── docker-compose.yml          # V4: o sistema inteiro em contêineres
├── .dockerignore               # V4: o que nunca entra na imagem (.env!)
├── render.yaml                 # nuvem: os quatro componentes no Render
├── backend/
│   ├── servicos/               # V3: os três serviços (um processo cada)
│   │   ├── base.py             # estrutura comum: CORS, erros, /health, /ws/eventos
│   │   ├── catalogo.py         # porta 8001
│   │   ├── usuarios.py         # porta 8002
│   │   └── emprestimos.py      # porta 8003
│   ├── servicos_remotos.py     # V3/V5: cliente HTTP com timeout, novas tentativas e disjuntor
│   ├── resiliencia.py          # V5: disjuntor (circuit breaker)
│   ├── reconciliacao.py        # V5: libera exemplares presos
│   ├── config.py               # leitura do .env (banco, endereços, token, timeout)
│   ├── database.py             # engine PostgreSQL e sessões
│   ├── errors.py               # respostas de erro seguras
│   ├── eventos.py              # V2: canal WebSocket e broadcast de mensagens
│   ├── origens.py              # origens permitidas (CORS e WebSocket)
│   ├── autenticacao.py         # login: hash de senha (PBKDF2) e token de sessão (JWT)
│   ├── dependencies/           # sessão de banco, sessão do usuário (perfis) e token interno
│   ├── models/                 # Livro, Exemplar, Usuario, Emprestimo
│   ├── schemas/                # validação Pydantic de entrada e saída
│   └── routers/                # catalogo.py, usuarios.py, emprestimos.py
├── migrations/versions/        # 0001 catálogo · 0002 usuários e empréstimos · 0003 cópia de dados · 0004 V5
├── tests/                      # apoio.py e os testes de catálogo, circulação, eventos e serviços
├── scripts/                    # iniciar_servicos, definir_senha, popular_dados, teste_concorrencia, monitor_eventos
├── cliente/                    # Cliente Web (V1–V3), Dockerfile com nginx (V4) e config.js da nuvem
├── servico-catalogo/           # README do Serviço de Catálogo
├── servico-usuarios/           # README do Serviço de Usuários
├── servico-emprestimos/        # README do Serviço de Empréstimos
├── dashboard/                  # apresentação estática (V0)
├── docs/                       # arquitetura e guias de estudo
└── banco/                      # reservado
```

## Portas

| Componente | Porta | Situação |
| --- | --- | --- |
| Serviço de Catálogo | 8001 | Implementado (V3). |
| Serviço de Usuários | 8002 | Implementado (V3). |
| Serviço de Empréstimos | 8003 | Implementado (V3). |
| Cliente Web | 8080 | Implementado (servidor estático; nginx no Docker). |

A porta 8000, da API única das versões V1 e V2, deixou de ser usada.

## Situações de falha

| Falha documentada na V0 | Situação na V3 |
| --- | --- |
| 1. Serviço de Empréstimos indisponível | **Isolada e recuperada**: com o Empréstimos fora do ar, Catálogo e Usuários continuam funcionando, e o cliente informa qual serviço caiu. Se o processo morrer, o Docker o reinicia sozinho (V5). |
| 2. Dois usuários pedem o mesmo exemplar | **Resolvida** entre serviços: retirada atômica no Catálogo, índice único parcial e compensação, demonstrados contra o Neon. Se a compensação falhar, a reconciliação libera o exemplar (V5). |
| 3. Falha de comunicação Empréstimos → Catálogo | **Tratada e recuperada**: tempo limite, respostas `503`/`504` claras, novas tentativas automáticas nas operações seguras e disjuntor que evita esperas inúteis (V5). |

## Evolução

| Versão | Etapa | Status |
| --- | --- | --- |
| **V0** | **Ideia e arquitetura** | **Concluída** |
| **V1** | **Cliente-servidor** | **Concluída**: API completa, banco no Neon, Cliente Web funcional, concorrência tratada. |
| **V2** | **Sockets / mensagens** | **Concluída**: WebSocket com broadcast de eventos, cliente em tempo real com reconexão, monitor de terminal. |
| **V3** | **Serviços separados** | **Concluída**: três processos (8001–8003), comunicação HTTP com timeout, saga com compensação, rotas internas com token, falhas 1 e 3 demonstradas. |
| **V4** | **Docker** | **Concluída**: imagem dos serviços e do cliente, `docker-compose.yml` com migração automática, rede interna por nome de serviço, segredos fora da imagem. |
| **V5** | **Falhas e recuperação** | **Concluída**: novas tentativas com espera crescente, disjuntor por serviço, reconciliação periódica, reinício automático dos contêineres. |
| V6 | Orquestração | Planejada |

Cada versão concluída está marcada com uma *tag* no Git (`v1`, `v2`, `v3`, `v4`, `v5`).

## Tecnologias

| Tecnologia | Uso |
| --- | --- |
| Python 3.13 | Linguagem dos serviços. |
| FastAPI + Uvicorn | Serviços HTTP/REST e WebSocket, servidor ASGI. |
| httpx | Cliente HTTP entre serviços, com tempo limite (V3). |
| websockets | Suporte a WebSocket no Uvicorn e cliente do `monitor_eventos.py`. |
| SQLAlchemy 2 + psycopg 3 | ORM, transações e driver PostgreSQL. |
| Alembic | Migrations versionadas do banco. |
| Pydantic | Validação de entrada e saída. |
| python-dotenv | Leitura do `.env`. |
| PostgreSQL / Neon | Banco de dados na nuvem. |
| HTML, CSS e JavaScript puro | Cliente Web e dashboard, sem frameworks. |
| unittest | Testes automatizados. |
| Docker + Docker Compose | Contêineres dos serviços e do cliente; sistema inteiro com um comando (V4). |
| nginx | Servidor web do Cliente Web no contêiner (V4). |
| Render | Hospedagem gratuita dos serviços e do Cliente Web na nuvem. |
| Git / GitHub | Versionamento e hospedagem. |

## Repositório

[github.com/luizfelipefelixalves41-dot/projeto-booknet](https://github.com/luizfelipefelixalves41-dot/projeto-booknet)
