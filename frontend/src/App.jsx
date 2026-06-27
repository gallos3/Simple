import { useState, useEffect, useRef } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";
import CytoscapeComponent from "react-cytoscapejs";
import ReactMarkdown from "react-markdown";

/** Το browser STT συχνά χωρίζει «2024» σε «20 24» — ενώνουμε πριν σταλεί στο backend. */
function normalizeTranscriptYearDigits(text) {
  if (!text) return text;
  return text.replace(/20[\s\u00A0\u2009]+(\d)(\d)(?!\d)/g, "20$1$2");
}

/**
 * Πολλαπλά alternatives (όπου υποστηρίζεται): προτιμάμε μεταγραφή που περιέχει έτος 202x/2018+.
 */
function pickBestSpeechTranscript(results) {
  const alts = results[0];
  if (!alts || alts.length === 0) return "";
  let best = alts[0].transcript;
  let bestScore = -1;
  for (let i = 0; i < alts.length; i++) {
    const t = normalizeTranscriptYearDigits(alts[i].transcript);
    const conf = typeof alts[i].confidence === "number" ? alts[i].confidence : 0;
    let bonus = 0;
    if (/\b20[2-3][0-9]\b/.test(t)) bonus += 2;
    else if (/\b201[89]\b/.test(t) || /\b202[0-9]\b/.test(t)) bonus += 1.5;
    const score = conf + bonus;
    if (score > bestScore) {
      bestScore = score;
      best = t;
    }
  }
  return best;
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [userName, setUserName] = useState(localStorage.getItem("userName") || "");
  const [userRole, setUserRole] = useState(localStorage.getItem("userRole") || "AUDITOR");
  const [webSearchEnabled, setWebSearchEnabled] = useState(true);
  const [showTools, setShowTools] = useState(false);
  const [showChart, setShowChart] = useState(false);
  const [showGraph, setShowGraph] = useState(false);
  const [chartData, setChartData] = useState([]);
  const [graphElements, setGraphElements] = useState([]);
  const [showHitl, setShowHitl] = useState(false);
  const [pendingReviews, setPendingReviews] = useState([]);
  const [reviewEntity, setReviewEntity] = useState("Buyer");
  const [isLoadingReviews, setIsLoadingReviews] = useState(false);
  
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const recognitionRef = useRef(null);
  const abortControllerRef = useRef(null);
  const messagesEndRef = useRef(null);
   // Auto-scroll
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, streamingText]);
  // Pre-load voices
  useEffect(() => {
    const loadVoices = () => {
      window.speechSynthesis.getVoices();
    };
    loadVoices();
    if (window.speechSynthesis.onvoiceschanged !== undefined) {
      window.speechSynthesis.onvoiceschanged = loadVoices;
    }
  }, []);
  


  // Global push-to-talk: κρατάω πατημένο το αριστερό κλικ οπουδήποτε
  useEffect(() => {
    let holdTimer;

    const handleMouseDown = (e) => {
      // 0 = αριστερό κουμπί
      if (e.button !== 0) return;
      if (isProcessing) return;
      if (isListening) return;

      // ξεκινά ακρόαση μόνο αν κρατηθεί πατημένο > 300ms
      holdTimer = setTimeout(() => {
        console.log("[SPEECH] startListening from mousedown");
        startListening();
      }, 300);
    };

    const handleMouseUp = (e) => {
      if (e.button !== 0) return;
      clearTimeout(holdTimer);

      // αν είμαστε σε listening mode, σταμάτα και άσε το onresult/onend να τρέξουν
      if (isListening) {
        console.log("[SPEECH] mouseup → stopListening");
        stopListening();
      }
    };

    window.addEventListener("mousedown", handleMouseDown);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousedown", handleMouseDown);
      window.removeEventListener("mouseup", handleMouseUp);
      clearTimeout(holdTimer);
    };
  }, [isListening, isProcessing]);

    const speak = (text) => {
    if (!text) return;
    const emojiFree = text.replace(/[\p{Emoji_Presentation}\p{Extended_Pictographic}]/gu, "");
    const cleaned = emojiFree.replace(/\s+/g, " ").trim();
    if (cleaned) {
      const utterance = new SpeechSynthesisUtterance(cleaned);
      
      // Βρες τις διαθέσιμες φωνές
      const voices = window.speechSynthesis.getVoices();
      
      // Ανίχνευση γλώσσας: Αν περιέχει ελληνικούς χαρακτήρες, θεωρούμε ότι είναι ελληνικά
      const isGreek = /[\u0370-\u03FF]/.test(cleaned);

      if (isGreek) {
        // Φίλτρο για ελληνικά (el-GR)
        const greekVoices = voices.filter(v => v.lang.startsWith('el'));
        if (greekVoices.length > 0) {
          // Προτίμηση σε Athina ή Pelopia (αν υπάρχουν στα Windows) αντί για τον Στέφανο
          const preferred = greekVoices.find(v => v.name.includes('Athina') || v.name.includes('Pelopia'));
          if (preferred) {
            utterance.voice = preferred;
            console.log("[TTS] Using preferred Greek voice:", preferred.name);
          } else {
            utterance.voice = greekVoices[0];
            console.log("[TTS] Using default Greek voice:", greekVoices[0].name);
          }
        }
        utterance.lang = "el-GR";
      } else {
        // Αγγλικά (για τα σενάρια)
        const englishVoices = voices.filter(v => v.lang.startsWith('en'));
        if (englishVoices.length > 0) {
          // Αναζήτηση γυναικείας φωνής για πιο ανθρώπινο αποτέλεσμα στα σενάρια
          // Προτιμάμε Microsoft Zira (Windows), Google US English, ή Samantha (Mac)
          const femaleEnglish = englishVoices.find(v => 
            v.name.includes('Zira') || 
            v.name.includes('Samantha') || 
            v.name.includes('Google US English') ||
            v.name.includes('Female') ||
            v.name.includes('Susan') ||
            v.name.includes('Hazel')
          );
          if (femaleEnglish) {
            utterance.voice = femaleEnglish;
            console.log("[TTS] Using female English voice:", femaleEnglish.name);
          } else {
            utterance.voice = englishVoices[0];
            console.log("[TTS] Using default English voice:", englishVoices[0].name);
          }
        }
        utterance.lang = "en-US";
      }

      utterance.pitch = 1.05; // Ελαφρώς πιο φυσικός τόνος
      utterance.rate = 1.0;   // Κανονική ταχύτητα
      speechSynthesis.speak(utterance);
    }
  };
  const addMessage = (role, text, meta = {}) => {
    if (!text) return; // Don't add empty messages
    console.log(`[UI] Adding message: role=${role}, text=${text.substring(0, 50)}...`);
    setMessages((prev) => [...prev, { role, text, ...meta }]);
  };
  // Escape markdown list syntax (numbers at start of line followed by period)
  const escapeMarkdownLists = (text) => {
    if (!text) return "";
    // Escape "123." at start of line to prevent list interpretation
    return text.replace(/^(\d+)\./gm, "$1\\.");
  };
  // Ensure complete sentences
  const ensureCompleteText = (text) => {
    if (!text) return "";
    let t = text.trim();
    
    // Αν είναι μόνο αριθμός (π.χ. "2008", "56989"), επέστρεψέ το όπως είναι
    if (/^\d+$/.test(t)) {
      return t;
    }
    
    // Αν είναι αριθμός με κείμενο (π.χ. "Έχεις 2008 αρχές"), επέστρεψέ το
    if (/^\d+\s+\S/.test(t) || /\S\s+\d+$/.test(t)) {
      return t.endsWith('.') ? t : t + '.';
    }
    
    t = t.replace(/^\s*(Απάντηση|Συμπέρασμα)\s*[:\-]\s*/i, "");
    t = t.replace(/^\s*\d+[\.\)]\s*/, "");
    if (/[.!;?]$/.test(t)) return t;
    const lastPeriod = t.lastIndexOf(".");
    const lastQuestion = t.lastIndexOf(";");
    const lastExclaim = t.lastIndexOf("!");
    const cut = Math.max(lastPeriod, lastQuestion, lastExclaim);
    if (cut > t.length * 0.3) {
      return t.slice(0, cut + 1);
    }
    return t.replace(/[,;:\-\s]+$/, "") + ".";
  };

  // =========================================================================
  // STREAMING QUESTION HANDLER (FIXED)
  // =========================================================================
  const handleQuestionStream = async (questionText, options = {}) => {
    if (!questionText.trim()) return;
    const { fromVoice = false } = options;

    setInput("");
    setIsProcessing(true);
    setStreamingText("");
    window.speechSynthesis.cancel(); // Σταμάτα την προηγούμενη ομιλία
    window._lastSpokenIndex = 0;

    abortControllerRef.current = new AbortController();

    let fullText = "";
    let buffer = ""; // Buffer for partial SSE messages
    let downloadReportData = null; // Store download event payload

    try {
      console.log("[UI] Fetching /ask_stream...");
      const response = await fetch("/ask_stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          question: questionText, 
          from_voice: fromVoice,
          role: userRole,
          web_search_enabled: webSearchEnabled,
          history: messages
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          console.log("[UI] Stream ended");
          break;
        }

        // Add new chunk to buffer
        buffer += decoder.decode(value, { stream: true });
        
        // Process complete SSE messages (ending with \n\n)
        const messages_raw = buffer.split("\n\n");
        
        // Keep the last incomplete message in buffer
        buffer = messages_raw.pop() || "";

        for (const msg of messages_raw) {
          const lines = msg.split("\n");
          
          for (let line of lines) {
            line = line.trim();
            if (!line.startsWith("data:")) continue;

            try {
              // Remove "data:" prefix (with or without space)
              const jsonStr = line.replace(/^data:\s*/, "");
              if (!jsonStr) continue;
              
              console.log("[UI] Parsing SSE:", jsonStr.substring(0, 100));
              const data = JSON.parse(jsonStr);

              if (data.type === "start") {
                console.log("[UI] Stream started, intent:", data.intent);
              } else if (data.type === "token") {
                const content = data.content || "";
                fullText += content;
                setStreamingText(fullText);
                
                // --- STREAMING TTS LOGIC (Robust while-loop for all ready chunks) ---
                let lastSpokenIndex = window._lastSpokenIndex || 0;
                let newText = fullText.substring(lastSpokenIndex);
                let match;
                while ((match = newText.match(/.*?(?:\n|[.!?;](\s+|$))/)) !== null) {
                  const chunk = match[0].trim();
                  if (chunk.length > 2) { 
                    console.log("[TTS] Streaming chunk:", chunk);
                    speak(chunk);
                  }
                  lastSpokenIndex += match[0].length;
                  window._lastSpokenIndex = lastSpokenIndex;
                  newText = fullText.substring(lastSpokenIndex);
                }
                // ---------------------------

              } else if (data.type === "action") {
                const actionData = data.data;
                console.log("[UI] Action received:", actionData?.action);
                
                if (actionData?.action === "show_chart") {
                  setChartData(actionData.data || []);
                  setShowChart(true);
                  if (actionData?.text) {
                    addMessage("bot", actionData.text);
                    speak(actionData.text);
                  }
                } else if (actionData?.action === "show_graph") {
                  const graphData = actionData.data || [];
                  setGraphElements(graphData);
                  setShowGraph(true);
                  if (actionData?.text) {
                    addMessage("bot", actionData.text, {
                      graphData: graphData,
                      suggestions: actionData.suggestions || []
                    });
                    speak(actionData.text);
                  }
                } else {
                  // Other actions (report_generated etc.)
                  if (actionData?.text) {
                    addMessage("bot", actionData.text);
                    speak(actionData.text);
                  }
                }
              } else if (data.type === "end") {
                console.log("[UI] End event received, fullText:", fullText);
                const cleaned = ensureCompleteText(fullText);
                if (cleaned) {
                  addMessage("bot", cleaned, {
                    ...(downloadReportData && { download_report: downloadReportData })
                  });
                  
                  // Final check for any remaining text in buffer that wasn't spoken
                  const lastIdx = window._lastSpokenIndex || 0;
                  const remaining = cleaned.substring(lastIdx).trim();
                  if (remaining.length > 2) {
                    speak(remaining);
                  }
                }
                setStreamingText("");
                fullText = "";
                window._lastSpokenIndex = 0;
              } else if (data.type === "download_report") {
                console.log("[UI] Download report event:", data.data || data);
                downloadReportData = data.data || data;
              } else if (data.type === "error") {
                console.error("[UI] Error from server:", data.content);
                addMessage("bot", `⚠️ ${data.content}`);
                setStreamingText("");
              }
            } catch (e) {
              console.error("[UI] JSON parse error:", e, "Line:", line);
            }
          }
        }
      }

      // Handle any remaining text if stream ended without "end" event
      if (fullText && !streamingText) {
        console.log("[UI] Handling remaining text after stream end");
        const cleaned = ensureCompleteText(fullText);
        if (cleaned) {
          addMessage("bot", cleaned, {
            ...(downloadReportData && { download_report: downloadReportData })
          });
          speak(cleaned);
        }
      }

    } catch (error) {
      if (error.name === "AbortError") {
        addMessage("bot", "✅ Το ερώτημα ακυρώθηκε.");
      } else {
        console.error("[UI] Streaming error:", error);
        await handleQuestionFallback(questionText, options);
      }
    } finally {
      setIsProcessing(false);
      setStreamingText("");
      abortControllerRef.current = null;
    }
  };

  // =========================================================================
  // FALLBACK (NON-STREAMING) HANDLER
  // =========================================================================
  const handleQuestionFallback = async (questionText, options = {}) => {
    const { fromVoice = false } = options;
    console.log("[UI] Using fallback /ask endpoint");
    try {
      const res = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          question: questionText, 
          from_voice: fromVoice,
          role: userRole,
          web_search_enabled: webSearchEnabled,
          history: messages
        })
      });

      const data = await res.json();

      if (data.action === "show_chart") {
        setChartData(data.data || []);
        setShowChart(true);
        if (data.text) {
          addMessage("bot", data.text);
          speak(data.text);
        }
        return;
      }

      if (data.action === "show_graph") {
        const elements = Array.isArray(data.data) ? data.data : [];
        if (elements.length === 0) {
          addMessage("bot", "⚠️ Δεν υπάρχουν δεδομένα για το γράφημα.");
          return;
        }
        setGraphElements(elements);
        setShowGraph(true);
        if (data.text) {
          addMessage("bot", data.text, {
            graphData: elements,
            suggestions: data.suggestions || []
          });
          speak(data.text);
        }
        return;
      }

      const responseText = data.text || data.result || "⚠️ Δεν δόθηκε απάντηση.";
      addMessage("bot", responseText);
      speak(responseText);
    } catch (error) {
      console.error("[UI] Fallback error:", error);
      addMessage("bot", "❌ Σφάλμα σύνδεσης με τον server.");
    }
  };

  // =========================================================================
  // MAIN HANDLER
  // =========================================================================
  const handleQuestionSend = async (questionText, options = {}) => {
    if (!questionText.trim()) return;
    addMessage("user", questionText);
    await handleQuestionStream(questionText, options);
  };

  // =========================================================================
  // STOP PROCESSING
  // =========================================================================
  const stopProcessing = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    speechSynthesis.cancel();
    setIsProcessing(false);
    setStreamingText("");
  };

  // =========================================================================
  // SPEECH HANDLER
  // =========================================================================
  const handleSpeech = (speech) => {
    const normalized = speech.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    
    if (normalized.includes("γεια") || normalized.includes("καλημερα") || normalized.includes("καλησπερα")) {
      const hour = new Date().getHours();
      const greeting = hour < 12 ? "Καλημέρα" : "Καλησπέρα";
      const response = userName ? `${greeting} ${userName}!` : `${greeting}! Πώς σε λένε;`;
      speak(response);
      addMessage("bot", response);
      return;
    }

    if (normalized.startsWith("με λενε")) {
      const name = speech.toLowerCase().replace(/^με λ[εέ]νε\s*/i, "").trim();
      setUserName(name);
      localStorage.setItem("userName", name);
      const response = `Χάρηκα ${name}! Πώς μπορώ να βοηθήσω;`;
      speak(response);
      addMessage("bot", response);
      return;
    }

    if (normalized.includes("σταματα") || normalized.includes("σταματησε")) {
      stopProcessing();
      return;
    }

    if (normalized.includes("καθαρισε")) {
      setMessages([]);
      speak("Καθάρισα την οθόνη.");
      return;
    }

    handleQuestionSend(speech, { fromVoice: true });
  };

  // =========================================================================
  // FEEDBACK HANDLER (AI-Ready Debugging)
  // =========================================================================
  const handleFeedback = async () => {
    const comment = prompt("Τι πήγε λάθος; (Περιγράψτε το πρόβλημα για να το διορθώσω)");
    if (!comment) return;

    try {
      const res = await fetch("/submit_feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comment })
      });
      const data = await res.json();
      if (data.status === "success") {
        alert("✅ Η αναφορά στάλθηκε επιτυχώς! Ο βοηθός θα αναλύσει το trace για να το διορθώσει.");
      } else {
        alert("❌ Σφάλμα κατά την αποστολή: " + data.message);
      }
    } catch (e) {
      alert("❌ Σφάλμα σύνδεσης με τον server.");
    }
  };

  // =========================================================================
  // FILE UPLOAD
  // =========================================================================
  const handleSingleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/upload_file", {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      if (data.warnings?.length > 0) {
        data.warnings.forEach((w) => addMessage("bot", `⚠️ ${w}`));
      }
      addMessage("bot", data.message || "✅ Το αρχείο ανέβηκε.");
    } catch (error) {
      addMessage("bot", "❌ Σφάλμα κατά το ανέβασμα.");
    }
  };

  // =========================================================================
  // SPEECH RECOGNITION
  // =========================================================================
    // =========================================================================
  // SPEECH RECOGNITION
  // =========================================================================
  const pendingTranscriptRef = useRef("");
  
  const startListening = () => {
    if (isListening) return; // μην ξεκινάς δεύτερη φορά αν ήδη ακούς
    pendingTranscriptRef.current = ""; // reset accumulated transcript

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Ο browser δεν υποστηρίζει φωνητική αναγνώριση.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "el-GR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 5;
    recognition.continuous = true; // Don't auto-stop on silence

    recognition.onresult = (e) => {
      // Accumulate all final results (continuous mode fires multiple onresult events)
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) {
          const chunk = pickBestSpeechTranscript({ 0: e.results[i], length: 1 });
          if (chunk) {
            pendingTranscriptRef.current += (pendingTranscriptRef.current ? " " : "") + chunk;
          }
        }
      }
      console.log("[SPEECH] onresult (accumulated):", pendingTranscriptRef.current);
    };

    recognition.onstart = () => {
      console.log("[SPEECH] onstart");
      setIsListening(true);
    };
    recognition.onend = () => {
      console.log("[SPEECH] onend");
      setIsListening(false);
      // If we have accumulated transcript, fire it now
      const transcript = pendingTranscriptRef.current.trim();
      if (transcript) {
        console.log("[SPEECH] firing handleSpeech with:", transcript);
        handleSpeech(transcript);
        pendingTranscriptRef.current = "";
      }
    };

    recognitionRef.current = recognition;
    recognition.start();
  };
    const stopListening = () => {
    const recognition = recognitionRef.current;
    if (recognition) {
      try {
        console.log("[SPEECH] stopListening()");
        recognition.stop(); // This triggers onend → which fires handleSpeech
      } catch (e) {
        console.warn("[SPEECH] Error stopping recognition:", e);
      }
    }
    // Το onend θα καλέσει setIsListening(false) και handleSpeech
  };

  // =========================================================================
  // HITL DASHBOARD HANDLERS
  // =========================================================================
  const loadPendingReviews = async (entityType) => {
    setIsLoadingReviews(true);
    try {
      const res = await fetch(`/api/pending_reviews?entity=${entityType}`);
      const data = await res.json();
      setPendingReviews(data);
    } catch (e) {
      console.error("Error loading reviews", e);
    } finally {
      setIsLoadingReviews(false);
    }
  };

  const handleResolveReview = async (action, pair) => {
    try {
      const res = await fetch('/api/resolve_review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: action,
          id1: pair.id1,
          id2: pair.id2,
          entity: reviewEntity
        })
      });
      if (res.ok) {
        setPendingReviews(prev => prev.filter(p => p.id1 !== pair.id1 || p.id2 !== pair.id2));
      } else {
        alert("Σφάλμα κατά την ανάλυση");
      }
    } catch (e) {
      alert("Σφάλμα δικτύου");
    }
  };

  // =========================================================================
  // RENDER
  // =========================================================================
  return (
    <div className="min-h-screen bg-gray-900 text-white flex flex-col items-center justify-center p-4 relative">
      <div className="absolute top-4 right-4">
        {/* WEB SEARCH TOGGLE */}
        <button
          onClick={() => setWebSearchEnabled(!webSearchEnabled)}
          className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold transition border shadow-lg ${
            webSearchEnabled 
              ? "bg-blue-900 border-blue-500 text-blue-200 hover:bg-blue-800" 
              : "bg-gray-800 border-gray-600 text-gray-500 hover:bg-gray-700"
          }`}
          title={webSearchEnabled ? "Web Search Ενεργό" : "Web Search Ανενεργό"}
        >
          {webSearchEnabled ? "🌐 WEB ON" : "🔒 WEB OFF"}
        </button>
      </div>

      <div className="flex items-center gap-4 mb-6 mt-4">
        <h1 className="text-5xl font-extrabold tracking-tight">Simple</h1>
      </div>

      {/* MESSAGES */}
      <div className="w-full max-w-3xl h-[60vh] overflow-y-auto bg-gray-800 rounded-2xl shadow-lg p-4 space-y-2">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`p-3 rounded-xl max-w-[80%] whitespace-pre-wrap break-words ${
              m.role === "user"
                ? "bg-blue-600 ml-auto text-right"
                : "bg-gray-700 mr-auto text-left"
            }`}
          >
            <ReactMarkdown 
              components={{
                a: ({node, ...props}) => <a {...props} target="_blank" rel="noopener noreferrer" className="text-blue-300 hover:text-blue-200 underline font-bold" />
              }}
            >
              {escapeMarkdownLists(m.text)}
            </ReactMarkdown>
            
            {/* Re-open graph button */}
            {m.graphData && (
              <button
                onClick={() => { setGraphElements(m.graphData); setShowGraph(true); }}
                className="mt-2 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm flex items-center gap-1.5 transition-colors"
                title="Άνοιξε ξανά τον γράφο"
              >
                📊 Άνοιξε γράφημα
              </button>
            )}
            
            {/* Download Report Button */}
            {m.download_report && (
              <a
                href={m.download_report.url.startsWith("http") ? m.download_report.url : `http://localhost:5051${m.download_report.url}`}
                download={m.download_report.filename || "report.md"}
                className="mt-3 px-4 py-2 bg-green-600 hover:bg-green-500 rounded-lg text-sm text-white font-bold flex w-fit items-center gap-2 transition-colors no-underline shadow-md"
                target="_blank"
                rel="noopener noreferrer"
              >
                📥 {m.download_report.label || "Download Expert Review Report"}
              </a>
            )}

            {/* 
              Scenario graph preview is instructor-only and must not be shown during learner gameplay.
              Instructors can manually access http://localhost:5051/graph_preview/<scenario_id>.html
            */}

            {/* Follow-up suggestion buttons */}
            {m.suggestions && m.suggestions.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {m.suggestions.map((s, si) => (
                  <button
                    key={si}
                    onClick={() => handleQuestionSend(s.query || s)}
                    className="px-3 py-1.5 bg-gray-600 hover:bg-gray-500 rounded-lg text-xs border border-gray-500 transition-colors"
                    title={s.query || s}
                  >
                    {s.label || s}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        
        {/* STREAMING TEXT */}
        {streamingText && (
          <div className="p-3 rounded-xl max-w-[80%] bg-gray-700 mr-auto text-left">
            <ReactMarkdown 
              components={{
                a: ({node, ...props}) => <a {...props} target="_blank" rel="noopener noreferrer" className="text-blue-300 hover:text-blue-200 underline font-bold" />
              }}
            >
              {escapeMarkdownLists(streamingText)}
            </ReactMarkdown>
            <span className="inline-block w-2 h-4 bg-green-400 animate-pulse ml-1">|</span>
          </div>
        )}
        
        {/* PROCESSING INDICATOR */}
        {isProcessing && !streamingText && (
          <div className="p-3 rounded-xl bg-gray-700 mr-auto flex items-center gap-2">
            <div className="flex gap-1">
              <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{animationDelay: '0ms'}}></span>
              <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{animationDelay: '150ms'}}></span>
              <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{animationDelay: '300ms'}}></span>
            </div>
            <span className="text-gray-400 text-sm">Processing...</span>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* INPUT */}
      <div className="w-full max-w-3xl flex flex-col items-end mt-4">
        <div className="flex w-full gap-2">
          <input
            className="flex-1 p-3 rounded-full bg-gray-700 text-white"
            placeholder="Type your question..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && input.trim() && !isProcessing) {
                handleQuestionSend(input.trim());
              }
            }}
            disabled={isProcessing}
          />
          <button
            onClick={() => setShowTools(!showTools)}
            className="bg-gray-600 px-3 py-2 rounded-full"
          >
            {showTools ? "⬆️" : "⬇️"}
          </button>
        </div>

        {/* TOOLS */}
        {showTools && (
          <div className="flex w-full gap-2 mt-2">
            <button
              onClick={handleFeedback}
              className="flex-1 flex justify-center items-center bg-green-600 py-2 rounded-full hover:bg-green-700 text-white font-bold border border-green-400"
            >
              🚩 Bug Report
            </button>
            <button 
              onClick={() => {
                setShowHitl(true);
                loadPendingReviews("Buyer");
              }} 
              className="flex-1 flex justify-center items-center bg-indigo-600 py-2 rounded-full hover:bg-indigo-700 text-white font-bold border border-indigo-400"
            >
              👥 Review
            </button>
           <button 
              disabled={isProcessing}
              className={`hidden py-2 rounded-full ${
                isListening ? "bg-red-600 animate-pulse" : "bg-green-600"
              }`}
            >
              🎤 {isListening ? "Listening..." : "Speak"}
            </button>

            <button 
              onClick={stopProcessing} 
              className="flex-1 flex justify-center items-center bg-red-600 py-2 rounded-full hover:bg-red-700 font-bold"
            >
              🛑 Stop
            </button>
            <button 
              onClick={() => setMessages([])} 
              className="flex-1 flex justify-center items-center bg-yellow-500 py-2 rounded-full text-black font-bold"
            >
              🧹 Clear
            </button>
            <label className="flex-1 flex justify-center items-center bg-purple-600 py-2 rounded-full cursor-pointer hover:bg-purple-700 font-bold">
              📁 Upload
              <input type="file" onChange={handleSingleUpload} className="hidden" />
            </label>
          </div>
        )}
      </div>

      {/* CHART MODAL */}
      {showChart && (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50">
          <div className="bg-white text-black p-4 rounded-xl max-w-4xl w-full">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-bold">📊 Διάγραμμα</h2>
              <button onClick={() => setShowChart(false)}>❌</button>
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData}>
                <XAxis dataKey="Αναθέτουσα Αρχή" tick={{ fontSize: 10 }} interval={0} angle={-45} textAnchor="end" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="Πλήθος Αναθέσεων" fill="#82ca9d" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* GRAPH MODAL */}
      {showGraph && (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 text-white p-6 rounded-2xl max-w-5xl w-full border border-gray-700 shadow-2xl">
            <div className="flex justify-between items-center mb-6">
              <div>
                <h2 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                  🧠 Advanced Graph Reasoning
                </h2>
                <p className="text-sm text-gray-400">Node size indicates Centrality (Influence)</p>
              </div>
              <div className="flex items-center gap-2">
                <button 
                  onClick={() => {
                    const cy = window.cy;
                    if (!cy) return;
                    const png = cy.png({ scale: 2, bg: '#0b0f1a', full: true });
                    const link = document.createElement('a');
                    link.href = png;
                    link.download = `graph_${new Date().toISOString().slice(0,10)}.png`;
                    link.click();
                  }}
                  className="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 rounded-lg text-sm transition-colors flex items-center gap-1"
                  title="Αποθήκευση ως PNG"
                >
                  💾 PNG
                </button>
                <button 
                  onClick={() => setShowGraph(false)}
                  className="hover:bg-gray-800 p-2 rounded-full transition-colors"
                >
                  ❌
                </button>
              </div>
            </div>

            {/* TIMELINE SLIDER */}
            <div className="mb-6 bg-gray-800 p-4 rounded-xl border border-gray-700">
              <div className="flex justify-between text-xs text-gray-400 mb-2">
                <span>Timeline Start</span>
                <span className="text-blue-400 font-bold">Dynamic Filter</span>
                <span>Latest</span>
              </div>
              <input 
                type="range" 
                min="0" 
                max="100" 
                defaultValue="100"
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  const cy = window.cy;
                  if (!cy) return;
                  
                  // Get all contract timestamps
                  const timestamps = cy.nodes('[group = "Award"]').map(n => n.data('timestamp')).filter(ts => ts > 0);
                  if (timestamps.length === 0) return;
                  
                  const minTs = Math.min(...timestamps);
                  const maxTs = Math.max(...timestamps);
                  const currentThreshold = minTs + (maxTs - minTs) * (val / 100);
                  
                  cy.batch(() => {
                    cy.nodes('[group = "Award"]').forEach(node => {
                      const ts = node.data('timestamp');
                      if (ts && ts > currentThreshold) {
                        node.style('display', 'none');
                        node.connectedEdges().style('display', 'none');
                      } else {
                        node.style('display', 'element');
                        node.connectedEdges().style('display', 'element');
                      }
                    });
                    
                    // Hide Winner nodes that have no visible edges
                    cy.nodes('[group = "Winner"]').forEach(node => {
                      const hasVisibleEdges = node.connectedEdges().some(edge => edge.style('display') !== 'none');
                      if (!hasVisibleEdges) {
                        node.style('display', 'none');
                      } else {
                        node.style('display', 'element');
                      }
                    });
                  });
                }}
              />
            </div>

            <div className="rounded-xl overflow-hidden border border-gray-700">
              <CytoscapeComponent
                elements={CytoscapeComponent.normalizeElements(graphElements)}
                style={{ width: "100%", height: "550px", backgroundColor: "#0b0f1a" }}
                cy={(cy) => { window.cy = cy; }}
                layout={{ 
                  name: "cose",
                  nodeOverlap: 40,
                  componentSpacing: 120,
                  nodeRepulsion: 800000,
                  edgeElasticity: 200,
                  nestingFactor: 10,
                  gravity: 50,
                  numIter: 1500
                }}
                stylesheet={[
                  { 
                    selector: "node", 
                    style: { 
                      content: "data(label)", 
                      color: "#94a3b8", 
                      backgroundColor: "#4b5563", 
                      textValign: "bottom", 
                      textHalign: "center",
                      textMarginY: 8,
                      fontSize: 10,
                      // CENTRALITY BASED SIZING
                      width: "mapData(centrality, 1, 5, 30, 90)",
                      height: "mapData(centrality, 1, 5, 30, 90)",
                      transitionProperty: "width, height, background-color",
                      transitionDuration: "0.3s"
                    } 
                  },
                  { selector: "node[group = 'Buyer']", style: { backgroundColor: "#3b82f6", fontWeight: 'bold', color: '#fff' } },
                  { selector: "node[group = 'Winner']", style: { backgroundColor: "#10b981" } },
                  { selector: "node[group = 'Award'][risk = 'low']", style: { backgroundColor: "#64748b" } },
                  { selector: "node[group = 'Award'][risk = 'medium']", style: { backgroundColor: "#f59e0b" } },
                  { selector: "node[group = 'Award'][risk = 'high']", style: { backgroundColor: "#ef4444", borderWidth: 3, borderColor: '#fff' } },
                  { selector: "node[group = 'CPV']", style: { backgroundColor: "#8b5cf6", shape: 'ellipse' } },
                  { selector: "node[group = 'LegalRule']", style: { backgroundColor: "#facc15", shape: 'ellipse' } },
                  { selector: "node[group = 'Threshold']", style: { backgroundColor: "#94a3b8", shape: 'ellipse' } },
                  { 
                    selector: "edge", 
                    style: { 
                      width: "mapData(weight, 0, 500000, 1, 8)", 
                      lineColor: "#334155", 
                      targetArrowColor: "#334155", 
                      targetArrowShape: "triangle",
                      curveStyle: "bezier",
                      label: "data(label)",
                      fontSize: 8,
                      color: "#475569",
                      textRotation: "autorotate",
                      opacity: 0.6
                    } 
                  }
                ]}
              />
            </div>
          </div>
        </div>
      )}

      {/* HITL DASHBOARD MODAL */}
      {showHitl && (
        <div className="fixed inset-0 bg-black bg-opacity-80 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 text-white p-6 rounded-2xl max-w-5xl w-full border border-gray-700 shadow-2xl h-[90vh] flex flex-col">
            <div className="flex justify-between items-center mb-6">
              <div>
                <h2 className="text-2xl font-bold text-indigo-400">
                  👥 Human-in-the-Loop Dashboard
                </h2>
                <p className="text-sm text-gray-400">Επιβεβαίωση και συγχώνευση διπλοεγγραφών (Entity Resolution)</p>
              </div>
              <button 
                onClick={() => setShowHitl(false)}
                className="hover:bg-gray-800 p-2 rounded-full transition-colors"
              >
                ❌
              </button>
            </div>
            
            <div className="flex gap-4 mb-4">
              <select 
                className="bg-gray-800 text-white border border-gray-600 rounded p-2"
                value={reviewEntity}
                onChange={(e) => {
                  setReviewEntity(e.target.value);
                  loadPendingReviews(e.target.value);
                }}
              >
                <option value="Buyer">Αναθέτουσες Αρχές (Buyers)</option>
                <option value="Winner">Ανάδοχοι (Winners)</option>
              </select>
              <button 
                onClick={() => loadPendingReviews(reviewEntity)}
                className="bg-blue-600 px-4 py-2 rounded text-white"
              >
                Ανανέωση
              </button>
            </div>

            <div className="overflow-y-auto flex-1 p-2 space-y-4">
              {isLoadingReviews && <div className="text-center mt-10">Φόρτωση...</div>}
              {!isLoadingReviews && pendingReviews.length === 0 && (
                <div className="text-center mt-10 text-gray-400">
                  <h4 className="text-xl">Δεν βρέθηκαν εκκρεμότητες! 🎉</h4>
                  <p>Το σύστημα Entity Resolution δεν έχει εντοπίσει άλλες ασαφείς διπλοεγγραφές.</p>
                </div>
              )}
              {!isLoadingReviews && pendingReviews.map((pair, idx) => (
                <div key={idx} className="bg-gray-800 rounded-xl p-4 border border-gray-700 flex flex-col gap-4">
                  <div className="flex justify-between items-center border-b border-gray-700 pb-2">
                    <span className="font-bold text-gray-300">Πιθανή Διπλοεγγραφή</span>
                    <span className={`px-3 py-1 rounded-full text-xs font-bold ${pair.score > 0.85 ? 'bg-green-600 text-white' : 'bg-yellow-600 text-white'}`}>
                      Ομοιότητα: {(pair.score * 100).toFixed(1)}%
                    </span>
                  </div>
                  
                  <div className="flex gap-4">
                    <div className="flex-1 bg-gray-700 p-4 rounded-lg">
                      <div className="text-xs text-gray-400 mb-1">ΟΝΤΟΤΗΤΑ 1 (Target)</div>
                      <div className="text-lg font-bold text-blue-300 mb-2">{pair.name1}</div>
                      <div className="text-sm">ΑΦΜ: <span className="text-gray-300">{pair.vat1 || '-'}</span></div>
                      <div className="text-sm">Συμβάσεις: <span className="text-gray-300">{pair.count1}</span></div>
                    </div>
                    
                    <div className="flex items-center justify-center text-3xl opacity-50">🆚</div>
                    
                    <div className="flex-1 bg-gray-700 p-4 rounded-lg">
                      <div className="text-xs text-gray-400 mb-1">ΟΝΤΟΤΗΤΑ 2 (Source)</div>
                      <div className="text-lg font-bold text-blue-300 mb-2">{pair.name2}</div>
                      <div className="text-sm">ΑΦΜ: <span className="text-gray-300">{pair.vat2 || '-'}</span></div>
                      <div className="text-sm">Συμβάσεις: <span className="text-gray-300">{pair.count2}</span></div>
                    </div>
                  </div>
                  
                  <div className="flex justify-end gap-3 mt-2">
                    <button 
                      onClick={() => handleResolveReview('reject', pair)}
                      className="bg-red-600 hover:bg-red-700 px-4 py-2 rounded font-bold transition-colors"
                    >
                      ❌ Απόρριψη (Είναι διαφορετικά)
                    </button>
                    <button 
                      onClick={() => handleResolveReview('approve', pair)}
                      className="bg-green-600 hover:bg-green-700 px-4 py-2 rounded font-bold transition-colors"
                    >
                      ✅ Έγκριση & Συγχώνευση (Merge)
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
