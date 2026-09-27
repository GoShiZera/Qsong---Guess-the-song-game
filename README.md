# Qsong — Guess The Song 🎵

> Jogo web de adivinhação musical: ouça um trecho, digite o nome da música.  
> Feito com **FastAPI + HTML/CSS/JS puro** • **Spotify (metadados + auth)** • **Deezer (áudio)** • Deploy no **Render Free Tier**

---

## 🎮 Descrição e Proposta

**Qsong** é um jogo single-player no navegador onde o desafio é identificar músicas a partir de trechos de áudio progressivamente mais longos.

**Como funciona:**
1. Você **loga com sua conta Spotify** (OAuth) ou usa uma **playlist pública direta** (sem login)
2. O backend busca as faixas da playlist/álbum via Spotify API
3. Cada faixa é "matchada" com a **Deezer** para obter um preview de 30s
4. O jogo sorteia uma música → toca um trecho curto (0.4s) → você tenta adivinhar
5. Errou? O trecho aumenta (0.8s → 1.6s → 2.0s → 2.5s)
6. São **5 tentativas fixas** por música • Skip conta como erro
7. No final: tela de resumo com **acertos/erros** + detalhamento round a round

**Por que não usar só o Spotify para áudio?**  
O campo `preview_url` da Web API do Spotify foi descontinuado/restringido (nov/2024). Por isso: **Spotify = metadados (nome, artista, duração) + auth do usuário** • **Deezer = áudio (preview 30s)**.

---

## 🕹️ Como Jogar / Controles

### Fluxo Básico
```
1. Acesse a página → "Entrar com Spotify" OU cole link de playlist pública → "Iniciar Jogo"
2. (Se logado) Escolha uma de suas playlists OU cole link direto → defina rodadas → "Iniciar Jogo"
3. Ouça o trecho → Digite o nome da música no autocomplete → "Adivinhar" (Enter)
4. Errou? Trecho aumenta → Tente de novo (até 5x)
5. Acertou ou esgotou? Revela a música + toca preview completo (30s)
6. Próxima rodada... até completar as rounds definidas
7. Tela final: placar + histórico detalhado por música
```

### Mapeamento de Teclado / Mouse / Touch

| Ação | Teclado | Mouse / Touch | Contexto |
|------|---------|---------------|----------|
| **Play / Pause** | `Espaço` | Clique no botão ▶️⏸️ | Durante reprodução do trecho |
| **Enviar Palpite** | `Enter` | Clique em "Adivinhar" | Campo de busca focado |
| **Pular (Skip)** | `S` | Clique em "Pular" | Qualquer momento na rodada |
| **Navegar Autocomplete** | `Seta ↑/↓` | Clique na opção | Dropdown aberto |
| **Fechar Modal/Overlay** | `Esc` | Clique fora / botão ✕ | Fim de rodada, resumo, confirmar saída |
| **Ajustar Volume** | — | Slider do player | Player de áudio |
| **Selecionar Playlist** | `Enter` / `Clique` | Clique no card | Tela de seleção (logado) |
| **Voltar ao Início** | — | Botão ← no header | Durante o jogo |

> **Dica:** O autocomplete usa `<datalist>` nativo — digite parte do nome/artista e as sugestões aparecem instantaneamente (zero latência, 100% client-side).

---

## 🛠️ Tecnologias e Bibliotecas

### Backend (Python 3.11+)
| Tecnologia | Versão | Uso |
|------------|--------|-----|
| **FastAPI** | 0.115+ | Framework web assíncrono, validação automática (Pydantic) |
| **Uvicorn** | 0.32+ | Servidor ASGI para produção |
| **httpx** | 0.28+ | Cliente HTTP assíncrono (chamadas Spotify/Deezer) |
| **Pydantic** | 2.9+ | Modelos de dados, serialização, validação |
| **itsdangerous** | 2.2+ | Assinatura de cookies (TimestampSigner) |
| **python-dotenv** | 1.2+ | Carregamento de `.env` |

### Frontend (Vanilla — sem build step)
| Tecnologia | Uso |
|------------|-----|
| **HTML5** | SPA com 4 views (setup → select-playlist → game → summary) |
| **CSS3** | Tema escuro estilo Spotify, responsivo, acessível (ARIA, AA contrast) |
| **Vanilla JS (ES6+)** | State machine, Web Audio API, autocomplete nativo |
| **Web Audio API** | `AudioContext` → `fetch(arrayBuffer)` → `decodeAudioData()` → `AudioBufferSourceNode.start(when, offset, duration)` — precisão de 0.1s |

### APIs Externas
| API | Auth | Endpoints Usados | Propósito |
|-----|------|------------------|-----------|
| **Spotify Web API** | **Authorization Code Flow** (user login) + **Client Credentials** (fallback público) | `/api/token`, `/authorize`, `/v1/me`, `/v1/me/playlists`, `/v1/playlists/{id}/items`, `/v1/me/tracks` | Login do usuário, metadados da playlist, playlists privadas, Músicas Curtidas |
| **Deezer API** | Pública (sem auth) | `/search?q=artist:"X"+track:"Y"` | Preview de áudio 30s + matching por rank |

