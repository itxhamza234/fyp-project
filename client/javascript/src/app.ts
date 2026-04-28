/**
 * Copyright (c) 2024–2025, Daily
 *
 * SPDX-License-Identifier: BSD 2-Clause License
 */

import {
  Participant,
  PipecatClient,
  PipecatClientOptions,
  RTVIEvent,
} from '@pipecat-ai/client-js';
import {
  DailyEventCallbacks,
  DailyTransport,
} from '@pipecat-ai/daily-transport';
import SoundUtils from './util/soundUtils';

type VoiceState = 'idle' | 'listening' | 'speaking';

class InstantVoiceClient {
  private declare pcClient: PipecatClient;
  private connectBtn: HTMLButtonElement | null = null;
  private disconnectBtn: HTMLButtonElement | null = null;
  private statusSpan: HTMLElement | null = null;
  private statusDot: HTMLElement | null = null;
  private voiceStatus: HTMLElement | null = null;
  private avatar: HTMLElement | null = null;
  private chatContainer: HTMLElement | null = null;
  private botAudio: HTMLAudioElement;
  private declare startTime: number;

  constructor() {
    this.botAudio = document.getElementById('bot-audio') as HTMLAudioElement;
    if (!this.botAudio) {
      this.botAudio = document.createElement('audio');
      this.botAudio.id = 'bot-audio';
      this.botAudio.autoplay = true;
      document.body.appendChild(this.botAudio);
    }
    this.setupDOMElements();
    this.setupEventListeners();
    this.initializePipecatClient();
  }

  private setupDOMElements(): void {
    this.connectBtn = document.getElementById('connect-btn') as HTMLButtonElement;
    this.disconnectBtn = document.getElementById('disconnect-btn') as HTMLButtonElement;
    this.statusSpan = document.getElementById('connection-status');
    this.statusDot = document.getElementById('status-dot');
    this.voiceStatus = document.getElementById('voice-status');
    this.avatar = document.getElementById('avatar');
    this.chatContainer = document.getElementById('chat-container');
  }

  private setupEventListeners(): void {
    this.connectBtn?.addEventListener('click', () => this.connect());
    this.disconnectBtn?.addEventListener('click', () => this.disconnect());
  }

  private setVoiceState(state: VoiceState): void {
    if (!this.avatar || !this.voiceStatus) return;

    // Update avatar classes
    this.avatar.classList.remove('idle', 'listening', 'speaking');
    this.avatar.classList.add(state);

    // Update status text
    const statusText = {
      idle: 'Ready',
      listening: 'Listening...',
      speaking: 'Speaking...'
    };
    this.voiceStatus.textContent = statusText[state];
  }

  private async addMessage(role: 'user' | 'bot', text: string): Promise<void> {
    if (!this.chatContainer) return;

    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', role);

    if (role === 'bot') {
      const contentSpan = document.createElement('span');
      const cursor = document.createElement('span');
      cursor.classList.add('typing-cursor');
      messageDiv.appendChild(contentSpan);
      messageDiv.appendChild(cursor);
      this.chatContainer.appendChild(messageDiv);
      this.scrollToBottom();

      await this.typewriter(contentSpan, text);
      cursor.remove();
    } else {
      messageDiv.textContent = text;
      this.chatContainer.appendChild(messageDiv);
      this.scrollToBottom();
    }
  }

  private typewriter(element: HTMLElement, text: string): Promise<void> {
    return new Promise((resolve) => {
      let i = 0;
      const interval = setInterval(() => {
        element.textContent += text[i];
        i++;
        this.scrollToBottom();
        if (i === text.length) {
          clearInterval(interval);
          resolve();
        }
      }, 30); // Adjust speed here
    });
  }

  private scrollToBottom(): void {
    if (this.chatContainer) {
      this.chatContainer.parentElement?.scrollTo({
        top: this.chatContainer.parentElement.scrollHeight,
        behavior: 'smooth'
      });
    }
  }

