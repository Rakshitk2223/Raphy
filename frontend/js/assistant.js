document.addEventListener('DOMContentLoaded', () => {
    const orbWrapper = document.getElementById('orb-wrapper');
    const orbElement = document.getElementById('orb');
    const voiceStatus = document.getElementById('voice-status');
    const statusIndicator = document.getElementById('status-indicator');
    const muteBtn = document.getElementById('mute-btn');

    const orb = new OrbController(orbElement);
    
    let isListening = false;
    let isProcessing = false;
    let isSpeaking = false;
    let conversationActive = false;
    let isMuted = localStorage.getItem('raphael_muted') === 'true';

    function updateMuteUI() {
        if (isMuted) {
            muteBtn.classList.add('muted');
            orb.setIdle();
            setStatus('Mic paused - click to unmute', '');
        } else {
            muteBtn.classList.remove('muted');
            if (!conversationActive) {
                orb.setListening();
                setStatus('Listening...', 'listening');
            }
        }
    }

    if (muteBtn) {
        muteBtn.addEventListener('click', (e) => {
            e.preventDefault();
            isMuted = !isMuted;
            localStorage.setItem('raphael_muted', isMuted);
            updateMuteUI();
            
            if (!isMuted && conversationActive) {
                ws.startConversation();
            } else if (isMuted && conversationActive) {
                ws.stopConversation();
            }
        });
    }

    updateMuteUI();

    let clientId = localStorage.getItem('raphael_assistant_id');
    if (!clientId) {
        clientId = `assistant_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        localStorage.setItem('raphael_assistant_id', clientId);
    }
    
    const wsUrl = `ws://${window.location.host}/ws/${clientId}`;

    const ws = new RaphaelWebSocket(wsUrl, {
        onConnect: () => {
            statusIndicator.classList.add('connected');
            
            if (isMuted) {
                setStatus('Mic paused - click to unmute', '');
                return;
            }
            
            setStatus('Starting...', 'thinking');
            
            setTimeout(() => {
                ws.startConversation();
                conversationActive = true;
            }, 500);
        },
        onDisconnect: () => {
            statusIndicator.classList.remove('connected');
            setStatus('Connection lost...', 'error');
            conversationActive = false;
        },
        onError: (error) => {
            statusIndicator.classList.add('error');
            setStatus('Connection error', 'error');
            orb.setError();
            console.error('WebSocket error:', error);
        },
        onStart: (data) => {
            isProcessing = true;
            orb.setThinking();
            setStatus('Thinking...', 'thinking');
        },
        onChunk: (content) => {
        },
        onEnd: (stopped) => {
            isProcessing = false;
            if (!isSpeaking) {
                orb.setListening();
                if (stopped) {
                    setStatus('Stopped. Listening...', 'listening');
                } else {
                    setStatus('Listening...', 'listening');
                }
            }
        },
        onVoiceState: (state) => {
            switch (state) {
                case 'listening':
                    orb.setListening();
                    isListening = true;
                    isSpeaking = false;
                    isProcessing = false;
                    setStatus('Listening...', 'listening');
                    break;
                case 'processing':
                    orb.setThinking();
                    isListening = false;
                    isProcessing = true;
                    setStatus('Processing...', 'thinking');
                    break;
                case 'speaking':
                    orb.setSpeaking();
                    isSpeaking = true;
                    isListening = false;
                    isProcessing = false;
                    setStatus('Speaking... (click to interrupt)', 'speaking');
                    break;
                case 'idle':
                    if (!isProcessing && !isMuted) {
                        orb.setListening();
                        setStatus('Listening...', 'listening');
                    }
                    isListening = true;
                    isSpeaking = false;
                    break;
                case 'muted':
                    orb.setIdle();
                    isListening = false;
                    isSpeaking = false;
                    if (!isMuted) {
                        setStatus('Muted. Click to unmute.', '');
                    }
                    break;
            }
        },
        onTranscription: (text) => {
            if (text) {
                setStatus(`"${text.substring(0, 50)}${text.length > 50 ? '...' : ''}"`, 'thinking');
            }
        }
    });

    ws.connect();

    function setStatus(text, className = '') {
        voiceStatus.textContent = text;
        voiceStatus.className = 'status-text';
        if (className) {
            voiceStatus.classList.add(className);
        }
    }

    function handleOrbClick() {
        if (isMuted) {
            isMuted = false;
            localStorage.setItem('raphael_muted', isMuted);
            updateMuteUI();
            if (conversationActive) {
                ws.startConversation();
            }
            return;
        }
        
        orb.pulse();

        if (isSpeaking) {
            ws.stopGeneration();
            isSpeaking = false;
            orb.setListening();
            setStatus('Interrupted. Listening...', 'listening');
            return;
        }

        if (isProcessing) {
            ws.stopGeneration();
            isProcessing = false;
            orb.setListening();
            setStatus('Stopped. Listening...', 'listening');
            return;
        }
    }

    orbWrapper.addEventListener('click', handleOrbClick);

    document.addEventListener('keydown', (e) => {
        if (e.code === 'Space' && !e.target.matches('input, textarea')) {
            e.preventDefault();
            handleOrbClick();
        }

        if (e.key === 'Escape') {
            if (isSpeaking || isProcessing) {
                ws.stopGeneration();
                isSpeaking = false;
                isProcessing = false;
                if (!isMuted) {
                    orb.setListening();
                    setStatus('Stopped. Listening...', 'listening');
                }
            }
        }
    });

    window.addEventListener('beforeunload', () => {
        if (conversationActive) {
            ws.stopConversation();
        }
    });

    window.clearAssistantSession = function() {
        localStorage.removeItem('raphael_assistant_id');
        ws.stopConversation();
        setStatus('Session cleared. Refresh to start fresh.', '');
        setTimeout(() => {
            location.reload();
        }, 1500);
    };

    setStatus('Connecting...', '');
});
