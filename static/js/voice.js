let voiceRecognition = null;
let voiceModeKind = null;
let voiceRecognitionRestartTimer = null;

function isSpeechPlaybackActive() {
  return !!(window.speechSynthesis && window.speechSynthesis.speaking);
}

async function startVoiceSession(focus) {
  setVoiceStatus('Requesting microphone...');
  voiceTranscriptMessages = [];
  currentAssistantTranscriptEl = null;
  currentAssistantTranscript = '';

  try {
    voiceStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    setVoiceStatus('Mic denied');
    appendMessage('assistant', 'Could not access your microphone. Please allow mic access and try again, or use text mode.');
    return;
  }

  micMuted = false;
  updateMicButton();

  if (shouldUseOpenAIRealtimeVoice()) {
    await startOpenAIRealtimeVoice(focus);
    return;
  }

  await startGenericVoiceSession();
}

function shouldUseOpenAIRealtimeVoice() {
  if (typeof loadProviderSettings !== 'function') return false;
  const settings = loadProviderSettings();
  const baseUrl = (settings?.base_url || '').trim().replace(/\/+$/, '').toLowerCase();
  const apiKey = (settings?.api_key || '').trim();
  return baseUrl === 'https://api.openai.com/v1' && !!apiKey;
}

async function startOpenAIRealtimeVoice(focus) {
  voiceModeKind = 'realtime';
  setVoiceStatus('Connecting...');

  voicePc = new RTCPeerConnection();

  voiceAudioEl = document.createElement('audio');
  voiceAudioEl.autoplay = true;
  voicePc.ontrack = (e) => {
    voiceAudioEl.srcObject = e.streams[0];
  };

  voicePc.addTrack(voiceStream.getTracks()[0]);

  voiceDc = voicePc.createDataChannel('oai-events');
  voiceDc.addEventListener('open', onDataChannelOpen);
  voiceDc.addEventListener('message', onDataChannelMessage);

  voicePc.oniceconnectionstatechange = () => {
    if (voicePc.iceConnectionState === 'disconnected' || voicePc.iceConnectionState === 'failed') {
      setVoiceStatus('Disconnected');
    }
  };

  const offer = await voicePc.createOffer();
  await voicePc.setLocalDescription(offer);

  try {
    const sdpResp = await fetch(`/api/realtime/session?focus=${encodeURIComponent(focus)}`, {
      method: 'POST',
      body: offer.sdp,
      headers: { 'Content-Type': 'application/sdp' },
    });

    if (!sdpResp.ok) {
      const err = await readVoiceErrorResponse(sdpResp);
      setVoiceStatus('Connection failed');
      appendMessage('assistant', err);
      cleanupVoice();
      return;
    }

    const answerSdp = await sdpResp.text();
    await voicePc.setRemoteDescription({ type: 'answer', sdp: answerSdp });
  } catch (e) {
    setVoiceStatus('Connection error');
    appendMessage('assistant', `Connection error: ${e.message}`);
    cleanupVoice();
  }
}

async function startGenericVoiceSession() {
  voiceModeKind = 'generic';
  appendVoiceTranscriptBanner('Browser voice mode');
  setVoiceStatus('processing', 'Starting interview...');

  await streamInterviewStartForGenericVoice();

  const RecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!RecognitionCtor) {
    setVoiceStatus('muted', 'Voice input unsupported');
    appendMessage('assistant', 'This browser does not support speech recognition. Voice output can still speak replies, but microphone transcription needs Chrome or another Web Speech compatible browser.');
    return;
  }

  voiceRecognition = new RecognitionCtor();
  voiceRecognition.lang = 'en-US';
  voiceRecognition.interimResults = false;
  voiceRecognition.continuous = false;

  voiceRecognition.onstart = () => {
    if (!micMuted) {
      setVoiceStatus('listening', 'Listening...');
    }
  };

  voiceRecognition.onresult = async (event) => {
    const transcript = Array.from(event.results)
      .slice(event.resultIndex)
      .map((result) => result[0]?.transcript || '')
      .join(' ')
      .trim();
    if (!transcript) {
      queueVoiceRecognitionRestart();
      return;
    }
    await sendGenericVoiceMessage(transcript);
  };

  voiceRecognition.onerror = (event) => {
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
      setVoiceStatus('muted', 'Mic blocked');
      appendMessage('assistant', 'Browser speech recognition is blocked. Allow microphone and speech access, then try voice mode again.');
      return;
    }
    if (event.error !== 'aborted') {
      setVoiceStatus('processing', 'Voice recognition error');
    }
  };

  voiceRecognition.onend = () => {
    if (voiceModeKind === 'generic' && !micMuted && !isStreaming && !isSpeechPlaybackActive()) {
      queueVoiceRecognitionRestart();
    }
  };

  queueVoiceRecognitionRestart(150);
}

