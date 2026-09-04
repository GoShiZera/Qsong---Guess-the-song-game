# Guess The Song — Especificação do Projeto

## Visão geral

Jogo web de adivinhação musical. O jogador conecta sua conta Spotify, escolhe uma playlist, e o jogo sorteia faixas dessa playlist uma a uma. Para cada faixa, o jogador ouve um trecho curto de áudio (que aumenta de duração a cada tentativa errada) e tenta adivinhar o nome da música usando um campo de busca com autocomplete. Projeto pessoal, sem necessidade de escala — hospedagem gratuita (Render, free tier).

## Stack técnica

- **Frontend:** HTML/CSS/JS puro, servido pelo próprio FastAPI (arquivos estáticos) — sem framework de frontend
- **Fonte de dados de playlist:** Spotify Web API (OAuth Authorization Code Flow) — **requer conta Spotify Premium do dono do app** (confirmado nesta fase do projeto; validade de 3 meses de Premium disponível, suficiente para o prazo de desenvolvimento estimado)
- **Fonte de áudio:** Deezer API (`/search`, endpoint público, sem autenticação) — fornece preview de 30s por faixa
- **Sessão:** cookie assinado, sem banco de dados. Estado de partida mantido em memória no processo do backend (aceitável dado que Render free reinicia o processo após inatividade — se isso acontecer no meio de uma partida, o jogador perde a partida em andamento e precisa recarregar a playlist)
- **Hospedagem:** Render (free tier). Cold start (~30-60s) após 15 min de inatividade é esperado e aceito.

## Por que não usar apenas o Spotify para áudio

O campo `preview_url` da Web API do Spotify foi descontinuado/restringido para a maioria dos apps a partir de nov/2024 e retorna nulo consistentemente. Por isso, o Spotify é usado **apenas como fonte de metadados da playlist** (nome da faixa + artista); o áudio em si vem da Deezer.

## Barreira de política Spotify (contexto para manutenção futura)

Desde fev/2026, o Spotify exige que o **dono do app** (não o usuário final) tenha assinatura Premium ativa para o app funcionar em modo de desenvolvimento — mesmo usando Authorization Code Flow com login de usuário real. Isso foi confirmado via teste manual: o mesmo erro 403 (`Active premium subscription required for the owner of the app`) ocorre tanto em Client Credentials quanto em Authorization Code Flow. Modo de desenvolvimento também limita a 5 usuários de teste allowlisted no Spotify Developer Dashboard.

**Risco documentado:** a assinatura Premium do dono do app garantida para este projeto é válida por 3 meses. Se o desenvolvimento ultrapassar esse prazo, o app para de funcionar. Alternativa de contingência já desenhada e descartável a qualquer momento: fluxo manual via **Exportify** (github.com/pavelkomarov/exportify, 100% client-side, roda com o app Spotify do próprio mantenedor) — usuário exporta a playlist para CSV fora do site, depois faz upload do arquivo no jogo. Não implementado nesta fase; considerar reativar apenas se o Premium expirar antes do projeto terminar.

## Fluxo de dados ponta a ponta

