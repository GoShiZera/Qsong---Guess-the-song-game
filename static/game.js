// ============================================
// Guess The Song - Frontend Game Logic
// Web Audio API + Autocomplete + State Machine + Spotify Auth
// ============================================

(() => {
    'use strict';

    // ---------- Constants ----------
    const CLIP_DURATIONS = [400, 800, 1600, 2000, 2500];
    const MAX_ATTEMPTS = 5;
    const API_BASE = '';

    // ---------- State ----------
    const state = {
        view: 'setup',
        sessionCookie: null,
        pool: [],
        currentTrack: null,
        startOffset: 0,
        attempt: 0,
        roundNumber: 1,
        totalRounds: 0,
        correctCount: 0,
        wrongCount: 0,
        roundHistory: [],
        audioCtx: null,
        audioBuffer: null,
        sourceNode: null,
        gainNode: null,
        isPlaying: false,
        playStartTime: 0,
        scheduledStopTime: 0,
        progressAnimationId: null,
        selectedPlaylistId: null,
        currentClipDuration: 100,  // Track current clip duration
        currentRoundGuesses: [], // array de { attempt, guess, correct, skipped }
    };

    // ---------- DOM Elements ----------
    const els = {
        // Views
        viewSetup: document.getElementById('view-setup'),
        viewSelectPlaylist: document.getElementById('view-select-playlist'),
        viewGame: document.getElementById('view-game'),
        viewSummary: document.getElementById('view-summary'),

        // Setup (public)
        setupForm: document.getElementById('setup-form'),
        playlistInput: document.getElementById('playlist-input'),
        roundsInput: document.getElementById('rounds-input'),
        btnStart: document.getElementById('btn-start'),
        setupError: document.getElementById('setup-error'),
        setupProgress: document.getElementById('setup-progress'),
        progressBar: document.querySelector('#setup-progress .progress-bar'),
        progressText: document.querySelector('#setup-progress .progress-text'),

        // Login
        btnLoginSpotify: document.getElementById('btn-login-spotify'),

        // Select Playlist (after login)
        userProfile: document.getElementById('user-profile'),
        userAvatar: document.getElementById('user-avatar'),
        userName: document.getElementById('user-name'),
        btnLogout: document.getElementById('btn-logout'),
        playlistsLoading: document.getElementById('playlists-loading'),
        playlistsError: document.getElementById('playlists-error'),
        playlistsList: document.getElementById('playlists-list'),
        roundsInputSelect: document.getElementById('rounds-input-select'),
        selectUrlForm: document.getElementById('select-url-form'),
        selectPlaylistInput: document.getElementById('select-playlist-input'),
        btnStartSelectUrl: document.getElementById('btn-start-select-url'),
        // Select playlist config
        selectPlaylistConfig: document.getElementById('select-playlist-config'),
        selectRoundsInput: document.getElementById('select-rounds-input'),
        btnStartPlaylistGame: document.getElementById('btn-start-playlist-game'),

        // Game
        scoreCorrect: document.getElementById('score-correct'),
        scoreTotal: document.getElementById('score-total'),
        totalRounds: document.getElementById('total-rounds'),
        attemptsBoxes: document.getElementById('attempts-boxes'),
        playerContainer: document.getElementById('player-container'),
        waveform: document.getElementById('waveform'),
        btnPlayPause: document.getElementById('btn-play-pause'),
        timeCurrent: document.getElementById('time-current'),
        timeTotal: document.getElementById('time-total'),
        progressBarPlayer: document.getElementById('progress-bar-player'),
        guessForm: document.getElementById('guess-form'),
        guessInput: document.getElementById('guess-input'),
        tracksDatalist: document.getElementById('tracks-datalist'),
        btnGuess: document.getElementById('btn-guess'),
        btnSkip: document.getElementById('btn-skip'),
        roundResult: document.getElementById('round-result'),

        // HUD Clip Info
        clipAttemptLabel: document.getElementById('clip-attempt-label'),
        clipDurationLabel: document.getElementById('clip-duration-label'),

        // Guess Log
        guessLog: document.getElementById('guess-log'),
        guessLogList: document.getElementById('guess-log-list'),

        // Back Home Modal
        btnBackHome: document.getElementById('btn-back-home'),
        modalConfirmBack: document.getElementById('modal-confirm-back'),
        modalBtnCancel: document.getElementById('modal-btn-cancel'),
        modalBtnConfirm: document.getElementById('modal-btn-confirm'),

        // Summary
        finalCorrect: document.getElementById('final-correct'),
        finalWrong: document.getElementById('final-wrong'),
        roundsDetail: document.getElementById('rounds-detail'),
        btnNewGame: document.getElementById('btn-new-game'),

        // Round Result
        resultCover: document.getElementById('result-cover'),
        resultStatus: document.getElementById('result-status'),
        resultTrackName: document.getElementById('result-track-name'),
        resultArtist: document.getElementById('result-artist'),
        btnNextRound: document.getElementById('btn-next-round'),
    };

    // ---------- Utility Functions ----------
    const $ = (sel, ctx = document) => ctx.querySelector(sel);
    const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

    const formatTime = (ms) => {
        if (ms < 1000) {
            return `${(ms / 1000).toFixed(1)}s`;
        }
        const totalSec = Math.floor(ms / 1000);
        const min = Math.floor(totalSec / 60);
        const sec = totalSec % 60;
        return `${min}:${sec.toString().padStart(2, '0')}`;
    };

    const showView = (viewName) => {
        const viewMap = {
            setup: 'viewSetup',
            selectPlaylist: 'viewSelectPlaylist',
            game: 'viewGame',
            summary: 'viewSummary',
        };
        Object.entries(viewMap).forEach(([key, elKey]) => {
            const isActive = key === viewName;
            els[elKey].classList.toggle('active', isActive);
            els[elKey].hidden = !isActive;
        });
        state.view = viewName;
    };

    const setLoading = (btn, loading) => {
        btn.disabled = loading;
        const text = btn.querySelector('.btn-text');
        const loader = btn.querySelector('.btn-loader');
        if (text) text.hidden = loading;
        if (loader) loader.hidden = !loading;
    };

    const showError = (el, msg) => {
        el.textContent = msg;
        el.hidden = false;
    };

    const hideError = (el) => {
        el.hidden = true;
    };

    const updateProgress = (percent, text) => {
        if (els.progressBar) {
            els.progressBar.value = percent;
            els.progressBar.style.setProperty('--progress', `${percent}%`);
        }
        if (els.progressText) els.progressText.textContent = text;
    };

    // ---------- Modal Confirm Back Home ----------
    const showConfirmBackModal = () => {
        stopAudio();
        if (els.modalConfirmBack) {
            els.modalConfirmBack.hidden = false;
            els.modalBtnCancel?.focus();
        }
    };

    const hideConfirmBackModal = () => {
        if (els.modalConfirmBack) {
            els.modalConfirmBack.hidden = true;
        }
    };

    const confirmBackHome = () => {
        hideConfirmBackModal();
        stopAudio();
        // Redireciona a página para a URL raiz limpa
        window.location.href = '/';
    };

    // ---------- Audio (Web Audio API) ----------
    const initAudioContext = () => {
        if (!state.audioCtx) {
            state.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            state.gainNode = state.audioCtx.createGain();
            state.gainNode.connect(state.audioCtx.destination);
            state.gainNode.gain.value = 1.0;
        }
        if (state.audioCtx.state === 'suspended') {
            state.audioCtx.resume();
        }
    };

    const fetchAndDecodeAudio = async (url) => {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`Failed to fetch audio: ${response.status}`);
        const arrayBuffer = await response.arrayBuffer();
        return state.audioCtx.decodeAudioData(arrayBuffer);
    };

    const playClip = async (previewUrl, startTimeMs, durationMs) => {
        if (!previewUrl) {
            console.warn('No preview URL provided');
            return;
        }
        
        // Store current clip duration for replay
        state.currentClipDuration = durationMs;
        
        initAudioContext();
        stopAudio();

        try {
            state.audioBuffer = await fetchAndDecodeAudio(previewUrl);
        } catch (e) {
            console.error('Audio decode error:', e);
            // Re-enable controls so user can skip or guess
            setGameControlsEnabled(true);
            return;
        }

        const startTime = startTimeMs / 1000;
        const duration = durationMs / 1000;
        const bufferDuration = state.audioBuffer.duration;

        const actualStart = Math.min(startTime, bufferDuration - 0.05);
        const actualDuration = Math.min(duration, bufferDuration - actualStart);

        state.sourceNode = state.audioCtx.createBufferSource();
        state.sourceNode.buffer = state.audioBuffer;
        state.sourceNode.connect(state.gainNode);

        state.sourceNode.start(0, actualStart, actualDuration);

        state.isPlaying = true;
        state.playStartTime = state.audioCtx.currentTime;
        state.scheduledStopTime = state.playStartTime + actualDuration;

        updateWaveform(true);
        updatePlayPauseButton(true);
        startProgressLoop(actualDuration * 1000);

        state.sourceNode.onended = () => onAudioEnded();
    };

    const stopAudio = () => {
        if (state.sourceNode) {
            try { state.sourceNode.stop(); } catch {}
            state.sourceNode.onended = null;
            state.sourceNode.disconnect();
            state.sourceNode = null;
        }
        state.isPlaying = false;
        stopProgressLoop();
        updateWaveform(false);
        updatePlayPauseButton(false);
    };

    const togglePlayPause = () => {
        if (state.isPlaying) {
            stopAudio();
        } else if (state.audioBuffer && state.currentTrack) {
            // If audio was ended (scheduledStopTime <= currentTime), replay from start
            if (state.scheduledStopTime <= state.audioCtx.currentTime) {
                // Replay full preview from start (limited to 30s)
                const previewUrl = state.currentTrack?.preview_url;
                const previewDurationMs = Math.min(state.currentTrack?.duration_ms || 30000, 30000);
                if (previewUrl) {
                    playFullPreview(previewUrl, previewDurationMs);
                }
            } else {
                resumeAudio();
            }
        }
    };

    const replayClip = () => {
        if (!state.audioBuffer || !state.currentTrack) return;
        initAudioContext();
        stopAudio();

        const startTime = state.startOffset / 1000;
        const duration = state.currentClipDuration / 1000;
        const bufferDuration = state.audioBuffer.duration;

        const actualStart = Math.min(startTime, bufferDuration - 0.05);
        const actualDuration = Math.min(duration, bufferDuration - actualStart);

        state.sourceNode = state.audioCtx.createBufferSource();
        state.sourceNode.buffer = state.audioBuffer;
        state.sourceNode.connect(state.gainNode);

        state.sourceNode.start(0, actualStart, actualDuration);

        state.isPlaying = true;
        state.playStartTime = state.audioCtx.currentTime;
        state.scheduledStopTime = state.playStartTime + actualDuration;

        updateWaveform(true);
        updatePlayPauseButton(true);
        startProgressLoop(actualDuration * 1000);

        state.sourceNode.onended = () => onAudioEnded();
    };

    const resumeAudio = () => {
        if (!state.audioBuffer || !state.currentTrack) return;
        initAudioContext();

        const elapsed = state.audioCtx.currentTime - state.playStartTime;
        const remaining = Math.max(0, state.scheduledStopTime - state.audioCtx.currentTime);

        state.sourceNode = state.audioCtx.createBufferSource();
        state.sourceNode.buffer = state.audioBuffer;
        state.sourceNode.connect(state.gainNode);

        const startOffset = state.startOffset / 1000 + elapsed;
        state.sourceNode.start(0, startOffset, remaining);

        state.isPlaying = true;
        state.playStartTime = state.audioCtx.currentTime;
        state.scheduledStopTime = state.audioCtx.currentTime + remaining;

        updateWaveform(true);
        updatePlayPauseButton(true);
        startProgressLoop(remaining * 1000);

        state.sourceNode.onended = () => onAudioEnded();
    };

    const onAudioEnded = () => {
        state.isPlaying = false;
        state.sourceNode = null;
        stopProgressLoop();
        updateWaveform(false);
        updatePlayPauseButton(false);
        els.timeCurrent.textContent = els.timeTotal.textContent;
        if (els.progressBarPlayer) {
            els.progressBarPlayer.style.setProperty('--progress', '100%');
            const fill = els.progressBarPlayer.querySelector('.progress-fill');
            if (fill) fill.style.width = '100%';
        }
    };

    const startProgressLoop = (totalMs) => {
        stopProgressLoop();
        const start = performance.now();
        const animate = () => {
            if (!state.isPlaying) return;
            const elapsed = performance.now() - start;
            const progress = Math.min(1, elapsed / totalMs);
            const currentMs = Math.min(totalMs, elapsed);
            els.timeCurrent.textContent = formatTime(currentMs);
            if (els.progressBarPlayer) {
                els.progressBarPlayer.style.setProperty('--progress', `${progress * 100}%`);
                const fill = els.progressBarPlayer.querySelector('.progress-fill');
                if (fill) fill.style.width = `${progress * 100}%`;
            }
            state.progressAnimationId = requestAnimationFrame(animate);
        };
        animate();
    };

    const stopProgressLoop = () => {
        if (state.progressAnimationId) {
            cancelAnimationFrame(state.progressAnimationId);
            state.progressAnimationId = null;
        }
    };

    const updateWaveform = (playing) => {
        els.waveform.classList.toggle('playing', playing);
    };

    const updatePlayPauseButton = (playing) => {
        const playIcon = els.btnPlayPause.querySelector('.icon-play');
        const pauseIcon = els.btnPlayPause.querySelector('.icon-pause');
        if (playIcon && pauseIcon) {
            playIcon.hidden = playing;
            pauseIcon.hidden = !playing;
        }
        els.btnPlayPause.setAttribute('aria-label', playing ? 'Pausar' : 'Tocar');
    };

    const updateClipInfo = (attemptNumber, durationMs) => {
        if (els.clipAttemptLabel) {
            els.clipAttemptLabel.textContent = `Tentativa ${attemptNumber}/5`;
        }
        if (els.clipDurationLabel) {
            const durationSec = (durationMs / 1000).toFixed(1);
            els.clipDurationLabel.textContent = `Trecho: ${durationSec}s`;
        }
    };

    // Play full preview (from 0 to end of preview, max 30s)
    const playFullPreview = async (previewUrl, durationMs) => {
        if (!previewUrl) {
            console.warn('No preview URL provided');
            return;
        }
        
        // Limit preview duration to 30 seconds (30000ms)
        const limitedDurationMs = Math.min(durationMs, 30000);
        state.currentClipDuration = limitedDurationMs;
        
        initAudioContext();
        stopAudio();

        try {
            state.audioBuffer = await fetchAndDecodeAudio(previewUrl);
        } catch (e) {
            console.error('Audio decode error:', e);
            return;
        }

        const bufferDuration = state.audioBuffer.duration;
        const actualDuration = Math.min(limitedDurationMs / 1000, bufferDuration);

        state.sourceNode = state.audioCtx.createBufferSource();
        state.sourceNode.buffer = state.audioBuffer;
        state.sourceNode.connect(state.gainNode);

        state.sourceNode.start(0, 0, actualDuration);

        state.isPlaying = true;
        state.playStartTime = state.audioCtx.currentTime;
        state.scheduledStopTime = state.playStartTime + actualDuration;

        updateWaveform(true);
        updatePlayPauseButton(true);
        startProgressLoop(actualDuration * 1000);

        state.sourceNode.onended = () => onAudioEnded();
    };

    // ---------- API Calls ----------
    const api = {
        async startGame(playlistId, rounds) {
            const params = new URLSearchParams({ playlist_id: playlistId });
            if (rounds) params.set('rounds', rounds.toString());
            const res = await fetch(`${API_BASE}/game/start?${params}`, {
                credentials: 'include',
            });
            return handleResponse(res);
        },

        async getUserProfile() {
            const res = await fetch(`${API_BASE}/user/profile`, {
                credentials: 'include',
            });
            return handleResponse(res);
        },

        async getUserPlaylists() {
            const res = await fetch(`${API_BASE}/user/playlists`, {
                credentials: 'include',
            });
            return handleResponse(res);
        },

        async startRound() {
            const res = await fetch(`${API_BASE}/round/start`, {
                method: 'POST',
                credentials: 'include',
            });
            return handleResponse(res);
        },

        async guess(guessText) {
            const res = await fetch(`${API_BASE}/round/guess`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ guess: guessText }),
            });
            return handleResponse(res);
        },

        async skip() {
            const res = await fetch(`${API_BASE}/round/skip`, {
                method: 'POST',
                credentials: 'include',
            });
            return handleResponse(res);
        },

        async summary() {
            const res = await fetch(`${API_BASE}/game/summary`, {
                credentials: 'include',
            });
            return handleResponse(res);
        },

        async logout() {
            const res = await fetch(`${API_BASE}/logout`, {
                method: 'POST',
                credentials: 'include',
            });
            return handleResponse(res);
        },
    };

    const handleResponse = async (res) => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            let errorMsg = data.detail || `HTTP ${res.status}`;
            if (res.status === 502 || res.status === 500) {
                errorMsg = 'Erro de conexão com Spotify. Verifique sua internet e tente novamente.';
            } else if (res.status === 404) {
                errorMsg = data.detail || 'Nenhuma faixa disponível. Tente outra playlist.';
            } else if (res.status === 401) {
                errorMsg = 'Sessão expirada. Faça login novamente.';
            }
            const err = new Error(errorMsg);
            err.status = res.status;
            err.data = data;
            throw err;
        }
        return data;
    };

    // ---------- UI Rendering ----------
    const createAttemptBoxes = () => {
        els.attemptsBoxes.innerHTML = '';
        for (let i = 0; i < MAX_ATTEMPTS; i++) {
            const box = document.createElement('div');
            box.className = 'attempt-box';
            box.dataset.attempt = i + 1;
            box.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
            els.attemptsBoxes.appendChild(box);
        }
    };

    const markAttempt = (attemptIndex, correct) => {
        const box = els.attemptsBoxes.querySelector(`[data-attempt="${attemptIndex + 1}"]`);
        if (box) {
            box.classList.remove('wrong', 'correct');
            box.classList.add(correct ? 'correct' : 'wrong');
        }
    };

    const resetAttemptBoxes = () => {
        $$('.attempt-box', els.attemptsBoxes).forEach(box => {
            box.classList.remove('wrong', 'correct');
        });
    };

    const addGuessToLog = (attemptNumber, guessText, isCorrect, isSkip) => {
        // Adiciona ao estado local da rodada
        state.currentRoundGuesses.push({
            attempt: attemptNumber,
            guess: guessText,
            correct: isCorrect,
            skipped: isSkip,
        });
        // Determina a classe e ícone do item
        let itemClass, iconSvg;
        if (isCorrect) {
            itemClass = 'correct';
            iconSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                           <polyline points="20 6 9 17 4 12"></polyline>
                       </svg>`;
        } else if (isSkip) {
            itemClass = 'skipped';
            iconSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                           <polyline points="5 12 12 5 19 12"></polyline>
                       </svg>`;
        } else {
            itemClass = 'wrong';
            iconSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                           <line x1="18" y1="6" x2="6" y2="18"></line>
                           <line x1="6" y1="6" x2="18" y2="18"></line>
                       </svg>`;
        }
        const displayText = isSkip
            ? '— Pulou —'
            : (guessText && guessText.trim() ? guessText : '— Pulou —');
        const li = document.createElement('li');
        li.className = `guess-log-item ${itemClass}`;
        li.innerHTML = `
            <span class="guess-log-num">${attemptNumber}</span>
            <span class="guess-log-text">${displayText}</span>
            <span class="guess-log-icon">${iconSvg}</span>
        `;
        els.guessLogList.appendChild(li);
        // Exibe o container se ainda estava oculto
        els.guessLog.hidden = false;
    };

    const clearGuessLog = () => {
        state.currentRoundGuesses = [];
        els.guessLogList.innerHTML = '';
        els.guessLog.hidden = true;
    };

    const populateDatalist = (tracks) => {
        els.tracksDatalist.innerHTML = '';
        // Sort tracks alphabetically by name (A-Z)
        const sortedTracks = [...tracks].sort((a, b) =>
            a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
        );
        const seen = new Set();
        sortedTracks.forEach(t => {
            const artist = t.artist || '';
            const displayValue = artist ? `${t.name} - ${artist}` : t.name;
            // Avoid duplicate entries in the datalist
            if (seen.has(displayValue)) return;
            seen.add(displayValue);
            const option = document.createElement('option');
            option.value = displayValue;
            els.tracksDatalist.appendChild(option);
        });
    };

    const updateScoreDisplay = () => {
        els.scoreCorrect.querySelector('strong').textContent = state.correctCount;
        els.scoreTotal.querySelector('strong').textContent = state.roundNumber;
        els.totalRounds.textContent = state.totalRounds;
    };

    const setGameControlsEnabled = (enabled) => {
        els.guessInput.disabled = !enabled;
        els.btnGuess.disabled = !enabled;
        els.btnSkip.disabled = !enabled;
        // btnPlayPause permanece habilitado para permitir reproduzir/pausar o preview revelado
        els.btnPlayPause.disabled = false;
    };

    const showRoundResult = (data, trackName) => {
        const isCorrect = data.correct;
        const isRoundOver = data.round_over || data.game_over || Boolean(data.revealed_track);
        const isGameOver = data.game_over || state.roundNumber >= state.totalRounds;
        
        let displayTrackName = '';
        let displayArtist = '';
        let coverUrl = '';
        
        if (isRoundOver && data.revealed_track) {
            // Round is over - show the actual track name and artist
            displayTrackName = data.revealed_track.name;
            displayArtist = data.revealed_track.artist;
            coverUrl = data.revealed_track.image_url || '';
        } else if (data.correct) {
            // Correct guess - use the guessed track name
            displayTrackName = trackName;
            displayArtist = state.currentTrack?.artist || '';
            coverUrl = state.currentTrack?.image_url || '';
        } else {
            // Wrong guess or skip - show what was guessed or "Pulou"
            displayTrackName = trackName || 'Pulou';
            displayArtist = '';
            coverUrl = state.currentTrack?.image_url || '';
        }
        
        // Update the result card elements
        if (els.resultCover) {
            if (coverUrl) {
                els.resultCover.src = coverUrl;
                els.resultCover.hidden = false;
            } else {
                els.resultCover.hidden = true;
            }
        }
        
        if (els.resultStatus) {
            els.resultStatus.textContent = isCorrect ? 'Acertou!' : 'Errou!';
            els.resultStatus.className = `result-status ${isCorrect ? 'correct' : 'wrong'}`;
        }
        
        if (els.resultTrackName) {
            els.resultTrackName.textContent = displayTrackName;
        }
        
        if (els.resultArtist) {
            els.resultArtist.textContent = displayArtist;
        }
        
        // Show/hide and set next button text
        if (els.btnNextRound) {
            if (isGameOver) {
                els.btnNextRound.textContent = 'Ver Resumo';
            } else {
                els.btnNextRound.textContent = 'Próxima Rodada';
            }
            els.btnNextRound.hidden = false;
        }
        
        // Show the result card
        els.roundResult.hidden = false;
        els.roundResult.className = `round-result ${isCorrect ? 'correct' : 'wrong'}`;
        
        // Disable guess controls
        setGameControlsEnabled(false);
        
        // Play full preview (limited to 30s)
        const previewUrl = data.revealed_track?.preview_url || state.currentTrack?.preview_url;
        const previewDurationMs = Math.min(data.revealed_track?.duration_ms || state.currentTrack?.duration_ms || 30000, 30000);
        if (previewUrl) {
            playFullPreview(previewUrl, previewDurationMs);
            els.timeCurrent.textContent = formatTime(0);
            els.timeTotal.textContent = formatTime(previewDurationMs);
        }
    };

    const hideRoundResult = () => {
        els.roundResult.hidden = true;
    };

    const renderSummary = (summary) => {
        els.finalCorrect.textContent = summary.acertos ?? 0;
        els.finalWrong.textContent = summary.erros ?? 0;

        els.roundsDetail.innerHTML = '';
        (summary.rounds || []).forEach((round, idx) => {
            const card = document.createElement('div');
            card.className = `round-card ${round.correct ? 'correct' : 'wrong'}`;
            card.innerHTML = `
                <div class="round-header">
                    <span class="round-number">Rodada ${idx + 1}</span>
                    <span class="round-outcome">${round.correct ? 'Acertou' : 'Errou'}</span>
                </div>
                <div class="round-track">
                    <span class="round-track-name">${round.track?.name || 'Música'}</span>
                    <span class="round-track-artist">${round.track?.artist || ''}</span>
                </div>
                <div class="round-guesses">
                    ${(round.guesses || []).map(g => `
                        <span class="guess-tag ${g.correct ? 'correct' : ''}">
                            ${g.attempt}. ${g.guess}
                        </span>
                    `).join('')}
                </div>
            `;
            els.roundsDetail.appendChild(card);
        });
    };

    const renderPlaylists = (playlists) => {
        els.playlistsList.innerHTML = '';
        if (!playlists.length) {
            els.playlistsList.innerHTML = '<li class="playlists-empty">Nenhuma playlist encontrada</li>';
            return;
        }
        playlists.forEach(pl => {
            const li = document.createElement('li');
            li.className = 'playlist-item';
            li.tabIndex = 0;
            li.dataset.playlistId = pl.id;
            const imgUrl = pl.images?.[0]?.url || '';
            const trackCount = pl.tracks_total || 0;
            li.innerHTML = `
                ${imgUrl ? `<img src="${imgUrl}" alt="" loading="lazy">` : '<div class="playlist-placeholder" style="width:56px;height:56px;border-radius:8px;background:var(--bg-tertiary);display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:20px;">🎵</div>'}
                <div class="playlist-info">
                    <span class="playlist-name">${pl.name}</span>
                    <span class="playlist-meta">${trackCount} faixas ${pl.public ? '• Pública' : '• Privada'}</span>
                </div>
                <svg class="playlist-arrow" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>
            `;
            const selectPlaylist = () => {
                // Visual selection
                $$('.playlist-item', els.playlistsList).forEach(item => item.classList.remove('selected'));
                li.classList.add('selected');
                state.selectedPlaylistId = pl.id;
                // Show config and enable start button
                if (els.selectPlaylistConfig) {
                    els.selectPlaylistConfig.hidden = false;
                }
                if (els.btnStartPlaylistGame) {
                    els.btnStartPlaylistGame.disabled = false;
                }
            };
            li.addEventListener('click', selectPlaylist);
            li.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    selectPlaylist();
                }
            });
            els.playlistsList.appendChild(li);
        });
    };

    // ---------- Game Flow ----------
    const startNewGame = async (playlistId, rounds) => {
        hideError(els.setupError);
        els.setupForm.hidden = true;
        els.setupProgress.hidden = false;
        setLoading(els.btnStart, true);
        updateProgress(0, 'Conectando ao Spotify...');

        try {
            const progressSteps = [
                { p: 20, t: 'Buscando playlist...' },
                { p: 40, t: 'Encontrando prévias no Deezer...' },
                { p: 70, t: 'Validando faixas...' },
                { p: 90, t: 'Preparando jogo...' },
            ];

            for (const step of progressSteps) {
                updateProgress(step.p, step.t);
                await new Promise(r => setTimeout(r, 300));
            }

            const data = await api.startGame(playlistId, rounds);
            
            updateProgress(100, 'Pronto!');
            await new Promise(r => setTimeout(r, 300));

            state.pool = data.tracks.map(t => ({ name: t.name, artist: t.artist }));
            state.totalRounds = data.rounds_total;
            state.roundNumber = 1;
            state.correctCount = 0;
            state.wrongCount = 0;
            state.roundHistory = [];

            populateDatalist(data.tracks);
            createAttemptBoxes();
            updateScoreDisplay();
            showView('game');
            await startNextRound();

        } catch (err) {
            console.error('Start game error:', err);
            const msg = err.message || 'Erro desconhecido';
            if (err.status === 502 || err.status === 500 || msg.includes('Erro de conexão com Spotify')) {
                showError(els.setupError, 'Erro de conexão com Spotify. Verifique sua internet e tente novamente.');
            } else if (msg.includes('Nenhuma faixa') || msg.includes('Nenhuma faixa válida')) {
                showError(els.setupError, 'Nenhuma faixa disponível nesta playlist. Tente outra playlist.');
            } else if (msg.includes('Não autenticado') || err.status === 401) {
                showError(els.setupError, 'Sessão expirada. Faça login novamente.');
            } else {
                showError(els.setupError, msg);
            }
            els.setupForm.hidden = false;
        } finally {
            els.setupProgress.hidden = true;
            setLoading(els.btnStart, false);
        }
    };

    const startGameFromPlaylist = async (playlistId, rounds = null) => {
        state.selectedPlaylistId = playlistId;
        hideError(els.playlistsError);
        els.playlistsList.hidden = true;
        els.playlistsLoading.hidden = false;
        try {
            const data = await api.startGame(playlistId, rounds);
            updateProgress(100, 'Pronto!');
            await new Promise(r => setTimeout(r, 300));

            state.pool = data.tracks.map(t => ({ name: t.name, artist: t.artist }));
            state.totalRounds = data.rounds_total;
            state.roundNumber = 1;
            state.correctCount = 0;
            state.wrongCount = 0;
            state.roundHistory = [];

            populateDatalist(data.tracks);
            createAttemptBoxes();
            updateScoreDisplay();
            showView('game');
            await startNextRound();
        } catch (err) {
            console.error('Start game error:', err);
            const msg = err.message || 'Erro desconhecido';
            if (err.status === 502 || err.status === 500 || msg.includes('Erro de conexão com Spotify')) {
                showError(els.playlistsError, 'Erro de conexão com Spotify. Verifique sua internet e tente novamente.');
            } else if (msg.includes('Nenhuma faixa') || msg.includes('Nenhuma faixa válida')) {
                showError(els.playlistsError, 'Nenhuma faixa disponível nesta playlist. Tente outra playlist.');
            } else if (msg.includes('Não autenticado') || err.status === 401) {
                showError(els.playlistsError, 'Sessão expirada. Faça login novamente.');
            } else {
                showError(els.playlistsError, msg);
            }
            els.playlistsList.hidden = false;
        } finally {
            els.playlistsLoading.hidden = true;
        }
    };

    const startNextRound = async () => {
        if (state.roundNumber > state.totalRounds) {
            await finishGame();
            return;
        }

        hideRoundResult();
        if (els.btnNextRound) {
            els.btnNextRound.hidden = true;
        }
        resetAttemptBoxes();
        clearGuessLog();
        state.attempt = 0;
        setGameControlsEnabled(false);
        els.guessInput.value = '';
        els.timeCurrent.textContent = '0:00';
        els.timeTotal.textContent = '0:00';
        if (els.progressBarPlayer) {
            els.progressBarPlayer.style.setProperty('--progress', '0%');
            const fill = els.progressBarPlayer.querySelector('.progress-fill');
            if (fill) fill.style.width = '0%';
        }
        updateWaveform(false);
        updatePlayPauseButton(false);

        try {
            const data = await api.startRound();
            if (!data.preview_url) {
                throw new Error('Sem preview de áudio disponível para esta faixa');
            }
            state.currentTrack = data;
            state.startOffset = data.start_time_ms;

            els.timeCurrent.textContent = formatTime(0);
            els.timeTotal.textContent = formatTime(data.clip_duration_ms);
            setGameControlsEnabled(true);
            els.guessInput.focus();

            await playClip(data.preview_url, data.start_time_ms, data.clip_duration_ms);
            updateClipInfo(1, data.clip_duration_ms);
            updateScoreDisplay();

        } catch (err) {
            console.error('Start round error:', err);
            const msg = err.message || 'Erro desconhecido';
            // If game is already finished or no tracks available, finish the game
            if (err.status === 400 || msg.includes('Partida já finalizada') || msg.includes('Nenhuma faixa com preview disponível')) {
                await finishGame();
                return;
            }
            setGameControlsEnabled(true); // Re-enable controls on error
            showRoundResult({ correct: false, revealed_track: { name: 'Erro ao carregar faixa', artist: '' } }, 'Erro');
        }
    };

    const handleGuess = async (guessText) => {
        if (!guessText.trim() || !state.currentTrack) return;

        setGameControlsEnabled(false);
        stopAudio();

        try {
            const data = await api.guess(guessText);
            state.attempt = data.attempt;
            markAttempt(state.attempt - 1, data.correct);

            // Use revealed_track if available, otherwise use the guessed text
            const trackName = data.revealed_track?.name || guessText;
            
            // Adicionar ao log de palpites ANTES de mostrar resultado
            const attemptDisplayNumber = state.attempt;
            addGuessToLog(attemptDisplayNumber, guessText, data.correct, false);

            // Check if round is over using explicit round_over flag or revealed_track
            const isRoundOver = data.round_over || Boolean(data.revealed_track) || data.correct;
            const isGameOver = data.game_over || state.roundNumber >= state.totalRounds;
            
            // Increment correct/wrong counters
            if (data.correct) {
                state.correctCount++;
            } else if (isRoundOver) {
                state.wrongCount++;
            }
            
            // Update score display
            updateScoreDisplay();

            if (isRoundOver) {
                state.roundNumber++;
                showRoundResult(data, trackName);
            } else {
                setTimeout(async () => {
                    setGameControlsEnabled(true);
                    els.guessInput.value = '';
                    els.guessInput.focus();
                    updateClipInfo(state.attempt + 1, data.next_clip_duration_ms);
                    els.timeTotal.textContent = formatTime(data.next_clip_duration_ms);
                    els.timeCurrent.textContent = formatTime(0);
                    await playClip(state.currentTrack.preview_url, state.startOffset, data.next_clip_duration_ms);
                }, 1500);
            }

        } catch (err) {
            console.error('Guess error:', err);
            setGameControlsEnabled(true);
        }
    };

    const handleSkip = async () => {
        if (!state.currentTrack) return;
        setGameControlsEnabled(false);
        stopAudio();

        try {
            const data = await api.skip();
            state.attempt = data.attempt;
            markAttempt(state.attempt - 1, false);

            // Use revealed track name if available, otherwise "Pulou"
            const trackName = data.revealed_track?.name || 'Pulou';
            
            // Adicionar ao log de palpites ANTES de mostrar resultado
            const attemptDisplayNumber = state.attempt;
            addGuessToLog(attemptDisplayNumber, '', false, true);

            // Check if round is over using explicit round_over flag or revealed_track
            const isRoundOver = data.round_over || Boolean(data.revealed_track);
            const isGameOver = data.game_over || state.roundNumber >= state.totalRounds;
            
            // Increment wrong counter if round is over
            if (isRoundOver) {
                state.wrongCount++;
            }
            
            // Update score display
            updateScoreDisplay();

            if (isRoundOver) {
                state.roundNumber++;
                showRoundResult(data, trackName);
            } else {
                setTimeout(async () => {
                    setGameControlsEnabled(true);
                    els.guessInput.value = '';
                    els.guessInput.focus();
                    updateClipInfo(state.attempt + 1, data.next_clip_duration_ms);
                    els.timeTotal.textContent = formatTime(data.next_clip_duration_ms);
                    els.timeCurrent.textContent = formatTime(0);
                    await playClip(state.currentTrack.preview_url, state.startOffset, data.next_clip_duration_ms);
                }, 1000);
            }

        } catch (err) {
            console.error('Skip error:', err);
            setGameControlsEnabled(true);
        }
    };

    const finishGame = async () => {
        try {
            const summary = await api.summary();
            renderSummary(summary);
            showView('summary');
        } catch (err) {
            console.error('Summary error:', err);
            renderSummary({
                acertos: state.correctCount,
                erros: state.wrongCount,
                rounds: state.roundHistory,
            });
            showView('summary');
        }
    };

    // ---------- Auth / Playlist Selection ----------
    const handleLoginSpotify = () => {
        window.location.href = '/login';
    };

    const loadUserPlaylists = async () => {
        els.playlistsLoading.hidden = false;
        els.playlistsError.hidden = true;
        els.playlistsList.hidden = true;
        // Hide config section when reloading playlists
        if (els.selectPlaylistConfig) {
            els.selectPlaylistConfig.hidden = true;
        }
        // Reset selection
        state.selectedPlaylistId = null;
        if (els.btnStartPlaylistGame) {
            els.btnStartPlaylistGame.disabled = true;
        }
        // Carregar dados de perfil do usuário
        try {
            const profile = await api.getUserProfile();
            if (profile) {
                els.userProfile.hidden = false;
                els.userName.textContent = profile.display_name;
                if (profile.avatar_url) {
                    els.userAvatar.src = profile.avatar_url;
                    els.userAvatar.style.display = 'block';
                } else {
                    // Fallback para ícone genérico se o usuário não tiver foto
                    els.userAvatar.src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23b3b3b3'%3E%3Cpath d='M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z'/%3E%3C/svg%3E";
                }
            }
        } catch (err) {
            console.warn('Erro ao carregar perfil do usuário:', err);
        }
        // Carregar lista de playlists
        try {
            const playlists = await api.getUserPlaylists();
            renderPlaylists(playlists);
        } catch (err) {
            console.error('Load playlists error:', err);
            const msg = err.message || 'Erro desconhecido';
            if (err.status === 401 || msg.includes('Não autenticado') || msg.includes('Sessão expirada')) {
                showError(els.playlistsError, 'Sessão expirada. Faça login novamente.');
            } else {
                showError(els.playlistsError, 'Erro ao carregar playlists. Tente fazer login novamente.');
            }
        } finally {
            els.playlistsLoading.hidden = true;
            els.playlistsList.hidden = false;
        }
    };

    const handleLogout = async () => {
        try {
            await api.logout();
        } catch {}
        // Clear local state
        state.pool = [];
        state.currentTrack = null;
        state.roundHistory = [];
        state.selectedPlaylistId = null;
        els.setupForm.hidden = false;
        els.playlistInput.value = '';
        els.roundsInput.value = '';
        els.btnStart.disabled = true;
        showView('setup');
        els.playlistInput.focus();
    };

    // ---------- Event Listeners ----------
    const initEventListeners = () => {
        // Setup form (public)
        els.setupForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const playlist = els.playlistInput.value.trim();
            const rounds = els.roundsInput.value ? parseInt(els.roundsInput.value, 10) : null;
            if (playlist) startNewGame(playlist, rounds);
        });

        els.playlistInput.addEventListener('input', () => {
            els.btnStart.disabled = !els.playlistInput.value.trim();
            hideError(els.setupError);
        });

        // Login button
        els.btnLoginSpotify?.addEventListener('click', handleLoginSpotify);

        // Logout
        els.btnLogout?.addEventListener('click', handleLogout);

        // Select playlist form
        if (els.roundsInputSelect) {
            els.roundsInputSelect.addEventListener('input', () => {
                // validation if needed
            });
        }

        // URL form (para usuários logados jogarem com link direto)
        els.selectUrlForm?.addEventListener('submit', (e) => {
            e.preventDefault();
            const playlist = els.selectPlaylistInput.value.trim();
            if (playlist) startNewGame(playlist, null);
        });

        els.selectPlaylistInput?.addEventListener('input', () => {
            els.btnStartSelectUrl.disabled = !els.selectPlaylistInput.value.trim();
        });

        // Manual start button for selected playlist
        els.btnStartPlaylistGame?.addEventListener('click', () => {
            const playlistId = state.selectedPlaylistId;
            const rounds = els.selectRoundsInput?.value ? parseInt(els.selectRoundsInput.value, 10) : null;
            if (playlistId) {
                startGameFromPlaylist(playlistId, rounds);
            }
        });

        // Game controls
        els.btnPlayPause.addEventListener('click', togglePlayPause);
        els.btnGuess.addEventListener('click', (e) => {
            e.preventDefault();
            handleGuess(els.guessInput.value);
        });
        els.guessForm.addEventListener('submit', (e) => {
            e.preventDefault();
            handleGuess(els.guessInput.value);
        });
        els.btnSkip.addEventListener('click', handleSkip);
        els.btnNextRound?.addEventListener('click', () => {
            stopAudio();
            hideRoundResult();
            if (state.roundNumber > state.totalRounds) {
                finishGame();
            } else {
                startNextRound();
            }
        });

        // Progress bar click to seek
        els.progressBarPlayer?.addEventListener('click', (e) => {
            if (!state.isPlaying || !state.audioBuffer) return;
            const rect = els.progressBarPlayer.getBoundingClientRect();
            const percent = (e.clientX - rect.left) / rect.width;
        });

        // New game button
        els.btnNewGame.addEventListener('click', () => {
            state.pool = [];
            state.currentTrack = null;
            state.roundHistory = [];
            state.selectedPlaylistId = null;
            els.setupForm.hidden = false;
            els.playlistInput.value = '';
            els.roundsInput.value = '';
            els.btnStart.disabled = true;
            hideError(els.setupError);
            showView('setup');
            els.playlistInput.focus();
        });

        // Back Home Modal
        els.btnBackHome?.addEventListener('click', showConfirmBackModal);
        els.modalBtnCancel?.addEventListener('click', hideConfirmBackModal);
        els.modalBtnConfirm?.addEventListener('click', confirmBackHome);
        // Fechar modal com tecla Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && els.modalConfirmBack && !els.modalConfirmBack.hidden) {
                hideConfirmBackModal();
            }
        });
        // Fechar clicando no fundo escuro (fora do card)
        els.modalConfirmBack?.addEventListener('click', (e) => {
            if (e.target === els.modalConfirmBack) {
                hideConfirmBackModal();
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (state.view !== 'game') return;
            if (e.target.tagName === 'INPUT') return;
            
            if (e.key === ' ' || e.key === 'Space') {
                e.preventDefault();
                togglePlayPause();
            } else if (e.key === 'Enter' && !els.guessInput.disabled) {
                handleGuess(els.guessInput.value);
            } else if (e.key === 's' || e.key === 'S') {
                handleSkip();
            }
        });

        // Visibility change - pause audio when tab hidden
        document.addEventListener('visibilitychange', () => {
            if (document.hidden && state.isPlaying) {
                stopAudio();
            }
        });
    };

    // ---------- Init ----------
    const init = () => {
        initEventListeners();
        createAttemptBoxes();

        // Check current URL to determine initial view
        const path = window.location.pathname;
        if (path === '/select-playlist') {
            loadUserPlaylists();
            showView('selectPlaylist');
        } else {
            showView('setup');
            els.playlistInput.focus();
        }
    };

    // Start when DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();