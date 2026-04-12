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
    return;
  }

  micMuted = false;
  updateMicButton();
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
  if (!voiceDc || voiceDc.readyState !== 'open') {
    alert('Voice session not connected.');
    return;
  }

  const code = editor.getValue().trim();
  if (!code || code === '# Write your solution here') {
    alert('Write some code in the editor first.');
    return;
  }

  const displayText = "Here's my solution:\n\n```python\n" + code + '\n```';
  appendMessage('user', displayText);

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
}

function toggleMic() {
  if (!voiceStream) return;
  micMuted = !micMuted;
  voiceStream.getTracks().forEach(t => { t.enabled = !micMuted; });
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
