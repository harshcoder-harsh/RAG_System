"use client";

import { ChatInterface } from "@/components/ChatInterface";
import { SyncPanel } from "@/components/SyncPanel";
import { DocsPanel } from "@/components/DocsPanel";
import { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import axios from "axios";
import { Sparkles } from "lucide-react";
import Link from "next/link";
import { getApiBaseUrl } from "@/utils/apiBaseUrl";

function DashboardContent() {
  const [docs, setDocs] = useState<{ id: string, name: string, status: string }[]>([]);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [sidebarTab, setSidebarTab] = useState<"docs" | "claws">("docs");
  const searchParams = useSearchParams();
  const router = useRouter();
  const shouldAutoSync = searchParams.get("sync") === "true";

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const res = await axios.get(`${getApiBaseUrl()}/auth/status`);
        if (res.data.authenticated) {
          setIsAuthenticated(true);
        } else {
          router.push("/");
        }
      } catch (error) {
        console.error("Failed to check auth status:", error);
        router.push("/");
      }
    };
    
    checkAuth();
  }, [router]);

  useEffect(() => {
    const fetchDocs = async () => {
      try {
        const res = await axios.get(`${getApiBaseUrl()}/documents`);
        if (res.data && Array.isArray(res.data.documents)) {
          setDocs(res.data.documents);
        }
      } catch (err) {
        // ignore
      }
    };

    if (isAuthenticated) {
      fetchDocs();
    }
  }, [isAuthenticated]);

  const handleSyncSuccess = (newDocs: { id: string, name: string, status: string }[]) => {
    setDocs((prev) => {
      // Prevent duplicates by checking doc.id
      const existingIds = new Set(prev.map(d => d.id));
      const uniqueNewDocs = newDocs.filter(d => !existingIds.has(d.id));
      return [...uniqueNewDocs, ...prev];
    });
  };

  const handleDocumentClick = (doc: { id: string, name: string }) => {
    // We can dispatch a custom event that ChatInterface will listen to
    window.dispatchEvent(new CustomEvent('requestDocumentSummary', { detail: { docId: doc.id, docName: doc.name } }));
  };

  if (isAuthenticated === null) {
    return <div className="flex items-center justify-center min-h-screen text-white bg-[#030303]">Verifying access...</div>;
  }

  return (
    <div className="flex h-screen w-full bg-[#030303] text-white font-sans overflow-hidden selection:bg-white selection:text-black">
      
      {/* --- PREMIUM BACKGROUND EFFECTS --- */}
      <div className="absolute inset-0 z-0 opacity-[0.03] mix-blend-overlay pointer-events-none" style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")` }} />
      <div className="absolute top-[-10%] left-1/2 -translate-x-1/2 w-[100vw] max-w-[1200px] h-[600px] bg-[radial-gradient(ellipse_at_top,rgba(255,255,255,0.06),transparent_70%)] pointer-events-none z-0" />
      <div className="absolute inset-0 z-0 bg-[linear-gradient(to_right,#8080800A_1px,transparent_1px),linear-gradient(to_bottom,#8080800A_1px,transparent_1px)] bg-[size:32px_32px] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_0%,#000_70%,transparent_100%)] pointer-events-none" />

      {/* Left Sidebar */}
      <div className="w-[320px] shrink-0 border-r border-white/[0.08] bg-[#050505]/80 backdrop-blur-2xl flex flex-col relative z-10 shadow-[4px_0_24px_rgba(0,0,0,0.5)]">
        
        {/* App Brand Header */}
        <Link href="/" className="h-16 flex items-center px-6 border-b border-white/[0.06] hover:bg-white/[0.02] transition-colors cursor-pointer group">
          <div className="w-7 h-7 rounded-lg bg-white flex items-center justify-center mr-3 shadow-[0_0_15px_rgba(255,255,255,0.3)] group-hover:scale-105 transition-transform">
            <Sparkles className="w-4 h-4 text-black" />
          </div>
          <span className="font-semibold tracking-wide text-[0.95rem] text-white/90 group-hover:text-white transition-colors">Highwatch RAG</span>
        </Link>

        {/* Sync Section */}
        <div className="p-5 border-b border-white/[0.06]">
          <SyncPanel onSyncSuccess={handleSyncSuccess} autoSync={shouldAutoSync} />
        </div>

        {/* Tab Selector */}
        <div className="flex px-5 py-2 border-b border-white/[0.06] bg-black/20 gap-2">
          <button
            onClick={() => setSidebarTab("docs")}
            className={`flex-1 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all border ${
              sidebarTab === "docs" 
                ? "bg-white/[0.08] text-white border-white/10 shadow-inner" 
                : "text-white/40 border-transparent hover:text-white/70"
            }`}
          >
            Knowledge Base
          </button>
          <button
            onClick={() => setSidebarTab("claws")}
            className={`flex-1 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all border ${
              sidebarTab === "claws" 
                ? "bg-white/[0.08] text-white border-white/10 shadow-inner" 
                : "text-white/40 border-transparent hover:text-white/70"
            }`}
          >
            Analytical Claws
          </button>
        </div>

        {/* Docs or Claws Section */}
        <div className="flex-1 flex flex-col min-h-0 p-5 pt-4 overflow-y-auto custom-scrollbar">
          {sidebarTab === "docs" ? (
            <div className="flex-1 flex flex-col min-h-0">
              <h3 className="text-[0.7rem] font-semibold text-white/40 uppercase tracking-[0.15em] mb-4 pl-1">Knowledge Base</h3>
              <DocsPanel docs={docs} onDocumentClick={handleDocumentClick} />
            </div>
          ) : (
            <div className="space-y-4">
              <h3 className="text-[0.7rem] font-semibold text-white/40 uppercase tracking-[0.15em] mb-2 pl-1">Claw Registry</h3>
              
              {[
                { name: "Data Analyst Claw", role: "Raw Data Specialist", color: "bg-blue-500" },
                { name: "KPI Monitoring Claw", role: "Metric Sentinel", color: "bg-green-500" },
                { name: "Anomaly Detection Claw", role: "Operational Risk Guard", color: "bg-red-500" },
                { name: "Customer Segmentation Claw", role: "Cohort Demographer", color: "bg-purple-500" },
                { name: "Business Performance Claw", role: "Strategic Synthesizer", color: "bg-amber-500" }
              ].map((claw, idx) => (
                <div key={idx} className="p-3 rounded-xl bg-white/[0.01] border border-white/[0.04] hover:bg-white/[0.03] transition-all flex flex-col gap-1 backdrop-blur-md">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-white/90">{claw.name}</span>
                    <span className="flex h-2 w-2 relative">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white/20 opacity-75"></span>
                      <span className={`relative inline-flex rounded-full h-2 w-2 ${claw.color}`}></span>
                    </span>
                  </div>
                  <span className="text-[9px] text-white/40">{claw.role}</span>
                </div>
              ))}

              <div className="pt-4 border-t border-white/[0.06]">
                <h4 className="text-[0.7rem] font-semibold text-white/40 uppercase tracking-[0.15em] mb-3 pl-1">Analysis Templates</h4>
                <button
                  onClick={() => {
                    window.dispatchEvent(new CustomEvent('loadTemplate', { detail: { 
                      query: "Incoming Request: Q2 Partner Performance & Risk Assessment\n\nExecute a sequential analysis using the Data Analyst Claw, the Anomaly Detection Claw, and the Customer Segmentation Claw to deliver a unified, executive-ready diagnostic report." 
                    }}));
                  }}
                  className="w-full text-left p-3 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 hover:border-white/20 transition-all flex flex-col gap-1 active:scale-[0.98]"
                >
                  <span className="text-[11px] font-semibold text-white">Q2 Partner Assessment</span>
                  <span className="text-[9px] text-white/50 leading-relaxed">Runs sequential analysis (Data Analyst &rarr; Anomaly &rarr; Segmentation) for network report.</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right Column: Chat */}
      <div className="flex-1 relative z-10 flex flex-col min-w-0 bg-transparent">
        <ChatInterface />
      </div>
    </div>
  );
}

export default function Dashboard() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-screen text-white bg-[#030303]">Loading...</div>}>
      <DashboardContent />
    </Suspense>
  );
}
