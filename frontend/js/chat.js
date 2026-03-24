document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const chatList = document.getElementById('chat-list');
    const chatTitle = document.getElementById('chat-title');
    const messagesContainer = document.getElementById('messages');
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const stopBtn = document.getElementById('stop-btn');
    const micBtn = document.getElementById('mic-btn');
    const newChatBtn = document.getElementById('new-chat-btn');
    const toggleSidebarBtn = document.getElementById('toggle-sidebar-btn');
    const statusIndicator = document.getElementById('status-indicator');
    const statusText = document.getElementById('status-text');

    let currentChatId = null;
    let chats = loadChats();
    let currentAssistantMessage = null;
    let isProcessing = false;
    let isRecording = false;

    const clientId = `chat_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const wsUrl = `ws://${window.location.host}/ws/${clientId}`;

    const ws = new RaphaelWebSocket(wsUrl, {
        onConnect: () => {
            statusIndicator.classList.add('connected');
            statusText.textContent = 'Connected';
        },
        onDisconnect: () => {
            statusIndicator.classList.remove('connected');
            statusText.textContent = 'Reconnecting...';
        },
        onError: (error) => {
            statusText.textContent = 'Connection error';
            console.error('WebSocket error:', error);
        },
        onStart: (data) => {
            isProcessing = true;
            updateUI();
            currentAssistantMessage = createMessage('assistant');
            messagesContainer.appendChild(currentAssistantMessage);
            hideWelcome();
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
            updateUI();
            if (currentAssistantMessage) {
                finishMessage(currentAssistantMessage, stopped);
                saveCurrentChat();
            }
            currentAssistantMessage = null;
            scrollToBottom();
        },
        onTranscription: (text) => {
            if (text) {
                messageInput.value = text;
                sendMessage();
            }
            isRecording = false;
            micBtn.classList.remove('recording');
        },
        onVoiceState: (state) => {
            if (state === 'listening') {
                isRecording = true;
                micBtn.classList.add('recording');
            } else if (state === 'idle' || state === 'processing') {
                isRecording = false;
                micBtn.classList.remove('recording');
            }
        }
    });

    ws.connect();

    function loadChats() {
        try {
            const saved = localStorage.getItem('raphael_chats');
            return saved ? JSON.parse(saved) : [];
        } catch (e) {
            return [];
        }
    }

    function saveChats() {
        try {
            localStorage.setItem('raphael_chats', JSON.stringify(chats));
        } catch (e) {
            console.error('Failed to save chats:', e);
        }
    }

    function saveCurrentChat() {
        if (!currentChatId) return;
        
        const chat = chats.find(c => c.id === currentChatId);
        if (chat) {
            const messages = [];
            messagesContainer.querySelectorAll('.message').forEach(msg => {
                const role = msg.classList.contains('user') ? 'user' : 'assistant';
                const content = msg.querySelector('p')?.dataset.rawContent || 
                               msg.querySelector('p')?.textContent || '';
                if (content) {
                    messages.push({ role, content });
                }
            });
            chat.messages = messages;
            chat.updatedAt = Date.now();
            
            if (messages.length > 0 && chat.title === 'New Chat') {
                const firstMsg = messages[0].content;
                chat.title = firstMsg.substring(0, 30) + (firstMsg.length > 30 ? '...' : '');
                chatTitle.textContent = chat.title;
            }
            
            saveChats();
            renderChatList();
        }
    }

    function createChat() {
        const chat = {
            id: `chat_${Date.now()}`,
            title: 'New Chat',
            messages: [],
            createdAt: Date.now(),
            updatedAt: Date.now()
        };
        chats.unshift(chat);
        saveChats();
        loadChat(chat.id);
        renderChatList();
    }

    function loadChat(chatId) {
        currentChatId = chatId;
        const chat = chats.find(c => c.id === chatId);
        
        if (!chat) {
            createChat();
            return;
        }
        
        chatTitle.textContent = chat.title;
        messagesContainer.innerHTML = '';
        
        if (chat.messages.length === 0) {
            showWelcome();
        } else {
            chat.messages.forEach(msg => {
                const msgEl = createMessage(msg.role);
                const p = msgEl.querySelector('p');
                p.dataset.rawContent = msg.content;
                p.innerHTML = formatMessage(msg.content);
                addCopyButton(msgEl);
                addCodeCopyButtons(msgEl);
                messagesContainer.appendChild(msgEl);
            });
        }
        
        renderChatList();
        scrollToBottom();
        ws.clearHistory();
    }

    function deleteChat(chatId) {
        chats = chats.filter(c => c.id !== chatId);
        saveChats();
        
        if (currentChatId === chatId) {
            if (chats.length > 0) {
                loadChat(chats[0].id);
            } else {
                createChat();
            }
        }
        
        renderChatList();
    }

    function renderChatList() {
        chatList.innerHTML = '';
        
        chats.forEach(chat => {
            const item = document.createElement('div');
            item.className = `chat-item ${chat.id === currentChatId ? 'active' : ''}`;
            item.innerHTML = `
                <svg class="chat-item-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                </svg>
                <span class="chat-item-title">${escapeHtml(chat.title)}</span>
                <button class="chat-item-delete" title="Delete chat">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z"/>
                    </svg>
                </button>
            `;
            
            item.addEventListener('click', (e) => {
                if (!e.target.closest('.chat-item-delete')) {
                    loadChat(chat.id);
                }
            });
            
            item.querySelector('.chat-item-delete').addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm('Delete this chat?')) {
                    deleteChat(chat.id);
                }
            });
            
            chatList.appendChild(item);
        });
    }

    function showWelcome() {
        if (!messagesContainer.querySelector('.welcome-message')) {
            messagesContainer.innerHTML = `
                <div class="welcome-message">
                    <div class="welcome-icon">R</div>
                    <h2>How can I help you today?</h2>
                    <p>Ask me anything - coding help, explanations, drafting text, or just have a conversation.</p>
                </div>
            `;
        }
    }

    function hideWelcome() {
        const welcome = messagesContainer.querySelector('.welcome-message');
        if (welcome) {
            welcome.remove();
        }
    }

    function createMessage(role) {
        const message = document.createElement('div');
        message.className = `message ${role}`;
        
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = role === 'user' ? 'U' : 'R';
        
        const content = document.createElement('div');
        content.className = 'message-content';
        
        const paragraph = document.createElement('p');
        paragraph.dataset.rawContent = '';
        paragraph.innerHTML = '<span class="typing-cursor"></span>';
        
        content.appendChild(paragraph);
        message.appendChild(avatar);
        message.appendChild(content);
        
        return message;
    }

    function appendToMessage(messageElement, text) {
        const paragraph = messageElement.querySelector('p');
        const cursor = paragraph.querySelector('.typing-cursor');
        
        paragraph.dataset.rawContent = (paragraph.dataset.rawContent || '') + text;
        
        if (cursor) cursor.remove();
        
        paragraph.innerHTML = formatMessageLive(paragraph.dataset.rawContent);
        paragraph.innerHTML += '<span class="typing-cursor"></span>';
    }

    function finishMessage(messageElement, wasStopped = false) {
        const paragraph = messageElement.querySelector('p');
        const cursor = paragraph.querySelector('.typing-cursor');
        if (cursor) cursor.remove();
        
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
                showCopied(copyBtn);
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
                    showCopied(copyBtn);
                });
            });
            
            pre.appendChild(copyBtn);
        });
    }

    function showCopied(btn) {
        btn.classList.add('copied');
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20 6 9 17 4 12"></polyline>
        </svg>`;
        setTimeout(() => {
            btn.classList.remove('copied');
            btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>`;
        }, 2000);
    }

    function addUserMessage(content) {
        hideWelcome();
        const message = createMessage('user');
        const p = message.querySelector('p');
        p.dataset.rawContent = content;
        p.innerHTML = formatMessage(content);
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
    }

    function sendMessage() {
        const content = messageInput.value.trim();
        if (!content || isProcessing || !ws.isConnected()) return;

        addUserMessage(content);
        ws.sendMessage(content, false);
        messageInput.value = '';
        messageInput.style.height = 'auto';
        updateUI();
    }

    function stopGeneration() {
        if (isProcessing) {
            ws.stopGeneration();
        }
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
        if (e.altKey && e.key === 'Enter') {
            e.preventDefault();
            if (!isRecording) {
                ws.startVoice();
            } else {
                ws.stopVoice();
            }
        }

        if (e.key === 'Escape') {
            if (isProcessing) {
                stopGeneration();
            } else if (isRecording) {
                ws.cancelVoice();
            }
        }
    });

    sendBtn.addEventListener('click', sendMessage);
    stopBtn.addEventListener('click', stopGeneration);
    newChatBtn.addEventListener('click', createChat);
    
    micBtn.addEventListener('click', () => {
        if (!isRecording) {
            ws.startVoice();
        } else {
            ws.stopVoice();
        }
    });

    toggleSidebarBtn.addEventListener('click', () => {
        sidebar.classList.toggle('hidden');
    });

    if (chats.length === 0) {
        createChat();
    } else {
        loadChat(chats[0].id);
    }
    
    renderChatList();
    updateUI();
});
