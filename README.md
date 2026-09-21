# BookNet

**Sistema Distribuído de Gerenciamento de Biblioteca Universitária**  
Disciplina: Sistemas Distribuídos  
Etapa atual: **V1.1 — Catálogo em preparação**, como parte da V1 — Cliente-servidor em desenvolvimento

Entrega concluída: **Checkpoint 01 / V0 — Ideia e arquitetura**

## Integrantes

- André
- João Henrique
- Luiz Felipe

## Sobre o projeto

O BookNet é um projeto acadêmico da disciplina de Sistemas Distribuídos voltado ao gerenciamento de uma biblioteca universitária. Seu desenvolvimento será incremental ao longo do semestre, relacionando cada versão aos conceitos estudados em aula.

A V0 reúne a proposta, a estrutura inicial do projeto, a documentação da arquitetura e um dashboard estático de apresentação. A V1 iniciou o backend com FastAPI e uma verificação de conexão com PostgreSQL hospedado no Neon. A V1.1 prepara os modelos e endpoints de livros e exemplares, com testes isolados e uma migration ainda não aplicada ao Neon. O catálogo não deve ser considerado implantado. Usuários, empréstimos, devoluções, frontend funcional e comunicação entre serviços continuam planejados para etapas futuras.

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

O objetivo acadêmico é estudar comunicação entre processos e distribuição de responsabilidades, observando seus efeitos sobre concorrência, consistência, disponibilidade, escalabilidade e tolerância a falhas. A implementação desses conceitos ocorrerá gradualmente durante a disciplina.

## Usuários

Os dois perfis abaixo compõem o escopo funcional planejado. Ainda não há autenticação, implementação desses perfis ou interface funcional para suas operações. A V1.1 prepara somente as operações de catálogo na API.

### Aluno

- Pesquisar livros.
- Verificar disponibilidade.
- Solicitar empréstimos.
- Realizar devoluções.
- Consultar seus empréstimos.

### Bibliotecário

- Cadastrar livros.
- Alterar dados dos livros.
- Consultar usuários.
- Acompanhar empréstimos.

## Escopo inicial

O escopo inicial do sistema a ser desenvolvido inclui:

| Área | Responsabilidade prevista |
| --- | --- |
| Catálogo | Organizar as informações dos livros e permitir sua pesquisa. |
| Usuários | Gerenciar os dados de alunos e bibliotecários. |
| Exemplares | Identificar as unidades físicas de cada livro e sua disponibilidade. |
| Empréstimos | Registrar e consultar a relação entre usuário, exemplar e datas do empréstimo. |
| Devoluções | Registrar a devolução e a mudança de estado do empréstimo e do exemplar. |
| Comunicação entre componentes | Permitir solicitações e respostas pela rede entre cliente e serviços e nas consultas entre serviços. |

Na V0, esse escopo foi definido conceitualmente e foi implementado o dashboard de apresentação. A V1 contém uma única aplicação FastAPI com rotas de identificação e verificação de saúde. A V1.1 acrescenta o catálogo em preparação nessa mesma API; os serviços separados e as demais operações de gerenciamento serão construídos nas etapas seguintes.

## Fora do escopo inicial

- Pagamentos.
- Multas complexas.
- Recomendação com IA.
- Aplicativo mobile.
- Reconhecimento facial.
- Integrações externas.

## Arquitetura

![Arquitetura conceitual do BookNet: Cliente Web envia solicitações aos serviços de Usuários, Catálogo e Empréstimos; os três acessam o Banco de Dados. Empréstimos consulta diretamente Usuários e Catálogo.](docs/arquitetura.svg)

A arquitetura definida para o BookNet possui cinco componentes:

1. Cliente Web.
2. Serviço de Usuários.
3. Serviço de Catálogo.
4. Serviço de Empréstimos.
5. Banco de Dados.

O Cliente Web se comunicará com os serviços por HTTP/REST. Os serviços acessarão conceitualmente o Banco de Dados, e o Serviço de Empréstimos também consultará diretamente os serviços de Usuários e Catálogo.

O banco permanece como um único componente conceitual compartilhado neste desenho inicial. O cliente não acessará o banco diretamente. As setas do diagrama indicam o sentido das solicitações; as respostas retornarão ao solicitante.

A [documentação da arquitetura](docs/arquitetura.md) detalha os componentes, modelos e interações planejadas. Ela, o diagrama e o dashboard preservam o registro da V0. A aplicação em `backend/` é a base inicial da V1 e ainda não implementa os três serviços separados do desenho.

