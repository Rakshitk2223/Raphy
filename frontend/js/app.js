document.addEventListener('DOMContentLoaded', () => {
    const messagesContainer = document.getElementById('messages');
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const stopBtn = document.getElementById('stop-btn');
    const clearBtn = document.getElementById('clear-btn');
    const voiceBtn = document.getElementById('voice-btn');
    const muteBtn = document.getElementById('mute-btn');
    const statusIndicator = document.getElementById('status-indicator');
    const statusText = document.getElementById('status-text');
    const voiceStatus = document.getElementById('voice-status');
    const orbElement = document.getElementById('orb');

    const orb = new OrbController(orbElement);
    let currentAssistantMessage = null;
    let isProcessing = false;
    let isMuted = true;
    let isRecording = false;
    let voiceOutputEnabled = false;

    const clientId = `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const wsUrl = `ws://${window.location.host}/ws/${clientId}`;

    const ws = new RaphaelWebSocket(wsUrl, {
        onConnect: () => {
            statusIndicator.classList.add('connected');
            statusIndicator.classList.remove('error');
            statusText.textContent = 'Connected';
            orb.setIdle();
        },
        onDisconnect: () => {
            statusIndicator.classList.remove('connected');
            statusText.textContent = 'Reconnecting...';
        },
        onError: (error) => {
            statusIndicator.classList.add('error');
            statusText.textContent = 'Connection error';
            orb.setError();
            console.error('WebSocket error:', error);
        },
        onStart: (data) => {
            isProcessing = true;
            updateButtons();
            orb.setThinking();
            currentAssistantMessage = createMessage('assistant');
            messagesContainer.appendChild(currentAssistantMessage);
            scrollToBottom();
        },
        onChunk: (content) => {
            orb.setSpeaking();
            if (currentAssistantMessage) {
                appendToMessage(currentAssistantMessage, content);
                scrollToBottom();
            }
        },
        onEnd: (stopped) => {
            isProcessing = false;
            updateButtons();
            if (currentAssistantMessage) {
                finishMessage(currentAssistantMessage, stopped);
            }
            currentAssistantMessage = null;
            scrollToBottom();
        },
        onSystem: (content) => {
            const systemMessage = document.createElement('div');
            systemMessage.className = 'system-message';
            systemMessage.textContent = content;
            messagesContainer.appendChild(systemMessage);
            scrollToBottom();
        },
        onVoiceState: (state) => {
            switch (state) {
                case 'listening':
                    orb.setListening();
                    isRecording = true;
                    voiceBtn.classList.add('recording');
                    showVoiceStatus('Listening...', 0);
                    break;
                case 'processing':
                    orb.setThinking();
                    showVoiceStatus('Processing speech...', 0);
                    break;
                case 'speaking':
                    orb.setSpeaking();
                    showVoiceStatus('Speaking...', 0);
                    break;
                case 'muted':
                    orb.setIdle();
                    hideVoiceStatus();
                    break;
                case 'idle':
                default:
                    orb.setIdle();
                    isRecording = false;
                    voiceBtn.classList.remove('recording');
                    hideVoiceStatus();
                    break;
            }
            updateButtons();
        },
        onTranscription: (text) => {
            addUserMessage(text);
            showVoiceStatus('Transcribed: ' + text.substring(0, 30) + (text.length > 30 ? '...' : ''));
        },
    });

    ws.connect();

    function createMessage(role) {
        const message = document.createElement('div');
        message.className = `message ${role}`;
        
        const content = document.createElement('div');
        content.className = 'message-content';
        
        const paragraph = document.createElement('p');
        paragraph.innerHTML = '<span class="typing-cursor"></span>';
        
        content.appendChild(paragraph);
        message.appendChild(content);
        
        return message;
    }

    function appendToMessage(messageElement, text) {
        const paragraph = messageElement.querySelector('p');
        const cursor = paragraph.querySelector('.typing-cursor');
        
        if (cursor) {
            cursor.remove();
        }
        
        paragraph.innerHTML += escapeHtml(text);
        paragraph.innerHTML += '<span class="typing-cursor"></span>';
    }

    function finishMessage(messageElement, wasStopped = false) {
        const paragraph = messageElement.querySelector('p');
        const cursor = paragraph.querySelector('.typing-cursor');
        if (cursor) {
            cursor.remove();
        }
        
        let content = paragraph.textContent;
        if (wasStopped && content) {
            content += ' [stopped]';
        }
        paragraph.innerHTML = formatMessage(content);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatMessage(text) {
        let formatted = escapeHtml(text);
        formatted = formatted.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
        formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');
        formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        formatted = formatted.replace(/\n/g, '<br>');
        
        return formatted;
    }

    function addUserMessage(content) {
        const message = document.createElement('div');
        message.className = 'message user';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const paragraph = document.createElement('p');
        paragraph.innerHTML = formatMessage(content);
        
        contentDiv.appendChild(paragraph);
        message.appendChild(contentDiv);
        messagesContainer.appendChild(message);
        
        scrollToBottom();
    }

    function scrollToBottom() {
        const chatContainer = document.getElementById('chat-container');
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function updateButtons() {
        sendBtn.disabled = !messageInput.value.trim() || isProcessing || !ws.isConnected();
        
        if (isProcessing) {
            sendBtn.classList.add('hidden');
            stopBtn.classList.remove('hidden');
        } else {
            sendBtn.classList.remove('hidden');
            stopBtn.classList.add('hidden');
        }

        voiceBtn.disabled = isMuted || isProcessing;
    }

    function sendMessage(speak = false) {
        const content = messageInput.value.trim();
        if (!content || isProcessing || !ws.isConnected()) return;

        addUserMessage(content);
        ws.sendMessage(content, speak);
        messageInput.value = '';
        messageInput.style.height = 'auto';
        updateButtons();
    }

    function stopGeneration() {
        if (isProcessing) {
            ws.stopGeneration();
        }
    }

    function toggleVoiceRecording() {
        if (isMuted) {
            showVoiceStatus('Unmute microphone first');
            return;
        }

        if (isRecording) {
            ws.stopVoice();
        } else {
            ws.startVoice();
        }
    }

    messageInput.addEventListener('input', () => {
        updateButtons();
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
    });

    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.altKey) {
            e.preventDefault();
            sendMessage(voiceOutputEnabled);
        }
        if (e.key === 'Enter' && e.altKey) {
            e.preventDefault();
            toggleVoiceRecording();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (isProcessing) {
                stopGeneration();
            } else if (isRecording) {
                ws.cancelVoice();
            }
        }
    });

    sendBtn.addEventListener('click', () => sendMessage(voiceOutputEnabled));
    stopBtn.addEventListener('click', stopGeneration);

    clearBtn.addEventListener('click', () => {
        if (confirm('Clear conversation history?')) {
            ws.clearHistory();
            messagesContainer.innerHTML = '';
            const welcomeMessage = createMessage('assistant');
            const content = welcomeMessage.querySelector('p');
            content.innerHTML = 'Hello! I\'m Raphael, your personal AI assistant. How can I help you today?';
            messagesContainer.appendChild(welcomeMessage);
        }
    });

    voiceBtn.addEventListener('click', toggleVoiceRecording);

    muteBtn.addEventListener('click', () => {
        isMuted = !isMuted;
        muteBtn.classList.toggle('muted', isMuted);
        muteBtn.title = isMuted ? 'Microphone muted (click to enable)' : 'Microphone active (click to mute)';
        ws.setMuted(isMuted);
        
        if (isMuted) {
            showVoiceStatus('Microphone muted');
            if (isRecording) {
                ws.cancelVoice();
            }
        } else {
            showVoiceStatus('Microphone enabled - use Left Alt+Enter or click mic');
        }
        updateButtons();
    });

    function showVoiceStatus(text, duration = 2000) {
        voiceStatus.textContent = text;
        voiceStatus.classList.add('visible');
        if (duration > 0) {
            setTimeout(() => {
                voiceStatus.classList.remove('visible');
            }, duration);
        }
    }

    function hideVoiceStatus() {
        voiceStatus.classList.remove('visible');
    }

    muteBtn.classList.add('muted');
    updateButtons();
});