1. `GET /login` → gera URL de autorização Spotify (scope `playlist-read-private`) → redireciona o usuário.
2. `GET /callback?code=...` → troca `code` por `access_token` + `refresh_token`, salva na sessão (cookie), redireciona para a tela de seleção de playlist.
3. `GET /playlists` → chama `/v1/me/playlists` do Spotify (via wrapper com auto-refresh) → devolve lista para o jogador escolher.
4. `GET /playlist/{id}/tracks` → chama `/v1/playlists/{id}/items` (endpoint `/tracks` descontinuado em fev/2026) → extrai `{nome, artista}` de cada faixa → dispara buscas paralelas na Deezer (`asyncio.gather`) → valida cada resultado (ver regra de matching abaixo) → monta pool de faixas jogáveis → guarda pool completo em memória associado à sessão → devolve ao client apenas `{nome, artista}` de cada faixa (sem preview_url ainda), para abastecer o autocomplete.
5. Jogador define o número de rounds (músicas) desejado para a partida, ou deixa em branco para usar o máximo de faixas disponíveis no pool.
6. `POST /round/start` → backend sorteia uma música do pool ainda não jogada, sorteia o ponto de início do corte (ver regra de sorteio abaixo), guarda internamente qual é a resposta certa da rodada (nunca exposta ao client neste momento), devolve `{preview_url, start_time, clip_duration}`.
7. Client toca o trecho via Web Audio API, jogador digita um palpite no campo de busca com autocomplete (filtrando localmente a lista de nomes já carregada) ou aperta skip.
8. `POST /round/guess` (ou `/round/skip`) → backend compara o palpite com a música sorteada (comparação feita inteiramente no servidor) → se errou ou deu skip, registra a tentativa no histórico da rodada, avança para o próximo tempo de corte da sequência fixa, decrementa tentativas restantes → se acertou ou esgotou as 7 tentativas, finaliza a música: revela nome real + artista, toca o preview completo de 30s, registra o resultado no histórico da partida.
9. Repete os passos 6-8 até completar o número de rounds (músicas) definido no passo 5.
10. Ao final da partida, tela de resumo: total de acertos e erros, e detalhamento round a round (música a música) mostrando todos os palpites dados em cada tentativa daquela música + qual era a resposta correta.

## Regra de matching Spotify → Deezer

Para cada faixa `{nome, artista}` vinda do Spotify:

1. Busca na Deezer com query estruturada: `artist:"{artista}" track:"{nome}"`.
2. Entre os resultados retornados, descarta qualquer um cujo `artist.name` não corresponda (razoavelmente) ao artista esperado — isso evita pegar covers, tributos ou artistas de nome parecido.
3. Entre os resultados restantes, escolhe o de maior valor no campo `rank` (heurística observada: a versão original/mais popular tende a ter rank mais alto que remixes, covers e versões ao vivo).
4. Se nenhum resultado passar na validação de artista, a faixa é **descartada silenciosamente** do pool — não entra no jogo, sem aviso ao jogador. Risco aceito: se a taxa de descarte for alta, o jogador pode notar que músicas conhecidas da playlist nunca aparecem, sem explicação visível. Aceito conscientemente para este projeto.

## Regra de sorteio do ponto de início do áudio

- Sorteado **uma única vez por música**, no momento em que o round daquela música começa.
- Esse ponto permanece **fixo** durante todas as tentativas daquela música — apenas a duração do corte tocado a partir desse ponto aumenta a cada tentativa.
- Range válido do sorteio: `0` até `(duração_do_preview - 2.5s)`, garantindo que mesmo o corte mais longo (2.5s, última tentativa) nunca ultrapasse o fim dos 30s do preview.

## Mecânica de tentativas

- **Exatamente 7 tentativas fixas por música**, sempre — não varia por configuração de partida.
- Sequência de duração do corte de áudio, em segundos, por tentativa (constante fixa, não calculada por fórmula): `[0.1, 0.2, 0.4, 0.8, 1.6, 2.0, 2.5]`.
- Skip consome uma tentativa, com o mesmo efeito de um palpite errado (avança para o próximo tempo da sequência).
- Sem pontuação numérica — apenas contagem de acertos e erros por partida.

## Reprodução de áudio (frontend)

- **Não usar a tag `<audio>` simples** — a precisão necessária para cortes de 0.1s exige a **Web Audio API** (`AudioContext`, `fetch` → `decodeAudioData` → `AudioBufferSourceNode` com `start(quando, ponto_inicio, duração)`), já que `play()`/`pause()` via DOM têm latência variável que compromete cortes tão curtos.
- Testado e confirmado: não há bloqueio de CORS/CSP no fetch direto de URLs de preview da Deezer a partir de uma página sem CSP restritivo. Atenção: se a hospedagem de produção aplicar um header CSP, é necessário permitir explicitamente `connect-src` para o domínio de CDN da Deezer (`*.dzcdn.net`).

## Segurança de validação (anti-trapaça)

