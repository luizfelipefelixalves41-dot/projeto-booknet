# Arquitetura do BookNet

**Sistema Distribuído de Gerenciamento de Biblioteca Universitária**  
Sistemas Distribuídos · Checkpoint 01 · V0 — Ideia e arquitetura  
**Integrantes:** André · João Henrique · Luiz Felipe

## Escopo desta versão

A V0 está concluída e apresenta a proposta, o dashboard estático e a arquitetura conceitual. Os serviços, as APIs, a autenticação, o banco funcional, o Docker e o processamento real de empréstimos ainda não estão implementados. Os exemplos abaixo descrevem comportamento futuro.

O objetivo é gerenciar uma biblioteca universitária separando usuários, catálogo e empréstimos em componentes que poderão se comunicar pela rede.

## Visão da arquitetura

![Cliente Web envia solicitações HTTP/REST a Usuários, Catálogo e Empréstimos. Cada serviço acessa conceitualmente o Banco de Dados. Empréstimos consulta diretamente Usuários e Catálogo.](arquitetura.svg)

Há cinco componentes. O Banco de Dados aparece como um único componente conceitual compartilhado neste desenho inicial; a organização da persistência poderá ser revista conforme a disciplina evoluir. SQLite é uma possibilidade para a primeira implementação, sem decisão ou banco criado nesta entrega.

| Componente | Responsabilidade | Interações planejadas |
| --- | --- | --- |
| Cliente Web | Oferecer a interface utilizada por alunos e bibliotecários. Na V0, apresentar o projeto. | Enviará solicitações HTTP aos três serviços e exibirá suas respostas. |
| Serviço de Usuários | Gerenciar dados dos alunos e bibliotecários. | Receberá consultas do Cliente Web e a verificação de existência do usuário enviada por Empréstimos; acessará seus dados persistidos. |
| Serviço de Catálogo | Gerenciar livros, exemplares e sua disponibilidade. | Receberá pesquisas e operações de cadastro do Cliente Web, além da consulta de disponibilidade enviada por Empréstimos; acessará seus dados persistidos. |
| Serviço de Empréstimos | Gerenciar empréstimos, devoluções e consultas de empréstimos. | Receberá solicitações do Cliente Web, consultará Usuários e Catálogo e persistirá os registros de empréstimo. |
| Banco de Dados | Persistir usuários, livros, exemplares e empréstimos. | Será acessado pelos serviços; o cliente não acessará o banco diretamente. |

## Usuários e funcionalidades previstas

| Perfil | Escopo futuro |
| --- | --- |
| ALUNO | Pesquisar livros; verificar disponibilidade; solicitar empréstimo; devolver livros; consultar seus empréstimos. |
| BIBLIOTECARIO | Cadastrar livros; alterar informações dos livros; consultar usuários; acompanhar empréstimos. |

Os perfis são parte do modelo conceitual. Não há tela de login, autenticação ou autorização implementada.

## Modelos conceituais

Os campos abaixo são uma descrição de domínio, sem tabelas, migrações, classes ou contratos de API implementados. Tipos técnicos e regras de validação serão definidos nas próximas versões.

### Usuario

Responsável: Serviço de Usuários.

| Campo | Significado |
| --- | --- |
| `id` | Identificador do usuário. |
| `nome` | Nome do aluno ou bibliotecário. |
| `email` | E-mail do usuário. |
| `matricula` | Identificação institucional do usuário. |
| `tipo` | Perfil: `ALUNO` ou `BIBLIOTECARIO`. |

### Livro

Responsável: Serviço de Catálogo.

| Campo | Significado |
| --- | --- |
| `id` | Identificador do livro. |
| `titulo` | Título da obra. |
| `autor` | Autor da obra. |
| `isbn` | Identificador ISBN da obra ou edição. |

### Exemplar

Responsável: Serviço de Catálogo. Um livro pode ter vários exemplares físicos.

| Campo | Significado |
| --- | --- |
| `id` | Identificador do exemplar físico. |
| `livro_id` | Referência ao livro correspondente. |
| `status` | Situação: `DISPONIVEL` ou `EMPRESTADO`. |

### Emprestimo

Responsável: Serviço de Empréstimos. Cada registro relaciona um usuário a um exemplar.

| Campo | Significado |
| --- | --- |
| `id` | Identificador do empréstimo. |
| `usuario_id` | Referência ao usuário que solicita o empréstimo. |
| `exemplar_id` | Referência ao exemplar emprestado. |
| `data_emprestimo` | Data em que o empréstimo foi registrado. |
| `data_prevista_devolucao` | Prazo previsto para devolver o exemplar. |
| `data_devolucao` | Data da devolução efetiva; sem valor enquanto não houver devolução. |
| `status` | Situação: `ATIVO` ou `DEVOLVIDO`. |

As referências entre modelos representam vínculos conceituais. Não pressupõem banco ou comunicação implementados.

## Comunicação planejada

HTTP/REST será a tecnologia inicial para a comunicação entre cliente e serviços e para as consultas diretas entre serviços. As setas do diagrama indicam o sentido de início das solicitações; as respostas retornam ao solicitante. O acesso ao banco é representado conceitualmente, sem protocolo de persistência definido.