  private initializePipecatClient(): void {
    const PipecatConfig: PipecatClientOptions = {
      transport: new DailyTransport({
        bufferLocalAudioUntilBotReady: true,
      }),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onConnected: () => {
          this.updateStatus('Connected');
          this.statusDot?.classList.add('connected');
          if (this.connectBtn) this.connectBtn.disabled = true;
          if (this.disconnectBtn) this.disconnectBtn.disabled = false;
        },
        onDisconnected: () => {
          this.updateStatus('Disconnected');
          this.statusDot?.classList.remove('connected');
          this.setVoiceState('idle');
          if (this.connectBtn) this.connectBtn.disabled = false;
          if (this.disconnectBtn) this.disconnectBtn.disabled = true;
          console.warn('Pipecat Client: Disconnected from session');
        },
        onBotConnected: (participant: Participant) => {
          console.log(`onBotConnected, timeTaken: ${Date.now() - this.startTime}`);
        },
        onBotReady: (data) => {
          console.log(`onBotReady, timeTaken: ${Date.now() - this.startTime}`);
          this.setupMediaTracks();
        },
        onUserTranscript: (data) => {
          if (data.final) {
            this.addMessage('user', data.text);
          }
        },
        onBotTranscript: (data) => {
          this.setVoiceState('speaking');
          this.addMessage('bot', data.text).then(() => {
            // After bot finishes speaking/typing, if it's not still buffering, set back to idle
            // Note: This is a simplification; actual state might be better tracked via audio events
            setTimeout(() => this.setVoiceState('idle'), 500);
          });
        },
        onMessageError: (error) => console.error('Pipecat Client: Message error:', error),
        onError: (error) => console.error('Pipecat Client: Error:', error),
        onTransportStateChanged: (state) => {
          console.log(`Pipecat Client: Transport state changed to ${state}`);
          if (state === 'error') {
            console.error('Pipecat Client: Transport failed!');
          }
        },
        onAudioBufferingStarted: () => {
          SoundUtils.beep();
          this.setVoiceState('listening');
        },
        onAudioBufferingStopped: () => {
          this.setVoiceState('idle');
        },
      } as DailyEventCallbacks,
    };

    this.pcClient = new PipecatClient(PipecatConfig);
    this.setupTrackListeners();
  }

  private updateStatus(status: string): void {
    if (this.statusSpan) {
      this.statusSpan.textContent = status;
    }
  }

  setupMediaTracks() {
    if (!this.pcClient) return;
    const tracks = this.pcClient.tracks();
    if (tracks.bot?.audio) {
      this.setupAudioTrack(tracks.bot.audio);
    }
  }

  setupTrackListeners() {
    if (!this.pcClient) return;

    this.pcClient.on(RTVIEvent.TrackStarted, (track, participant) => {
      if (!participant?.local && track.kind === 'audio') {
        this.setupAudioTrack(track);
      }
    });

    this.pcClient.on(RTVIEvent.TrackStopped, (track, participant) => {
      console.log(`Track stopped: ${track.kind} from ${participant?.name || 'unknown'}`);
    });
  }

  private setupAudioTrack(track: MediaStreamTrack): void {
    if (this.botAudio.srcObject && 'getAudioTracks' in this.botAudio.srcObject) {
      const oldTrack = this.botAudio.srcObject.getAudioTracks()[0];
      if (oldTrack?.id === track.id) return;
    }
    this.botAudio.srcObject = new MediaStream([track]);
  }

  public async connect(): Promise<void> {
    try {
      this.startTime = Date.now();
      const apiInput = document.getElementById("chatbot-id-input") as HTMLInputElement;

      if (!apiInput || !apiInput.value.trim()) {
        alert("Please enter Chatbot ID");
        return;
      }

      const chatbotId = apiInput.value.trim();
      const sessionId = "session_" + Date.now();

      console.log('Pipecat Client: Connecting to bot...');
      const response = await this.pcClient.startBotAndConnect({
        endpoint: '/connect',
        requestData: {
          chatbot_id: chatbotId,
          session_id: sessionId,
        },
      });
      console.log('Pipecat Client: Connection response:', response);

    } catch (error) {
      const errorMessage = (error as Error).message || 'Unknown error';
      console.error(`Error connecting: ${errorMessage}`);
      this.updateStatus(`Error: ${errorMessage}`);
      alert(`Connection Failed: ${errorMessage}`);

      if (this.pcClient) {
        try {
          await this.pcClient.disconnect();
        } catch (disconnectError) {
          console.error(`Error during disconnect: ${disconnectError}`);
        }
      }
    }
  }

  public async disconnect(): Promise<void> {
    try {
      await this.pcClient.disconnect();
      if (this.botAudio.srcObject && 'getAudioTracks' in this.botAudio.srcObject) {
        this.botAudio.srcObject.getAudioTracks().forEach((track) => track.stop());
        this.botAudio.srcObject = null;
      }
    } catch (error) {
      console.error(`Error disconnecting: ${(error as Error).message}`);
    }
  }
}

declare global {
  interface Window {
    InstantVoiceClient: typeof InstantVoiceClient;
  }
}

window.addEventListener('DOMContentLoaded', () => {
  window.InstantVoiceClient = InstantVoiceClient;
  new InstantVoiceClient();

  // Global error handler for easier debugging
  window.onerror = function (message, source, lineno, colno, error) {
    console.error('Global Error:', message, 'at', source, ':', lineno, ':', colno);
    return false;
  };
});
