"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Bot, User, Sparkles, FileText, Loader2, ArrowRight, Trash2 } from "lucide-react";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import axios from "axios";
import { getApiBaseUrl } from "@/utils/apiBaseUrl";

interface Message {
  role: "user" | "ai";
  content: string;
  sources?: { doc_id: string; name: string; chunk_text: string }[];
  active_claws?: string[];
}

export function ChatInterface() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [isOrchestratorMode, setIsOrchestratorMode] = useState(false);
  const [loaderStatus, setLoaderStatus] = useState("Routing query & planning analysis...");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Load chat history on mount
    const fetchHistory = async () => {
      try {
        const res = await axios.get(`${getApiBaseUrl()}/chat/history?t=${new Date().getTime()}`);
        if (res.data && res.data.history) {
          setMessages(res.data.history);
        }
      } catch (err) {
        console.error("Failed to load chat history", err);
      }
    };
    fetchHistory();
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  useEffect(() => {
    let intervalId: any;
    if (loading && isOrchestratorMode) {
      const loaderStates = [
        "Planning execution pipeline...",
        "Data Analyst Claw: Ingesting Q2 KPIs...",
        "Anomaly Detection Claw: Scanning for WoW drops...",
        "Anomaly Detection Claw: Logging exception rates...",
        "Customer Segmentation Claw: Mapping behavioral DNA...",
        "Customer Segmentation Claw: Formulating cohorts...",
        "Business Performance Claw: Synthesizing executive pulse...",
        "Compiling final briefings..."
      ];
      let i = 0;
      setLoaderStatus(loaderStates[0]);
      intervalId = setInterval(() => {
        i = (i + 1) % loaderStates.length;
        setLoaderStatus(loaderStates[i]);
      }, 3500);
    }
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [loading, isOrchestratorMode]);

  useEffect(() => {
    const handleLoadTemplate = (e: Event) => {
      const customEvent = e as CustomEvent<{ query: string }>;
      if (customEvent.detail && customEvent.detail.query) {
        setQuery(customEvent.detail.query);
        setIsOrchestratorMode(true);
      }
    };

    window.addEventListener('loadTemplate', handleLoadTemplate);
    return () => {
      window.removeEventListener('loadTemplate', handleLoadTemplate);
    };
  }, []);

  useEffect(() => {
    const handleDocumentSummaryRequest = (e: Event) => {
      const customEvent = e as CustomEvent<{ docId?: string; docName: string }>;
      if (customEvent.detail && customEvent.detail.docName) {
        handleSourceClick(customEvent.detail.docName, customEvent.detail.docId);
      }
    };

    window.addEventListener('requestDocumentSummary', handleDocumentSummaryRequest);
    return () => {
      window.removeEventListener('requestDocumentSummary', handleDocumentSummaryRequest);
    };
  }, [loading]);

  const handleSubmit = async (e?: React.FormEvent, overrideQuery?: string, filterMetadata?: any) => {
    if (e) e.preventDefault();
    const userQuery = (overrideQuery || query).trim();
    if (!userQuery) return;

    setQuery("");
    setMessages((prev) => [...prev, { role: "user", content: userQuery }]);
    setLoading(true);

    try {
      const endpoint = isOrchestratorMode ? "/analytics/orchestrate" : "/ask";
      const res = await axios.post(`${getApiBaseUrl()}${endpoint}`, { query: userQuery, filter_metadata: filterMetadata || undefined });
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content: res.data.answer,
          sources: res.data.sources,
          active_claws: res.data.active_claws,
        },
      ]);
    } catch (err: any) {
      let errorMsg = "Sorry, I encountered an error answering that.";
      
      // Handle rate limits or other specific errors from the backend
      if (err.response?.data?.detail) {
        if (typeof err.response.data.detail === 'string' && err.response.data.detail.toLowerCase().includes('rate limit')) {
          errorMsg = "The AI rate limit has been reached for today. Please wait a while or upgrade your API key to continue chatting.";
        } else {
          errorMsg = `Error: ${err.response.data.detail}`;
        }
      }

      setMessages((prev) => [
        ...prev,
        { role: "ai", content: errorMsg },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSourceClick = (docName: string, docId?: string) => {
    if (loading) return;
    const summaryQuery = `Please provide a comprehensive summary of the document: ${docName}`;
    const filterMetadata = docId ? { doc_id: docId } : undefined;
    handleSubmit(undefined, summaryQuery, filterMetadata);
  };

  const handleClearChat = async () => {
    if (loading || messages.length === 0) return;
    if (!confirmClear) {
      setConfirmClear(true);
      setTimeout(() => setConfirmClear(false), 3000);
      return;
    }
    
    try {
      setLoading(true);
      await axios.delete(`${getApiBaseUrl()}/chat`);
      setMessages([]);
      setConfirmClear(false);
    } catch (err) {
      console.error("Failed to clear chat", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full w-full relative">
      {/* Header Area with Clear Chat button */}
      {messages.length > 0 && (
        <div className="absolute top-4 right-6 z-20">
          <button 
            onClick={handleClearChat}
            disabled={loading}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all backdrop-blur-md active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed ${
              confirmClear 
                ? "bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30" 
                : "bg-white/[0.03] text-white/50 border border-white/[0.05] hover:bg-white/[0.08] hover:border-white/20 hover:text-white/90"
            }`}
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>{confirmClear ? "Click again to confirm" : "Clear Chat"}</span>
          </button>
        </div>
      )}

      {/* Messages Area */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-6 scroll-smooth custom-scrollbar"
      >
        <div className="max-w-4xl mx-auto space-y-8 pb-10">
          {messages.length === 0 ? (
            <div className="h-[60vh] flex flex-col items-center justify-center text-white/30 space-y-5 opacity-70">
              <Bot className="w-12 h-12 opacity-50" />
              <div className="text-center">
                <p className="text-xl font-medium text-white/70 mb-2">How can I help you today?</p>
                <p className="text-sm font-normal max-w-sm text-white/40">
                  Ask anything about the documents in your synced Google Drive.
                </p>
              </div>
            </div>
          ) : (
            messages.map((msg, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex gap-5 w-full"
            >
              <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                msg.role === "user" ? "bg-white/[0.05] text-white/70 border border-white/[0.05]" : "bg-white text-black shadow-[0_0_15px_rgba(255,255,255,0.2)]"
              }`}>
                {msg.role === "user" ? <User className="w-4 h-4" /> : <Sparkles className="w-4 h-4" />}
              </div>
              
              <div className="flex flex-col gap-2 min-w-0 w-full pt-1">
                {msg.active_claws && msg.active_claws.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-1.5 items-center">
                    <span className="text-[9px] uppercase font-bold text-white/30 tracking-wider">Executed Claws:</span>
                    {msg.active_claws.map((clawId) => {
                      const names: Record<string, string> = {
                        data_analyst: "Data Analyst",
                        kpi_monitoring: "KPI Monitoring",
                        anomaly_detection: "Anomaly Detection",
                        customer_segmentation: "Customer Segmentation",
                        business_performance: "Business Performance"
                      };
                      return (
                        <span key={clawId} className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-white/60">
                          {names[clawId] || clawId}
                        </span>
                      );
                    })}
                  </div>
                )}
                
                <div className={`text-[0.95rem] leading-relaxed prose prose-sm prose-invert max-w-none ${
                  msg.role === "user" 
                    ? "text-white/90 font-medium prose-p:text-white/90" 
                    : "text-white/80 prose-p:text-white/80 prose-headings:text-white/90 prose-strong:text-white"
                }`}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>

                {msg.sources && msg.sources.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-3">
                    {msg.sources.map((src, i) => (
                      <div 
                        key={i} 
                        onClick={() => handleSourceClick(src.name, src.doc_id)}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.05] text-white/50 hover:text-white/90 hover:bg-white/[0.08] hover:border-white/20 transition-all cursor-pointer group/src backdrop-blur-sm active:scale-95"
                        title="Click to summarize this document"
                      >
                        <FileText className="w-3 h-3 group-hover/src:text-white" />
                        <span className="truncate max-w-[200px] font-medium">{src.name}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          ))
          )}
          
          {loading && (
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex gap-5"
            >
              <div className="w-8 h-8 rounded-full bg-white text-black flex items-center justify-center shrink-0 shadow-[0_0_15px_rgba(255,255,255,0.2)]">
                <Sparkles className="w-4 h-4" />
              </div>
              <div className="px-5 py-4 rounded-2xl bg-white/[0.03] border border-white/[0.05] rounded-tl-sm flex items-center gap-3 backdrop-blur-md">
                <Loader2 className="w-4 h-4 animate-spin text-white/50" />
                <span className="text-sm text-white/50 font-medium">
                  {isOrchestratorMode ? `[Orchestrator] ${loaderStatus}` : "Analyzing documents..."}
                </span>
              </div>
            </motion.div>
          )}
        </div>
      </div>

      {/* Input Area */}
      <div className="p-6 pt-0 pb-8 relative z-10 bg-gradient-to-t from-[#030303] via-[#030303]/80 to-transparent">
        <div className="max-w-4xl mx-auto relative flex flex-col gap-3">
          
          {/* Mode Switcher */}
          <div className="flex self-start bg-[#0A0A0A] border border-white/10 p-1 rounded-xl text-xs gap-1 shadow-md z-20">
            <button
              type="button"
              onClick={() => setIsOrchestratorMode(false)}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all ${!isOrchestratorMode ? "bg-white text-black font-semibold shadow" : "text-white/40 hover:text-white/70"}`}
            >
              Standard Ask
            </button>
            <button
              type="button"
              onClick={() => setIsOrchestratorMode(true)}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all flex items-center gap-1.5 ${isOrchestratorMode ? "bg-white text-black font-semibold shadow" : "text-white/40 hover:text-white/70"}`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              Claw Orchestrator
            </button>
          </div>

          <form onSubmit={handleSubmit} className="relative flex items-center shadow-[0_0_40px_rgba(0,0,0,0.8)] rounded-2xl">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={isOrchestratorMode ? "Run advanced analytical queries..." : "Ask about your documents..."}
              className={`w-full bg-[#0A0A0A]/90 backdrop-blur-xl border text-white placeholder-white/30 rounded-2xl pl-6 pr-16 py-4 focus:outline-none focus:ring-1 focus:ring-white/20 focus:border-white/20 transition-all text-[0.95rem] ${
                isOrchestratorMode ? "border-white/20 shadow-[0_0_20px_rgba(255,255,255,0.05)]" : "border-white/10"
              }`}
            />
            <button
              type="submit"
              disabled={!query.trim() || loading}
              className="absolute right-2.5 w-10 h-10 rounded-xl bg-white text-black flex items-center justify-center hover:scale-105 active:scale-95 disabled:opacity-50 disabled:hover:scale-100 transition-all shadow-[0_0_15px_rgba(255,255,255,0.15)]"
            >
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>
          <p className="text-center text-[10px] text-white/30 mt-1 font-medium font-sans">
            {isOrchestratorMode ? "Analytical Claws run sequentially. Outputs are aggregated." : "LLaMA 3.3 can make mistakes. Always verify important information."}
          </p>
        </div>
      </div>
    </div>
  );
}
