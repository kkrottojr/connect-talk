# Connect Talk — plataforma de atendimento e comunicação via WhatsApp

[![Testes](https://github.com/kkrottojr/connect-talk/actions/workflows/tests.yml/badge.svg)](https://github.com/kkrottojr/connect-talk/actions/workflows/tests.yml)

**Demo no ar:** https://connect-talk-graq.onrender.com (pode levar até ~1 minuto pra "acordar" — plano free do Render hiberna sem uso)

SaaS multiempresa (multi-tenant) de atendimento e comunicação via WhatsApp — campanhas, conversas e times de atendimento —, construído em Django.

Este projeto foi construído como estudo de caso de produto: da estrutura multiempresa até um fluxo completo de campanha — importar contatos, criar template com botões de decisão, montar e disparar campanha, e tratar a resposta do contato — com uma arquitetura de disparo pensada para nunca enviar mensagem real por acidente.

## Avaliar em 2 minutos

1. Acesse a demo (link acima) e entre com um destes usuários (empresa "Empresa Exemplo", já populada com contatos/templates/campanhas):
   - **Gestor** — usuário `gestor`, senha `demo12345` (acesso a templates, campanhas, agendamentos e conversas)
   - **Operador** — usuário `operador`, senha `demo12345` (só a fila de conversas — "assumir atendimento" e interagir)
2. Veja o **Dashboard** (métricas reais) → **Campanhas** (uma já disparada em modo teste) → **Conversas** (clique num contato da fila "Aguardando atendimento" pra ver a tela de chat).
3. Todo envio é simulado — ver "Modo de envio" abaixo pra entender a trava de segurança que impede mensagem real por acidente.

## Funcionalidades

- Autenticação, cadastro de empresas e usuários por empresa, com isolamento total de dados entre empresas.
- Três perfis com permissão de verdade (não só cosmética): **Administrador** (acesso total, inclusive gestão de equipe), **Gestor** (templates, campanhas, agendamentos e conversas) e **Operador** (só conversas — interagir e assumir atendimentos).
- Tela **Equipe**, onde um Administrador cadastra/gerencia os membros da própria empresa e define o perfil de cada um.
- Dashboard com métricas reais: contatos, campanhas, mensagens simuladas, respostas recebidas, leads em atendimento, contatos bloqueados.
- Importador de contatos (Excel/CSV) com mapeamento de colunas, validação de telefone (E.164) e registro de consentimento (opt-in).
- Templates de mensagem com placeholders (`{{nome}}`, `{{telefone}}`) e até 3 botões de decisão configuráveis, cada um associado a "Prosseguir" (transfere ao atendente) ou "Parar" (bloqueia o contato).
- Campanhas segmentáveis por tag, com pré-visualização da mensagem antes do disparo, e **Agendamentos** para disparar numa data/hora futura.
- Conversas: simula a resposta de um contato aos botões — a ação tem efeito real no sistema (descadastro, fila de atendimento com "assumir atendimento" por usuário).
- Configuração para SQLite local ou PostgreSQL em produção (Docker).
- Suíte de testes automatizados cobrindo isolamento entre empresas, permissões por perfil, importação, disparo, conversas e agendamentos.

## Destaques técnicos

**Trava de segurança no disparo.** Nenhuma campanha manda mensagem real por padrão. Um modo de envio (`WHATSAPP_SEND_MODE`) controla tudo: `dry_run` (padrão) nunca chama nenhum provedor de envio, não importa o que mais esteja configurado; `test` só chama o provedor para números explicitamente liberados por empresa — qualquer outro contato é bloqueado no código, não só na interface. Não existe modo "produção" que ignore essa restrição. Ver [campaigns/services.py](campaigns/services.py).

**Provedor de envio plugável.** O envio é uma interface (`send(phone, message) -> SendResult`) com dois provedores: um mock (padrão, nunca faz chamada de rede) e um para a Meta WhatsApp Cloud API, prontos para trocar por variável de ambiente sem mexer no resto do fluxo de campanha. Ver [campaigns/sending.py](campaigns/sending.py).

**Multiempresa de verdade.** Toda consulta sensível (`Contact`, `Campaign`, `MessageTemplate`) é escopada pela empresa do usuário logado via `Membership.objects.active_for(user)` — testado explicitamente (dados de uma empresa nunca aparecem para outra).

**Permissões centralizadas.** `tenants/permissions.py` concentra os dois únicos jeitos de proteger uma view (`membership_required`, `roles_required(*roles)`), reaproveitados por todos os apps — em vez de checagem de perfil espalhada e reinventada tela por tela.

**Consentimento como dado de primeira classe.** Contatos guardam `consent_given`/`consent_source`/`consent_at` desde a importação, e um contato pode se descadastrar (`opted_out`) respondendo "Parar" — o que o remove de qualquer campanha futura automaticamente, na própria query (`Campaign.recipients()`), não como checagem manual espalhada pela UI.

## Stack

Django 5.2 · SQLite (dev) / PostgreSQL (produção) · `phonenumbers` (validação de telefone) · `openpyxl` (leitura de planilhas) · `requests` (integração HTTP) · `whitenoise` (estáticos em produção) · Docker/gunicorn, deploy no Render.

## Executar no Windows

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Acesse `http://127.0.0.1:8000/admin/`, crie uma empresa e vincule seu usuário a ela. Depois abra `http://127.0.0.1:8000/`.

### Popular com dados de demonstração

```powershell
python manage.py seed_demo_data
```

Cria (de forma idempotente — pode rodar de novo sem duplicar) uma "Empresa Exemplo" com contatos variados, templates com e sem botões, e campanhas em estados diferentes (rascunho, disparada em simulação, disparada em modo teste com um contato bloqueado por não estar na allowlist). Requer um superusuário já criado — ele é quem fica vinculado à empresa.

## Executar com Docker e PostgreSQL

```bash
docker compose up --build
```

Em outro terminal:

```bash
docker compose exec web python manage.py createsuperuser
```

## Deploy (Render)

O repositório já tem um [render.yaml](render.yaml) (Blueprint) pronto:

1. Em [render.com](https://render.com), **New +** → **Blueprint**, aponte para este repositório.
2. O Render lê o `render.yaml`, builda pelo [Dockerfile](Dockerfile) e sobe um serviço web (plano free) já com `DJANGO_SECRET_KEY` e a senha do admin geradas automaticamente.
3. O plano free não dá acesso a Shell — por isso o próprio container já cria o superusuário e popula os dados de demonstração sozinho a cada start (`ensure_superuser` + `seed_demo_data`, ambos idempotentes, encadeados no `CMD` do [Dockerfile](Dockerfile)). Usuário: `admin`. Pra pegar a senha gerada: painel do serviço → **Environment** → `DJANGO_SUPERUSER_PASSWORD`.

### Banco de dados persistente (PostgreSQL externo)

O Render deixou de ter plano free permanente pra Postgres, então o `render.yaml` aponta pra um **Postgres externo** — funciona com qualquer provedor, mas o mais simples pra portfólio é o [Neon](https://neon.tech) (tier free permanente):

1. Crie uma conta no Neon e um projeto novo (Postgres 16+).
2. No painel do projeto, copie a **connection string** (formato `postgresql://usuario:senha@host/nome_do_banco?sslmode=require`).
3. No Render, abra o serviço **connect-talk** → **Environment** e preencha, a partir dessa connection string:
   - `DB_NAME` — o nome do banco (depois da última `/`)
   - `DB_USER` — o usuário (antes de `:` na connection string)
   - `DB_PASSWORD` — a senha
   - `DB_HOST` — o host (depois de `@`)
   - (`DB_ENGINE=postgresql`, `DB_SSLMODE=require` e `DB_PORT=5432` já vêm prontos do `render.yaml`)
4. Salve — o Render redeploya sozinho, já migrando e populando os dados de demonstração no banco novo (`migrate` + `ensure_superuser` + `seed_demo_data`, mesma cadeia do `CMD` do Dockerfile). A partir daqui, os dados (e a senha que você trocar) sobrevivem a novos deploys.

Sem essas variáveis preenchidas, o app cai de volta pro SQLite local — funciona, mas sem persistir entre deploys (cada novo deploy nasce zerado). O hostname público do Render é reconhecido automaticamente (`RENDER_EXTERNAL_HOSTNAME` em [connect_talk/settings.py](connect_talk/settings.py)) — não precisa configurar `DJANGO_ALLOWED_HOSTS` na mão.

## Variáveis de ambiente

Use `.env.example` como referência. Nunca publique a chave secreta, senhas do banco ou tokens da Meta no código-fonte.

## Modo de envio (segurança dos disparos)

- **`dry_run`** (padrão): todo disparo é 100% simulado — nenhum provedor é chamado, não importa o que mais esteja configurado.
- **`test`**: só os números cadastrados em *Admin › Empresas › "números de teste"* passam pelo provedor configurado (`WHATSAPP_PROVIDER`); qualquer outro contato é bloqueado automaticamente. É o único modo que pode enviar mensagem real, e só para esses números.

Não existe modo `live` separado — quando um provedor real estiver plugado, é o próprio `test` que passa a enviar de verdade, sempre restrito à allowlist.

## Integrando um provedor real de WhatsApp

Hoje o provedor padrão é um mock (`campaigns/sending.py::MockProvider`) — nenhuma chamada de rede acontece. Já existe um segundo provedor pronto para a **Meta WhatsApp Cloud API** (`MetaCloudAPIProvider`), desligado por padrão.

Para habilitar:

1. Crie um app em [developers.facebook.com](https://developers.facebook.com/), adicione o produto **WhatsApp** e gere um número de teste (ou use um número verificado da sua conta Business).
2. Gere um token de acesso (comece com o token temporário de teste; para produção, um token permanente de usuário de sistema).
3. Anote o **Phone Number ID** do número.
4. Preencha no `.env`:
   ```
   WHATSAPP_PROVIDER=meta_cloud
   WHATSAPP_API_TOKEN=...
   WHATSAPP_PHONE_NUMBER_ID=...
   ```
5. Cadastre 1–2 números de teste em *Admin › Empresas › "números de teste"* e mantenha `WHATSAPP_SEND_MODE=test` — só esses números vão receber mensagem de verdade.

**Antes de usar em produção**, falta resolver uma limitação real da API: mensagens iniciadas pela empresa (o caso das campanhas) só podem usar um **template pré-aprovado pela Meta** — não o texto livre que `MessageTemplate.body` guarda hoje. Fora da janela de 24h após o contato escrever primeiro, texto livre é rejeitado pela API. Isso significa mapear cada `MessageTemplate` para o nome e os parâmetros de um template aprovado no Meta Business Manager antes de usar `meta_cloud` fora do modo `test`/sandbox.

## Agendamentos

Uma campanha em rascunho pode ser agendada (`campaigns:schedule`) para uma data/hora futura em vez de disparada na hora. O projeto não tem um worker tipo Celery rodando sozinho, então o disparo automático no horário depende de algo externo chamar:

```powershell
python manage.py run_scheduled_campaigns
```

periodicamente (cron no Linux, Agendador de Tarefas no Windows). Sem isso configurado, os agendamentos vencidos ficam marcados "Atrasado" na tela *Agendamentos* até alguém clicar em "Executar agendamentos pendentes agora" (mesma lógica do comando, só que restrita à empresa de quem clicou).

## Testes

```powershell
python manage.py test
```

## Próxima etapa

Resolver o mapeamento de templates aprovados pela Meta (ver "Integrando um provedor real de WhatsApp" acima) para liberar envio real fora do modo de teste.