## Componentes

### Cliente Web

Será a interface utilizada por alunos e bibliotecários para acessar as funcionalidades da biblioteca e enviar requisições HTTP aos serviços.

Na V0, o diretório `dashboard/` contém a apresentação acadêmica do projeto em HTML, CSS e JavaScript puro. Essa apresentação não realiza pesquisas no acervo, autenticação ou processamento de empréstimos.

### Serviço de Usuários

Será responsável pelos dados dos alunos e bibliotecários e pelas consultas necessárias para identificar um usuário.

**Modelo conceitual — `Usuario`:**

| Campo | Significado |
| --- | --- |
| `id` | Identificador do usuário. |
| `nome` | Nome do aluno ou bibliotecário. |
| `email` | E-mail do usuário. |
| `matricula` | Identificação institucional do usuário. |
| `tipo` | Perfil do usuário: `ALUNO` ou `BIBLIOTECARIO`. |

### Serviço de Catálogo

Será responsável pelos livros e seus exemplares. Um livro representa a obra cadastrada, enquanto um exemplar representa uma unidade física disponível para circulação.

**Modelo conceitual — `Livro`:**

| Campo | Significado |
| --- | --- |
| `id` | Identificador do livro. |
| `titulo` | Título da obra. |
| `autor` | Autor da obra. |
| `isbn` | Identificador ISBN da obra ou edição. |

**Modelo conceitual — `Exemplar`:**

| Campo | Significado |
| --- | --- |
| `id` | Identificador do exemplar físico. |
| `livro_id` | Referência ao livro correspondente. |
| `status` | Situação do exemplar: `DISPONIVEL` ou `EMPRESTADO`. |

### Serviço de Empréstimos

Será responsável pelos empréstimos e devoluções. Antes de registrar um empréstimo, consultará Usuários para verificar o usuário e Catálogo para verificar a disponibilidade do exemplar.

**Modelo conceitual — `Emprestimo`:**

| Campo | Significado |
| --- | --- |
| `id` | Identificador do empréstimo. |
| `usuario_id` | Referência ao usuário solicitante. |
| `exemplar_id` | Referência ao exemplar emprestado. |
| `data_emprestimo` | Data de registro do empréstimo. |
| `data_prevista_devolucao` | Prazo previsto para a devolução. |
| `data_devolucao` | Data da devolução efetiva; sem valor enquanto ela não ocorrer. |
| `status` | Situação do empréstimo: `ATIVO` ou `DEVOLVIDO`. |

### Banco de Dados

Persistirá futuramente os usuários, livros, exemplares e empréstimos, incluindo as informações de devolução registradas em `Emprestimo`.

SQLite foi a opção inicialmente considerada na V0. Para a base da V1, foi escolhido PostgreSQL hospedado no Neon, acessado por SQLAlchemy e pelo driver psycopg. A verificação de conexão continua executando apenas `SELECT 1`, sem criar tabelas. A V1.1 prepara os modelos SQLAlchemy `Livro` e `Exemplar` e uma migration inicial, ainda não aplicada ao Neon. Os modelos conceituais acima preservam a proposta da V0; a estrutura implementada do catálogo está detalhada na seção da V1.1. SQLite em memória é utilizado apenas nos testes isolados.

## Comunicação entre componentes

| Origem | Destino | Comunicação e finalidade planejadas |
| --- | --- | --- |
| Cliente Web | Serviços de Usuários, Catálogo e Empréstimos | HTTP/REST para enviar solicitações relacionadas às responsabilidades de cada serviço e receber suas respostas. |
| Serviço de Empréstimos | Serviço de Usuários | HTTP/REST para verificar se o usuário existe e está apto a solicitar um empréstimo, conforme critérios a definir. |
| Serviço de Empréstimos | Serviço de Catálogo | HTTP/REST para verificar a disponibilidade do exemplar. |
| Serviços | Banco de Dados | Consulta e persistência dos dados sob responsabilidade de cada serviço; a V1 utiliza PostgreSQL por SQLAlchemy e psycopg, com o catálogo da V1.1 em preparação. |

A arquitetura atual já prevê a verificação de existência do usuário. Os critérios de aptidão para empréstimo ainda serão definidos nas próximas etapas, sem acrescentar campos ou regras de negócio ao modelo da V0.