| Origem | Destino | Finalidade |
| --- | --- | --- |
| Cliente Web | Usuários | Consultar dados dos usuários. |
| Cliente Web | Catálogo | Pesquisar livros, consultar disponibilidade, cadastrar e alterar livros. |
| Cliente Web | Empréstimos | Solicitar empréstimo, registrar devolução e consultar empréstimos. |
| Empréstimos | Usuários | Verificar se o usuário informado existe. |
| Empréstimos | Catálogo | Verificar se o exemplar está disponível. |
| Usuários | Banco de Dados | Ler e persistir usuários. |
| Catálogo | Banco de Dados | Ler e persistir livros e exemplares. |
| Empréstimos | Banco de Dados | Ler e persistir empréstimos. |

| Serviço | Porta futura planejada |
| --- | --- |
| Catálogo | `8001` |
| Usuários | `8002` |
| Empréstimos | `8003` |

Essas portas não estão sendo abertas pela V0. O servidor estático opcional do README é apenas um meio de exibir o dashboard.

## Fluxo principal: solicitar empréstimo

```text
Aluno escolhe um livro
        ↓
Cliente Web
        ↓  POST /emprestimos (exemplo futuro)
Serviço de Empréstimos
        ├──→ Serviço de Usuários: o usuário existe?
        └──→ Serviço de Catálogo: o exemplar está disponível?
        ↓  Se as duas verificações forem positivas
Registro do empréstimo
        ↓
Confirmação ao Cliente Web → aluno
```

1. O aluno escolhe um livro e solicita um exemplar.
2. O Cliente Web envia a solicitação ao Serviço de Empréstimos.
3. Empréstimos consulta Usuários para verificar se o usuário existe.
4. Empréstimos consulta Catálogo para verificar a disponibilidade do exemplar.
5. Se o usuário existir e o exemplar estiver disponível, o empréstimo é criado.
6. O Cliente Web recebe uma confirmação e a apresenta ao aluno.

`POST /emprestimos` é apenas um exemplo ilustrativo: não existe uma rota implementada. Se o usuário não existir ou o exemplar estiver emprestado, os requisitos para aprovar a operação não estarão atendidos. Se uma consulta falhar, não será possível confirmar esses requisitos.

O estado futuro esperado após um empréstimo é `Emprestimo.ATIVO` e `Exemplar.EMPRESTADO`. Na devolução, deverão ser registrados `data_devolucao`, `Emprestimo.DEVOLVIDO` e `Exemplar.DISPONIVEL`. Como coordenar essas mudanças entre serviços, inclusive em caso de concorrência ou falha parcial, será estudado nas próximas versões; não há mecanismo implementado na V0.

## Situações de falha para estudo

| Situação | Cenário | Consequência | Conceitos relacionados |
| --- | --- | --- | --- |
| Serviço indisponível | O Serviço de Empréstimos fica offline. | Novos empréstimos ficam indisponíveis. A consulta ao catálogo ainda poderá funcionar se seus componentes estiverem disponíveis. | Disponibilidade; tolerância a falhas. |
| Concorrência entre usuários | Dois usuários tentam pegar o mesmo exemplar ao mesmo tempo. | Sem controle adequado, duas solicitações podem observar disponibilidade e gerar dois empréstimos para um único exemplar. | Concorrência; consistência. |
| Falha de comunicação entre serviços | Empréstimos consulta Catálogo, mas a rede falha ou a resposta não chega. | Não é possível confirmar a disponibilidade do exemplar. | Rede; timeout; comunicação distribuída. |

Esses casos são problemas documentados para discussão acadêmica. Não foram implementadas soluções de recuperação, controle de concorrência, repetição de solicitações ou timeout.

## Por que uma arquitetura distribuída?

O BookNet utiliza uma arquitetura distribuída como proposta para separar as diferentes responsabilidades do sistema. O gerenciamento de usuários, catálogo e empréstimos será realizado por componentes independentes que se comunicarão pela rede. Essa separação permite que os serviços evoluam independentemente e possibilita estudar conceitos fundamentais de Sistemas Distribuídos, como comunicação entre processos, concorrência, disponibilidade, escalabilidade e tolerância a falhas. Além disso, uma falha em determinado serviço não precisa necessariamente interromper todas as funcionalidades do sistema.

Essa independência depende do desenho das dependências: solicitar um empréstimo exige consultar outros componentes, e um banco compartilhado também pode afetar mais de um serviço. A V0 expõe essas relações para orientar a evolução do projeto.

> Para uma biblioteca pequena, uma aplicação monolítica poderia ser suficiente. Neste projeto, a arquitetura distribuída foi escolhida principalmente para permitir a aplicação prática dos conceitos estudados na disciplina.

## Evolução prevista

| Versão | Tema | Status |
| --- | --- | --- |
| **V0** | **Ideia e arquitetura** | **CONCLUÍDA** |
| V1 | Cliente-servidor | PRÓXIMA ETAPA |
| V2 | Sockets / mensagens | FUTURA |
| V3 | Serviços separados | FUTURA |
| V4 | Docker | FUTURA |
| V5 | Falhas e recuperação | FUTURA |
| V6 | Orquestração | FUTURA |

Somente a V0 está concluída. A evolução será incremental conforme os conteúdos da disciplina.
