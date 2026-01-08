class OrbController {
    constructor(orbElement) {
        this.orb = orbElement;
        this.particlesContainer = orbElement.querySelector('#orb-particles');
        this.state = 'idle';
        this.createParticles();
    }

    createParticles() {
        const particleCount = 6;
        for (let i = 0; i < particleCount; i++) {
            const particle = document.createElement('div');
            particle.className = 'particle';
            particle.style.animationDelay = `${(i / particleCount) * 4}s`;
            particle.style.animationDuration = `${3 + Math.random() * 2}s`;
            this.particlesContainer.appendChild(particle);
        }
    }

    setState(state) {
        this.orb.classList.remove('idle', 'speaking', 'thinking', 'listening', 'error');
        this.state = state;
        if (state !== 'idle') {
            this.orb.classList.add(state);
        }
    }

    setIdle() {
        this.setState('idle');
    }

    setSpeaking() {
        this.setState('speaking');
    }

    setThinking() {
        this.setState('thinking');
    }

    setListening() {
        this.setState('listening');
    }

    setError() {
        this.setState('error');
    }

    pulse() {
        this.orb.classList.add('pulse');
        setTimeout(() => this.orb.classList.remove('pulse'), 300);
    }
}

window.OrbController = OrbController;