As interações entre serviços desse desenho representam a arquitetura planejada. Na V1, as requisições HTTP alcançam uma única API FastAPI, e a rota `/health/database` verifica a conexão com o PostgreSQL. O router de catálogo da V1.1 pertence a essa mesma aplicação; não é um serviço separado. O dashboard continua estático, sem integração com essa API, e não há comunicação entre serviços implementada.

## Exemplo de fluxo de empréstimo

O fluxo abaixo representa o comportamento futuro do sistema:

1. O usuário seleciona um livro pelo Cliente Web.
2. O cliente solicita o empréstimo ao Serviço de Empréstimos.
3. Empréstimos consulta o Serviço de Usuários para verificar a existência do usuário; os critérios adicionais de aptidão serão detalhados posteriormente.
4. Empréstimos consulta o Serviço de Catálogo para verificar a disponibilidade do exemplar.
5. Se o usuário existir e o exemplar estiver disponível, o empréstimo é registrado no Banco de Dados, conforme o fluxo conceitual definido na V0.
6. A resposta retorna ao Cliente Web, que apresenta a confirmação ao usuário.

```text
Aluno seleciona um livro
        ↓
Cliente Web
        ↓ POST /emprestimos (planejado)
Serviço de Empréstimos
        ├──→ Serviço de Usuários: o usuário existe?
        └──→ Serviço de Catálogo: o exemplar está disponível?
        ↓ Se as verificações forem positivas
Registro do empréstimo → Banco de Dados
        ↓
Resposta → Cliente Web → Aluno
```

`POST /emprestimos` é um exemplo conceitual, sem rota implementada. A coordenação das mudanças de estado do empréstimo e do exemplar será estudada nas próximas versões.

## Situações de falha

### 1. Serviço de Empréstimos indisponível

**Cenário:** o Serviço de Empréstimos fica offline enquanto os demais componentes podem continuar disponíveis.

**Consequência:** o usuário não consegue realizar empréstimos. A consulta ao catálogo ainda poderá funcionar se os componentes necessários a essa consulta estiverem disponíveis.

**Conceitos relacionados:** disponibilidade e tolerância a falhas.

### 2. Dois usuários solicitam o mesmo exemplar simultaneamente

**Cenário:** dois usuários tentam pegar o mesmo exemplar ao mesmo tempo, e suas solicitações observam o exemplar como disponível.

**Consequência:** sem controle adequado, podem ser registrados dois empréstimos para um único exemplar físico.

**Conceitos relacionados:** concorrência e consistência.

### 3. Falha de comunicação entre Empréstimos e Catálogo

**Cenário:** o Serviço de Empréstimos consulta o Serviço de Catálogo, mas a rede falha ou a resposta não chega.

**Consequência:** não é possível confirmar a disponibilidade do exemplar nem concluir com segurança as verificações necessárias ao empréstimo.

**Conceitos relacionados:** rede, timeout, comunicação distribuída e tolerância a falhas.

Essas três falhas foram identificadas e documentadas na V0. Serão estudadas nas próximas etapas da disciplina, quando serão desenvolvidas e avaliadas soluções. Nenhum mecanismo de tratamento dessas falhas está implementado nesta entrega.

## Por que o BookNet deve ser distribuído?

O BookNet adota uma arquitetura distribuída como proposta para separar as diferentes responsabilidades do sistema. O gerenciamento de usuários, catálogo e empréstimos será realizado por componentes independentes que se comunicarão pela rede. Essa separação permitirá que os serviços evoluam independentemente e possibilitará estudar conceitos fundamentais de Sistemas Distribuídos, como comunicação entre processos, concorrência, disponibilidade, escalabilidade e tolerância a falhas.

Além disso, uma falha em determinado serviço não precisa necessariamente interromper todas as funcionalidades. Esse comportamento dependerá das relações entre os componentes: solicitar um empréstimo exige consultas a outros serviços, e o banco compartilhado também constitui uma dependência da arquitetura inicial.

> Para uma biblioteca pequena, uma aplicação monolítica poderia ser suficiente. Neste projeto, a arquitetura distribuída foi escolhida principalmente para permitir a aplicação prática dos conceitos estudados na disciplina.

## Tecnologias atuais e planejadas