O nome da música sorteada **nunca é enviado ao client** até o momento da revelação (acerto ou esgotamento de tentativas). Toda comparação entre palpite e resposta correta acontece no backend, dentro do estado de sessão em memória — o client recebe apenas o áudio e a lista de opções para o autocomplete, nunca a resposta da rodada atual antecipadamente. Isso permite evoluir futuramente para modos competitivos/multiplayer sem redesenhar o fluxo de dados, apenas reforçando autenticação.

## Renovação automática de token (auto-refresh)

Implementado como uma função wrapper única (`chamar_spotify_com_refresh`) que envolve todas as chamadas à API do Spotify: se uma chamada retornar 401 (token expirado), a função renova automaticamente via `refresh_token`, atualiza a sessão (inclusive se o Spotify rotacionar para um novo `refresh_token`) e repete a chamada original de forma transparente para quem a invocou. Toda nova função que precisar falar com a API do Spotify deve obrigatoriamente passar por esse wrapper — chamadas feitas fora dele não têm proteção contra expiração de token.

## Estrutura de arquivos

```
projeto/
├── app/
│   ├── main.py              # cria o FastAPI, registra rotas
│   ├── config.py             # variáveis de ambiente (client_id, client_secret, redirect_uri)
│   ├── routes/
│   │   ├── auth.py           # /login, /callback
│   │   └── game.py           # /playlists, /playlist/{id}/tracks, /round/start, /round/guess, /round/skip
│   ├── services/
│   │   ├── spotify.py        # troca code por token, wrapper de auto-refresh, listar playlists/faixas
│   │   └── deezer.py         # busca de faixa, validação de matching, montagem do pool
│   ├── game_state.py         # dicionário em memória: sessão → EstadoPartida (pool, música atual, round atual, tentativas, histórico de palpites)
│   └── models.py             # modelos Pydantic das estruturas de dados trafegadas
├── static/
│   ├── index.html
│   ├── game.js                # lógica de jogo no client, Web Audio API, autocomplete local
│   └── style.css
└── requirements.txt
```

## Especificação de UI/UX

### Identidade visual
- Fundo principal cinza escuro, paleta e estilo de botões inspirados na identidade visual do Spotify.

### Tela de configuração da partida
- Seleção da playlist (obrigatória).
- Campo opcional para escolher o número de rounds (músicas) da partida. Se não preenchido, usa o número máximo de faixas disponíveis no pool após o matching com a Deezer.

### Estados de carregamento
- Sempre que houver espera (ex: buscando faixas e fazendo matching com a Deezer), exibir barra de progresso.

### Tela de jogo (durante uma música)
- Contador de tentativas no formato `X/7`.
- Ao lado esquerdo, checkboxes representando as 7 tentativas, visíveis por completo desde o início da música (não aparecem progressivamente) — cada tentativa errada ou skip marca a caixinha correspondente com um X vermelho.
- Barra de player mostrando a música tocando, posicionada entre o placar (contador/checkboxes) e o campo de palpite.
- Campo de palpite no estilo de barra de busca, com dropdown de autocomplete que filtra a lista de faixas da playlist conforme o jogador digita (filtragem client-side, sem nova chamada ao backend a cada tecla).
- Botão de enviar palpite com o texto "Adivinhar", cor verde, ao lado do campo de busca.

### Fim de música (round individual)
- Ao acertar ou esgotar as 7 tentativas: revela o nome correto da faixa + artista, e toca o preview completo de 30 segundos.

### Fim de partida (após todos os rounds)
- Tela de resumo mostrando: total de acertos e total de erros da partida.
- Detalhamento navegável round a round (música a música): para cada música jogada, lista todos os palpites dados em cada tentativa + qual era a resposta correta.

## Pendências conhecidas (não bloqueiam início do desenvolvimento, mas precisam de decisão eventual)

- Nenhum tratamento de erro definido para o caso em que o `refresh_token` também expira ou é revogado (o que exigiria novo login completo). Fluxo de erro/reautenticação nesse cenário ainda não desenhado.
- Nenhuma persistência entre sessões do servidor — reinício do processo (comum em cold start do Render) descarta partidas em andamento sem aviso ao jogador.