### Qualidade & Deploy
| Ferramenta | Configuração |
|------------|--------------|
| **Ruff** | Linting rápido (`line-length=88`, `select=["E","F","I","TID","N802","N815"]`) |
| **MyPy** | Type checking estrito (`strict=True`, `disallow_untyped_defs=True`) |
| **pytest** | Testes assíncronos (`asyncio_mode=auto`, 33 testes) |
| **GitHub Actions** | CI: lint + typecheck + test em push/PR |
| **Render** | Free tier, cold start ~30-60s após 15min inatividade |

---

## 🚀 Como Rodar Localmente

### Pré-requisitos
- **Python 3.11+**
- **Conta Spotify Developer** (para `CLIENT_ID`, `CLIENT_SECRET` e configurar Redirect URI)
- (Opcional) Conta Render para deploy

### 1. Clone e configure o ambiente
```bash
git clone https://github.com/GoShiZera/Qsong---Guess-the-song-game.git
cd Qsong---Guess-the-song-game

# Crie venv e instale dependências
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure variáveis de ambiente para **desenvolvimento local**
```bash
cp .env.example .env
# Edite .env com suas credenciais:
# SPOTIFY_CLIENT_ID=seu_client_id
# SPOTIFY_CLIENT_SECRET=seu_client_secret
# SPOTIFY_REDIRECT_URI=http://localhost:8000/callback
# SESSION_SECRET=gere-com-openssl-rand-hex-32
# COOKIE_SECURE=false  # IMPORTANTE: false para HTTP localhost
```

> **Como gerar `SESSION_SECRET`:**
> ```bash
> openssl rand -hex 32
> ```

### 3. Configure o Redirect URI no Spotify Developer Dashboard
1. Acesse [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Selecione seu App → **Edit Settings**
3. Em **Redirect URIs**, adicione: `http://localhost:8000/callback`
4. Salve

> ⚠️ **Nota:** O OAuth do Spotify **exige HTTPS em produção**, mas permite `http://localhost` para desenvolvimento. Por isso `COOKIE_SECURE=false` no `.env` local.

### 4. Rode o servidor
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Acesse no navegador
```
http://localhost:8000
```

### 6. Jogue!
- **Opção A (Login):** Clique "Entrar com Spotify" → autorize → escolha sua playlist (inclui privadas e Músicas Curtidas)
- **Opção B (Público):** Cole link de playlist/álbum público direto na tela inicial → "Iniciar Jogo"
- Divirta-se! 🎶

---

## 🧪 Testes e Verificação

```bash
# Linting
python -m ruff check .

# Type checking
python -m mypy --explicit-package-bases app

# Testes (33 testes)
python -m pytest -q

# Tudo junto (CI local)
python -m ruff check . && python -m mypy --explicit-package-bases app && python -m pytest -q
```

**Cobertura esperada:** 33 testes passando (config, game_state, spotify, deezer, game_engine)

---

## 📁 Estrutura de Arquivos

```
Qsong/
├── app/                          # Backend FastAPI
│   ├── config.py                 # Settings (dotenv) — carrega .env, cookie_secure
│   ├── game_state.py             # Serialização/deserialização de sessão (cookie assinado, 7 dias)
│   ├── main.py                   # FastAPI app + middleware sessão + static files + HTTPSRedirect
│   ├── models.py                 # Modelos Pydantic (Track, GameState, RoundResult, etc.)
│   ├── routes/
│   │   ├── auth.py               # /login, /callback, /logout (OAuth Authorization Code Flow)
│   │   └── game.py               # Endpoints: /game/start, /round/*, /game/summary, /user/*
│   └── services/
│       ├── spotify.py            # OAuth (exchange_code, refresh), fetch playlists/tracks, auto-refresh token
│       └── deezer.py             # Busca + matching fuzzy + semáforo 10 req + retry exponencial
├── static/                       # Frontend (servido pelo FastAPI)
│   ├── index.html                # SPA: 4 views (setup → select-playlist → game → summary)
│   ├── game.js                   # Web Audio API, state machine UI, autocomplete, atalhos
│   └── style.css                 # Tema escuro Spotify, responsivo, acessível
├── tests/                        # Suite de testes (pytest + httpx.ASGITransport)
│   ├── test_config.py
│   ├── test_game_state.py
│   ├── test_spotify.py
│   ├── test_deezer.py
│   └── test_game_engine.py
├── requirements.txt              # Dependências produção
├── requirements-dev.txt          # Dependências dev (pytest, ruff, mypy)
├── pyproject.toml                # Config ruff, mypy, pytest
├── .env.example                  # Template de variáveis de ambiente
├── render.yaml                   # Config deploy Render
├── projeto.md                    # Especificação original (regras imutáveis)
├── direcionamento.md             # Guia vivo para agentes/desenvolvedores
└── README.md                     # Este arquivo
```