function appendVoiceTranscriptBanner(label) {
  const container = document.getElementById('chat-messages');
  if (!container || container.querySelector('.transcript-banner')) return;
  const banner = document.createElement('div');
  banner.className = 'transcript-banner';
  banner.textContent = label;
  container.appendChild(banner);
}

function queueVoiceRecognitionRestart(delay = 350) {
  if (voiceModeKind !== 'generic' || micMuted || !voiceRecognition) return;
  clearTimeout(voiceRecognitionRestartTimer);
  voiceRecognitionRestartTimer = setTimeout(() => {
    try {
      voiceRecognition.start();
    } catch (e) {}
  }, delay);
}

async function streamInterviewStartForGenericVoice() {
  isStreaming = true;
  const msgEl = appendStreamingMessage();
  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/start`, { method: 'POST' });
    if (!res.ok) {
      updateStreamingMessage(msgEl, `Error: Server error ${res.status}`);
      return;
    }

    const fullContent = await readSSEStream(res, {
      onContent: (full) => updateStreamingMessage(msgEl, full),
      onError: (err) => updateStreamingMessage(msgEl, `Error: ${err}`),
    });
    finalizeStreamingMessage(msgEl, fullContent);
    if (fullContent) {
      speakVoiceText(fullContent);
    }
  } catch (e) {
    updateStreamingMessage(msgEl, `Connection error: ${e.message}`);
  } finally {
    isStreaming = false;
    if (!micMuted) {
      queueVoiceRecognitionRestart();
    }
  }
}

async function sendGenericVoiceMessage(text, extra = {}, options = {}) {
  if (isStreaming || !currentSessionId) return;

  const displayText = options.displayText || text;
  const transcriptText = options.transcriptText || text;

  appendMessage('user', displayText);
  voiceTranscriptMessages.push({ role: 'user', content: transcriptText });
  saveTranscriptToServer();

  isStreaming = true;
  const msgEl = appendStreamingMessage();
  setVoiceStatus('processing', 'Processing...');

  try {
    const payload = { message: text, language: currentLanguage, ...extra };
    const res = await fetch(`/api/sessions/${currentSessionId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      updateStreamingMessage(msgEl, `Error: Server error ${res.status}`);
      return;
    }

    const fullContent = await readSSEStream(res, {
      onContent: (full) => updateStreamingMessage(msgEl, full),
      onTestResults: (results) => renderTestResults(results, msgEl),
      onError: (err) => updateStreamingMessage(msgEl, `Error: ${err}`),
    });

    finalizeStreamingMessage(msgEl, fullContent);
    if (fullContent.trim()) {
      voiceTranscriptMessages.push({ role: 'assistant', content: fullContent.trim() });
      saveTranscriptToServer();
      speakVoiceText(fullContent);
    }
  } catch (e) {
    updateStreamingMessage(msgEl, `Connection error: ${e.message}`);
  } finally {
    isStreaming = false;
    if (!micMuted && !isSpeechPlaybackActive()) {
      queueVoiceRecognitionRestart();
    }
  }
}

function speakVoiceText(text) {
  const synth = window.speechSynthesis;
  if (!synth || !text.trim()) {
    if (!micMuted) queueVoiceRecognitionRestart();
    return;
  }

  const speakable = stripSpeechMarkup(text);
  if (!speakable) {
    if (!micMuted) queueVoiceRecognitionRestart();
    return;
  }

  synth.cancel();
  const utterance = new SpeechSynthesisUtterance(speakable);
  utterance.rate = 1;
  utterance.pitch = 1;
  utterance.onstart = () => setVoiceStatus('speaking', 'Interviewer speaking...');
  utterance.onend = () => {
    if (!micMuted) queueVoiceRecognitionRestart(200);
  };
  utterance.onerror = () => {
    if (!micMuted) queueVoiceRecognitionRestart(200);
  };
  synth.speak(utterance);
}

