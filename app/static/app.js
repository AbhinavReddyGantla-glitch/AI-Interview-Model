/** AI Interview Evaluation Platform - Client Application with Lip-Sync Emoji Avatar & Proctoring */
function initInterviewApp() {
    function $(id) { return document.getElementById(id); }
    // ══════════════════════════════════════════════════════════════
    // Developer Flag Check: VITE_DEBUG_MIC=true or ?debug=1 or ?debug=true
    // NOTE: The browser's native microphone permission prompt and tab recording
    // indicator cannot be programmatically hidden — they are OS and browser-level security controls.
    // ══════════════════════════════════════════════════════════════
    const urlParams = new URLSearchParams(window.location.search);
    const isDebugMic = urlParams.get('debug') === '1' ||
                       urlParams.get('debug') === 'true' ||
                       urlParams.has('debug_mic') ||
                       (typeof window !== 'undefined' && (window.VITE_DEBUG_MIC === true || window.VITE_DEBUG_MIC === 'true'));

    if (isDebugMic) {
        document.body.classList.add('debug-mic-mode');
        console.log('[DEBUG_MIC] Developer microphone debug mode enabled (?debug=1 or VITE_DEBUG_MIC=true).');
    } else {
        document.body.classList.remove('debug-mic-mode');
    }

    let candidate = null;
    let sessionId = null;
    let currentQuestion = null;
    let totalQuestions = 10;
    let minDurationSec = 300;
    let maxDurationSec = 600;
    let interviewStartTime = null;
    let interviewClockInterval = null;
    let persistentAudioStream = null;
    let audioStream = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let recordedAudio = null;
    let liveTranscribeSocket = null;
    let recognition = null;
    let isRecording = false;
    let autoSubmitTimer = null;
    let hasSubmittedCurrentQuestion = false;
    let ariaPlaybackActive = false;
    let timerInterval = null;
    let timerSeconds = 0;
    let finalTranscript = '';
    let resolveRecorderStop = null;
    let cameraStream = null;
    let videoRecorder = null;
    let videoChunks = [];
    let recordedVideo = null;
    let resolveVideoStop = null;
    let silenceTimer = null;
    let lipSyncInterval = null;
    let isSpeakingTTS = false;
    let selectedAudioDeviceId = '';
    let micTestStream = null;
    let micTestAudioCtx = null;
    let micTestAnalyser = null;
    let micTestInterval = null;
    let isMicTesting = false;
    let recognitionSlots = [];

    const submitErrorBanner = $('submit-error-banner');
    const submitErrorMessage = $('submit-error-message');
    const retrySubmitBtn = $('retry-submit-btn');

    function showSubmitError(msg) {
        if (submitErrorMessage) submitErrorMessage.textContent = msg || 'Could not submit your answer, please try again.';
        if (submitErrorBanner) {
            submitErrorBanner.classList.remove('hidden');
            submitErrorBanner.style.display = 'flex';
        }
    }

    function hideSubmitError() {
        if (submitErrorBanner) {
            submitErrorBanner.classList.add('hidden');
            submitErrorBanner.style.display = 'none';
        }
    }

    if (retrySubmitBtn) {
        retrySubmitBtn.addEventListener('click', () => {
            hideSubmitError();
            submitAnswer();
        });
    }

    /* ── Shared API Fetch Helper ─────────────────────────────────── */
    /**
     * Shared API Fetch helper:
     * 1. Reads response.text() first.
     * 2. Parses JSON safely (never throws unhandled "Unexpected token 'I'...").
     * 3. Checks response.ok.
     * 4. Logs raw status and body on error.
     * 5. Throws a readable Error with status and detail.
     */
    async function apiFetch(url, options = {}) {
        let response;
        let rawText = '';
        try {
            response = await fetch(url, options);
            rawText = await response.text();
        } catch (netErr) {
            console.error(`[apiFetch] Network failure calling ${url}:`, netErr);
            const err = new Error('Network error. Please check your internet connection and try again.');
            err.status = 0;
            throw err;
        }

        let parsedData = null;
        try {
            parsedData = rawText ? JSON.parse(rawText) : {};
        } catch (jsonErr) {
            console.warn(`[apiFetch] Non-JSON response (HTTP ${response.status}) from ${url}:`, rawText);
        }

        if (!response.ok) {
            const detailMsg = (parsedData && (parsedData.detail || parsedData.message))
                ? (typeof parsedData.detail === 'string' ? parsedData.detail : JSON.stringify(parsedData.detail))
                : (response.status >= 500
                    ? 'Internal server error. Please try again.'
                    : `Request failed with status ${response.status}.`);

            console.error(`[apiFetch] HTTP ${response.status} Error on ${url}:`, {
                status: response.status,
                rawBody: rawText,
                parsed: parsedData,
            });

            const err = new Error(detailMsg);
            err.status = response.status;
            err.data = parsedData;
            err.rawBody = rawText;
            throw err;
        }

        return parsedData !== null ? parsedData : rawText;
    }

    /* ── Transcript helpers ───────────────────────────────────────── */
    /**
     * Collapse consecutive repeated words/phrases in a string.
     * E.g. "my name is Sam my name is" → "my name is Sam"
     */
    /** Helper to strip punctuation and normalize a single word */
    function cleanWord(w) {
        return (w || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    }

    /** Normalize a phrase into an array of cleaned lowercase alphanumeric tokens */
    function normalizeTokens(text) {
        if (!text) return [];
        return text
            .trim()
            .split(/\s+/)
            .map(cleanWord)
            .filter(w => w.length > 0);
    }

    /**
     * Collapse consecutive repeated words/phrases in a string.
     * E.g. "my name is Sam my name is" → "my name is Sam"
     * Handles punctuation differences ("Sam," vs "Sam.")
     */
    function collapseRepeatedPhrases(text) {
        if (!text) return '';
        let result = text.trim();

        // 1. Remove duplicate consecutive phrases (window size from 8 down to 1)
        for (let windowSize = 8; windowSize >= 1; windowSize--) {
            const words = result.split(/\s+/);
            const out = [];
            let i = 0;
            while (i < words.length) {
                const segWords = words.slice(i, i + windowSize);
                if (segWords.length === windowSize) {
                    const segClean = segWords.map(cleanWord).join(' ');
                    let j = i + windowSize;
                    let matched = false;
                    while (j + windowSize <= words.length) {
                        const nextSegClean = words.slice(j, j + windowSize).map(cleanWord).join(' ');
                        if (segClean && segClean === nextSegClean) {
                            matched = true;
                            j += windowSize;
                        } else {
                            break;
                        }
                    }
                    if (matched) {
                        out.push(...segWords);
                        i = j;
                        continue;
                    }
                }
                out.push(words[i]);
                i++;
            }
            result = out.join(' ');
        }

        // 2. Check if trailing words repeat a prefix of the sentence (e.g. "my name is Sam my name is")
        const words = result.split(/\s+/);
        for (let k = Math.floor(words.length / 2); k >= 1; k--) {
            const tailClean = words.slice(-k).map(cleanWord).join(' ');
            const headClean = words.slice(0, k).map(cleanWord).join(' ');
            if (tailClean && tailClean === headClean) {
                result = words.slice(0, -k).join(' ');
                break;
            }
        }

        return result;
    }

    /**
     * Fix transcript: trim, collapse duplicates, fix capitalization, apply name dict.
     * @param {string} text - raw transcript chunk
     * @param {string[]} nameDict - candidate name tokens to preserve capitalization
     */
    function fixTranscriptChunk(text, nameDict = []) {
        if (!text) return '';
        let t = text.trim();

        // 1. Phonetic & Domain corrections for observed misheard terms
        const phoneticFixes = [
            [/\b(Avino|Abino|Avinav)\b/gi, (candidate && candidate.name) ? candidate.name.split(/\s+/)[0] : 'Abhinav'],
            [/\bscreen\s+(university|institute|college)\b/gi, 'Sreenidhi $1'],
            [/\bfrom\s+screen\b/gi, 'from Sreenidhi'],
            [/\bposting\s+with\s+degrees?\b/gi, 'pursuing my degree'],
            [/\bposting\s+(my|a|with)\s+degree\b/gi, 'pursuing $1 degree'],
            [/\bposting\b(?=\s+(my|a|degree|phd|btech|mtech))/gi, 'pursuing'],
            [/\bI'm\s+University\b/gi, 'from University'],
        ];
        for (const [pattern, rep] of phoneticFixes) {
            t = t.replace(pattern, rep);
        }

        // 2. Capitalize first letter
        t = t.charAt(0).toUpperCase() + t.slice(1);

        // 3. Apply name dictionary corrections (case-insensitive replace)
        for (const name of nameDict) {
            const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            t = t.replace(new RegExp(`\\b${escaped}\\b`, 'gi'), name);
        }
        return t;
    }

    /** Build name correction dictionary from candidate profile */
    function buildNameDict() {
        if (!candidate || !candidate.name) return [];
        // Split full name into tokens (first name, last name, etc.)
        return candidate.name.split(/\s+/).filter(n => n.length > 1);
    }

    /**
     * Append a final transcript chunk, de-duplicating overlap with existing finalTranscript.
     * Prevents duplicate sentences, partial echoes, and overlapping speech events.
     */
    function appendFinalChunk(chunk) {
        const trimmed = (chunk || '').trim();
        if (!trimmed) return false;

        const fixed = fixTranscriptChunk(trimmed, buildNameDict());
        if (!finalTranscript) {
            finalTranscript = fixed;
            return true;
        }

        const ftTokens = normalizeTokens(finalTranscript);
        const chunkTokens = normalizeTokens(fixed);
        if (chunkTokens.length === 0) return false;

        // 1. Exact match or finalTranscript already ends with this entire chunk
        if (chunkTokens.length <= ftTokens.length) {
            let fullMatch = true;
            for (let i = 0; i < chunkTokens.length; i++) {
                if (ftTokens[ftTokens.length - chunkTokens.length + i] !== chunkTokens[i]) {
                    fullMatch = false;
                    break;
                }
            }
            if (fullMatch) {
                // Entire chunk is already at the end of finalTranscript! Discard duplicate.
                return false;
            }
        }

        // 2. 3-Word Tail Replacement Rule:
        // If a new chunk starts with the same first 3 words as an earlier sentence/tail in finalTranscript,
        // replace that tail instead of appending! (e.g. refined recognition replacing earlier fragment)
        if (chunkTokens.length >= 3 && ftTokens.length >= 3) {
            const first3Chunk = chunkTokens.slice(0, 3).join(' ');
            const ftWords = finalTranscript.split(/\s+/);
            let replaceIdx = -1;
            for (let idx = ftWords.length - 3; idx >= 0; idx--) {
                const check3 = ftWords.slice(idx, idx + 3).map(cleanWord).join(' ');
                if (check3 === first3Chunk) {
                    replaceIdx = idx;
                    break;
                }
            }
            if (replaceIdx !== -1) {
                const preservedHead = ftWords.slice(0, replaceIdx).join(' ');
                finalTranscript = preservedHead ? `${preservedHead} ${fixed}` : fixed;
                finalTranscript = collapseRepeatedPhrases(finalTranscript);
                return true;
            }
        }

        // 3. Check if chunk is already fully contained in the recent tail of finalTranscript
        const recentWindow = ftTokens.slice(-Math.max(chunkTokens.length + 6, 12)).join(' ');
        const chunkStr = chunkTokens.join(' ');
        if (recentWindow.includes(chunkStr)) {
            return false;
        }

        // 4. Check for partial overlap: end of finalTranscript matches beginning of chunk
        // e.g. finalTranscript: "My name is", chunk: "My name is Sam" -> append only "Sam"
        const maxOverlap = Math.min(ftTokens.length, chunkTokens.length);
        let overlapCount = 0;
        for (let k = maxOverlap; k >= 1; k--) {
            const ftTail = ftTokens.slice(-k).join(' ');
            const chunkHead = chunkTokens.slice(0, k).join(' ');
            if (ftTail === chunkHead) {
                overlapCount = k;
                break;
            }
        }

        if (overlapCount > 0) {
            if (overlapCount === chunkTokens.length) {
                // Chunk has no new words
                return false;
            }
            // Only append the non-overlapping words from the chunk
            const chunkWords = fixed.split(/\s+/);
            const newWords = chunkWords.slice(overlapCount).join(' ');
            if (newWords) {
                finalTranscript = `${finalTranscript} ${newWords}`;
            }
        } else {
            // No overlap, append chunk with space
            finalTranscript = `${finalTranscript} ${fixed}`;
        }

        finalTranscript = collapseRepeatedPhrases(finalTranscript);
        return true;
    }

    // Proctoring Variables
    let tabSwitchCount = 0;
    let proctoringIntegrityScore = 100;
    let proctorWarningTimeout = null;
    let proctoringEvents = [];
    let blurStartTime = null;
    let isWindowUnfocused = false;

    const welcomeScreen = $('welcome-screen');
    const interviewScreen = $('interview-screen');
    const reportScreen = $('report-screen');
    const loadingOverlay = $('loading-overlay');
    const loadingText = $('loading-text');
    const uploadZone = $('upload-zone');
    const resumeFileInput = $('resume-file-input');
    const uploadBrowseLink = $('upload-browse-link');
    const uploadProgressRow = $('upload-progress-row');
    const uploadProgressFill = $('upload-progress-fill');
    const uploadProgressText = $('upload-progress-text');
    const uploadErrorBanner = $('upload-error-banner');
    const uploadErrorText = $('upload-error-text');
    const resumePreview = $('resume-preview');
    const startInterviewBtn = $('start-interview-btn');
    const startHint = $('start-hint');
    const jobRoleSelect = $('job-role-select');
    const micBtn = $('mic-btn');
    const micIcon = $('mic-icon');
    const micInstruction = $('mic-instruction');
    const micPulseRing = $('mic-pulse-ring');
    const timer = $('recording-timer');
    const timerText = $('timer-text');
    const transcriptText = $('transcript-text');
    const transcriptPlaceholder = $('transcript-placeholder');
    const sttWarning = $('stt-warning');
    const submitAnswerBtn = $('submit-answer-btn');
    const questionText = $('question-text');
    const questionCategory = $('question-category');
    const questionDifficulty = $('question-difficulty');
    const questionOrder = $('question-order');
    const progressFill = $('progress-fill');
    const avatarStateLabel = $('avatar-state-label');
    const speechBubble = $('speech-bubble');
    const speechBubbleText = $('speech-bubble-text');
    const avatarCard = $('avatar-card');
    const speechLanguage = $('speech-language');
    const candidateVideoPreview = $('candidate-video-preview');
    const candidateVideoStatus = $('candidate-video-status');
    const cameraRecordingBadge = $('camera-recording-badge');
    const interviewClock = $('interview-clock');
    const avatarMouth = $('avatar-mouth');

    // Proctoring Elements
    const headerProctorStatus = $('header-proctor-status');
    const headerIntegrityScore = $('header-integrity-score');
    const liveIntegrityPct = $('live-integrity-pct');
    const hudTabStatus = $('hud-tab-status');
    const proctorWarningBanner = $('proctor-warning-banner');
    const proctorWarningText = $('proctor-warning-text');

    // End Interview Elements
    const endInterviewBtn = $('end-interview-btn');
    const endInterviewModal = $('end-interview-modal');
    const closeEndModalBtn = $('close-end-modal-btn');
    const cancelEndModalBtn = $('cancel-end-modal-btn');
    const confirmEndModalBtn = $('confirm-end-modal-btn');
    let answeredQuestionsCount = 0;

    // Mic Device & Setup Elements
    const micDeviceSelect = $('mic-device-select');
    const testMicBtn = $('test-mic-btn');
    const testMicLabel = $('test-mic-label');
    const micMeterBar = $('mic-meter-bar');
    const micVolumeNum = $('mic-volume-num');
    const micTestFeedback = $('mic-test-feedback');
    const unsupportedBrowserBanner = $('unsupported-browser-banner');
    const browserSupportBadge = $('browser-support-badge');

    function formatMicErrorMessage(err) {
        const errorStr = (typeof err === 'string' ? err : (err && (err.name || err.message)) || '').toLowerCase();
        if (errorStr.includes('notallowed') || errorStr.includes('permission') || errorStr.includes('not-allowed')) {
            return 'Microphone permission was denied. Please allow microphone access in your browser settings (click the lock/tune icon near your address bar).';
        }
        if (errorStr.includes('notfound') || errorStr.includes('devicesnotfound') || errorStr.includes('no-mic') || errorStr.includes('audio-capture')) {
            return 'No microphone was found on your system. Please connect a microphone or headset.';
        }
        if (errorStr.includes('notreadable') || errorStr.includes('trackstart') || errorStr.includes('in use')) {
            return 'Microphone is currently in use by another application or OS service. Please close other apps using the mic.';
        }
        if (errorStr.includes('no-speech')) {
            return 'No speech was detected. Please speak closer to your microphone or check input volume.';
        }
        if (errorStr.includes('network')) {
            return 'Network connection issue during speech recognition. Please check your internet connection.';
        }
        return 'Microphone notice: ' + ((err && err.message) || errorStr || 'unable to access audio input');
    }

    async function populateAudioInputDevices() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const audioInputs = devices.filter(d => d.kind === 'audioinput');
            if (micDeviceSelect) {
                const currentVal = micDeviceSelect.value;
                micDeviceSelect.innerHTML = '<option value="">Default Microphone</option>';
                audioInputs.forEach((device, idx) => {
                    const opt = document.createElement('option');
                    opt.value = device.deviceId;
                    opt.textContent = device.label || `Microphone ${idx + 1}`;
                    micDeviceSelect.appendChild(opt);
                });
                if (currentVal && audioInputs.some(d => d.deviceId === currentVal)) {
                    micDeviceSelect.value = currentVal;
                }
            }
        } catch (err) {
            console.warn('Could not enumerate audio devices:', err);
        }
    }

    function checkBrowserSpeechSupport() {
        const isChrome = /Chrome/.test(navigator.userAgent) && /Google Inc/.test(navigator.vendor);
        const isEdge = /Edg/.test(navigator.userAgent);
        const hasSpeech = !!(window.SpeechRecognition || window.webkitSpeechRecognition);

        if (!hasSpeech || (!isChrome && !isEdge)) {
            if (unsupportedBrowserBanner) unsupportedBrowserBanner.classList.remove('hidden');
            if (browserSupportBadge) {
                browserSupportBadge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Chrome/Edge Recommended';
                browserSupportBadge.style.color = '#eab308';
                browserSupportBadge.style.borderColor = '#eab30844';
                browserSupportBadge.style.background = '#eab30822';
            }
        } else {
            if (unsupportedBrowserBanner) unsupportedBrowserBanner.classList.add('hidden');
            if (browserSupportBadge) {
                browserSupportBadge.innerHTML = '<i class="fa-solid fa-circle-check"></i> Speech API Ready';
            }
        }
    }

    async function startMicTest() {
        try {
            const audioConstraints = {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                channelCount: 1,
                sampleRate: 16000,
                ...(selectedAudioDeviceId ? { deviceId: { exact: selectedAudioDeviceId } } : {})
            };
            micTestStream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
            await populateAudioInputDevices();
            if (selectedAudioDeviceId && micDeviceSelect) micDeviceSelect.value = selectedAudioDeviceId;

            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) {
                if (micTestFeedback) {
                    micTestFeedback.innerHTML = '<i class="fa-solid fa-circle-check" style="color:#10b981;"></i> Microphone access granted (Web Audio API not supported).';
                }
                return;
            }

            micTestAudioCtx = new AudioContext();
            micTestAnalyser = micTestAudioCtx.createAnalyser();
            micTestAnalyser.fftSize = 256;
            const source = micTestAudioCtx.createMediaStreamSource(micTestStream);
            source.connect(micTestAnalyser);

            const dataArray = new Uint8Array(micTestAnalyser.frequencyBinCount);
            isMicTesting = true;
            if (testMicLabel) testMicLabel.textContent = 'Stop Test';
            if (testMicBtn) testMicBtn.classList.add('recording');

            let micFloor = 100;
            let micPeak = 0;
            let tickCount = 0;

            micTestInterval = setInterval(() => {
                if (!micTestAnalyser) return;
                micTestAnalyser.getByteFrequencyData(dataArray);
                let sum = 0;
                for (let i = 0; i < dataArray.length; i++) {
                    sum += dataArray[i];
                }
                const avg = sum / dataArray.length;
                const pct = Math.min(100, Math.round((avg / 128) * 100));
                if (micMeterBar) micMeterBar.style.width = `${pct}%`;
                if (micVolumeNum) micVolumeNum.textContent = `${pct}%`;

                tickCount++;
                if (tickCount > 10) {
                    micFloor = Math.min(micFloor, pct);
                    micPeak = Math.max(micPeak, pct);
                }

                if (micTestFeedback) {
                    if (micFloor > 18 && (micPeak - micFloor) < 15 && tickCount > 25) {
                        micTestFeedback.innerHTML = '<i class="fa-solid fa-triangle-exclamation" style="color:#f59e0b;"></i> <span class="snr-warning-pill">Poor SNR</span> High ambient noise detected. Consider moving to a quieter space or bringing mic closer.';
                    } else if (pct < 5) {
                        micTestFeedback.innerHTML = '<i class="fa-solid fa-circle-exclamation" style="color:#94a3b8;"></i> Too quiet — speak into your microphone.';
                    } else if (pct > 80) {
                        micTestFeedback.innerHTML = '<i class="fa-solid fa-triangle-exclamation" style="color:#ef4444;"></i> Too noisy / clipping — move slightly back from mic.';
                    } else {
                        micTestFeedback.innerHTML = '<i class="fa-solid fa-circle-check" style="color:#10b981;"></i> Sounds good! Microphone level is clear and optimal.';
                    }
                }
            }, 60);
        } catch (err) {
            console.error('Error starting mic test:', err);
            const errMsg = formatMicErrorMessage(err);
            if (micTestFeedback) {
                micTestFeedback.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color:#ef4444;"></i> ${errMsg}`;
            }
            stopMicTest();
        }
    }

    function stopMicTest() {
        isMicTesting = false;
        if (micTestInterval) {
            clearInterval(micTestInterval);
            micTestInterval = null;
        }
        if (micTestStream) {
            micTestStream.getTracks().forEach(t => t.stop());
            micTestStream = null;
        }
        if (micTestAudioCtx) {
            try { micTestAudioCtx.close(); } catch (e) {}
            micTestAudioCtx = null;
        }
        micTestAnalyser = null;
        if (micMeterBar) micMeterBar.style.width = '0%';
        if (micVolumeNum) micVolumeNum.textContent = '0%';
        if (testMicLabel) testMicLabel.textContent = 'Test Microphone';
        if (testMicBtn) testMicBtn.classList.remove('recording');
    }

    if (testMicBtn) {
        testMicBtn.addEventListener('click', () => {
            if (isMicTesting) {
                stopMicTest();
            } else {
                startMicTest();
            }
        });
    }

    if (micDeviceSelect) {
        micDeviceSelect.addEventListener('change', (e) => {
            selectedAudioDeviceId = e.target.value;
            if (isMicTesting) {
                stopMicTest();
                startMicTest();
            }
        });
    }

    if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
        navigator.mediaDevices.addEventListener('devicechange', populateAudioInputDevices);
    }

    // Initialize mic devices and browser support check
    populateAudioInputDevices();
    checkBrowserSpeechSupport();

    function formatClock(seconds) {
        const m = String(Math.floor(seconds / 60)).padStart(2, '0');
        const s = String(Math.floor(seconds % 60)).padStart(2, '0');
        return `${m}:${s}`;
    }

    function updateTimingMetadata(data) {
        if (data.max_duration_seconds) maxDurationSec = data.max_duration_seconds;
        if (data.min_duration_seconds) minDurationSec = data.min_duration_seconds;
        const dynamicBadge = $('dynamic-time-badge');
        if (dynamicBadge) {
            if (data.bonus_seconds_added && data.bonus_seconds_added > 0) {
                const bonusM = Math.round(data.bonus_seconds_added / 60);
                dynamicBadge.innerHTML = `<i class="fa-solid fa-bolt"></i> Dynamic Time +${bonusM}m`;
                dynamicBadge.classList.remove('hidden');
            } else if (!data.is_extended) {
                dynamicBadge.classList.add('hidden');
            }
        }
    }

    function updateInterviewClock(elapsedSec) {
        interviewClock.textContent = `${formatClock(elapsedSec)} / ${formatClock(maxDurationSec)}`;
        const pct = Math.min(100, (elapsedSec / maxDurationSec) * 100);
        progressFill.style.width = `${pct}%`;
    }

    function startInterviewClock() {
        interviewStartTime = Date.now();
        if (interviewClockInterval) clearInterval(interviewClockInterval);
        interviewClockInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - interviewStartTime) / 1000);
            updateInterviewClock(elapsed);
        }, 1000);
    }

    function stopInterviewClock() {
        if (interviewClockInterval) {
            clearInterval(interviewClockInterval);
            interviewClockInterval = null;
        }
    }

    /* ══════════════════════════════════════════ */
    /*  CAMERA & PROCTORING INITIALIZATION       */
    /* ══════════════════════════════════════════ */
    async function startInterviewCamera() {
        try {
            cameraStream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
                audio: false,
            });
            candidateVideoPreview.srcObject = cameraStream;
            candidateVideoStatus.classList.add('hidden');
            cameraRecordingBadge.classList.remove('hidden');
            headerProctorStatus.classList.remove('hidden');
        } catch {
            candidateVideoStatus.innerHTML = '<i class="fa-solid fa-video-slash"></i><span>Camera unavailable — continuing in audio-only mode.</span>';
            candidateVideoStatus.classList.remove('hidden');
            cameraRecordingBadge.classList.add('hidden');
        }

        // Initialize microphone ONCE at the start of the interview for all questions
        if (!persistentAudioStream || persistentAudioStream.getAudioTracks().every(t => t.readyState === 'ended')) {
            try {
                const audioConstraints = {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    channelCount: 1,
                    sampleRate: 16000,
                    ...(selectedAudioDeviceId ? { deviceId: { exact: selectedAudioDeviceId } } : {})
                };
                persistentAudioStream = await navigator.mediaDevices.getUserMedia({
                    audio: audioConstraints,
                });
                audioStream = persistentAudioStream;
                sttWarning.classList.add('hidden');
                console.log("Microphone initialized successfully for the entire interview.");
            } catch (micErr) {
                console.error("Microphone access error at interview initialization:", micErr);
                sttWarning.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ${formatMicErrorMessage(micErr)}`;
                sttWarning.classList.remove('hidden');
            }
        }
    }

    /* ══════════════════════════════════════════ */
    /*  REAL-TIME PROCTORING & FOCUS MONITORING  */
    /* ══════════════════════════════════════════ */
    function saveProctoringState() {
        if (!sessionId) return;
        try {
            localStorage.setItem('ai_interview_tab_switches', String(tabSwitchCount));
            localStorage.setItem('ai_interview_integrity_score', String(proctoringIntegrityScore));
            localStorage.setItem('ai_interview_proctoring_events', JSON.stringify(proctoringEvents));
        } catch (e) {}
    }

    function updateIntegrityDisplay() {
        const rounded = Math.round(proctoringIntegrityScore);
        if (liveIntegrityPct) liveIntegrityPct.textContent = `${rounded}%`;
        if (headerIntegrityScore) headerIntegrityScore.textContent = `${rounded}%`;
    }

    function logProctoringDebugEvent(ev) {
        proctoringEvents.unshift(ev);
        if (proctoringEvents.length > 30) proctoringEvents.pop();
        saveProctoringState();
        renderProctorDebugEvents();
    }

    function renderProctorDebugEvents() {
        const tbody = $('proctor-debug-tbody');
        const countBadge = $('proctor-debug-count');
        if (!tbody) return;

        if (countBadge) {
            countBadge.textContent = `${proctoringEvents.length} event${proctoringEvents.length === 1 ? '' : 's'}`;
        }

        if (proctoringEvents.length === 0) {
            tbody.innerHTML = `
                <tr class="empty-row" id="proctor-debug-empty-row">
                    <td colspan="7" style="text-align:center; color:#64748b; padding:0.8rem;">
                        No infractions detected. Natural movements (blinking, minor gaze shifts, natural head movement) tolerated without penalty.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.replaceChildren();
        proctoringEvents.forEach((ev) => {
            const tr = document.createElement('tr');
            const sevClass = (ev.severity || '').toLowerCase();
            const penaltyClass = (ev.penaltyValue && ev.penaltyValue > 0) ? 'penalty-deduct' : 'penalty-zero';
            tr.innerHTML = `
                <td>${ev.time || '—'}</td>
                <td><strong>${ev.event}</strong></td>
                <td>${ev.confidence || '95%'}</td>
                <td>${ev.duration || '—'}</td>
                <td><span class="sev-tag sev-${sevClass}">${ev.severity || 'Normal'}</span></td>
                <td><span class="penalty-tag ${penaltyClass}">${ev.penalty || '0%'}</span></td>
                <td><small>${ev.reason || '—'}</small></td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Toggle Proctor Debug Log Accordion
    const proctorDebugHeader = $('proctor-debug-header');
    const proctorDebugContent = $('proctor-debug-content');
    const proctorDebugChevron = $('proctor-debug-chevron');
    if (proctorDebugHeader && proctorDebugContent) {
        proctorDebugHeader.addEventListener('click', () => {
            const isHidden = proctorDebugContent.classList.toggle('hidden');
            if (proctorDebugChevron) {
                proctorDebugChevron.className = isHidden ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-up';
            }
        });
    }

    function showWarningBanner(msg) {
        if (proctorWarningText && proctorWarningBanner) {
            proctorWarningText.textContent = `Notice: ${msg}`;
            proctorWarningBanner.classList.remove('hidden');
            if (proctorWarningTimeout) clearTimeout(proctorWarningTimeout);
            proctorWarningTimeout = setTimeout(() => {
                proctorWarningBanner.classList.add('hidden');
            }, 4000);
        }
    }

    function handleFocusLoss(reason) {
        if (!interviewScreen.classList.contains('active')) return;
        if (isWindowUnfocused) return; // Prevent duplicate triggers between blur and visibilitychange
        isWindowUnfocused = true;
        blurStartTime = Date.now();

        if (hudTabStatus) {
            hudTabStatus.querySelector('.hud-dot').className = 'hud-dot red';
            hudTabStatus.querySelector('.hud-label').textContent = 'Tab Unfocused';
        }
    }

    function handleFocusRegain() {
        if (!interviewScreen.classList.contains('active')) return;
        if (!isWindowUnfocused) return;
        isWindowUnfocused = false;

        const durationSec = blurStartTime ? Math.max(0.1, (Date.now() - blurStartTime) / 1000) : 0;
        blurStartTime = null;

        if (hudTabStatus) {
            hudTabStatus.querySelector('.hud-dot').className = 'hud-dot green';
            hudTabStatus.querySelector('.hud-label').textContent = 'Tab Focused';
        }

        evaluateProctoringFocusEvent(durationSec);
    }

    function evaluateProctoringFocusEvent(durationSec) {
        let severity = "Normal";
        let penalty = 0;
        let reason = "";
        const conf = "95%";

        // PIPELINE: Detection -> confidence -> duration -> frequency/repetition -> severity -> score impact
        if (durationSec < 1.2) {
            // Accidental/momentary loss (e.g. system notification click, menu dropdown)
            severity = "Normal";
            penalty = 0;
            reason = `Brief focus loss (${durationSec.toFixed(1)}s) - classified as momentary/accidental. Tolerated with 0% penalty.`;
        } else if (durationSec < 4.0) {
            tabSwitchCount += 1;
            severity = "Low";
            // First short tab switch gets 1% penalty, subsequent get 2%
            penalty = tabSwitchCount === 1 ? 1.0 : 2.0;
            reason = `Short tab switch (${durationSec.toFixed(1)}s, alert #${tabSwitchCount}) - minor deduction applied.`;
            showWarningBanner(`Short tab switch detected (${durationSec.toFixed(1)}s). Alert #${tabSwitchCount}`);
        } else {
            tabSwitchCount += 1;
            severity = durationSec < 8.0 ? "Medium" : "High";
            penalty = Math.min(10.0, Math.round(2.0 + (durationSec * 0.7) + (tabSwitchCount * 1.2)));
            reason = `Prolonged tab unfocus (${durationSec.toFixed(1)}s, alert #${tabSwitchCount}) outside active window.`;
            showWarningBanner(`Extended tab unfocus (${durationSec.toFixed(1)}s) logged!`);
        }

        proctoringIntegrityScore = Math.max(35, Math.round((proctoringIntegrityScore - penalty) * 10) / 10);
        saveProctoringState();
        updateIntegrityDisplay();

        logProctoringDebugEvent({
            time: new Date().toLocaleTimeString(),
            event: durationSec < 1.2 ? "Momentary focus shift" : "Tab / Window switch",
            confidence: conf,
            duration: `${durationSec.toFixed(1)}s`,
            severity: severity,
            penalty: penalty > 0 ? `-${penalty}%` : "0%",
            penaltyValue: penalty,
            reason: reason
        });
    }

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            handleFocusLoss('Document hidden / minimized');
        } else {
            handleFocusRegain();
        }
    });

    window.addEventListener('blur', () => {
        handleFocusLoss('Window blur');
    });

    window.addEventListener('focus', () => {
        handleFocusRegain();
    });

    /* ══════════════════════════════════════════ */
    /*  SMILING EMOJI AVATAR & LIP-SYNC ENGINE   */
    /* ══════════════════════════════════════════ */
    function startLipSyncAnimation() {
        if (lipSyncInterval) clearInterval(lipSyncInterval);
        const visemeShapes = [
            { h: '14px', w: '36px', r: '6px 6px 36px 36px' },
            { h: '24px', w: '42px', r: '8px 8px 42px 42px' },
            { h: '30px', w: '44px', r: '4px 4px 44px 44px' },
            { h: '18px', w: '40px', r: '10px 10px 30px 30px' },
            { h: '26px', w: '38px', r: '6px 6px 38px 38px' },
            { h: '12px', w: '34px', r: '4px 4px 34px 34px' },
        ];

        let index = 0;
        lipSyncInterval = setInterval(() => {
            if (!isSpeakingTTS || !avatarMouth) {
                stopLipSyncAnimation();
                return;
            }
            const shape = visemeShapes[index % visemeShapes.length];
            avatarMouth.style.height = shape.h;
            avatarMouth.style.width = shape.w;
            avatarMouth.style.borderRadius = shape.r;
            index += 1;
        }, 140);
    }

    function stopLipSyncAnimation() {
        if (lipSyncInterval) {
            clearInterval(lipSyncInterval);
            lipSyncInterval = null;
        }
        if (avatarMouth) {
            avatarMouth.style.height = '20px';
            avatarMouth.style.width = '42px';
            avatarMouth.style.borderRadius = '0 0 42px 42px';
        }
    }

    function setAvatarState(state, label) {
        avatarCard.classList.remove('is-speaking', 'is-listening');
        if (state) avatarCard.classList.add(`is-${state}`);
        avatarStateLabel.textContent = label;
        if (state === 'speaking') {
            isSpeakingTTS = true;
            startLipSyncAnimation();
        } else {
            isSpeakingTTS = false;
            stopLipSyncAnimation();
        }
    }

    function speakAsAria(text) {
        if (!text) return;
        speechBubbleText.textContent = text;
        speechBubble.classList.remove('hidden');

        ariaPlaybackActive = true;
        let autoStartTriggered = false;
        let ariaSafetyTimer = null;

        const triggerRecordingOnce = () => {
            if (!autoStartTriggered) {
                autoStartTriggered = true;
                if (ariaSafetyTimer) {
                    clearTimeout(ariaSafetyTimer);
                    ariaSafetyTimer = null;
                }
                ariaPlaybackActive = false;
                setAvatarState('', 'Your turn');
                // Automatically begin answer recording
                setTimeout(() => {
                    if (!isRecording && currentQuestion && !hasSubmittedCurrentQuestion) {
                        console.log('[STT] Auto-starting answer recording for question...');
                        startRecording();
                    }
                }, 350);
            }
        };

        // Safety fallback: if SpeechSynthesis gets paused, stalled, or never fires onend (common in Chromium)
        const wordCount = (text.split(/\s+/).filter(Boolean)).length;
        const fallbackMs = Math.min(Math.max(wordCount * 350, 2500), 7500);
        ariaSafetyTimer = setTimeout(() => {
            console.log(`[STT] SpeechSynthesis fallback timer (${fallbackMs}ms) fired. Triggering recording.`);
            triggerRecordingOnce();
        }, fallbackMs);

        if (!('speechSynthesis' in window)) {
            triggerRecordingOnce();
            return;
        }

        try {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            const voices = window.speechSynthesis.getVoices();
            utterance.voice = voices.find((voice) => /en-IN|en-GB|en-US/i.test(voice.lang) && /female|zira|aria|samantha|google/i.test(voice.name)) || voices.find((voice) => /en/i.test(voice.lang)) || null;
            utterance.rate = 0.95;
            utterance.pitch = 1.05;

            utterance.onstart = () => setAvatarState('speaking', 'Asking question');
            utterance.onend = () => {
                triggerRecordingOnce();
            };
            utterance.onerror = (err) => {
                console.warn('[STT] SpeechSynthesis error:', err);
                triggerRecordingOnce();
            };

            window.speechSynthesis.speak(utterance);
        } catch (err) {
            console.warn('[STT] Could not invoke SpeechSynthesis:', err);
            triggerRecordingOnce();
        }
    }

    function updateTranscript(interimText = '') {
        const combined = `${finalTranscript}${interimText ? `${finalTranscript ? ' ' : ''}${interimText}` : ''}`.trim();
        transcriptText.textContent = combined;
        if (combined) transcriptPlaceholder.classList.add('hidden');
        enableSubmission();
        if (sessionId && combined) {
            try {
                localStorage.setItem('ai_interview_draft_transcript_' + sessionId, combined);
            } catch (e) {}
        }
    }

    /** Highlight low-confidence words in amber in the editable transcript container */
    function renderConfidenceTranscript(text, wordConfidences = []) {
        if (!text) {
            transcriptText.textContent = '';
            return;
        }
        if (!wordConfidences || wordConfidences.length === 0) {
            transcriptText.textContent = text;
            return;
        }

        const lowConfWords = new Set();
        wordConfidences.forEach((wc) => {
            if (wc.low_confidence || (wc.probability && wc.probability < 0.70)) {
                lowConfWords.add(cleanWord(wc.word));
            }
        });

        if (lowConfWords.size === 0) {
            transcriptText.textContent = text;
            return;
        }

        const tokens = text.split(/\s+/);
        transcriptText.replaceChildren();
        tokens.forEach((token, idx) => {
            const cleaned = cleanWord(token);
            if (lowConfWords.has(cleaned)) {
                const span = document.createElement('span');
                span.className = 'low-confidence-word';
                span.textContent = token;
                span.title = 'Review pronunciation or spelling';
                transcriptText.appendChild(span);
            } else {
                transcriptText.appendChild(document.createTextNode(token));
            }
            if (idx < tokens.length - 1) {
                transcriptText.appendChild(document.createTextNode(' '));
            }
        });
    }

    /** Visual mic on/off indicator */
    function updateMicIndicator(isActive) {
        if (!micBtn) return;
        const micDot = $('mic-status-dot');
        const micLabel = $('mic-status-label');
        const stopBtn = $('stop-btn');
        if (isActive) {
            micBtn.setAttribute('aria-label', 'Microphone active — click to stop');
            micBtn.title = 'Microphone ON — click to stop';
            if (micDot) micDot.style.background = '#22c55e';
            if (micLabel) {
                micLabel.textContent = 'Mic: ON (Listening)';
                micLabel.style.color = '#15803d';
            }
            if (stopBtn) stopBtn.classList.remove('hidden');
        } else {
            micBtn.setAttribute('aria-label', 'Microphone off — click to start');
            micBtn.title = 'Microphone OFF — click to record';
            if (micDot) micDot.style.background = '#94a3b8';
            if (micLabel) {
                micLabel.textContent = 'Mic: OFF';
                micLabel.style.color = '#64748b';
            }
            if (stopBtn) stopBtn.classList.add('hidden');
        }
    }

    function showLoading(message) {
        loadingText.textContent = message || 'Processing...';
        loadingOverlay.classList.remove('hidden');
    }

    function hideLoading() {
        loadingOverlay.classList.add('hidden');
    }

    function showUploadError(message) {
        console.error('[Resume Upload Error]:', message);
        if (uploadErrorText) uploadErrorText.textContent = message;
        if (uploadErrorBanner) {
            uploadErrorBanner.classList.remove('hidden');
            uploadErrorBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        if (typeof showToast === 'function') {
            showToast(message, 'warning');
        }
    }

    function clearUploadError() {
        uploadErrorBanner.classList.add('hidden');
    }

    function setUploadProgress(percent, message) {
        uploadProgressRow.classList.remove('hidden');
        uploadProgressFill.style.width = `${percent}%`;
        uploadProgressText.textContent = message;
    }

    function resetUpload() {
        candidate = null;
        if (resumeFileInput) resumeFileInput.value = '';
        const resumeDirectInput = $('resume-direct-input');
        if (resumeDirectInput) resumeDirectInput.value = '';
        resumePreview.classList.add('hidden');
        uploadZone.classList.remove('hidden');
        const manualWrap = $('manual-toggle-wrap');
        if (manualWrap) manualWrap.classList.remove('hidden');
        const directWrap = $('direct-file-wrap');
        if (directWrap) directWrap.classList.remove('hidden');
        uploadProgressRow.classList.add('hidden');
        clearUploadError();
        startInterviewBtn.disabled = true;
        startHint.textContent = 'Upload your resume to unlock the interview';
    }

    async function uploadResume(file) {
        if (!file) return;
        clearUploadError();
        console.log('[Resume Upload] Starting upload for file:', file.name, 'size:', file.size, 'type:', file.type);

        // 1. Client-side empty and size validation
        if (file.size === 0) {
            showUploadError('The selected file is empty (0 bytes). Please choose a valid resume.');
            return;
        }
        const MAX_SIZE_MB = 5;
        if (file.size > MAX_SIZE_MB * 1024 * 1024) {
            showUploadError(`File size exceeds ${MAX_SIZE_MB} MB. Please upload a smaller resume.`);
            return;
        }

        // 2. Reject obvious non-document executable extensions
        const blockedExtensions = /\.(exe|dll|bat|cmd|sh|bin|msi|apk|zip|rar|7z|tar|gz)$/i;
        if (blockedExtensions.test(file.name)) {
            showUploadError('Unsupported file type. Please upload a PDF, DOCX, or TXT resume.');
            return;
        }

        setUploadProgress(25, `Reading "${file.name}" (${Math.round(file.size / 1024)} KB)...`);
        const formData = new FormData();
        formData.append('resume_file', file);
        if (jobRoleSelect && jobRoleSelect.value) formData.append('job_role', jobRoleSelect.value);

        try {
            setUploadProgress(55, 'Extracting text and analyzing candidate profile with AI...');
            const data = await apiFetch('/api/v1/candidates/resume/upload-public', {
                method: 'POST',
                body: formData,
            });
            console.log('[Resume Upload] Successfully processed candidate:', data);
            candidate = data;
            const candidateName = data.name || (data.parsed_fields && data.parsed_fields.name) || 'Candidate';
            if ($('header-user-name')) $('header-user-name').textContent = candidateName.toUpperCase();
            if ($('preview-name')) $('preview-name').textContent = candidateName;
            if ($('preview-role')) $('preview-role').textContent = data.job_role || (data.parsed_fields && data.parsed_fields.job_role) || 'Software Engineer';
            if ($('preview-exp')) $('preview-exp').textContent = `${data.experience_years || 0} years`;
            
            if ($('preview-filename')) {
                $('preview-filename').textContent = file.name || data.filename || 'resume';
            }

            if ($('preview-education')) {
                const edu = (data.parsed_fields && data.parsed_fields.education) || [];
                $('preview-education').textContent = edu.length ? edu.join(', ') : 'Technical Degree';
            }

            if ($('preview-snippet-text')) {
                const summary = (data.parsed_fields && data.parsed_fields.resume_summary) || data.resume_summary || '';
                $('preview-snippet-text').textContent = summary || 'Resume parsed successfully. Core skills and background extracted.';
            }

            const skillsContainer = $('preview-skills');
            if (skillsContainer) {
                while (skillsContainer.firstChild) {
                    skillsContainer.removeChild(skillsContainer.firstChild);
                }
                const skillList = data.skills || (data.parsed_fields && data.parsed_fields.skills) || [];
                skillList.forEach((skill) => {
                    const chip = document.createElement('span');
                    chip.className = 'skill-chip';
                    chip.textContent = skill;
                    skillsContainer.appendChild(chip);
                });
                if (!skillList.length) skillsContainer.textContent = 'Core Fundamentals (DSA, OOP, Problem Solving)';
            }

            setUploadProgress(100, 'Resume parsed successfully!');
            if (uploadZone) uploadZone.classList.add('hidden');
            const directWrap = $('direct-file-wrap');
            if (directWrap) directWrap.classList.add('hidden');
            const manualWrap = $('manual-toggle-wrap');
            if (manualWrap) manualWrap.classList.add('hidden');
            if (resumePreview) resumePreview.classList.remove('hidden');
            if (startInterviewBtn) startInterviewBtn.disabled = false;
            if (startHint) startHint.textContent = 'Your personalized technical interview is ready. Click Start Interview!';
            if (typeof showToast === 'function') {
                showToast(`Resume uploaded! Welcome, ${candidateName}.`, 'success');
            }
        } catch (error) {
            console.error('[Resume Upload] Failed:', error);
            if (uploadProgressRow) uploadProgressRow.classList.add('hidden');
            showUploadError(error.message || 'Failed to process resume file. Please verify the file and try again.');
        }
    }

    // Native file input change listeners
    if (resumeFileInput) {
        resumeFileInput.addEventListener('click', (e) => {
            e.target.value = '';
        });
        resumeFileInput.addEventListener('change', (event) => {
            const file = event.target.files && event.target.files[0];
            if (file) {
                console.log('[Resume Upload] File selected via main dropzone:', file.name, file.size, file.type);
                uploadResume(file);
            }
        });
    }

    if (uploadZone) {
        uploadZone.addEventListener('click', (e) => {
            if (e.target !== resumeFileInput && resumeFileInput) {
                resumeFileInput.click();
            }
        });
    }

    const resumeDirectInput = $('resume-direct-input');
    if (resumeDirectInput) {
        resumeDirectInput.addEventListener('click', (e) => {
            e.target.value = '';
        });
        resumeDirectInput.addEventListener('change', (event) => {
            const file = event.target.files && event.target.files[0];
            if (file) {
                console.log('[Resume Upload] File selected via direct file picker:', file.name, file.size, file.type);
                uploadResume(file);
            }
        });
    }

    const reUploadBtn = $('re-upload-btn');
    if (reUploadBtn) reUploadBtn.addEventListener('click', resetUpload);

    // Manual details entry toggle and handlers
    const toggleManualBtn = $('toggle-manual-entry-btn');
    const manualCard = $('manual-entry-card');
    const cancelManualBtn = $('cancel-manual-btn');
    const saveManualBtn = $('save-manual-btn');
    const manualToggleWrap = $('manual-toggle-wrap');

    if (toggleManualBtn && manualCard) {
        toggleManualBtn.addEventListener('click', () => {
            manualCard.classList.toggle('hidden');
        });
    }
    if (cancelManualBtn && manualCard) {
        cancelManualBtn.addEventListener('click', () => {
            manualCard.classList.add('hidden');
        });
    }
    if (saveManualBtn) {
        saveManualBtn.addEventListener('click', () => {
            const name = ($('manual-name-input')?.value || '').trim();
            const email = ($('manual-email-input')?.value || '').trim();
            const skillsStr = ($('manual-skills-input')?.value || '').trim();
            if (!name) {
                alert('Please enter your full name.');
                return;
            }
            if (!email || !email.includes('@')) {
                alert('Please enter a valid email address.');
                return;
            }
            const skills = skillsStr ? skillsStr.split(',').map(s => s.trim()).filter(Boolean) : ['Python', 'Problem Solving'];
            const role = jobRoleSelect.value || 'Software Engineer';

            candidate = {
                name: name,
                email: email,
                job_role: role,
                skills: skills,
                experience_years: 0,
                resume_summary: `${name} (${email}) - ${role}. Skills: ${skills.join(', ')}`,
            };

            if ($('header-user-name')) $('header-user-name').textContent = name.toUpperCase();
            $('preview-name').textContent = name;
            $('preview-role').textContent = role;
            $('preview-exp').textContent = '0 years (Fresher)';
            if ($('preview-filename')) $('preview-filename').textContent = 'Manual Entry';
            if ($('preview-education')) $('preview-education').textContent = 'Direct Candidate Profile';
            if ($('preview-snippet-text')) $('preview-snippet-text').textContent = candidate.resume_summary;

            const skillsContainer = $('preview-skills');
            skillsContainer.replaceChildren();
            skills.forEach((skill) => {
                const chip = document.createElement('span');
                chip.className = 'skill-chip';
                chip.textContent = skill;
                skillsContainer.appendChild(chip);
            });

            uploadZone.classList.add('hidden');
            const directWrap = $('direct-file-wrap');
            if (directWrap) directWrap.classList.add('hidden');
            if (manualToggleWrap) manualToggleWrap.classList.add('hidden');
            if (manualCard) manualCard.classList.add('hidden');
            resumePreview.classList.remove('hidden');
            startInterviewBtn.disabled = false;
            startHint.textContent = 'Your personalized fresher interview is ready.';
        });
    }

    // Prevent default drag/drop behavior on window so browser does not open dropped file
    window.addEventListener('dragover', (e) => e.preventDefault(), false);
    window.addEventListener('drop', (e) => e.preventDefault(), false);

    ['dragenter', 'dragover'].forEach((eventName) => uploadZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        uploadZone.classList.add('drag-over');
    }));
    uploadZone.addEventListener('dragleave', (event) => {
        event.preventDefault();
        if (!uploadZone.contains(event.relatedTarget)) {
            uploadZone.classList.remove('drag-over');
        }
    });
    uploadZone.addEventListener('drop', (event) => {
        event.preventDefault();
        uploadZone.classList.remove('drag-over');
        const files = event.dataTransfer?.files;
        if (files && files[0]) {
            console.log('[Resume Upload] File dropped:', files[0].name, files[0].size, files[0].type);
            uploadResume(files[0]);
        }
    });

    startInterviewBtn.addEventListener('click', async () => {
        if (!candidate) return;
        stopMicTest();
        showLoading('Generating fresh personalized questions with Gemini...');
        try {
            tabSwitchCount = 0;
            proctoringIntegrityScore = 100;
            proctoringEvents = [];
            const data = await apiFetch('/api/v1/interview/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ candidate_id: candidate.candidate_id }),
            });
            sessionId = data.session_id;
            localStorage.setItem('ai_interview_active_session_id', sessionId);
            saveProctoringState();
            renderProctorDebugEvents();
            updateIntegrityDisplay();
            totalQuestions = data.total_questions || 10;
            minDurationSec = data.min_duration_seconds || 300;
            maxDurationSec = data.max_duration_seconds || 600;
            answeredQuestionsCount = 0;
            welcomeScreen.classList.remove('active');
            interviewScreen.classList.add('active');
            if (endInterviewBtn) endInterviewBtn.classList.remove('hidden');
            await startInterviewCamera();
            startInterviewClock();
            await fetchNextQuestion();
        } catch (error) {
            showUploadError(error.message);
        } finally {
            hideLoading();
        }
    });

    async function fetchNextQuestion() {
        showLoading('Loading next question...');
        try {
            const data = await apiFetch(`/api/v1/interview/${sessionId}/next-question`);
            currentQuestion = data;
            totalQuestions = data.total_questions || totalQuestions;
            updateTimingMetadata(data);
            if (data.elapsed_seconds) updateInterviewClock(data.elapsed_seconds);
            questionCategory.innerHTML = '<i class="fa-solid fa-folder-open"></i> ';
            questionCategory.append(document.createTextNode(data.category));
            questionDifficulty.textContent = data.difficulty.charAt(0).toUpperCase() + data.difficulty.slice(1);
            questionOrder.textContent = `Question ${data.order} · ${formatClock(minDurationSec)}–${formatClock(maxDurationSec)} interview`;
            questionText.textContent = data.question_text;
            resetAnswer();
            speakAsAria(data.question_text);
        } catch (error) {
            questionText.textContent = error.message;
        } finally {
            hideLoading();
        }
    }

    function updateTimer() {
        timerSeconds += 1;
        timerText.textContent = `${String(Math.floor(timerSeconds / 60)).padStart(2, '0')}:${String(timerSeconds % 60).padStart(2, '0')}`;
    }

    async function startRecording() {
        if (ariaPlaybackActive) {
            if (window.speechSynthesis) window.speechSynthesis.cancel();
            ariaPlaybackActive = false;
        }
        if (isRecording) return;
        hasSubmittedCurrentQuestion = false;
        if (autoSubmitTimer) {
            clearTimeout(autoSubmitTimer);
            autoSubmitTimer = null;
        }

        audioChunks = [];
        recordedAudio = null;
        recordedVideo = null;
        videoChunks = [];
        finalTranscript = '';
        transcriptText.textContent = '';
        transcriptPlaceholder.classList.add('hidden');
        submitAnswerBtn.disabled = false;

        console.log('[STT Step 1/6] startRecording invoked. Initializing audio stream & speech recognition...');

        // Check secure context (Microphone API requires HTTPS or localhost)
        const isSecureContext = window.isSecureContext || ['localhost', '127.0.0.1'].includes(location.hostname);
        if (!isSecureContext && location.protocol !== 'https:') {
            console.warn('[STT] WARNING: Page is not served over HTTPS or localhost. Microphone access may be blocked by browser policy.');
            sttWarning.classList.remove('hidden');
            sttWarning.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Microphone access requires a secure connection (<strong>HTTPS</strong> or <strong>localhost</strong>).';
        }

        // 1. Ensure persistent microphone stream is active
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            console.error('[STT] navigator.mediaDevices.getUserMedia is not supported or blocked in this browser.');
            sttWarning.classList.remove('hidden');
            sttWarning.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Microphone access is not supported or blocked in this browser. Please use Chrome or Edge.';
            return;
        }

        if (!persistentAudioStream || persistentAudioStream.getAudioTracks().every(t => t.readyState === 'ended')) {
            try {
                const audioConstraints = {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    channelCount: 1,
                    sampleRate: 16000,
                    ...(selectedAudioDeviceId ? { deviceId: { exact: selectedAudioDeviceId } } : {})
                };
                persistentAudioStream = await navigator.mediaDevices.getUserMedia({
                    audio: audioConstraints,
                });
                audioStream = persistentAudioStream;
                sttWarning.classList.add('hidden');
                console.log('[STT Step 1/6] Microphone stream active. Audio tracks:', audioStream.getAudioTracks().map(t => t.label).join(', '));
            } catch (error) {
                console.error('[STT] getUserMedia error:', error);
                sttWarning.classList.remove('hidden');
                sttWarning.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ${formatMicErrorMessage(error)}`;
                return;
            }
        } else {
            audioStream = persistentAudioStream;
            console.log('[STT Step 1/6] Reusing existing persistent microphone stream.');
        }

        // Track whether client browser SpeechRecognition is active so we never duplicate with server STT
        let browserSpeechActive = !!(window.SpeechRecognition || window.webkitSpeechRecognition);

        // 2. Connect to Deepgram live streaming STT via WebSocket (fallback server streaming)
        const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProto}//${location.host}/api/v1/interview/ws/transcribe`;
        try {
            if (liveTranscribeSocket) {
                try { liveTranscribeSocket.close(); } catch (e) {}
            }
            liveTranscribeSocket = new WebSocket(wsUrl);
            liveTranscribeSocket.binaryType = 'arraybuffer';
            liveTranscribeSocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'transcript' && data.transcript) {
                        // CRITICAL: Only write to transcript if browser Web Speech is NOT actively transcribing!
                        if (!browserSpeechActive) {
                            if (data.is_final) {
                                appendFinalChunk(data.transcript);
                                updateTranscript('');
                            } else {
                                updateTranscript(data.transcript.trim());
                            }
                            resetSilenceTimer();
                        }
                    } else if (data.type === 'info' || data.type === 'warning') {
                        console.log('Server STT status:', data.message);
                    }
                } catch (err) {
                    console.error('Error parsing live transcript:', err);
                }
            };
            liveTranscribeSocket.onerror = (err) => {
                console.debug('Deepgram WebSocket notice (client Web Speech active):', err);
            };
        } catch (wsErr) {
            console.debug('Deepgram WebSocket not available (client Web Speech active):', wsErr);
        }

        // 3. Start MediaRecorder with 250ms streaming timeslice
        if (window.MediaRecorder && audioStream) {
            const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus'
                : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '');
            mediaRecorder = mimeType ? new MediaRecorder(audioStream, { mimeType }) : new MediaRecorder(audioStream);
            mediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    audioChunks.push(event.data);
                    if (liveTranscribeSocket && liveTranscribeSocket.readyState === WebSocket.OPEN) {
                        liveTranscribeSocket.send(event.data);
                    }
                }
            };
            mediaRecorder.onstop = () => {
                if (audioChunks.length) {
                    recordedAudio = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
                }
                enableSubmission();
                if (resolveRecorderStop) {
                    resolveRecorderStop();
                    resolveRecorderStop = null;
                }
            };
            mediaRecorder.start(250);
        }

        // 4. Video Recording (if camera active)
        if (cameraStream && window.MediaRecorder && audioStream) {
            const interviewStream = new MediaStream([
                ...audioStream.getAudioTracks(),
                ...cameraStream.getVideoTracks(),
            ]);
            videoRecorder = new MediaRecorder(interviewStream);
            videoRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) videoChunks.push(event.data);
            };
            videoRecorder.onstop = () => {
                if (videoChunks.length) recordedVideo = new Blob(videoChunks, { type: videoRecorder.mimeType || 'video/webm' });
                if (resolveVideoStop) {
                    resolveVideoStop = resolve;
                    resolveVideoStop = null;
                }
            };
            videoRecorder.start(500);
        }

        // 5. Browser Web Speech Recognition Engine
        // Guard flag: prevents duplicate handler registrations
        let _recognizerActive = false;

        const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (Recognition) {
            const _startRecognizer = () => {
                // Safety: only one recognizer instance at a time
                if (_recognizerActive) return;
                if (recognition) {
                    try { recognition.abort(); } catch (e) {}
                    recognition = null;
                }
                recognition = new Recognition();
                recognition.continuous = true;
                recognition.interimResults = true;
                recognition.maxAlternatives = 3;
                recognition.lang = speechLanguage ? (speechLanguage.value || 'en-IN') : 'en-IN';
                _recognizerActive = true;

                recognition.onstart = () => {
                    browserSpeechActive = true;
                    recognitionSlots = [];
                    console.log(`[STT Step 2/6] Browser SpeechRecognition active in language: ${recognition.lang}`);
                    sttWarning.classList.add('hidden');
                    updateMicIndicator(true);
                };

                recognition.onresult = (event) => {
                    // Overwrite the slot on every onresult (loop from event.resultIndex, never from 0)
                    for (let i = event.resultIndex; i < event.results.length; i += 1) {
                        const result = event.results[i];
                        let bestText = result[0].transcript;
                        let bestConf = result[0].confidence || 0;
                        for (let a = 1; a < result.length; a++) {
                            if ((result[a].confidence || 0) > bestConf) {
                                bestConf = result[a].confidence;
                                bestText = result[a].transcript;
                            }
                        }
                        const trimmed = (bestText || '').trim();
                        if (result.isFinal) {
                            // Immediately commit final result to finalTranscript so text is never lost
                            if (!recognitionSlots[i] || !recognitionSlots[i].committed) {
                                appendFinalChunk(trimmed);
                                recognitionSlots[i] = { text: trimmed, isFinal: true, committed: true };
                                console.log(`[STT Step 3/6] Finalized speech slot [${i}]: "${trimmed}". finalTranscript="${finalTranscript}"`);
                            }
                        } else {
                            recognitionSlots[i] = { text: trimmed, isFinal: false, committed: false };
                        }
                    }

                    // Display active text: finalTranscript + any active uncommitted interim text
                    const activeInterimText = recognitionSlots
                        .filter(slot => slot && !slot.committed && slot.text)
                        .map(slot => slot.text)
                        .join(' ');

                    updateTranscript(activeInterimText);
                    console.log(`[STT Step 4/6] Live answer box updated. Text="${transcriptText.textContent}"`);
                    resetSilenceTimer();
                };

                recognition.onerror = (event) => {
                    _recognizerActive = false;
                    console.warn('[STT] SpeechRecognition error:', event.error);
                    if (event.error === 'not-allowed') {
                        browserSpeechActive = false;
                        sttWarning.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ${formatMicErrorMessage('not-allowed')}`;
                        sttWarning.classList.remove('hidden');
                        updateMicIndicator(false);
                    } else if (event.error === 'no-speech') {
                        // Benign: no speech heard; restart if still recording
                        console.info('[STT] No speech detected in current window; will continue listening.');
                    } else if (event.error === 'network') {
                        browserSpeechActive = false;
                        console.warn('[STT] Speech recognition network notice. Falling back to server STT.');
                    } else if (event.error === 'audio-capture') {
                        sttWarning.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ${formatMicErrorMessage('notfound')}`;
                        sttWarning.classList.remove('hidden');
                    } else if (event.error === 'aborted') {
                        // Intentional abort — do not restart
                    }
                };

                recognition.onend = () => {
                    _recognizerActive = false;
                    updateMicIndicator(false);

                    // Commit any trailing uncommitted speech chunks
                    const trailingText = recognitionSlots
                        .filter(slot => slot && !slot.committed && slot.text)
                        .map(slot => slot.text)
                        .join(' ');

                    if (trailingText) {
                        appendFinalChunk(trailingText);
                    }
                    recognitionSlots = [];
                    updateTranscript('');

                    // Restart ONLY if user still wants to record AND never while already running
                    if (isRecording && !_recognizerActive) {
                        setTimeout(() => {
                            if (isRecording && !_recognizerActive) _startRecognizer();
                        }, 150);
                    }
                };

                try {
                    recognition.start();
                } catch (err) {
                    _recognizerActive = false;
                    browserSpeechActive = false;
                    console.warn('Could not start SpeechRecognition:', err);
                }
            };

            _startRecognizer();
        } else {
            browserSpeechActive = false;
            sttWarning.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Browser speech recognition not supported. Please use <strong>Google Chrome</strong> or <strong>Microsoft Edge</strong>.';
            sttWarning.classList.remove('hidden');
        }

        isRecording = true;
        timerSeconds = 0;
        timerText.textContent = '00:00';
        timer.classList.remove('hidden');
        micBtn.classList.add('recording');
        micPulseRing.classList.add('active');
        micIcon.className = 'fa-solid fa-stop';
        setAvatarState('listening', 'Listening to you');

        // 6. Intelligent recording duration (60s max) & silence auto-submit
        let remainingSeconds = 60;
        micInstruction.textContent = 'Listening... Speak your answer (Click mic or Submit when finished)';

        function resetSilenceTimer() {
            if (silenceTimer) clearTimeout(silenceTimer);
            const currentAnswer = (transcriptText.textContent || finalTranscript || '').trim();
            if (currentAnswer.length > 0) {
                silenceTimer = setTimeout(() => {
                    if (isRecording && !hasSubmittedCurrentQuestion) {
                        const checkAnswer = (transcriptText.textContent || finalTranscript || '').trim();
                        if (checkAnswer.length > 0) {
                            console.log('[STT] Natural pause (8s silence) detected after answer. Auto-submitting...');
                            stopAndAutoSubmitAnswer();
                        }
                    }
                }, 8000);
            }
        }

        clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            remainingSeconds = Math.max(0, remainingSeconds - 1);
            timerSeconds += 1;
            timerText.textContent = formatClock(timerSeconds);

            if (remainingSeconds <= 10) {
                micInstruction.textContent = `Recording... Time remaining: ${remainingSeconds}s`;
            } else {
                micInstruction.textContent = 'Listening... Speak your answer (Click mic or Submit when finished)';
            }

            if (remainingSeconds <= 0) {
                clearInterval(timerInterval);
                if (isRecording && !hasSubmittedCurrentQuestion) {
                    console.log('Answer recording limit reached. Auto-submitting...');
                    stopAndAutoSubmitAnswer();
                }
            }
        }, 1000);
    }

    function enableSubmission() {
        submitAnswerBtn.disabled = false;
    }

    async function stopRecording() {
        if (autoSubmitTimer) {
            clearTimeout(autoSubmitTimer);
            autoSubmitTimer = null;
        }
        if (silenceTimer) {
            clearTimeout(silenceTimer);
            silenceTimer = null;
        }
        if (!isRecording) return Promise.resolve();
        isRecording = false;
        clearInterval(timerInterval);
        timer.classList.add('hidden');

        // Commit any uncommitted slots before stopping
        const uncommitted = recognitionSlots
            .filter(slot => slot && !slot.committed && slot.text)
            .map(slot => slot.text)
            .join(' ');
        if (uncommitted) {
            appendFinalChunk(uncommitted);
        }

        // Single source of truth: sync with any manual candidate edits
        const displayed = transcriptText.textContent.trim();
        if (displayed && !finalTranscript) {
            finalTranscript = displayed;
        }

        if (liveTranscribeSocket) {
            try {
                if (liveTranscribeSocket.readyState === WebSocket.OPEN) {
                    liveTranscribeSocket.send('CLOSE');
                }
                liveTranscribeSocket.close();
            } catch (e) {}
            liveTranscribeSocket = null;
        }

        if (recognition) {
            try { recognition.abort(); } catch (e) {}
            recognition = null;
        }
        recognitionSlots = [];
        updateMicIndicator(false);
        updateTranscript(''); // Refreshes answer box with complete finalTranscript without wiping!

        let stopPromise = Promise.resolve();
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            stopPromise = new Promise((resolve) => { resolveRecorderStop = resolve; });
            try { mediaRecorder.stop(); } catch (e) {}
        } else {
            if (audioChunks.length && !recordedAudio) {
                recordedAudio = new Blob(audioChunks, { type: 'audio/webm' });
            }
            enableSubmission();
        }

        let videoStopPromise = Promise.resolve();
        if (videoRecorder && videoRecorder.state !== 'inactive') {
            videoStopPromise = new Promise((resolve) => { resolveVideoStop = resolve; });
            try { videoRecorder.stop(); } catch (e) {}
        }

        // NOTE: We do NOT stop persistentAudioStream tracks!
        // Microphone remains continuously active for the entire interview.

        cameraRecordingBadge.classList.remove('hidden');
        micBtn.classList.remove('recording');
        micPulseRing.classList.remove('active');
        micIcon.className = 'fa-solid fa-microphone';
        micInstruction.textContent = 'Recording stopped. Review or edit your answer above and click Submit Answer.';
        setAvatarState('', 'Ready to submit');

        return Promise.all([stopPromise, videoStopPromise]);
    }

    async function stopAndAutoSubmitAnswer() {
        if (hasSubmittedCurrentQuestion) return;
        hasSubmittedCurrentQuestion = true;
        if (autoSubmitTimer) {
            clearTimeout(autoSubmitTimer);
            autoSubmitTimer = null;
        }
        if (silenceTimer) {
            clearTimeout(silenceTimer);
            silenceTimer = null;
        }
        await stopRecording();
        setTimeout(() => {
            if (currentQuestion) {
                submitAnswer();
            }
        }, 200);
    }

    function resetAnswer() {
        hasSubmittedCurrentQuestion = false;
        hideSubmitError();
        if (autoSubmitTimer) {
            clearTimeout(autoSubmitTimer);
            autoSubmitTimer = null;
        }
        if (silenceTimer) {
            clearTimeout(silenceTimer);
            silenceTimer = null;
        }
        stopRecording();
        finalTranscript = '';
        transcriptText.textContent = '';
        transcriptPlaceholder.classList.remove('hidden');
        submitAnswerBtn.disabled = true;
        recordedAudio = null;
        recordedVideo = null;
        audioChunks = [];
        videoChunks = [];
        candidateVideoStatus.classList.add('hidden');
        cameraRecordingBadge.classList.remove('hidden');
        sttWarning.classList.add('hidden');
        micInstruction.textContent = 'Aria is asking the question...';
    }

    micBtn.addEventListener('click', () => isRecording ? stopRecording() : startRecording());
    const stopBtn = $('stop-btn');
    if (stopBtn) {
        stopBtn.addEventListener('click', () => {
            if (isRecording) stopRecording();
        });
    }
    transcriptText.addEventListener('input', () => {
        finalTranscript = transcriptText.textContent.trim();
        if (finalTranscript) transcriptPlaceholder.classList.add('hidden');
        enableSubmission();
        hideSubmitError();
        if (sessionId) {
            try {
                localStorage.setItem('ai_interview_draft_transcript_' + sessionId, finalTranscript);
            } catch (e) {}
        }
    });
    $('replay-tts-btn').addEventListener('click', () => {
        if (currentQuestion) speakAsAria(currentQuestion.question_text);
    });

    async function submitAnswer() {
        if (!currentQuestion) return;
        hasSubmittedCurrentQuestion = true;
        hideSubmitError();
        if (autoSubmitTimer) {
            clearTimeout(autoSubmitTimer);
            autoSubmitTimer = null;
        }
        if (isRecording) await stopRecording();

        if (audioChunks.length && !recordedAudio) {
            recordedAudio = new Blob(audioChunks, { type: 'audio/webm' });
        }
        const transcript = (transcriptText.textContent || finalTranscript || '').trim();
        console.log(`[STT Step 5/6] submitAnswer called: transcript="${transcript}", recordedAudio=${recordedAudio ? recordedAudio.size : 0} bytes`);

        if (!transcript && (!recordedAudio || recordedAudio.size === 0)) {
            console.warn('[STT] Empty answer submission: neither transcript nor audio recorded.');
            showSubmitError('Please speak your answer or type it in the box before submitting.');
            hasSubmittedCurrentQuestion = false;
            return;
        }

        showLoading('Evaluating your response with Gemini AI...');
        try {
            const formData = new FormData();
            formData.append('question_id', currentQuestion.question_id);
            const langVal = speechLanguage ? (speechLanguage.value || 'en-IN') : 'en-IN';
            formData.append('speech_language', langVal);
            if (transcript) formData.append('answer_text', transcript);
            if (recordedAudio && recordedAudio.size > 0) formData.append('audio_file', recordedAudio, 'answer.webm');
            if (recordedVideo && recordedVideo.size > 0) formData.append('video_file', recordedVideo, 'answer.webm');

            console.log(`[STT Step 6/6] Sending /answer POST for question=${currentQuestion.question_id}, lang=${langVal}, answer_text="${transcript}"`);

            const data = await apiFetch(`/api/v1/interview/${sessionId}/answer`, { method: 'POST', body: formData });
            hideSubmitError();

            // Clear draft for this answered question
            try {
                localStorage.removeItem('ai_interview_draft_transcript_' + sessionId);
            } catch (e) {}

            // Incorporate any video proctoring audit events returned by vision model
            if (data.proctoring_debug_events && Array.isArray(data.proctoring_debug_events)) {
                data.proctoring_debug_events.forEach((dev) => {
                    logProctoringDebugEvent({
                        time: new Date().toLocaleTimeString(),
                        event: dev.event,
                        confidence: `${Math.round((dev.confidence || 0.9) * 100)}%`,
                        duration: `${(dev.duration_sec || 0).toFixed(1)}s`,
                        severity: dev.severity || 'Normal',
                        penalty: dev.penalty > 0 ? `-${dev.penalty}%` : '0%',
                        penaltyValue: dev.penalty || 0,
                        reason: dev.reason || 'Camera observation.'
                    });
                });
            }

            answeredQuestionsCount++;
            updateTimingMetadata(data);
            if (data.elapsed_seconds) updateInterviewClock(data.elapsed_seconds);
            if (data.should_submit) {
                await submitInterview();
            } else {
                await fetchNextQuestion();
            }
        } catch (error) {
            console.error('[SubmitAnswer] Failed to submit answer:', {
                status: error.status,
                message: error.message,
                rawBody: error.rawBody,
            });
            hasSubmittedCurrentQuestion = false;
            showSubmitError(error.message || 'Could not submit your answer, please try again.');
        } finally {
            hideLoading();
            submitAnswerBtn.disabled = false;
        }
    }

    submitAnswerBtn.addEventListener('click', submitAnswer);

    async function submitInterview() {
        showLoading('Compiling Gemini evaluation report & proctoring audit...');
        try {
            const queryParams = new URLSearchParams({
                tab_switches: String(tabSwitchCount),
                integrity_score: String(proctoringIntegrityScore),
                proctoring_data: JSON.stringify(proctoringEvents)
            });
            const data = await apiFetch(`/api/v1/interview/${sessionId}/submit?${queryParams.toString()}`, { method: 'POST' });
            renderReport(data);
            stopInterviewClock();
            if (cameraStream) {
                cameraStream.getTracks().forEach((track) => track.stop());
                cameraStream = null;
            }
            interviewScreen.classList.remove('active');
            reportScreen.classList.add('active');
            if (endInterviewBtn) endInterviewBtn.classList.add('hidden');
        } catch (error) {
            alert(error.message);
        } finally {
            hideLoading();
        }
    }

    function setList(id, items, icon) {
        const list = $(id);
        list.replaceChildren();
        (items || []).forEach((item) => {
            const li = document.createElement('li');
            li.innerHTML = `<i class="fa-solid ${icon}"></i> `;
            li.append(document.createTextNode(item));
            list.appendChild(li);
        });
    }

    function animateRing(ringId, valueId, score, color) {
        const safeScore = Math.max(0, Math.min(100, Number(score) || 0));
        $(valueId).textContent = `${Math.round(safeScore)}%`;
        $(ringId).style.background = `conic-gradient(var(${color}) ${safeScore * 3.6}deg, var(--card-bg) 0deg)`;
    }

    function renderReport(report) {
        $('report-candidate-name').textContent = candidate?.name || 'Candidate';
        $('report-candidate-role').textContent = candidate?.job_role || '—';
        $('report-date').textContent = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
        $('report-recommendation').textContent = report.recommendations || 'Performance demonstrated strong alignment with role expectations.';
        
        // Proctoring verdict
        const proctorScore = Math.round(proctoringIntegrityScore || 100);
        if ($('report-proctor-text')) {
            $('report-proctor-text').textContent = report.integrity_verdict || `Proctoring verified: ${tabSwitchCount} tab switch alerts, ${proctorScore}% integrity trust score.`;
        }

        // Render proctoring event audit trail in report if available
        const auditBox = $('report-proctor-events-box');
        const auditList = $('report-proctor-events-list');
        if (auditBox && auditList) {
            if (proctoringEvents.length > 0) {
                auditBox.classList.remove('hidden');
                auditList.replaceChildren();
                proctoringEvents.slice(0, 10).forEach((ev) => {
                    const li = document.createElement('li');
                    li.style.marginBottom = '0.25rem';
                    li.innerHTML = `<strong>${ev.event}</strong> (${ev.duration || '0s'}): ${ev.reason || ''} [Penalty: ${ev.penalty}]`;
                    auditList.appendChild(li);
                });
            } else {
                auditBox.classList.add('hidden');
            }
        }
        
        setList('report-strengths', report.strengths, 'fa-circle-check');
        setList('report-weaknesses', report.weaknesses, 'fa-circle-exclamation');
        setList('roadmap-short', report.learning_plan?.short_term, 'fa-chevron-right');
        setList('roadmap-long', report.learning_plan?.long_term, 'fa-chevron-right');
        animateRing('ring-overall', 'val-overall', report.overall_score, '--primary-purple');
        animateRing('ring-technical', 'val-technical', report.technical_score, '--badge-cyan');
        animateRing('ring-communication', 'val-communication', report.communication_score, '--badge-pink');
        animateRing('ring-integrity', 'val-integrity', proctorScore, '--success');
    }

    $('restart-btn').addEventListener('click', () => {
        reportScreen.classList.remove('active');
        welcomeScreen.classList.add('active');
        localStorage.removeItem('ai_interview_active_session_id');
        localStorage.removeItem('ai_interview_tab_switches');
        localStorage.removeItem('ai_interview_integrity_score');
        localStorage.removeItem('ai_interview_proctoring_events');
        if (sessionId) {
            localStorage.removeItem('ai_interview_draft_transcript_' + sessionId);
        }
        sessionId = null;
        currentQuestion = null;
        tabSwitchCount = 0;
        proctoringIntegrityScore = 100;
        proctoringEvents = [];
        answeredQuestionsCount = 0;
        renderProctorDebugEvents();
        updateIntegrityDisplay();
        if (endInterviewBtn) endInterviewBtn.classList.add('hidden');
        resetUpload();
    });

    /* ══════════════════════════════════════════ */
    /*  END INTERVIEW BUTTON & MODAL LOGIC        */
    /* ══════════════════════════════════════════ */
    function openEndInterviewModal() {
        if (endInterviewModal) endInterviewModal.classList.remove('hidden');
    }

    function closeEndInterviewModal() {
        if (endInterviewModal) endInterviewModal.classList.add('hidden');
    }

    if (endInterviewBtn) {
        endInterviewBtn.addEventListener('click', openEndInterviewModal);
    }
    if (closeEndModalBtn) {
        closeEndModalBtn.addEventListener('click', closeEndInterviewModal);
    }
    if (cancelEndModalBtn) {
        cancelEndModalBtn.addEventListener('click', closeEndInterviewModal);
    }
    if (endInterviewModal) {
        endInterviewModal.addEventListener('click', (event) => {
            if (event.target === endInterviewModal) closeEndInterviewModal();
        });
    }
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && endInterviewModal && !endInterviewModal.classList.contains('hidden')) {
            closeEndInterviewModal();
        }
    });

    if (confirmEndModalBtn) {
        confirmEndModalBtn.addEventListener('click', async () => {
            closeEndInterviewModal();
            await handleEndInterviewEarly();
        });
    }

    async function handleEndInterviewEarly() {
        if (!sessionId) {
            interviewScreen.classList.remove('active');
            welcomeScreen.classList.add('active');
            if (endInterviewBtn) endInterviewBtn.classList.add('hidden');
            return;
        }

        // Cancel any active speech synthesis
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
        }

        // Stop active mic/video recording cleanly
        if (isRecording) {
            try {
                await stopRecording();
            } catch {
                // proceed
            }
        }

        // Auto-save current in-progress answer if candidate entered or spoke text
        const currentDraft = transcriptText.textContent.trim();
        if (currentDraft && currentQuestion) {
            try {
                showLoading('Saving your current response before concluding...');
                const formData = new FormData();
                formData.append('question_id', currentQuestion.question_id);
                formData.append('speech_language', speechLanguage ? speechLanguage.value : 'en-IN');
                formData.append('answer_text', currentDraft);
                if (recordedAudio) formData.append('audio_file', recordedAudio, 'answer.webm');
                if (recordedVideo) formData.append('video_file', recordedVideo, 'answer.webm');
                await apiFetch(`/api/v1/interview/${sessionId}/answer`, { method: 'POST', body: formData });
                answeredQuestionsCount++;
            } catch (err) {
                console.warn('Could not auto-save final answer draft:', err);
            }
        }

        // Now finalize the interview evaluation
        try {
            await submitInterview();
        } catch (error) {
            if (answeredQuestionsCount === 0 || (error.message && error.message.includes('without any answers'))) {
                const exitConfirm = confirm('No answers have been recorded yet. Would you like to exit the interview and return to the home screen?');
                if (exitConfirm) {
                    stopInterviewClock();
                    if (cameraStream) {
                        cameraStream.getTracks().forEach((track) => track.stop());
                        cameraStream = null;
                    }
                    interviewScreen.classList.remove('active');
                    welcomeScreen.classList.add('active');
                    if (endInterviewBtn) endInterviewBtn.classList.add('hidden');
                    localStorage.removeItem('ai_interview_active_session_id');
                    localStorage.removeItem('ai_interview_tab_switches');
                    localStorage.removeItem('ai_interview_integrity_score');
                    localStorage.removeItem('ai_interview_proctoring_events');
                    if (sessionId) {
                        localStorage.removeItem('ai_interview_draft_transcript_' + sessionId);
                    }
                    resetUpload();
                }
            } else {
                alert(error.message);
            }
        }
    }

    /* ══════════════════════════════════════════ */
    /*  UPGRADED AI CHATBOT FUNCTIONALITY         */
    /* ══════════════════════════════════════════ */
    const chatbotContainer = $('chatbot-container');
    const chatInput = $('chatbot-input');
    const chatMessages = $('chatbot-messages');
    const chatTypingIndicator = $('chat-typing-indicator');

    const chatbotTrigger = $('chatbot-trigger');
    if (chatbotTrigger && chatbotContainer) {
        chatbotTrigger.addEventListener('click', () => chatbotContainer.classList.toggle('collapsed'));
    }
    const chatCloseBtn = $('chat-close-btn');
    if (chatCloseBtn && chatbotContainer) {
        chatCloseBtn.addEventListener('click', () => chatbotContainer.classList.add('collapsed'));
    }

    // Quick suggestion pills
    document.querySelectorAll('.suggestion-pill').forEach((pill) => {
        pill.addEventListener('click', () => {
            const query = pill.getAttribute('data-query');
            if (query && chatInput) {
                chatInput.value = query;
                sendChatMessage();
            }
        });
    });

    async function sendChatMessage() {
        if (!chatInput) return;
        const query = chatInput.value.trim();
        if (!query) return;
        chatInput.value = '';

        if (chatMessages) {
            const userBubble = document.createElement('div');
            userBubble.className = 'chat-bubble user';
            userBubble.textContent = query;
            chatMessages.appendChild(userBubble);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        if (chatTypingIndicator) chatTypingIndicator.classList.remove('hidden');

        try {
            const data = await apiFetch('/api/v1/chatbot/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query }),
            });
            if (chatTypingIndicator) chatTypingIndicator.classList.add('hidden');

            if (chatMessages) {
                const botBubble = document.createElement('div');
                botBubble.className = 'chat-bubble bot';
                botBubble.innerHTML = `<span class="bubble-speaker">Aria 😊</span>${data.response || 'I am here to assist you with your interview!'}`;
                chatMessages.appendChild(botBubble);
            }
        } catch {
            if (chatTypingIndicator) chatTypingIndicator.classList.add('hidden');
            if (chatMessages) {
                const botBubble = document.createElement('div');
                botBubble.className = 'chat-bubble bot';
                botBubble.innerHTML = '<span class="bubble-speaker">Aria 😊</span>I am here to help you prepare! You can ask about our scoring model, time limits, question topics, or proctoring rules.';
                chatMessages.appendChild(botBubble);
            }
        }
        if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    const chatbotSendBtn = $('chatbot-send-btn');
    if (chatbotSendBtn) {
        chatbotSendBtn.addEventListener('click', sendChatMessage);
    }
    if (chatInput) {
        chatInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') sendChatMessage();
        });
    }

    // ══════════════════════════════════════════════════
    //  PORTS, URLS & HTTPS ENDPOINT SPACE MANAGER
    // ══════════════════════════════════════════════════
    const sidebar = $('portal-sidebar');
    const sidebarToggle = $('sidebar-toggle');
    const headerMenuBtn = $('header-menu-btn');
    const mobileMenuBtn = $('mobile-menu-btn');
    const sidebarBackdrop = $('sidebar-backdrop');
    const endpointModal = $('endpoint-space-modal');
    const endpointTrigger = $('endpoint-space-trigger');
    const sidebarPortPill = $('sidebar-active-port-pill');
    const closeModalBtn = $('close-endpoint-modal-btn');
    const protoHttpBtn = $('proto-http-btn');
    const protoHttpsBtn = $('proto-https-btn');
    const hostInput = $('config-host-input');
    const portInput = $('config-port-input');
    const portChips = document.querySelectorAll('.port-chip');
    const pingServerBtn = $('ping-server-btn');
    const pingStatusBadge = $('ping-status-badge');
    const pingStatusText = $('ping-status-text');
    const displayBaseUrl = $('display-base-url');
    const copyBaseUrlBtn = $('copy-base-url-btn');
    const saveConfigBtn = $('save-endpoint-config-btn');
    const sidebarProtocolTag = $('sidebar-protocol-tag');

    // State for Port/HTTPS configuration
    let currentProtocol = window.location.protocol.replace(':', '') || 'http';
    let currentHost = window.location.hostname || '127.0.0.1';
    let currentPort = window.location.port || (currentProtocol === 'https' ? '443' : '8000');

    // Sidebar Toggle: Appears when clicked, disappears when clicked repeatedly
    function toggleSidebar(e) {
        if (e) {
            e.preventDefault();
            e.stopPropagation();
        }
        if (!sidebar) return;
        const isOpen = sidebar.classList.toggle('sidebar-open');
        if (sidebarBackdrop) {
            sidebarBackdrop.classList.toggle('active', isOpen);
        }
    }

    function closeSidebar() {
        if (!sidebar) return;
        sidebar.classList.remove('sidebar-open');
        if (sidebarBackdrop) {
            sidebarBackdrop.classList.remove('active');
        }
    }

    if (headerMenuBtn) headerMenuBtn.addEventListener('click', toggleSidebar);
    if (mobileMenuBtn) mobileMenuBtn.addEventListener('click', toggleSidebar);
    if (sidebarToggle) sidebarToggle.addEventListener('click', toggleSidebar);
    if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', closeSidebar);

    // Close on Escape key press
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeSidebar();
    });

    // Modal Open & Close Handlers
    function openEndpointModal() {
        if (!endpointModal) return;
        endpointModal.classList.remove('hidden');
        syncModalInputs();
        testServerPing();
    }

    function closeEndpointModal() {
        if (endpointModal) endpointModal.classList.add('hidden');
    }

    if (endpointTrigger) endpointTrigger.addEventListener('click', openEndpointModal);
    if (sidebarPortPill) sidebarPortPill.addEventListener('click', openEndpointModal);
    if (closeModalBtn) closeModalBtn.addEventListener('click', closeEndpointModal);

    if (endpointModal) {
        endpointModal.addEventListener('click', (e) => {
            if (e.target === endpointModal) closeEndpointModal();
        });
    }

    // Calculate Base URL
    function computeBaseUrl(proto, host, port) {
        const isStandardPort = (proto === 'http' && port === '80') || (proto === 'https' && port === '443');
        const portSuffix = port && !isStandardPort ? `:${port}` : '';
        return `${proto}://${host}${portSuffix}`;
    }

    // Sync input fields with current state
    function syncModalInputs() {
        if (protoHttpBtn && protoHttpsBtn) {
            protoHttpBtn.classList.toggle('active', currentProtocol === 'http');
            protoHttpsBtn.classList.toggle('active', currentProtocol === 'https');
        }
        if (hostInput) hostInput.value = currentHost;
        if (portInput) portInput.value = currentPort;
        updatePortChips(currentPort);
        refreshEndpointUrls();
    }

    // Update active port chips
    function updatePortChips(activePort) {
        portChips.forEach((chip) => {
            chip.classList.toggle('active', chip.dataset.port === String(activePort));
        });
    }

    // Refresh all rendered full endpoint URLs in modal
    function refreshEndpointUrls() {
        const baseUrl = computeBaseUrl(currentProtocol, currentHost, currentPort);
        if (displayBaseUrl) displayBaseUrl.textContent = baseUrl;

        // Update full URLs in table
        document.querySelectorAll('.endpoint-full-url').forEach((codeElem) => {
            const path = codeElem.dataset.path || '';
            codeElem.textContent = `${baseUrl}${path}`;
        });

        // Update open action links
        document.querySelectorAll('.table-open-btn').forEach((linkElem) => {
            const path = linkElem.dataset.openPath || '';
            linkElem.href = `${baseUrl}${path}`;
        });
    }

    // Protocol switcher events
    if (protoHttpBtn) {
        protoHttpBtn.addEventListener('click', () => {
            currentProtocol = 'http';
            if (portInput && (portInput.value === '443' || currentPort === '443')) {
                currentPort = '8000';
                portInput.value = '8000';
            }
            syncModalInputs();
        });
    }
    if (protoHttpsBtn) {
        protoHttpsBtn.addEventListener('click', () => {
            currentProtocol = 'https';
            if (portInput && portInput.value === '80') {
                currentPort = '443';
                portInput.value = '443';
            }
            syncModalInputs();
        });
    }

    // Host & Port input change events
    if (hostInput) {
        hostInput.addEventListener('input', (e) => {
            currentHost = e.target.value.trim() || '127.0.0.1';
            refreshEndpointUrls();
        });
    }
    if (portInput) {
        portInput.addEventListener('input', (e) => {
            currentPort = e.target.value.trim();
            updatePortChips(currentPort);
            refreshEndpointUrls();
        });
    }

    // Quick port chip clicks
    portChips.forEach((chip) => {
        chip.addEventListener('click', () => {
            currentPort = chip.dataset.port;
            if (portInput) portInput.value = currentPort;
            updatePortChips(currentPort);
            refreshEndpointUrls();
        });
    });

    // Copy Base URL with feedback
    if (copyBaseUrlBtn) {
        copyBaseUrlBtn.addEventListener('click', async () => {
            const baseUrl = computeBaseUrl(currentProtocol, currentHost, currentPort);
            try {
                await navigator.clipboard.writeText(baseUrl);
                const feedback = copyBaseUrlBtn.querySelector('.copy-feedback');
                if (feedback) {
                    feedback.classList.add('show');
                    setTimeout(() => feedback.classList.remove('show'), 1400);
                }
            } catch {
                // Fallback copy
                prompt('Copy Base URL:', baseUrl);
            }
        });
    }

    // 1-Click Copy in Endpoint Table
    document.querySelectorAll('.table-copy-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const path = btn.dataset.copyPath || '';
            const fullUrl = `${computeBaseUrl(currentProtocol, currentHost, currentPort)}${path}`;
            try {
                await navigator.clipboard.writeText(fullUrl);
                const originalHtml = btn.innerHTML;
                btn.innerHTML = '<i class="fa-solid fa-check" style="color:#10b981;"></i>';
                setTimeout(() => { btn.innerHTML = originalHtml; }, 1400);
            } catch {
                prompt('Copy Endpoint URL:', fullUrl);
            }
        });
    });

    // Live Server Connectivity Ping
    async function testServerPing() {
        if (!pingStatusBadge || !pingStatusText) return;
        pingStatusBadge.innerHTML = '<span class="ping-dot" style="background:#f59e0b;"></span><span id="ping-status-text">Pinging...</span>';
        
        const startTime = performance.now();
        try {
            const res = await fetch('/health', { method: 'GET', cache: 'no-cache' });
            const duration = Math.round(performance.now() - startTime);
            if (res.ok) {
                pingStatusBadge.innerHTML = `<span class="ping-dot green"></span><span style="color:#10b981;font-weight:700;">Connected (${duration}ms) • 200 OK</span>`;
            } else {
                pingStatusBadge.innerHTML = `<span class="ping-dot red"></span><span style="color:#ef4444;font-weight:700;">Status ${res.status} (${duration}ms)</span>`;
            }
        } catch {
            pingStatusBadge.innerHTML = '<span class="ping-dot red"></span><span style="color:#ef4444;font-weight:700;">Port unreachable</span>';
        }
    }

    if (pingServerBtn) pingServerBtn.addEventListener('click', testServerPing);

    // Apply / Save Configuration
    if (saveConfigBtn) {
        saveConfigBtn.addEventListener('click', () => {
            if (sidebarPortPill) {
                const portLabel = sidebarPortPill.querySelector('.port-label-text');
                if (portLabel) portLabel.textContent = currentPort ? `:${currentPort}` : `:${currentProtocol}`;
            }
            if (sidebarProtocolTag) {
                sidebarProtocolTag.textContent = `${currentProtocol.toUpperCase()} ${currentPort ? ':' + currentPort : ''}`;
            }
            // Update active assessments port badge if present
            const assessmentsBadge = $('port-badge-assessments');
            if (assessmentsBadge) assessmentsBadge.textContent = currentPort ? `:${currentPort}` : `:${currentProtocol}`;
            
            closeEndpointModal();
        });
    }

    // Floating notification toast helper
    function showToast(message, type = 'info') {
        let toast = document.getElementById('portal-floating-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'portal-floating-toast';
            toast.className = 'portal-toast';
            document.body.appendChild(toast);
        }
        toast.className = `portal-toast toast-${type} show`;
        toast.innerHTML = `<i class="fa-solid fa-circle-info"></i> <span>${message}</span>`;
        clearTimeout(toast._timeout);
        toast._timeout = setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }

    // Function to randomize navbar ports
    function randomizeNavPorts() {
        const portBadges = document.querySelectorAll('.sidebar-nav .nav-port-badge');
        const candidatePorts = [3000, 3001, 4200, 5000, 5173, 8000, 8080, 8081, 8443, 8888, 9000, 9090];
        
        // Shuffle candidate ports
        const shuffled = [...candidatePorts].sort(() => 0.5 - Math.random());
        
        portBadges.forEach((badge, idx) => {
            const randomPort = shuffled[idx] || (Math.floor(Math.random() * (9900 - 3000 + 1)) + 3000);
            badge.textContent = `:${randomPort}`;
            
            const parentItem = badge.closest('.nav-item');
            if (parentItem) {
                const label = parentItem.querySelector('.nav-label')?.textContent || 'Service';
                parentItem.setAttribute('title', `${label} (:${randomPort})`);
                parentItem.setAttribute('data-tooltip', `${label} (:${randomPort})`);
            }
        });

        showToast('🎲 Random ports assigned across Saarthak navigation!', 'info');
    }

    const randomizePortsBtn = $('randomize-ports-btn');
    if (randomizePortsBtn) {
        randomizePortsBtn.addEventListener('click', randomizeNavPorts);
    }

    // Sidebar navigation active state handler
    document.querySelectorAll('.sidebar-nav .nav-item').forEach((item) => {
        item.addEventListener('click', (e) => {
            if (item.getAttribute('target') === '_blank') {
                return; // Let browser open link in new tab normally
            }
            e.preventDefault();
            const navType = item.getAttribute('data-nav');
            const navLabel = item.querySelector('.nav-label')?.textContent || 'Module';
            const portText = item.querySelector('.nav-port-badge')?.textContent || '';

            if (navType === 'logout') {
                showToast('👋 You have successfully logged out of Saarthak Assessment Portal.', 'info');
                return;
            }

            // Set active item
            document.querySelectorAll('.sidebar-nav .nav-item').forEach((nav) => nav.classList.remove('active'));
            item.classList.add('active');

            if (navType === 'assessments' || navType === 'dashboard') {
                if (welcomeScreen) {
                    document.querySelectorAll('.workspace-screen').forEach((s) => s.classList.remove('active'));
                    welcomeScreen.classList.add('active');
                }
                showToast(`Switched to ${navLabel} (Port ${portText})`, 'success');
            } else {
                showToast(`Connected to ${navLabel} module on port ${portText}`, 'info');
            }
        });
    });

    // Initialize current date dynamically on banner
    try {
        const today = new Date();
        const options = { weekday: 'long', month: 'short', day: '2-digit', year: 'numeric' };
        const dateStr = today.toLocaleDateString('en-US', options);
        if ($('banner-date-text')) $('banner-date-text').textContent = dateStr;
        if ($('schedule-date-text')) {
            const shortOptions = { weekday: 'long', month: 'short', day: '2-digit' };
            $('schedule-date-text').textContent = today.toLocaleDateString('en-US', shortOptions);
        }
    } catch {
        // Fallback gracefully
    }

    // Run initial health check on sidebar load
    testServerPing();

    /* ══════════════════════════════════════════ */
    /*  AUTOMATIC INTERVIEW SESSION RESTORATION  */
    /* ══════════════════════════════════════════ */
    async function tryRestoreSession() {
        const savedSessionId = localStorage.getItem('ai_interview_active_session_id');
        if (!savedSessionId) return false;

        try {
            showLoading('Restoring your ongoing interview session...');
            const state = await apiFetch(`/api/v1/interview/${savedSessionId}/state`);
            sessionId = state.session_id;
            candidate = state.candidate;

            // 1. Restore candidate details & headers
            const candidateName = candidate?.name || 'Candidate';
            if ($('header-user-name')) $('header-user-name').textContent = candidateName.toUpperCase();
            if ($('preview-name')) $('preview-name').textContent = candidateName;
            if ($('preview-role')) $('preview-role').textContent = candidate?.job_role || 'Software Engineer';
            if ($('preview-exp')) $('preview-exp').textContent = `${candidate?.experience_years || 0} years (Fresher)`;

            // 2. Restore proctoring state & debug audit trail
            tabSwitchCount = parseInt(localStorage.getItem('ai_interview_tab_switches') || '0', 10);
            proctoringIntegrityScore = parseFloat(localStorage.getItem('ai_interview_integrity_score') || '100');
            try {
                proctoringEvents = JSON.parse(localStorage.getItem('ai_interview_proctoring_events') || '[]');
            } catch {
                proctoringEvents = [];
            }
            renderProctorDebugEvents();
            updateIntegrityDisplay();

            totalQuestions = state.total_questions || 10;
            minDurationSec = state.min_duration_seconds || 300;
            maxDurationSec = state.max_duration_seconds || 600;
            answeredQuestionsCount = state.answered_questions || 0;

            // 3. If interview was completed, restore report directly
            if (state.status === 'completed' && state.report) {
                welcomeScreen.classList.remove('active');
                interviewScreen.classList.remove('active');
                reportScreen.classList.add('active');
                renderReport(state.report);
                return true;
            }

            // 4. Ongoing interview in 'started' state
            welcomeScreen.classList.remove('active');
            reportScreen.classList.remove('active');
            interviewScreen.classList.add('active');
            if (endInterviewBtn) endInterviewBtn.classList.remove('hidden');

            // 5. Restore interview clock accurately
            const startOffsetMs = (state.elapsed_seconds || 0) * 1000;
            interviewStartTime = Date.now() - startOffsetMs;
            if (interviewClockInterval) clearInterval(interviewClockInterval);
            interviewClockInterval = setInterval(() => {
                const elapsed = Math.floor((Date.now() - interviewStartTime) / 1000);
                updateInterviewClock(elapsed);
            }, 1000);
            updateInterviewClock(state.elapsed_seconds || 0);

            // 6. Re-activate camera stream cleanly
            await startInterviewCamera();

            // 7. Restore current active question
            if (state.current_question) {
                currentQuestion = state.current_question;
                updateTimingMetadata(state.current_question);
                questionCategory.innerHTML = '<i class="fa-solid fa-folder-open"></i> ';
                questionCategory.append(document.createTextNode(currentQuestion.category));
                questionDifficulty.textContent = currentQuestion.difficulty.charAt(0).toUpperCase() + currentQuestion.difficulty.slice(1);
                questionOrder.textContent = `Question ${currentQuestion.order} · ${formatClock(minDurationSec)}–${formatClock(maxDurationSec)} interview`;
                questionText.textContent = currentQuestion.question_text;

                // Safely reset answer controls (handling any interrupted recording gracefully)
                resetAnswer();

                // If draft transcript existed before refresh, restore it safely
                const savedDraft = localStorage.getItem('ai_interview_draft_transcript_' + sessionId) || '';
                if (savedDraft.trim()) {
                    finalTranscript = savedDraft.trim();
                    transcriptText.textContent = finalTranscript;
                    transcriptPlaceholder.classList.add('hidden');
                    enableSubmission();
                    showToast('Draft answer restored from before refresh.', 'info');
                }

                // Prompt question
                speakAsAria(currentQuestion.question_text);
            } else if (state.answered_questions >= state.total_questions) {
                await submitInterview();
            }

            showToast('Session restored successfully.', 'success');
            return true;
        } catch (err) {
            console.error('Error restoring session:', err);
            localStorage.removeItem('ai_interview_active_session_id');
            return false;
        } finally {
            hideLoading();
        }
    }

    // Check and restore any active session on load
    tryRestoreSession();
}

// Lifecycle check: Run immediately if already loaded, else wait for DOMContentLoaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initInterviewApp);
} else {
    initInterviewApp();
}
