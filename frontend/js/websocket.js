class RaphaelWebSocket {
    constructor(url, callbacks = {}) {
        this.url = url;
        this.callbacks = callbacks;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
    }

    connect() {
        try {
            this.ws = new WebSocket(this.url);

            this.ws.onopen = () => {
                this.reconnectAttempts = 0;
                if (this.callbacks.onConnect) {
                    this.callbacks.onConnect();
                }
            };

            this.ws.onclose = (event) => {
                if (this.callbacks.onDisconnect) {
                    this.callbacks.onDisconnect(event);
                }
                this.attemptReconnect();
            };

            this.ws.onerror = (error) => {
                if (this.callbacks.onError) {
                    this.callbacks.onError(error);
                }
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (e) {
                    console.error('Failed to parse message:', e);
                }
            };
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this.attemptReconnect();
        }
    }

    handleMessage(data) {
        switch (data.type) {
            case 'start':
                if (this.callbacks.onStart) {
                    this.callbacks.onStart(data);
                }
                break;
            case 'chunk':
                if (this.callbacks.onChunk) {
                    this.callbacks.onChunk(data.content);
                }
                break;
            case 'end':
                if (this.callbacks.onEnd) {
                    this.callbacks.onEnd(data.stopped || false);
                }
                break;
            case 'error':
                if (this.callbacks.onError) {
                    this.callbacks.onError(data.content);
                }
                break;
            case 'system':
                if (this.callbacks.onSystem) {
                    this.callbacks.onSystem(data.content);
                }
                break;
            case 'voice_state':
                if (this.callbacks.onVoiceState) {
                    this.callbacks.onVoiceState(data.state);
                }
                break;
            case 'transcription':
                if (this.callbacks.onTranscription) {
                    this.callbacks.onTranscription(data.content);
                }
                break;
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => {
                this.connect();
            }, this.reconnectDelay * this.reconnectAttempts);
        }
    }

    send(type, data = {}) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type, ...data }));
        }
    }

    sendMessage(content, speak = false) {
        this.send('chat', { content, speak });
    }

    stopGeneration() {
        this.send('stop');
    }

    clearHistory() {
        this.send('clear');
    }

    startVoice() {
        this.send('voice_start');
    }

    stopVoice() {
        this.send('voice_stop');
    }

    cancelVoice() {
        this.send('voice_cancel');
    }

    setMuted(muted) {
        this.send('mute', { muted });
    }

    setVoiceOutput(enabled) {
        this.send('voice_output', { enabled });
    }

    startConversation() {
        this.send('conv_start');
    }

    stopConversation() {
        this.send('conv_stop');
    }

    isConnected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }

    close() {
        if (this.ws) {
            this.ws.close();
        }
    }
}

window.RaphaelWebSocket = RaphaelWebSocket;
