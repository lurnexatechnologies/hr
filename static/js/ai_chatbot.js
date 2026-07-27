document.addEventListener('DOMContentLoaded', function () {
    // Inject Custom Styles for Chatbot UI
    const styleElem = document.createElement('style');
    styleElem.innerHTML = `
        @keyframes aiPulse {
            0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(79, 70, 229, 0.5); }
            70% { transform: scale(1.05); box-shadow: 0 0 0 14px rgba(79, 70, 229, 0); }
            100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(79, 70, 229, 0); }
        }
        @keyframes fadeInSlide {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .ai-chat-card {
            box-shadow: 0 20px 40px rgba(15, 23, 42, 0.2), 0 1px 3px rgba(0, 0, 0, 0.08) !important;
            border: 1px solid rgba(226, 232, 240, 0.8) !important;
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
            animation: fadeInSlide 0.25s ease-out forwards;
        }
        .ai-toggle-pulse {
            animation: aiPulse 3s infinite;
        }
        .ai-toggle-btn:hover {
            transform: scale(1.06) !important;
        }
        #ai-chat-messages::-webkit-scrollbar {
            width: 4px;
        }
        #ai-chat-messages::-webkit-scrollbar-track {
            background: transparent;
        }
        #ai-chat-messages::-webkit-scrollbar-thumb {
            background: #cbd5e1;
            border-radius: 4px;
        }
        #ai-chat-messages::-webkit-scrollbar-thumb:hover {
            background: #94a3b8;
        }
        .ai-quick-chip {
            background: #ffffff;
            border: 1px solid #cbd5e1;
            color: #334155;
            font-size: 0.72rem;
            font-weight: 600;
            padding: 5px 12px;
            border-radius: 16px;
            cursor: pointer;
            transition: all 0.2s ease;
            white-space: nowrap;
            box-shadow: 0 1px 2px rgba(0,0,0,0.03);
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }
        .ai-quick-chip:hover {
            background: #4f46e5;
            color: #ffffff !important;
            border-color: #4f46e5;
            transform: translateY(-1px);
            box-shadow: 0 4px 10px rgba(79, 70, 229, 0.3);
        }
        .ai-msg-bubble {
            animation: fadeInSlide 0.2s ease-out forwards;
            line-height: 1.45;
        }
    `;
    document.head.appendChild(styleElem);

    // Inject Chatbot Widget HTML into page
    const widgetHtml = `
    <div id="ai-chatbot-container" style="position: fixed; bottom: 20px; right: 20px; z-index: 99999; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
        <!-- Toggle Button -->
        <button id="ai-chat-toggle-btn" class="ai-toggle-btn ai-toggle-pulse btn rounded-circle d-flex align-items-center justify-content-center shadow-lg position-relative" 
            style="width: 58px; height: 58px; background: linear-gradient(135deg, #6366f1 0%, #4f46e5 50%, #4338ca 100%); border: 2px solid rgba(255,255,255,0.4); transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);" title="Open Lurnexa AI HR Assistant">
            <i class="fa-solid fa-headset text-white fs-4" id="ai-chat-icon"></i>
            <span class="position-absolute rounded-circle" style="width: 14px; height: 14px; top: 2px; right: 2px; background-color: #10b981 !important; border: 2px solid #ffffff; box-shadow: 0 0 10px #10b981; z-index: 10;"></span>
        </button>

        <!-- Chat Panel -->
        <div id="ai-chat-panel" class="card border-0 rounded-4 d-none ai-chat-card overflow-hidden" 
            style="position: absolute; bottom: 72px; right: 0; width: 370px; max-width: calc(100vw - 32px); height: 540px; background: #ffffff;">
            
            <!-- Header -->
            <div class="card-header border-0 text-white px-3 py-2.5 d-flex align-items-center justify-content-between" 
                style="background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);">
                <div class="d-flex align-items-center gap-2" style="min-width: 0;">
                    <div class="position-relative flex-shrink-0">
                        <div class="rounded-circle d-flex align-items-center justify-content-center" style="width: 38px; height: 38px; background: rgba(255, 255, 255, 0.25); border: 1px solid rgba(255, 255, 255, 0.4);">
                            <i class="fa-solid fa-headset text-white fs-5"></i>
                        </div>
                        <span class="position-absolute bottom-0 end-0 rounded-circle" style="width: 11px; height: 11px; background-color: #10b981 !important; border: 2px solid #ffffff; box-shadow: 0 0 8px #10b981;"></span>
                    </div>
                    <div style="min-width: 0;">
                        <div class="d-flex align-items-center gap-1.5">
                            <h6 class="mb-0 fw-bold text-white text-truncate" style="font-size: 0.88rem;">Lurnexa AI Assistant</h6>
                            <span class="badge bg-warning text-dark font-mono px-1.5 py-0.5" style="font-size: 0.6rem; font-weight: 800; border-radius: 4px;">PRO</span>
                        </div>
                        <div class="text-white-50 text-truncate d-flex align-items-center gap-1" style="font-size: 0.72rem; margin-top: 1px;">
                            <span class="d-inline-block rounded-circle bg-success" style="width: 7px; height: 7px; box-shadow: 0 0 8px #22c55e;"></span>
                            <span class="fw-medium text-white">Live</span> &bull; Dynamic HR Engine
                        </div>
                    </div>
                </div>
                <div class="d-flex align-items-center gap-1.5 flex-shrink-0 ms-2">
                    <!-- Language Selector Dropdown -->
                    <select id="ai-lang-select" class="form-select form-select-sm border-0 text-dark bg-white rounded-3 font-medium" 
                        style="font-size: 0.72rem; width: 98px; padding: 3px 6px; cursor: pointer; box-shadow: none;">
                        <option value="en-US" selected>English</option>
                        <option value="te-IN">తెలుగు (Telugu)</option>
                        <option value="hi-IN">हिंदी (Hindi)</option>
                        <option value="ta-IN">தமிழ் (Tamil)</option>
                        <option value="kn-IN">కన్నడ (Kannada)</option>
                        <option value="es-ES">Español</option>
                    </select>
                    <button id="ai-voice-toggle-btn" class="btn btn-link text-white p-1 border-0 shadow-none ms-1" title="Mute/Unmute AI Voice Response">
                        <i class="fa-solid fa-volume-high fs-6" id="ai-voice-icon"></i>
                    </button>
                    <button id="ai-chat-close-btn" class="btn btn-link text-white-50 text-hover-white p-1 border-0 shadow-none">
                        <i class="fa-solid fa-xmark fs-5"></i>
                    </button>
                </div>
            </div>

            <!-- Messages Area -->
            <div id="ai-chat-messages" class="card-body p-3 d-flex flex-column gap-2.5" style="height: 395px; overflow-y: auto; background-color: #f8fafc;">
                <!-- Welcome Card -->
                <div class="ai-msg-bubble d-flex align-items-start gap-2">
                    <div class="position-relative flex-shrink-0">
                        <div class="bg-primary text-white rounded-circle p-1 d-flex align-items-center justify-content-center shadow-sm" style="width: 32px; height: 32px; background: #4f46e5 !important;">
                            <i class="fa-solid fa-headset fs-6"></i>
                        </div>
                        <span class="position-absolute bottom-0 end-0 bg-success border border-white rounded-circle" style="width: 8px; height: 8px; box-shadow: 0 0 6px #22c55e;"></span>
                    </div>
                    <div class="p-3 rounded-3 shadow-sm bg-white text-dark border" style="font-size: 0.82rem; border-color: #e2e8f0 !important; border-top-left-radius: 2px !important; color: #1e293b;">
                        <div class="fw-bold mb-1" style="color: #0f172a;">Hello! 👋 Welcome to Lurnexa AI.</div>
                        <div class="text-secondary" style="font-size: 0.8rem; line-height: 1.45;">How can I help you today? You can type or use voice commands in your preferred language.</div>
                    </div>
                </div>

                <!-- Quick Action Chips -->
                <div class="d-flex align-items-center gap-1.5 flex-wrap pt-1 px-0.5" id="ai-quick-actions">
                    <span class="ai-quick-chip" onclick="window.triggerQuickChat('I want to apply for leave')"><span>🏖️</span> Apply Leave</span>
                    <span class="ai-quick-chip" onclick="window.triggerQuickChat('What is my current leave balance?')"><span>📊</span> Leave Balance</span>
                    <span class="ai-quick-chip" onclick="window.triggerQuickChat('Check my attendance record today')"><span>⏰</span> Attendance</span>
                </div>
            </div>

            <!-- Speech Listening Indicator -->
            <div id="ai-speech-status" class="px-3 py-1.5 bg-danger bg-opacity-10 text-danger border-top d-none text-center fw-semibold" style="font-size: 0.73rem;">
                <i class="fa-solid fa-microphone fa-beat me-1.5"></i> Listening to voice... Speak now!
            </div>

            <!-- Footer / Input Bar -->
            <div class="card-footer border-0 px-2 py-2 bg-white border-top">
                <form id="ai-chat-form" class="d-flex align-items-center gap-1.5 m-0">
                    <button type="button" id="ai-mic-btn" class="btn btn-light rounded-circle border text-secondary d-flex align-items-center justify-content-center flex-shrink-0" 
                        style="width: 38px; height: 38px; background: #f1f5f9; border-color: #cbd5e1 !important;" title="Speak in selected language">
                        <i class="fa-solid fa-microphone fs-6" id="ai-mic-icon"></i>
                    </button>
                    <input type="text" id="ai-chat-input" class="form-control rounded-pill border px-3" 
                        placeholder="Type message or click mic..." style="font-size: 0.82rem; height: 38px; background-color: #f8fafc; border-color: #cbd5e1;" autocomplete="off">
                    <button type="submit" id="ai-send-btn" class="btn btn-primary rounded-circle d-flex align-items-center justify-content-center text-white flex-shrink-0 shadow-sm" 
                        style="width: 38px; height: 38px; background: #4f46e5; border: none;">
                        <i class="fa-solid fa-paper-plane fs-6"></i>
                    </button>
                </form>
            </div>
        </div>
    </div>
    `;

    document.body.insertAdjacentHTML('beforeend', widgetHtml);

    // DOM Elements
    const toggleBtn = document.getElementById('ai-chat-toggle-btn');
    const toggleIcon = document.getElementById('ai-chat-icon');
    const closeBtn = document.getElementById('ai-chat-close-btn');
    const chatPanel = document.getElementById('ai-chat-panel');
    const chatMessages = document.getElementById('ai-chat-messages');
    const chatForm = document.getElementById('ai-chat-form');
    const chatInput = document.getElementById('ai-chat-input');
    const micBtn = document.getElementById('ai-mic-btn');
    const micIcon = document.getElementById('ai-mic-icon');
    const langSelect = document.getElementById('ai-lang-select');
    const speechStatus = document.getElementById('ai-speech-status');

    let conversationHistory = [];
    let isListening = false;
    let recognition = null;

    // Global helper for quick actions
    window.triggerQuickChat = function (queryText) {
        if (!queryText) return;
        chatInput.value = queryText;
        submitMessage(queryText);
    };

    // Toggle Chat Widget Window
    toggleBtn.addEventListener('click', function () {
        chatPanel.classList.toggle('d-none');
        if (!chatPanel.classList.contains('d-none')) {
            chatInput.focus();
            toggleIcon.classList.replace('fa-headset', 'fa-chevron-down');
        } else {
            toggleIcon.classList.replace('fa-chevron-down', 'fa-headset');
        }
    });

    closeBtn.addEventListener('click', function () {
        chatPanel.classList.add('d-none');
        toggleIcon.classList.replace('fa-chevron-down', 'fa-headset');
    });

    // Voice Mute Toggle
    const voiceToggleBtn = document.getElementById('ai-voice-toggle-btn');
    const voiceIcon = document.getElementById('ai-voice-icon');
    let isVoiceMuted = false;

    if (voiceToggleBtn) {
        voiceToggleBtn.addEventListener('click', function() {
            isVoiceMuted = !isVoiceMuted;
            if (isVoiceMuted) {
                voiceIcon.className = 'fa-solid fa-volume-xmark fs-6 text-white-50';
                if ('speechSynthesis' in window) window.speechSynthesis.cancel();
            } else {
                voiceIcon.className = 'fa-solid fa-volume-high fs-6 text-white';
            }
        });
    }

    // Initialize Web Speech API for Multi-lingual STT
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;

        recognition.onstart = function () {
            isListening = true;
            speechStatus.classList.remove('d-none');
            micBtn.classList.replace('btn-light', 'btn-danger');
            micBtn.classList.add('text-white');
            micIcon.classList.replace('fa-microphone', 'fa-microphone-lines');
        };

        recognition.onresult = function (event) {
            const transcript = event.results[0][0].transcript;
            if (transcript && transcript.trim()) {
                chatInput.value = transcript;
                submitMessage(transcript);
            }
        };

        recognition.onerror = function (event) {
            console.warn("Speech Recognition Error:", event.error);
            stopListening();
            if (event.error === 'not-allowed') {
                alert("Microphone permission was denied. Please allow microphone permissions in your browser address bar.");
            }
        };

        recognition.onend = function () {
            stopListening();
        };
    } else {
        micBtn.disabled = true;
        micBtn.title = "Voice recognition is not supported in this browser.";
    }

    function stopListening() {
        isListening = false;
        speechStatus.classList.add('d-none');
        micBtn.classList.replace('btn-danger', 'btn-light');
        micBtn.classList.remove('text-white');
        micIcon.classList.replace('fa-microphone-lines', 'fa-microphone');
    }

    micBtn.addEventListener('click', function () {
        if (!recognition) {
            alert("Voice input is not supported in your browser. Please use Chrome or Edge.");
            return;
        }
        if (isListening) {
            recognition.stop();
        } else {
            try {
                recognition.lang = langSelect.value || 'en-US';
                recognition.start();
            } catch (ex) {
                console.warn("Recognition start error:", ex);
            }
        }
    });

    // Speak AI Response using Text-to-Speech (TTS)
    function speakText(text) {
        if (!('speechSynthesis' in window) || isVoiceMuted || !text) return;
        try {
            window.speechSynthesis.cancel(); // cancel any active speech
            
            // Strip HTML, markdown formatting, widget tags before speaking
            let cleanText = text
                .replace(/\[LEAVE_FORM_WIDGET\]/g, '')
                .replace(/\*\*(.*?)\*\*/g, '$1')
                .replace(/`([^`]+)`/g, '$1')
                .replace(/[-*•]/g, '')
                .replace(/<[^>]*>/g, '')
                .trim();

            if (!cleanText) return;

            const utterance = new SpeechSynthesisUtterance(cleanText);
            utterance.lang = langSelect.value || 'en-US';
            utterance.rate = 1.0;
            
            // Match voice language if available
            const voices = window.speechSynthesis.getVoices();
            if (voices && voices.length > 0) {
                const targetLangPrefix = (langSelect.value || 'en').split('-')[0];
                const matchingVoice = voices.find(v => v.lang && v.lang.startsWith(targetLangPrefix));
                if (matchingVoice) {
                    utterance.voice = matchingVoice;
                }
            }

            window.speechSynthesis.speak(utterance);
        } catch (ex) {
            console.warn("TTS speak error:", ex);
        }
    }

    // Handle Interactive Leave Form Submission inside Chat
    window.submitChatLeaveForm = function(btn) {
        const card = btn.closest('.ai-leave-form-card');
        if (!card) return;
        
        const leaveType = card.querySelector('#chat-leave-type').value;
        const startDate = card.querySelector('#chat-start-date').value;
        const endDate = card.querySelector('#chat-end-date').value || startDate;
        const reason = card.querySelector('#chat-leave-reason').value.trim();

        if (!startDate || !endDate) {
            alert('Please select valid Start Date and End Date.');
            return;
        }
        if (!reason) {
            alert('Please enter a reason for your leave request.');
            card.querySelector('#chat-leave-reason').focus();
            return;
        }

        const formattedMsg = `Apply leave: Leave Type: ${leaveType}, Start Date: ${startDate}, End Date: ${endDate}, Reason: ${reason}`;
        window.triggerQuickChat(formattedMsg);
    };

    function renderLeaveFormWidget() {
        const todayStr = new Date().toISOString().split('T')[0];
        return `
            <div class="ai-leave-form-card p-3 bg-white rounded-3 border shadow-sm my-1 text-dark" style="font-size: 0.82rem; background: #ffffff !important; border-color: #cbd5e1 !important;">
                <div class="fw-bold mb-2 d-flex align-items-center gap-1.5" style="color: #4f46e5 !important;">
                    <i class="fa-solid fa-calendar-plus fs-6"></i> Apply for Leave Form
                </div>
                <div class="mb-2">
                    <label class="form-label text-secondary mb-1 fw-semibold" style="font-size: 0.73rem;">Leave Type *</label>
                    <select class="form-select form-select-sm rounded-2 border" id="chat-leave-type" style="font-size: 0.8rem; background-color: #ffffff;">
                        <option value="Casual Leave (CL)">Casual Leave (CL)</option>
                        <option value="Sick Leave (SL)">Sick Leave (SL)</option>
                        <option value="Earned Leave (EL)">Earned Leave (EL)</option>
                        <option value="Marriage Leave">Marriage Leave</option>
                        <option value="Maternity Leave">Maternity Leave</option>
                        <option value="Paternity Leave">Paternity Leave</option>
                        <option value="Unpaid Leave">Unpaid Leave</option>
                    </select>
                </div>
                <div class="row g-2 mb-2">
                    <div class="col-6">
                        <label class="form-label text-secondary mb-1 fw-semibold" style="font-size: 0.73rem;">Start Date *</label>
                        <input type="date" class="form-control form-control-sm rounded-2 border" id="chat-start-date" value="${todayStr}" style="font-size: 0.8rem; background-color: #ffffff;">
                    </div>
                    <div class="col-6">
                        <label class="form-label text-secondary mb-1 fw-semibold" style="font-size: 0.73rem;">End Date *</label>
                        <input type="date" class="form-control form-control-sm rounded-2 border" id="chat-end-date" value="${todayStr}" style="font-size: 0.8rem; background-color: #ffffff;">
                    </div>
                </div>
                <div class="form-check form-switch mb-2.5">
                    <input class="form-check-input" type="checkbox" id="chat-half-day" style="cursor:pointer;">
                    <label class="form-check-label text-secondary fw-semibold" for="chat-half-day" style="font-size: 0.73rem; cursor:pointer;">Half Day Request</label>
                </div>
                <div class="mb-2.5">
                    <label class="form-label text-secondary mb-1 fw-semibold" style="font-size: 0.73rem;">Reason *</label>
                    <textarea class="form-control form-control-sm rounded-2 border" id="chat-leave-reason" rows="2" placeholder="Please provide brief details about your leave request..." style="font-size: 0.8rem; background-color: #ffffff;"></textarea>
                </div>
                <button type="button" class="btn btn-sm btn-primary w-100 rounded-pill py-1.5 font-weight-bold shadow-sm" style="background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%) !important; border:none; font-size: 0.8rem;" onclick="window.submitChatLeaveForm(this)">
                    <i class="fa-solid fa-paper-plane me-1"></i> Review Summary & Apply
                </button>
            </div>
        `;
    }

    // Format AI Message HTML with Markdown & Clickable Options
    function formatAiMessage(text) {
        if (!text) return '';
        
        let showLeaveWidget = text.includes('[LEAVE_FORM_WIDGET]') || text.toLowerCase().includes('fill out the leave application') || text.toLowerCase().includes('provide the following details');
        let cleanTextStr = text.replace(/\[LEAVE_FORM_WIDGET\]/g, '');

        let lines = cleanTextStr.split('\n');
        let outputHtml = '';
        let chipsHtml = '';
        
        const validChipKeywords = [
            'casual leave', 'sick leave', 'earned leave', 'paid leave', 'marriage leave', 
            'maternity', 'paternity', 'unpaid leave', 'full day', 'half day',
            'yes', 'no', 'confirm', 'cancel', 'submit'
        ];

        for (let line of lines) {
            let trimmed = line.trim();
            let bulletMatch = trimmed.match(/^(?:[-*•]|\d+\.)\s+(.+)$/);
            
            if (bulletMatch) {
                let optionContent = bulletMatch[1];
                let cleanText = optionContent.replace(/\*\*/g, '').replace(/<[^>]*>/g, '').trim();
                let lowerText = cleanText.toLowerCase();

                const isInfoReportLine = lowerText.includes('available') || lowerText.includes('assigned') || lowerText.includes('days') || lowerText.includes('taken') || lowerText.includes('count') || lowerText.includes('balance') || lowerText.includes('status') || lowerText.includes('summary') || lowerText.includes('employee id') || lowerText.includes('employee:') || lowerText.includes('reason:') || lowerText.includes('amount:') || lowerText.includes('description:') || lowerText.includes('no assets') || lowerText.includes('no requests') || lowerText.includes('no record') || lowerText.includes('no pending') || lowerText.startsWith('no ');

                let isYesNoConfirm = (lowerText === 'yes' || lowerText === 'no' || lowerText.includes('yes,') || lowerText.includes('no,') || lowerText.includes('confirm') || lowerText.includes('submit') || lowerText.includes('cancel'));
                let isLeaveTypeOption = validChipKeywords.some(kw => lowerText.includes(kw)) && !lowerText.includes('yyyy') && !lowerText.includes('format') && !lowerText.includes('reason for') && !lowerText.includes('start date') && !lowerText.includes('end date');

                const isValidOption = (isYesNoConfirm || isLeaveTypeOption) && !isInfoReportLine;

                if (isValidOption) {
                    let displayFormatted = optionContent.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                    let btnClass = "ai-quick-chip my-1 me-1";
                    if (lowerText.includes('yes') || lowerText.includes('confirm') || lowerText.includes('submit')) {
                        btnClass = "btn btn-sm btn-success text-white rounded-pill px-3 py-1 my-1 me-1 shadow-sm font-weight-bold";
                    } else if (lowerText.includes('no') || lowerText.includes('cancel')) {
                        btnClass = "btn btn-sm btn-outline-secondary rounded-pill px-3 py-1 my-1 me-1";
                    }
                    chipsHtml += `<button type="button" class="${btnClass}" style="font-size:0.75rem; cursor:pointer;" onclick="window.triggerQuickChat('${cleanText.replace(/'/g, "\\'")}')">${displayFormatted}</button>`;
                } else {
                    let formattedLine = escapeHtml(line).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                    outputHtml += `<div>${formattedLine}</div>`;
                }
            } else {
                let formattedLine = escapeHtml(line).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                if (trimmed) {
                    outputHtml += `<div>${formattedLine}</div>`;
                } else {
                    outputHtml += `<div style="height:4px;"></div>`;
                }
            }
        }
        
        if (showLeaveWidget) {
            outputHtml += renderLeaveFormWidget();
        }

        if (chipsHtml) {
            outputHtml += `<div class="d-flex flex-wrap align-items-center gap-1 mt-2 pt-2 border-top" style="border-color: #e2e8f0 !important;">${chipsHtml}</div>`;
        }
        
        return outputHtml;
    }

    // Append Message to Chat UI
    function appendMessage(sender, text) {
        const isUser = sender === 'user';
        const contentHtml = isUser ? escapeHtml(text).replace(/\n/g, '<br>') : formatAiMessage(text);
        
        const msgHtml = `
            <div class="ai-msg-bubble d-flex align-items-start gap-2 ${isUser ? 'justify-content-end' : ''}">
                ${!isUser ? `
                    <div class="bg-primary text-white rounded-circle p-1 d-flex align-items-center justify-content-center flex-shrink-0 shadow-sm" style="width: 28px; height: 28px; background: #4f46e5 !important;">
                        <i class="fa-solid fa-headset fs-6"></i>
                    </div>
                ` : ''}
                <div class="p-3 rounded-4 ${isUser ? 'bg-primary text-white shadow-sm' : 'bg-white text-dark border border-slate-100 shadow-sm'}" 
                    style="font-size: 0.85rem; max-width: 82%; ${isUser ? 'border-bottom-right-radius: 4px !important; background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%) !important;' : 'border-top-left-radius: 4px !important;'}">
                    ${contentHtml}
                </div>
            </div>
        `;
        chatMessages.insertAdjacentHTML('beforeend', msgHtml);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function escapeHtml(str) {
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // Submit Message to Django Backend
    function submitMessage(msgText) {
        const text = msgText || chatInput.value.trim();
        if (!text) return;

        appendMessage('user', text);
        chatInput.value = '';

        const lowerMsg = text.toLowerCase();
        const isLeaveIntent = (lowerMsg.includes('apply leave') || lowerMsg.includes('apply for leave') || lowerMsg.includes('want to apply leave') || lowerMsg.includes('need leave') || lowerMsg.includes('leave application')) && !text.startsWith('Apply leave: Leave Type:');

        if (isLeaveIntent) {
            setTimeout(() => {
                appendMessage('ai', 'Please fill out your leave application details below:\n[LEAVE_FORM_WIDGET]');
            }, 300);
            return;
        }

        // Add Loading Indicator
        const loadingId = 'loading-' + Date.now();
        const loadingHtml = `
            <div id="${loadingId}" class="ai-msg-bubble d-flex align-items-center gap-2 text-secondary px-2" style="font-size: 0.8rem;">
                <div class="spinner-grow spinner-grow-sm text-primary" role="status"></div>
                <span class="fw-medium">Lurnexa AI is thinking...</span>
            </div>
        `;
        chatMessages.insertAdjacentHTML('beforeend', loadingHtml);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        const selectedLangCode = langSelect.value;
        const selectedLangText = langSelect.options[langSelect.selectedIndex].text;

        fetch('/api/chatbot/chat/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: text,
                history: conversationHistory,
                language: selectedLangCode,
                language_name: selectedLangText
            })
        })
        .then(res => res.json())
        .then(data => {
            const loadingElem = document.getElementById(loadingId);
            if (loadingElem) loadingElem.remove();

            if (data.success && !data.reply.includes("Sorry, AI service error:")) {
                const reply = data.reply || "Done!";
                appendMessage('ai', reply);
                conversationHistory.push({ sender: 'user', text: text });
                conversationHistory.push({ sender: 'ai', text: reply });
                
                // Speak out the reply in user's selected language
                speakText(reply);
            } else {
                appendMessage('ai', data.reply || ("Sorry, I encountered an error: " + (data.error || "Unknown error")));
            }
        })
        .catch(err => {
            const loadingElem = document.getElementById(loadingId);
            if (loadingElem) loadingElem.remove();
            appendMessage('ai', "Unable to reach server. Please try again.");
            console.error("Chatbot submit error:", err);
        });
    }

    chatForm.addEventListener('submit', function (e) {
        e.preventDefault();
        submitMessage();
    });
});