---

## 🔑 Endpoints da API (Referência Rápida)

### Autenticação
| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/login` | Inicia OAuth Spotify → redireciona para accounts.spotify.com |
| `GET` | `/callback` | Recebe `code`, troca por tokens, seta cookie `auth_session`, redireciona para `/select-playlist` |
| `POST` | `/logout` | Deleta cookie `auth_session` |

### Jogo
| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/game/start?playlist_id=...` ou `?url=...` | Busca faixas (usa user token se logado, senão app token), matching Deezer, cria GameState no cookie `game_session`, retorna `{tracks: [{name, artist}], total, rounds_total}` |
| `POST` | `/round/start` | Sorteia track + offset aleatório, retorna `{preview_url, start_time_ms, clip_duration_ms: 400}` |
| `POST` | `/round/guess` | Body: `{guess: string}` → normaliza (NFD + lower + strip acentos), compara, retorna `{correct, attempt, round_over, game_over, next_clip_duration_ms?, revealed_track?}` |
| `POST` | `/round/skip` | Mesmo efeito de guess errado (consome tentativa) |
| `GET` | `/game/summary` | Retorna `{acertos, erros, rounds: [RoundResult]}` para tela final |

### Usuário (requer login)
| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/user/profile` | Perfil do usuário logado (nome, avatar) |
| `GET` | `/user/playlists` | Lista playlists do usuário (inclui "Músicas Curtidas") |

> **Segurança:** A resposta correta **nunca** vai ao client antes da revelação. Comparação 100% no backend (estado em memória via cookie assinado `game_session`).

---

## ⚙️ Regras de Negócio (Resumo)

| Regra | Detalhe |
|-------|---------|
| **Tentativas por música** | 5 fixas |
| **Duração dos trechos (ms)** | `[400, 800, 1600, 2000, 2500]` |
| **Offset de início** | Sorteado 1x por música ∈ `[0, min(duration_ms, 30000) - 2500]` |
| **Matching Deezer** | Busca por texto livre `"{artista} {nome}"` → filtro fuzzy de artista e de título → maior `rank` entre os que sobrarem |
| **Descartes silenciosos** | Faixas sem match válido na Deezer não entram no pool |
| **Autocomplete** | `<datalist>` nativo — 100% client-side |
| **Sessão de jogo** | Cookie `game_session` assinado (7 dias) guarda apenas o ID da sessão; o `GameState` em si fica em memória no processo — **não sobrevive** a um restart/cold start do servidor |
| **Sessão de auth** | Cookie `auth_session` assinado (7 dias) com tokens do usuário |
| **Anti-trapaça** | Resposta comparada só no backend; preview_url só enviado ao client no round |
| **HTTPS/Cookies** | `COOKIE_SECURE=true` (padrão/produção) → HTTPSRedirect + cookies Secure; `false` (local) → HTTP OK |

---

## ⚠️ Riscos Conhecidos

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| **Dono do app sem Premium (Spotify)** | App para de funcionar (403 "Active premium subscription required") | Fallback Exportify (CSV upload) — ativar só se expirar |
| **Rate limit Spotify** | Falha ao buscar playlist | Cache token app 55min + retry com backoff; auto-refresh user token |
| **Rate limit Deezer (paralelo)** | Matching falha/parcial | Semáforo 10 req simultâneas + retry exponencial (3x) |
| **Cold start Render (15min)** | Perde partida em andamento | Nenhuma hoje — o `GameState` fica só em memória. Mitigação futura: serializar o estado no próprio cookie ou usar um KV externo |
| **CSP bloqueia fetch Deezer** | Áudio não toca | Documentar `connect-src *.dzcdn.net` |
| **Redirect URI mismatch** | OAuth falha | Configurar URIs corretas no Spotify Dashboard (prod + local) |

---

## 📚 Documentação Interna

- **[projeto.md](projeto.md)** — Especificação original completa (regras imutáveis, fluxo end-to-end, matching, áudio, segurança)
- **[direcionamento.md](direcionamento.md)** — Guia vivo para desenvolvimento: checklist por fase, decisões arquiteturais, modelos Pydantic, endpoints, comandos de verificação

---

## 🤝 Contribuição

1. Leia `projeto.md` + `direcionamento.md`
2. Escolha tarefa no checklist da fase atual
3. Implemente com testes (TDD leve: teste falha → código → teste passa)
4. Rode os 3 comandos de verificação (ruff, mypy, pytest)
5. Commit atômico por feature/teste
6. Aguarde prompt para deploy manual no Render

---

## 📄 Licença

Projeto pessoal / educacional. Uso livre para estudo e referência.

---

> **Desenvolvido com ☕ e muito `AudioContext`**  
> Stack: FastAPI • Spotify Web API (OAuth + Client Credentials) • Deezer API • Web Audio API • Render