| Tecnologia | Uso |
| --- | --- |
| Python | Base do backend da V1. |
| FastAPI | API HTTP com identificação, verificações de saúde e endpoints de catálogo em preparação. |
| Uvicorn | Servidor para executar a aplicação FastAPI. |
| SQLAlchemy e psycopg | Verificação de conexão, modelos ORM e sessões por requisição para o catálogo. |
| Alembic | Controle das alterações de estrutura do banco por migrations; migration inicial preparada, sem aplicação no Neon. |
| python-dotenv | Carregamento da configuração local de conexão. |
| HTML/CSS/JavaScript | Cliente Web planejado e dashboard estático já implementado na V0. |
| PostgreSQL / Neon | Banco escolhido para a V1; a estrutura real permanece sem alterações nesta etapa. |
| Git | Versionamento do código e da documentação. |
| GitHub | Hospedagem do repositório e apresentação do projeto. |
| Docker | Conteinerização em etapa futura. |

As dependências Python estão registradas em `requirements.txt`. O dashboard atual usa apenas HTML, CSS e JavaScript puro, sem bibliotecas ou dependências externas. Docker, frontend funcional e os recursos da biblioteca além do catálogo permanecem para etapas futuras.

### Preparar o backend no PowerShell

Execute os comandos **na raiz `booknet/`**. Verifique o Python com `python --version` ou `py --version`. Se nenhum comando funcionar, será necessário instalar Python antes de continuar.

Crie o ambiente virtual, se ele ainda não existir:

```powershell
python -m venv .venv
```

Se apenas o comando `py` estiver disponível, use `py -m venv .venv`. Ative o ambiente e instale as dependências:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Caso a ativação seja bloqueada pelo PowerShell, use diretamente o Python do ambiente, sem alterar políticas de segurança:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

A variável `DATABASE_URL` deve ser preenchida manualmente no arquivo local `.env`, na raiz `booknet/`. Esse arquivo e o ambiente `.venv/` são ignorados pelo Git. O backend carrega a configuração a partir da raiz do projeto e informa um erro caso a variável esteja ausente; credenciais não devem ser incluídas no código ou no repositório.

### Executar e verificar a API

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

Com o ambiente ativado, também é possível usar `python -m uvicorn backend.main:app --reload --port 8000`. Para encerrar, pressione `Ctrl+C`.

