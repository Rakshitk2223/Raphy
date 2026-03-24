document.addEventListener('DOMContentLoaded', () => {
    const settingsBtn = document.getElementById('settings-btn');
    const settingsOverlay = document.getElementById('settings-overlay');
    const settingsClose = document.getElementById('settings-close');
    const themeToggle = document.getElementById('theme-toggle');
    const aboutTextarea = document.getElementById('about-textarea');
    const saveAboutBtn = document.getElementById('save-about-btn');
    const settingsStatus = document.getElementById('settings-status');
    const voiceSelect = document.getElementById('voice-select');
    
    const knowledgeInfo = document.getElementById('knowledge-info');
    const aboutInfo = document.getElementById('about-info');
    
    const viewBrainBtn = document.getElementById('view-brain-btn');
    const exportBrainBtn = document.getElementById('export-brain-btn');
    const viewRemindersBtn = document.getElementById('view-reminders-btn');
    const reindexBtn = document.getElementById('reindex-btn');
    const clearHistoryBtn = document.getElementById('clear-history-btn');

    const THEME_KEY = 'raphael_theme';
    const VOICE_KEY = 'raphael_voice';

    function loadTheme() {
        const savedTheme = localStorage.getItem(THEME_KEY) || 'dark';
        if (savedTheme === 'light') {
            document.body.classList.add('light');
            themeToggle.classList.add('light');
        }
    }

    function toggleTheme() {
        document.body.classList.toggle('light');
        const isLight = document.body.classList.contains('light');
        localStorage.setItem(THEME_KEY, isLight ? 'light' : 'dark');
        themeToggle.classList.toggle('light', isLight);
    }

    function openSettings() {
        settingsOverlay.classList.add('active');
        loadProfile();
        loadKnowledgeInfo();
        loadAboutInfo();
    }

    function closeSettings() {
        settingsOverlay.classList.remove('active');
    }

    async function loadProfile() {
        aboutTextarea.value = '';
    }

    async function saveProfile() {
        const about = aboutTextarea.value.trim();
        if (!about) {
            settingsStatus.textContent = 'Please tell me about yourself first!';
            settingsStatus.classList.add('error');
            return;
        }
        
        saveAboutBtn.disabled = true;
        settingsStatus.textContent = '';
        settingsStatus.className = 'settings-status';

        try {
            const response = await fetch('/api/profile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ about })
            });

            if (response.ok) {
                settingsStatus.textContent = 'Profile saved!';
                setTimeout(() => {
                    settingsStatus.textContent = '';
                    aboutTextarea.value = '';
                }, 1500);
            } else {
                throw new Error('Failed to save');
            }
        } catch (e) {
            console.error('Failed to save profile:', e);
            settingsStatus.textContent = 'Failed to save profile';
            settingsStatus.classList.add('error');
        } finally {
            saveAboutBtn.disabled = false;
        }
    }

    async function loadKnowledgeInfo() {
        if (!knowledgeInfo) return;
        try {
            const response = await fetch('/api/knowledge');
            const data = await response.json();
            
            if (data.error) {
                knowledgeInfo.innerHTML = 'No knowledge indexed';
                return;
            }
            
            let html = `<strong>Files:</strong> ${data.files?.join(', ') || 'None'}<br>`;
            html += `<strong>Chunks:</strong> ${data.total_chunks || 0}<br>`;
            if (data.categories) {
                html += `<strong>Categories:</strong> ${Object.entries(data.categories).map(([k, v]) => `${k} (${v})`).join(', ')}`;
            }
            knowledgeInfo.innerHTML = html;
        } catch (e) {
            knowledgeInfo.textContent = 'Failed to load';
        }
    }

    async function loadAboutInfo() {
        if (!aboutInfo) return;
        try {
            const response = await fetch('/api/models');
            let modelInfo = 'Qwen2.5 7B';
            if (response.ok) {
                const data = await response.json();
                modelInfo = data.models?.[0] || 'Qwen2.5 7B';
            }
            
            aboutInfo.innerHTML = `
                <strong>Raphael</strong> v1.0<br>
                <strong>Model:</strong> ${modelInfo}<br>
                <strong>Brain:</strong> data/memory/brain.json<br>
                <strong>Knowledge:</strong> data/memory/chroma/
            `;
        } catch (e) {
            aboutInfo.textContent = 'Raphael v1.0';
        }
    }

    async function viewBrain() {
        try {
            const [brainRes, profileRes] = await Promise.all([
                fetch('/api/brain'),
                fetch('/api/profile')
            ]);
            
            const brainData = await brainRes.json();
            const profileData = await profileRes.json();
            
            let message = '=== YOUR LEARNED INFO ===\n\n';
            
            const brainInfo = brainData.data?.info || {};
            const brainPrefs = brainData.data?.preferences || {};
            const brainSkills = brainData.data?.skills || [];
            const brainFacts = brainData.data?.learned_facts || [];
            
            if (Object.keys(brainInfo).length) {
                message += 'INFO (Brain):\n';
                for (let [k, v] of Object.entries(brainInfo)) {
                    message += `  ${k}: ${v}\n`;
                }
                message += '\n';
            }
            
            if (Object.keys(brainPrefs).length) {
                message += 'PREFERENCES (Brain):\n';
                for (let [k, v] of Object.entries(brainPrefs)) {
                    message += `  ${k}: ${v}\n`;
                }
                message += '\n';
            }
            
            if (brainSkills.length) {
                message += 'SKILLS:\n';
                message += '  ' + brainSkills.join(', ') + '\n\n';
            }
            
            if (brainFacts.length) {
                message += 'RECENT FACTS:\n';
                brainFacts.slice(-5).forEach(f => {
                    message += `  - ${f.fact} (${f.category})\n`;
                });
                message += '\n';
            }
            
            const profile = profileData.profile || {};
            const profilePrefs = profile.preferences || {};
            const profileAbout = profile.about;
            const profileNotes = profileData.notes || [];
            
            if (Object.keys(profilePrefs).length || profileAbout || profileNotes.length) {
                message += 'PROFILE DATA:\n';
                if (profileAbout) {
                    message += `  About: ${profileAbout}\n`;
                }
                for (let [k, v] of Object.entries(profilePrefs)) {
                    message += `  ${k}: ${v}\n`;
                }
                if (profileNotes.length) {
                    message += '\n  NOTES:\n';
                    profileNotes.slice(-3).forEach(n => {
                        message += `  - ${n.content} (${n.category})\n`;
                    });
                }
            }
            
            if (!message.includes(':')) {
                message = 'No information learned yet. Chat with me to teach me about yourself!';
            }
            
            alert(message);
        } catch (e) {
            alert('Failed to load brain: ' + e.message);
        }
    }

    async function exportBrain() {
        try {
            const [brainRes, profileRes] = await Promise.all([
                fetch('/api/brain/export'),
                fetch('/api/profile')
            ]);
            
            const brainData = await brainRes.json();
            const profileData = await profileRes.json();
            
            const exportData = {
                brain: brainData,
                profile: profileData.profile || {},
                exported_at: new Date().toISOString()
            };
            
            const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'raphael_brain.json';
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            alert('Failed to export: ' + e.message);
        }
    }

    async function viewReminders() {
        try {
            const response = await fetch('/api/memory/reminders');
            const data = await response.json();
            
            if (!data.reminders || data.reminders.length === 0) {
                alert('No reminders saved yet!\n\nSay "Remember to..." or "Remind me to..." to add reminders.');
                return;
            }
            
            let message = '=== YOUR REMINDERS ===\n\n';
            data.reminders.forEach((r, i) => {
                message += `${i + 1}. ${r.content || r}\n`;
            });
            
            alert(message);
        } catch (e) {
            alert('Failed to load reminders: ' + e.message);
        }
    }

    async function reindexKnowledge() {
        if (!confirm('Re-index all knowledge files? This will rebuild the vector database.')) {
            return;
        }
        
        reindexBtn.disabled = true;
        reindexBtn.textContent = 'Re-indexing...';
        
        try {
            const response = await fetch('/api/knowledge/reindex', { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                alert(`Re-indexed ${data.chunks} chunks from ${data.files} files!`);
                loadKnowledgeInfo();
            } else {
                throw new Error(data.error || 'Failed');
            }
        } catch (e) {
            alert('Re-index failed: ' + e.message);
        } finally {
            reindexBtn.disabled = false;
            reindexBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10"></polyline>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
            </svg> Re-index Files`;
        }
    }

    function clearHistory() {
        if (!confirm('Clear all conversation history? This cannot be undone.')) {
            return;
        }
        
        localStorage.removeItem('raphael_chats');
        alert('Chat history cleared! Refresh the page to start fresh.');
    }

    async function loadVoice() {
        const savedVoice = localStorage.getItem(VOICE_KEY);
        if (savedVoice && voiceSelect) {
            voiceSelect.value = savedVoice;
        }
        try {
            const response = await fetch('/api/settings/voices');
            const data = await response.json();
            if (data.current && voiceSelect) {
                voiceSelect.value = data.current;
            }
        } catch (e) {
            console.error('Failed to load voices:', e);
        }
    }

    voiceSelect?.addEventListener('change', async () => {
        const voice = voiceSelect.value;
        localStorage.setItem(VOICE_KEY, voice);
        try {
            await fetch('/api/settings/voice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ voice })
            });
        } catch (e) {
            console.error('Failed to save voice:', e);
        }
    });

    viewBrainBtn?.addEventListener('click', viewBrain);
    exportBrainBtn?.addEventListener('click', exportBrain);
    viewRemindersBtn?.addEventListener('click', viewReminders);
    reindexBtn?.addEventListener('click', reindexKnowledge);
    clearHistoryBtn?.addEventListener('click', clearHistory);

    loadTheme();
    loadVoice();

    settingsBtn?.addEventListener('click', openSettings);
    settingsClose?.addEventListener('click', closeSettings);
    settingsOverlay?.addEventListener('click', (e) => {
        if (e.target === settingsOverlay) {
            closeSettings();
        }
    });
    themeToggle?.addEventListener('click', toggleTheme);
    saveAboutBtn?.addEventListener('click', saveProfile);

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && settingsOverlay?.classList.contains('active')) {
            closeSettings();
        }
    });
});
