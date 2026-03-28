let editor;
let currentSessionId = null;
let timerInterval = null;
let timerSeconds = 0;
let isStreaming = false;
let interviewMode = 'text';
let allProblems = [];
let selectedCategory = 'all';
let searchQuery = '';
let selectedDifficulties = new Set();
let warmupOnly = false;
let attemptedProblems = {};
let codeSaveTimeout = null;
let visibleCount = 30;
let selectedSort = 'default';
let cmdPaletteItems = [];
let cmdPaletteIndex = 0;
let activeSkillFilter = null;

let currentStudyProblem = null;
let researchChatHistory = [];
let isResearchStreaming = false;

let currentInterviewProblemId = null;
let interviewTutorHistory = [];
let isInterviewTutorStreaming = false;
let tutorSidebarWidth = 320;
let tutorSidebarOpen = false;

let voicePc = null;
let voiceDc = null;
let voiceStream = null;
let voiceAudioEl = null;
let micMuted = false;
let voiceTranscriptMessages = [];

let currentAssistantTranscriptEl = null;
let currentAssistantTranscript = '';

let outputPanelCollapsed = true;
let outputPanelHeight = 200;