function stripSpeechMarkup(text) {
  return String(text || '')
    .replace(/```[\s\S]*?```/g, ' code block omitted ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[CODE\]/g, 'code')
    .replace(/[#>*_\-\[\]\(\)]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

async function readVoiceErrorResponse(response) {
  try {
    const payload = await response.json();
    if (payload?.error && payload?.details?.error?.message) {
      return `Voice mode failed: ${payload.details.error.message}`;
    }
    if (payload?.error) {
      return `Voice mode failed: ${payload.error}`;
    }
  } catch (e) {}

  try {
    const raw = await response.text();
    return `Voice mode failed: ${raw}`;
  } catch (e) {
    return `Voice mode failed with server error ${response.status}.`;
  }
}

function onDataChannelOpen() {
  setVoiceStatus('listening', 'Connected');

  const banner = document.createElement('div');
  banner.className = 'transcript-banner';
  banner.textContent = 'Live transcript — voice mode';
  document.getElementById('chat-messages').appendChild(banner);

  const kickoff = "Hi, I'm ready for the interview. Let's get started.";
  appendMessage('user', kickoff);

  const event = {
    type: 'conversation.item.create',
    item: {
      type: 'message',
      role: 'user',
      content: [{
        type: 'input_text',
        text: kickoff
      }]
    }
  };
  voiceDc.send(JSON.stringify(event));
  voiceDc.send(JSON.stringify({ type: 'response.create' }));
}

function onDataChannelMessage(e) {
  let event;
  try {
    event = JSON.parse(e.data);
  } catch {
    return;
  }

  if (!['response.output_audio.delta', 'response.audio.delta', 'input_audio_buffer.append'].includes(event.type)) {
    console.log('[realtime]', event.type, event);
  }

  switch (event.type) {
    case 'response.output_audio_transcript.delta':
    case 'response.audio_transcript.delta':
      handleAssistantTranscriptDelta(event.delta);
      setVoiceStatus('speaking', 'Interviewer speaking...');
      break;

    case 'response.output_audio_transcript.done':
    case 'response.audio_transcript.done':
      finalizeAssistantTranscript(event.transcript);
      break;

    case 'response.output_text.delta':
    case 'response.text.delta':
      handleAssistantTranscriptDelta(event.delta);
      setVoiceStatus('speaking', 'Interviewer speaking...');
      break;

    case 'response.output_text.done':
    case 'response.text.done':
      finalizeAssistantTranscript(event.text);
      break;

    case 'response.done':
      if (currentAssistantTranscriptEl && event.response?.output) {
        for (const item of event.response.output) {
          if (item.content) {
            for (const part of item.content) {
              if (part.transcript) {
                finalizeAssistantTranscript(part.transcript);
              } else if (part.text) {
                finalizeAssistantTranscript(part.text);
              }
            }
          }
        }
      }
      if (currentAssistantTranscriptEl) {
        finalizeAssistantTranscript(currentAssistantTranscript);
      }
      setVoiceStatus('listening', 'Listening...');
      break;

    case 'conversation.item.input_audio_transcription.completed':
      if (event.transcript && event.transcript.trim()) {
        appendMessage('user', event.transcript.trim());
        voiceTranscriptMessages.push({ role: 'user', content: event.transcript.trim() });
        saveTranscriptToServer();
      }
      break;

    case 'conversation.item.input_audio_transcription.delta':
      break;

    case 'input_audio_buffer.speech_started':
      setVoiceStatus('listening', 'Listening...');
      break;

    case 'input_audio_buffer.speech_stopped':
      setVoiceStatus('listening', 'Processing...');
      break;

    case 'error':
      console.error('Realtime error:', event.error);
      appendMessage('assistant', `Error: ${event.error?.message || JSON.stringify(event.error)}`);
      break;
  }
}

function handleAssistantTranscriptDelta(delta) {
  if (!currentAssistantTranscriptEl) {
    currentAssistantTranscriptEl = appendStreamingMessage();
    currentAssistantTranscript = '';
  }
  currentAssistantTranscript += delta;
  updateStreamingMessage(currentAssistantTranscriptEl, currentAssistantTranscript);
}

function finalizeAssistantTranscript(fullTranscript) {
  const text = fullTranscript || currentAssistantTranscript;
  if (currentAssistantTranscriptEl) {
    finalizeStreamingMessage(currentAssistantTranscriptEl, text);
  }
  if (text.trim()) {
    voiceTranscriptMessages.push({ role: 'assistant', content: text.trim() });
    saveTranscriptToServer();
  }
  currentAssistantTranscriptEl = null;
  currentAssistantTranscript = '';
}

async function saveTranscriptToServer() {
  if (!currentSessionId || voiceTranscriptMessages.length === 0) return;
  const toSave = [...voiceTranscriptMessages];
  voiceTranscriptMessages = [];
  try {
    await fetch(`/api/sessions/${currentSessionId}/transcript`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: toSave }),
    });
  } catch (e) {
    voiceTranscriptMessages = toSave.concat(voiceTranscriptMessages);
  }
}

function submitCodeVoice() {
  const code = editor.getValue().trim();
  if (!code || code === '# Write your solution here') {
    alert('Write some code in the editor first.');
    return;
  }

  const displayText = `Here's my solution:\n\n\`\`\`${currentLanguage}\n${code}\n\`\`\``;

  if (voiceModeKind === 'realtime') {
    appendMessage('user', displayText);
    if (!voiceDc || voiceDc.readyState !== 'open') {
      alert('Voice session not connected.');
      return;
    }

    const event = {
      type: 'conversation.item.create',
      item: {
        type: 'message',
        role: 'user',
        content: [{
          type: 'input_text',
          text: `Here's my code solution:\n\n${code}\n\nPlease review it.`
        }]
      }
    };
    voiceDc.send(JSON.stringify(event));
    voiceDc.send(JSON.stringify({ type: 'response.create' }));

    voiceTranscriptMessages.push({
      role: 'user',
      content: `[CODE]\n${code}`
    });
    saveTranscriptToServer();
    return;
  }

  sendGenericVoiceMessage(
    "Here's my code solution. Please review it.",
    {
      code,
      language: currentLanguage,
    },
    {
      displayText,
      transcriptText: `[CODE]\n${code}`,
    }
  );
}

function toggleMic() {
  if (!voiceStream && voiceModeKind !== 'generic') return;
  micMuted = !micMuted;
  if (voiceModeKind === 'realtime' && voiceStream) {
    voiceStream.getTracks().forEach(t => { t.enabled = !micMuted; });
  } else if (voiceModeKind === 'generic') {
    clearTimeout(voiceRecognitionRestartTimer);
    if (micMuted) {
      try { voiceRecognition?.stop(); } catch (e) {}
      window.speechSynthesis.cancel();
    } else {
      queueVoiceRecognitionRestart(150);
    }
  }
  updateMicButton();
  setVoiceStatus(
    micMuted ? 'muted' : 'listening',
    micMuted ? 'Muted' : 'Listening...'
  );
}

function updateMicButton() {
  const btn = document.getElementById('mic-btn');
  const label = document.getElementById('mic-label');
  if (micMuted) {
    btn.classList.add('muted');
    btn.classList.remove('active');
    if (label) label.textContent = 'Tap to unmute';
  } else {
    btn.classList.remove('muted');
    btn.classList.add('active');
    if (label) label.textContent = 'Tap to mute';
  }
}

function setVoiceStatus(stateOrText, text) {
  const el = document.getElementById('voice-status');
  if (text) {
    el.textContent = text;
    el.className = 'voice-status ' + stateOrText;
  } else {
    el.textContent = stateOrText;
    el.className = 'voice-status';
  }
}

function endVoiceSession() {
  saveTranscriptToServer();
  cleanupVoice();
  document.getElementById('text-input-area').style.display = '';
  document.getElementById('voice-controls').style.display = 'none';
  appendMessage('assistant', 'Voice session ended. You can continue the conversation by typing.');
}

function cleanupVoice() {
  clearTimeout(voiceRecognitionRestartTimer);
  voiceRecognitionRestartTimer = null;
  voiceModeKind = null;
  if (voiceRecognition) {
    voiceRecognition.onstart = null;
    voiceRecognition.onresult = null;
    voiceRecognition.onerror = null;
    voiceRecognition.onend = null;
    try { voiceRecognition.stop(); } catch {}
    voiceRecognition = null;
  }
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  if (voiceDc) {
    try { voiceDc.close(); } catch {}
    voiceDc = null;
  }
  if (voicePc) {
    try { voicePc.close(); } catch {}
    voicePc = null;
  }
  if (voiceStream) {
    voiceStream.getTracks().forEach(t => t.stop());
    voiceStream = null;
  }
  if (voiceAudioEl) {
    voiceAudioEl.srcObject = null;
    voiceAudioEl = null;
  }
  currentAssistantTranscriptEl = null;
  currentAssistantTranscript = '';
}
