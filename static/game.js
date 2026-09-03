// ============================================
// Guess The Song - Frontend Game Logic
// Web Audio API + Autocomplete + State Machine + Spotify Auth
// ============================================

(() => {
    'use strict';

    // ---------- Constants ----------
    const CLIP_DURATIONS = [100, 200, 400, 800, 1600, 2000, 2500];
    const MAX_ATTEMPTS = 7;
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

        // Summary
        finalCorrect: document.getElementById('final-correct'),
        finalWrong: document.getElementById('final-wrong'),
        roundsDetail: document.getElementById('rounds-detail'),
        btnNewGame: document.getElementById('btn-new-game'),
    };

    // ---------- Utility Functions ----------
    const $ = (sel, ctx = document) => ctx.querySelector(sel);
    const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

    const formatTime = (ms) => {
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
                replayClip();
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
            throw new Error(data.detail || `HTTP ${res.status}`);
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

    const populateDatalist = (tracks) => {
        els.tracksDatalist.innerHTML = '';
        tracks.forEach(t => {
            const option = document.createElement('option');
            option.value = t.name;
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
        els.btnPlayPause.disabled = !enabled;
    };

    const showRoundResult = (data, trackName) => {
        const isCorrect = data.correct;
        const isRoundOver = data.round_over || data.game_over || Boolean(data.revealed_track);
        
        let displayTrackName = '';
        let displayArtist = '';
        
        if (isRoundOver && data.revealed_track) {
            // Round is over - show the actual track name and artist
            displayTrackName = data.revealed_track.name;
            displayArtist = data.revealed_track.artist;
        } else if (data.correct) {
            // Correct guess - use the guessed track name
            displayTrackName = trackName;
            displayArtist = state.currentTrack?.artist || '';
        } else {
            // Wrong guess or skip - show what was guessed or "Pulou"
            displayTrackName = trackName || 'Pulou';
            displayArtist = '';
        }
        
        els.roundResult.hidden = false;
        els.roundResult.className = 'round-result';
        els.roundResult.innerHTML = `
            <div class="result-content ${isCorrect ? 'correct' : 'wrong'}">
                <div class="result-header">
                    <div class="result-icon">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                            ${isCorrect 
                                ? '<polyline points="20 6 9 17 4 12"></polyline>' 
                                : '<line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>'}
                        </svg>
                    </div>
                    <span class="result-title">${isCorrect ? 'Acertou!' : 'Errou!'}</span>
                </div>
                <div class="result-track">
                    <span class="result-track-name">${displayTrackName}</span>
                    <span class="result-track-artist">${displayArtist}</span>
                </div>
            </div>
        `;
    };

    const hideRoundResult = () => {
        els.roundResult.hidden = true;
    };

    const renderSummary = (summary) => {
        els.finalCorrect.textContent = summary.acertos;
        els.finalWrong.textContent = summary.erros;

        els.roundsDetail.innerHTML = '';
        summary.rounds.forEach((round, idx) => {
            const card = document.createElement('div');
            card.className = `round-card ${round.correct ? 'correct' : 'wrong'}`;
            card.innerHTML = `
                <div class="round-header">
                    <span class="round-number">Rodada ${idx + 1}</span>
                    <span class="round-outcome">${round.correct ? 'Acertou' : 'Errou'}</span>
                </div>
                <div class="round-track">
                    <span class="round-track-name">${round.track.name}</span>
                    <span class="round-track-artist">${round.track.artist}</span>
                </div>
                <div class="round-guesses">
                    ${round.guesses.map(g => `
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
            els.playlistsList.innerHTML = '<li class="playlists-empty">Nenhuma playlist com faixas encontrada</li>';
            return;
        }
        playlists.forEach(pl => {
            const li = document.createElement('li');
            li.className = 'playlist-item';
            li.tabIndex = 0;
            li.dataset.playlistId = pl.id;
            const imgUrl = pl.images?.[0]?.url || '';
            li.innerHTML = `
                ${imgUrl ? `<img src="${imgUrl}" alt="" loading="lazy">` : '<div class="playlist-placeholder" style="width:56px;height:56px;border-radius:8px;background:var(--bg-tertiary);display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:20px;">🎵</div>'}
                <div class="playlist-info">
                    <span class="playlist-name">${pl.name}</span>
                    <span class="playlist-meta">${pl.tracks_total} faixas ${pl.public ? '• Pública' : '• Privada'}</span>
                </div>
                <svg class="playlist-arrow" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>
            `;
            const selectPlaylist = () => startGameFromPlaylist(pl.id);
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
            showError(els.setupError, err.message || 'Erro ao iniciar jogo. Verifique a playlist e tente novamente.');
            els.setupForm.hidden = false;
        } finally {
            els.setupProgress.hidden = true;
            setLoading(els.btnStart, false);
        }
    };

    const startGameFromPlaylist = async (playlistId) => {
        const rounds = els.roundsInputSelect?.value ? parseInt(els.roundsInputSelect.value, 10) : null;
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
            showError(els.playlistsError, err.message || 'Erro ao iniciar jogo');
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
        resetAttemptBoxes();
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

            els.timeTotal.textContent = formatTime(state.currentTrack.duration_ms || 30000);
            setGameControlsEnabled(true);
            els.guessInput.focus();

            await playClip(data.preview_url, data.start_time_ms, data.clip_duration_ms);

        } catch (err) {
            console.error('Start round error:', err);
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
            showRoundResult(data, trackName);

            if (data.correct) {
                state.correctCount++;
                state.roundHistory.push({ ...data, track: state.currentTrack, correct: true });
            } else if (data.attempt >= MAX_ATTEMPTS || data.game_over) {
                state.wrongCount++;
                state.roundHistory.push({ ...data, track: state.currentTrack, correct: false });
            }

            updateScoreDisplay();

            // Check if round is over using explicit round_over flag or revealed_track
            const isRoundOver = data.round_over || Boolean(data.revealed_track);
            if (data.correct || isRoundOver) {
                state.roundNumber++;
                if (data.game_over || state.roundNumber > state.totalRounds) {
                    setTimeout(() => finishGame(), 2000);
                } else {
                    setTimeout(() => startNextRound(), 2000);
                }
            } else {
                setTimeout(async () => {
                    setGameControlsEnabled(true);
                    els.guessInput.value = '';
                    els.guessInput.focus();
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
            showRoundResult(data, trackName);
            state.wrongCount++;
            state.roundHistory.push({ ...data, track: state.currentTrack, correct: false });
            updateScoreDisplay();

            // Check if round is over using explicit round_over flag or revealed_track
            const isRoundOver = data.round_over || Boolean(data.revealed_track);
            if (isRoundOver) {
                state.roundNumber++;
                if (data.game_over || state.roundNumber > state.totalRounds) {
                    setTimeout(() => finishGame(), 1500);
                } else {
                    setTimeout(() => startNextRound(), 1500);
                }
            } else {
                setTimeout(async () => {
                    setGameControlsEnabled(true);
                    els.guessInput.value = '';
                    els.guessInput.focus();
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
        try {
            const playlists = await api.getUserPlaylists();
            renderPlaylists(playlists);
        } catch (err) {
            console.error('Load playlists error:', err);
            showError(els.playlistsError, 'Erro ao carregar playlists. Tente fazer login novamente.');
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