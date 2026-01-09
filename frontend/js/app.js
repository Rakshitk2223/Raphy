document.addEventListener('DOMContentLoaded', () => {
    const messagesContainer = document.getElementById('messages');
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const stopBtn = document.getElementById('stop-btn');
    const clearBtn = document.getElementById('clear-btn');
    const muteBtn = document.getElementById('mute-btn');
    const statusIndicator = document.getElementById('status-indicator');
    const statusText = document.getElementById('status-text');
    const voiceStatus = document.getElementById('voice-status');
    const orbWrapper = document.getElementById('orb-wrapper');
    const orbElement = document.getElementById('orb');
    const orbHint = document.getElementById('orb-hint');

    const orb = new OrbController(orbElement);
    let currentAssistantMessage = null;
    let isProcessing = false;
    let isMuted = true;
    let isRecording = false;
    let isSpeaking = false;
    let hasUsedVoice = false;

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
            updateUI();
            orb.setThinking();
            currentAssistantMessage = createMessage('assistant');
            messagesContainer.appendChild(currentAssistantMessage);
            scrollToBottom();
        },
        onChunk: (content) => {
            if (currentAssistantMessage) {
                appendToMessage(currentAssistantMessage, content);
                scrollToBottom();
            }
        },
        onEnd: (stopped) => {
            isProcessing = false;
            isSpeaking = false;
            updateUI();
            if (currentAssistantMessage) {
                finishMessage(currentAssistantMessage, stopped);
            }
            currentAssistantMessage = null;
            orb.setIdle();
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
                    isSpeaking = false;
                    showVoiceStatus('Listening...', 0, 'listening');
                    hideOrbHint();
                    break;
                case 'processing':
                    orb.setThinking();
                    isRecording = false;
                    showVoiceStatus('Processing speech...', 0);
                    break;
                case 'speaking':
                    orb.setSpeaking();
                    isSpeaking = true;
                    isRecording = false;
                    showVoiceStatus('Speaking...', 0);
                    break;
                case 'muted':
                    orb.setIdle();
                    isRecording = false;
                    isSpeaking = false;
                    hideVoiceStatus();
                    break;
                case 'idle':
                default:
                    if (!isProcessing) {
                        orb.setIdle();
                    }
                    isRecording = false;
                    isSpeaking = false;
                    hideVoiceStatus();
                    break;
            }
            updateUI();
        },
        onTranscription: (text) => {
            addUserMessage(text);
            showVoiceStatus('Transcribed: ' + text.substring(0, 30) + (text.length > 30 ? '...' : ''), 2000);
        },
    });

    ws.connect();

    function createMessage(role) {
        const message = document.createElement('div');
        message.className = `message ${role}`;
        
        const content = document.createElement('div');
        content.className = 'message-content';
        
        const paragraph = document.createElement('p');
        paragraph.dataset.rawContent = '';
        paragraph.innerHTML = '<span class="typing-cursor"></span>';
        
        content.appendChild(paragraph);
        message.appendChild(content);
        
        return message;
    }

    function appendToMessage(messageElement, text) {
        const paragraph = messageElement.querySelector('p');
        const cursor = paragraph.querySelector('.typing-cursor');
        
        paragraph.dataset.rawContent = (paragraph.dataset.rawContent || '') + text;
        
        if (cursor) {
            cursor.remove();
        }
        
        paragraph.innerHTML = formatMessageLive(paragraph.dataset.rawContent);
        paragraph.innerHTML += '<span class="typing-cursor"></span>';
    }

    function finishMessage(messageElement, wasStopped = false) {
        const paragraph = messageElement.querySelector('p');
        const cursor = paragraph.querySelector('.typing-cursor');
        if (cursor) {
            cursor.remove();
        }
        
        let content = paragraph.dataset.rawContent || paragraph.textContent;
        if (wasStopped && content) {
            content += ' [stopped]';
        }
        paragraph.innerHTML = formatMessage(content);
        
        addCopyButton(messageElement);
        addCodeCopyButtons(messageElement);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatMessage(text) {
        let formatted = escapeHtml(text);
        formatted = formatted.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');
        formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');
        formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        formatted = formatted.replace(/^---$/gm, '<hr>');
        formatted = formatted.replace(/\n/g, '<br>');
        
        return formatted;
    }

    function formatMessageLive(text) {
        let formatted = escapeHtml(text);
        
        const completeCodeBlocks = [];
        formatted = formatted.replace(/```(\w*)\n?([\s\S]*?)```/g, (match, lang, code) => {
            const placeholder = `__CODE_BLOCK_${completeCodeBlocks.length}__`;
            completeCodeBlocks.push(`<pre><code class="language-${lang}">${code}</code></pre>`);
            return placeholder;
        });
        
        formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');
        formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        formatted = formatted.replace(/^---$/gm, '<hr>');
        formatted = formatted.replace(/\n/g, '<br>');
        
        completeCodeBlocks.forEach((block, i) => {
            formatted = formatted.replace(`__CODE_BLOCK_${i}__`, block);
        });
        
        return formatted;
    }

    function addCopyButton(messageElement) {
        const content = messageElement.querySelector('.message-content');
        if (!content || messageElement.querySelector('.copy-msg-btn')) return;
        
        const copyBtn = document.createElement('button');
        copyBtn.className = 'copy-msg-btn';
        copyBtn.title = 'Copy message';
        copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>`;
        
        copyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const paragraph = messageElement.querySelector('p');
            const text = paragraph.dataset.rawContent || paragraph.textContent;
            navigator.clipboard.writeText(text).then(() => {
                copyBtn.classList.add('copied');
                copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>`;
                setTimeout(() => {
                    copyBtn.classList.remove('copied');
                    copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>`;
                }, 2000);
            });
        });
        
        content.appendChild(copyBtn);
    }

    function addCodeCopyButtons(messageElement) {
        const codeBlocks = messageElement.querySelectorAll('pre');
        codeBlocks.forEach(pre => {
            if (pre.querySelector('.copy-code-btn')) return;
            
            pre.style.position = 'relative';
            
            const copyBtn = document.createElement('button');
            copyBtn.className = 'copy-code-btn';
            copyBtn.title = 'Copy code';
            copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>`;
            
            copyBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const code = pre.querySelector('code');
                const text = code ? code.textContent : pre.textContent;
                navigator.clipboard.writeText(text).then(() => {
                    copyBtn.classList.add('copied');
                    copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>`;
                    setTimeout(() => {
                        copyBtn.classList.remove('copied');
                        copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>`;
                    }, 2000);
                });
            });
            
            pre.appendChild(copyBtn);
        });
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

    function updateUI() {
        sendBtn.disabled = !messageInput.value.trim() || isProcessing || !ws.isConnected();
        
        if (isProcessing) {
            sendBtn.classList.add('hidden');
            stopBtn.classList.remove('hidden');
        } else {
            sendBtn.classList.remove('hidden');
            stopBtn.classList.add('hidden');
        }

        muteBtn.classList.toggle('muted', isMuted);
        muteBtn.classList.toggle('unmuted', !isMuted);
        muteBtn.title = isMuted ? 'Click to enable voice' : 'Click to mute';
    }

    function sendMessage() {
        const content = messageInput.value.trim();
        if (!content || isProcessing || !ws.isConnected()) return;

        addUserMessage(content);
        ws.sendMessage(content, !isMuted);
        messageInput.value = '';
        messageInput.style.height = 'auto';
        updateUI();
    }

    function stopGeneration() {
        if (isProcessing || isSpeaking) {
            ws.stopGeneration();
            isSpeaking = false;
            orb.setIdle();
        }
    }

    function handleOrbClick() {
        orb.pulse();

        if (isSpeaking) {
            stopGeneration();
            return;
        }

        if (isProcessing) {
            stopGeneration();
            return;
        }

        if (isMuted) {
            showVoiceStatus('Unmute first (click speaker icon)', 2000, 'error');
            return;
        }

        if (isRecording) {
            ws.stopVoice();
        } else {
            ws.startVoice();
            if (!hasUsedVoice) {
                hasUsedVoice = true;
            }
        }
    }

    function toggleMute() {
        isMuted = !isMuted;
        ws.setMuted(isMuted);
        
        if (isMuted) {
            showVoiceStatus('Muted', 1500);
            if (isRecording) {
                ws.cancelVoice();
            }
        } else {
            showVoiceStatus('Voice enabled - click orb to speak', 2000);
        }
        updateUI();
    }

    function hideOrbHint() {
        if (!hasUsedVoice) {
            hasUsedVoice = true;
            orbHint.classList.add('hidden');
        }
    }

    function showVoiceStatus(text, duration = 2000, type = '') {
        voiceStatus.textContent = text;
        voiceStatus.className = 'voice-status visible';
        if (type) {
            voiceStatus.classList.add(type);
        }
        if (duration > 0) {
            setTimeout(() => {
                voiceStatus.classList.remove('visible');
            }, duration);
        }
    }

    function hideVoiceStatus() {
        voiceStatus.classList.remove('visible');
    }

    messageInput.addEventListener('input', () => {
        updateUI();
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
    });

    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.altKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Alt' && e.location === 1 && e.code === 'AltLeft') {
            return;
        }
        
        if (e.altKey && e.key === 'Enter') {
            e.preventDefault();
            handleOrbClick();
        }

        if (e.key === 'Escape') {
            if (isProcessing || isSpeaking) {
                stopGeneration();
            } else if (isRecording) {
                ws.cancelVoice();
                showVoiceStatus('Cancelled', 1500);
            }
        }
    });

    orbWrapper.addEventListener('click', handleOrbClick);
    sendBtn.addEventListener('click', sendMessage);
    stopBtn.addEventListener('click', stopGeneration);
    muteBtn.addEventListener('click', toggleMute);

    clearBtn.addEventListener('click', () => {
        if (confirm('Clear conversation history?')) {
            ws.clearHistory();
            messagesContainer.innerHTML = '';
            const welcomeMessage = createMessage('assistant');
            const content = welcomeMessage.querySelector('p');
            content.innerHTML = "Hello! I'm Raphael, your personal AI assistant. Click the orb above to speak, or type below.";
            messagesContainer.appendChild(welcomeMessage);
        }
    });

    muteBtn.classList.add('muted');
    updateUI();
});