| Endereço | Resultado esperado |
| --- | --- |
| [GET /](http://127.0.0.1:8000/) | HTTP 200 com `{"projeto":"BookNet","status":"online","versao":"V1"}`. |
| [GET /health](http://127.0.0.1:8000/health) | HTTP 200 com `{"status":"ok"}`. |
| [GET /health/database](http://127.0.0.1:8000/health/database) | HTTP 200 com `{"database":"online"}` quando `SELECT 1` funciona; HTTP 503 com `{"database":"offline"}` quando a conexão falha. |
| [/docs](http://127.0.0.1:8000/docs) | Documentação interativa da BookNet API, versão `1.1.0`, com as tags `Sistema` e `Catálogo`. |

O resultado de `/health/database` depende da configuração local e da disponibilidade do banco no momento da requisição. A resposta não revela detalhes internos da conexão e o teste não cria tabelas.

As respostas das três rotas de sistema foram preservadas, incluindo `"versao":"V1"` em `GET /`. O estado `online` da conexão não confirma a existência das tabelas do catálogo. Antes de autorizar e aplicar a migration em uma etapa posterior, não utilize os endpoints de catálogo para cadastrar ou alterar dados no Neon.

O CORS permite as origens locais `http://localhost:8080`, `http://127.0.0.1:8080`, `http://localhost:5500` e `http://127.0.0.1:5500`, com os métodos `GET`, `POST`, `PUT`, `DELETE` e `OPTIONS` e todos os headers. Não há cookies ou autenticação; permitir um método no CORS não cria rotas para ele.

## V1.1 — Catálogo em preparação

**MIGRATION NÃO APLICADA AO NEON.** O código do catálogo e sua migration estão preparados para revisão e testes isolados. As tabelas não são criadas automaticamente ao iniciar a API, e o catálogo ainda não deve ser considerado implantado.

### Modelos e integridade

Um livro representa a obra ou edição; um exemplar identifica uma unidade física desse livro. O relacionamento `Livro` ↔ `Exemplar` permite vários exemplares por livro, sem exclusão em cascata. Os modelos usam SQLAlchemy 2.x.

| Modelo / tabela | Campos | Regras principais |
| --- | --- | --- |
| `Livro` / `livros` | `id`, `titulo`, `autor`, `isbn`, `ativo`, `criado_em`, `atualizado_em` | Chave primária inteira; título e autor obrigatórios até 255 caracteres; ISBN obrigatório, único e mantido como string até 20 caracteres; `ativo` obrigatório, com padrão `true`. |
| `Exemplar` / `exemplares` | `id`, `livro_id`, `codigo_tombo`, `status`, `criado_em` | Chave primária inteira; livro obrigatório e existente; código de tombo único até 50 caracteres; status restrito a `DISPONIVEL` ou `EMPRESTADO`, com padrão `DISPONIVEL`. |

Os timestamps são preenchidos automaticamente, com suporte a fuso horário no PostgreSQL. `atualizado_em` é atualizado nas alterações de livro realizadas pelo ORM; isso não representa um trigger para escritas SQL externas. As constraints do banco protegem campos obrigatórios, valores válidos, unicidade e a referência ao livro. A chave estrangeira de `exemplares.livro_id` usa `RESTRICT` e possui índice, impedindo a exclusão de um livro que ainda tenha exemplares.

Os schemas Pydantic de entrada e saída são separados dos modelos ORM. Na entrada, título, autor, ISBN e código de tombo devem ser strings, têm espaços externos removidos e não podem ficar vazios. São respeitados os limites de tamanho; campos extras são rejeitados. Não há validação complexa do formato de ISBN nesta etapa.

### Endpoints preparados

As seis operações abaixo estão reunidas na tag `Catálogo` do Swagger, na mesma API da porta 8000. Sua persistência no Neon depende da aplicação posterior e autorizada da migration.

| Método | Rota | Comportamento |
| --- | --- | --- |
| `GET` | `/livros` | Lista somente livros ativos, com paginação e pesquisa opcionais. |
| `GET` | `/livros/{livro_id}` | Consulta um livro por ID, inclusive se estiver inativo; retorna `404` quando não existe. |
| `POST` | `/livros` | Cria um livro; retorna `201`, ou `409` para ISBN duplicado. |
| `PUT` | `/livros/{livro_id}` | Substitui os dados de um livro existente; retorna `404` se não existe ou `409` para conflito de ISBN. |
| `GET` | `/livros/{livro_id}/exemplares` | Lista os exemplares do livro; retorna `404` se o livro não existe. |
| `POST` | `/livros/{livro_id}/exemplares` | Cria um exemplar; retorna `201`, `404` para livro inexistente ou `409` para código de tombo duplicado. |

Em `GET /livros`, `skip` deve ser maior ou igual a zero e `limit` deve estar entre 1 e 100, com padrão 20. O parâmetro opcional `q` pesquisa título, autor e ISBN sem diferenciar maiúsculas de minúsculas. A consulta usa o ORM e parâmetros, tratando os caracteres de pesquisa como texto, sem concatenar entradas do usuário em SQL.

Para criar ou atualizar um livro, informe `titulo`, `autor` e `isbn`; `ativo` tem padrão `true`. O `PUT` exige os três campos e usa esse padrão se `ativo` for omitido: não se trata de atualização parcial. Ao criar um exemplar, informe `codigo_tombo`; `status` é opcional e aceita somente os dois valores definidos. Informar `EMPRESTADO` não cria um empréstimo: o controle de empréstimos permanece futuro.

Não há endpoint `DELETE`. Não foram acrescentados usuários, login, empréstimos, devoluções, frontend funcional ou serviços separados.

### Sessões, erros e logs

A dependency `get_db()` fornece uma sessão SQLAlchemy por requisição e a fecha ao final. As operações de escrita confirmam a transação somente quando bem-sucedidas e executam rollback em caso de falha. Não existe uma sessão global compartilhada entre requisições; a engine mantém `pool_pre_ping=True`.

Erros de validação da entrada usam a resposta padrão `422` do FastAPI. Recursos inexistentes retornam `404`, conflitos de unicidade retornam `409`, outras violações de integridade retornam `400`, e falhas de disponibilidade retornam `503` quando identificadas. Erros inesperados de banco retornam `500` com mensagem genérica. As respostas e os logs de erro de banco não incluem SQL, traceback, connection string, host, usuário ou senha.

### Alembic e migration inicial

O Alembic mantém o histórico de alterações estruturais do banco. A revisão inicial `0001_catalogo`, no arquivo `migrations/versions/0001_catalogo_livros_exemplares.py`, prepara a criação de `livros` e `exemplares`, com chaves primárias, constraints, índices e chave estrangeira. O arquivo da migration contém `upgrade()` para criar essa estrutura e `downgrade()` para revertê-la. O downgrade remove as tabelas do catálogo e perderia seus dados; existe como definição de reversão, mas não foi executado nem deve ser usado sem autorização e análise prévia.

O `alembic.ini` não contém URL de conexão. No modo online, `migrations/env.py` reutiliza a engine e a configuração segura existentes. O modo offline usa os metadados e o dialeto PostgreSQL, sem abrir o `.env` nem se conectar ao Neon. Além das duas tabelas do catálogo, o Alembic utiliza a tabela técnica `alembic_version` para registrar a revisão aplicada. Nenhuma migration é aplicada durante a inicialização do backend.

Para inspecionar o histórico local, execute na raiz `booknet/`:

```powershell
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic history
```

Esses comandos mostram as revisões disponíveis sem aplicar alterações. A aplicação da migration no Neon fica pendente de autorização explícita; este README não apresenta sua execução como um passo a realizar agora.

### Testes isolados

A suíte em `tests/` usa `unittest`, um banco SQLite em memória com chaves estrangeiras habilitadas e configuração isolada, sem ler o `.env` nem acessar o Neon. Ela verifica as rotas de sistema, validação, cadastro e atualização de livros, conflitos de unicidade, exemplares, busca, paginação e tratamento seguro de erros.

Execute na raiz `booknet/`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Na validação desta entrega, os **40 testes passaram**. A revisão `0001_catalogo` foi reconhecida por `alembic heads` e `alembic history`; seu SQL PostgreSQL foi gerado e inspecionado somente em modo offline, sem execução no banco. Não foi consultado o estado remoto por `alembic current` nesta etapa.

Os testes locais não substituem uma validação posterior no PostgreSQL e não indicam implantação do catálogo no Neon. Não é necessário instalar `pytest` ou `httpx` para executar essa suíte.

## Portas atuais e planejadas

| Serviço | Porta | Situação |
| --- | --- | --- |
| API FastAPI | 8000 | Base da V1. |
| Dashboard estático | 8080 | Servidor local opcional. |
| Catálogo | 8001 | Planejado. |
| Usuários | 8002 | Planejado. |
| Empréstimos | 8003 | Planejado. |

As portas dos três serviços são convenções para etapas futuras. A API atual usa a porta 8000; o servidor estático pode usar 8080 para funcionar ao mesmo tempo, sem conflito.

## Estrutura do projeto

A estrutura dos arquivos destinados ao versionamento na pasta `booknet/` é:

```text
booknet/
├── README.md
├── .gitignore
├── requirements.txt
├── alembic.ini
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── errors.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── livro.py
│   │   └── exemplar.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── livro.py
│   │   └── exemplar.py
│   ├── routers/
│   │   ├── __init__.py
│   │   └── catalogo.py
│   └── dependencies/
│       ├── __init__.py
│       └── database.py
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_catalogo_livros_exemplares.py
├── tests/
│   ├── __init__.py
│   └── test_catalogo.py
├── docs/
│   ├── arquitetura.md
│   ├── arquitetura.svg
│   ├── BookNet_Guia_de_Estudo_Checkpoint01_V1.docx
│   └── BookNet_Guia_de_Estudo_Checkpoint01_V1.doc
├── dashboard/
│   ├── index.html
│   ├── style.css
│   └── script.js
├── servico-catalogo/
│   └── .gitkeep
├── servico-usuarios/
│   └── .gitkeep
├── servico-emprestimos/
│   └── .gitkeep
└── banco/
    └── .gitkeep
```

As pastas dos serviços e do banco contêm apenas `.gitkeep`, utilizado para manter diretórios reservados no versionamento. A API está em `backend/`, o histórico de migrations em `migrations/` e a suíte isolada em `tests/`. Os arquivos de arquitetura e guias estão em `docs/`, e a apresentação visual está em `dashboard/`. Os arquivos locais de configuração e o ambiente virtual não fazem parte dessa estrutura versionada. Os guias Word preservam o acompanhamento até o início da V1; a V1.1 é registrada neste README.

## Evolução

| Versão | Etapa | Status |
| --- | --- | --- |
| **V0** | **Ideia e arquitetura** | **Concluída** |
| V1 | Cliente-servidor | Em desenvolvimento — base da API e verificação de conexão. |
| V1.1 | Catálogo persistente, dentro da V1 | Em preparação — modelos, endpoints e migration; não aplicado ao Neon. |
| V2 | Sockets / mensagens | Planejada |
| V3 | Serviços separados | Planejada |
| V4 | Docker | Planejada |
| V5 | Falhas e recuperação | Planejada |
| V6 | Orquestração | Planejada |

Somente a V0 está concluída. A V1 está em desenvolvimento, com uma única API; a V1.1 prepara o catálogo e ainda não está implantada no Neon. Não há frontend integrado. V2 a V6 continuam futuras. O dashboard e `docs/arquitetura.md` preservam o registro da entrega V0.

## Dashboard

O dashboard apresenta visão geral, arquitetura, componentes, comunicação, falhas e evolução. Possui layout responsivo, navegação suave, indicação da seção ativa, retorno ao topo e animações discretas. As interações são de apresentação e não processam operações da biblioteca.

### Abrir diretamente

Abra [dashboard/index.html](dashboard/index.html) no navegador. Os arquivos CSS e JavaScript são locais; o dashboard funciona sem instalação de dependências e sem conexão com a internet.

### Usar um servidor HTTP simples

Se o Python já estiver instalado, abra um terminal **dentro da pasta `booknet/dashboard/`** e execute:

```sh
python -m http.server 8080 --bind 127.0.0.1
```

Acesse [http://127.0.0.1:8080/](http://127.0.0.1:8080/). Para encerrar o servidor, pressione `Ctrl+C`.

Essa opção serve apenas os arquivos de `dashboard/`. Os links para `../docs/` ficam fora da pasta servida; para visualizá-los, use a abertura direta de `dashboard/index.html` ou abra os arquivos de `docs/` localmente. Mantenha o servidor estático restrito a `dashboard/`, pois a raiz do projeto contém a configuração local de conexão.

Esse servidor é opcional e serve somente os arquivos estáticos; não inicia os serviços planejados do BookNet.

## Repositório

O código e a documentação estão no repositório [projeto-booknet no GitHub](https://github.com/luizfelipefelixalves41-dot/projeto-booknet).

Os diretórios `backend/`, `migrations/`, `tests/`, `dashboard/`, `docs/`, `servico-catalogo/`, `servico-usuarios/`, `servico-emprestimos/` e `banco/` ficam diretamente na raiz do repositório. No workspace local, essa raiz corresponde à pasta `booknet/`. As alterações desta etapa da V1.1 devem ser revisadas antes de qualquer commit ou envio ao GitHub; não há publicação automática.

## Estado atual

**Checkpoint 01 / V0 concluído. V1 em desenvolvimento. V1.1 — Catálogo em preparação.**

| Entrega | Situação atual |
| --- | --- |
| Proposta e arquitetura conceitual | Concluídas, com cinco componentes definidos. |
| Documentação | Checkpoint 01 e guias existentes preservados em `docs/`; README atualizado até a V1.1. |
| Dashboard | Implementado como apresentação estática em HTML, CSS e JavaScript puro. |
| Estrutura inicial | Criada, com diretórios reservados para os serviços e o banco. |
| Backend e APIs | Rotas de sistema preservadas e seis operações de catálogo preparadas na mesma API FastAPI. |
| Conexão com o banco | Verificação de PostgreSQL/Neon com `SELECT 1`; o endpoint informa `online` ou `offline`. |
| Modelos SQLAlchemy | `Livro` e `Exemplar` implementados para o catálogo. |
| Migration e tabelas no Neon | Migration `0001_catalogo` preparada; **MIGRATION NÃO APLICADA AO NEON**. |
| Testes do catálogo | Suíte automatizada isolada, com SQLite em memória e sem alterações no Neon. |
| Catálogo em uso real | Ainda não implantado; depende de autorização para a migration e de validação posterior. |
| Autenticação, usuários, empréstimos e devoluções | Ainda não implementados. |
| Comunicação entre serviços e tratamento de falhas | Planejados para as próximas versões. |
| Docker e orquestração | Etapas futuras. |

A próxima entrega a concluir é a **V1 — Cliente-servidor**. A V1.1 prepara o catálogo de forma incremental, preservando o dashboard, as rotas existentes e o banco real. Qualquer aplicação da migration ou alteração de estrutura no Neon aguarda autorização explícita.
