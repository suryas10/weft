"use client";

import React, { useState, useEffect, useRef } from "react";
import { 
  Play, 
  RotateCcw, 
  Terminal, 
  Zap, 
  FileText, 
  CheckCircle2, 
  AlertTriangle,
  Layers,
  Cpu
} from "lucide-react";

interface SignalData {
  id: string;
  sender: string;
  signal_type: string;
  message: string;
  timestamp: number;
  latency_ms: number;
}

export default function WeftWorkspace() {
  const [isRunning, setIsRunning] = useState(false);
  const [researcherLogs, setResearcherLogs] = useState<string[]>([]);
  const [writerLogs, setWriterLogs] = useState<string[]>([]);
  const [activeSignal, setActiveSignal] = useState<SignalData | null>(null);
  const [canvasContent, setCanvasContent] = useState<string>(
    "# Collaborative Report: AI Agent Architectures\n\n*Click 'Launch Autonomous Workflow' to observe real-time agent coordination via Weft Shared Memory.*"
  );
  
  const wsRef = useRef<WebSocket | null>(null);

  const startSession = () => {
    setIsRunning(true);
    setResearcherLogs([]);
    setWriterLogs([]);
    setActiveSignal(null);
    setCanvasContent("# Collaborative Report: Initializing Agents...");

    // Connect to FastAPI WebSocket
    const ws = new WebSocket("ws://localhost:8000/ws/session-demo-01");
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "agent_thought") {
        if (data.agent === "researcher") {
          setResearcherLogs((prev) => [...prev, data.text]);
        } else if (data.agent === "writer") {
          setWriterLogs((prev) => [...prev, data.text]);
        }
      } else if (data.type === "moss_signal") {
        setActiveSignal(data.signal);
      } else if (data.type === "canvas_update") {
        setCanvasContent(data.content);
      }
    };

    ws.onclose = () => {
      setIsRunning(false);
    };
  };

  const resetSession = () => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    setIsRunning(false);
    setActiveSignal(null);
    setResearcherLogs([]);
    setWriterLogs([]);
    setCanvasContent(
      "# Collaborative Report: AI Agent Architectures\n\n*Ready for execution.*"
    );
  };

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-100 font-sans">
      {/* Top Header */}
      <header className="h-14 border-b border-zinc-800 px-6 flex items-center justify-between bg-zinc-900/50 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="bg-indigo-600 p-1.5 rounded-lg flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Layers className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-base tracking-tight text-white">Weft</span>
              <span className="text-xs bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-full border border-zinc-700">YC Sprint Track 2</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={resetSession}
            disabled={!isRunning && researcherLogs.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-zinc-700 hover:bg-zinc-800 text-xs text-zinc-300 transition-colors disabled:opacity-40"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset
          </button>
          <button
            onClick={startSession}
            disabled={isRunning}
            className="flex items-center gap-2 px-4 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            {isRunning ? "Engine Active..." : "Launch Autonomous Workflow"}
          </button>
        </div>
      </header>

      {/* Main Split Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Side: Notion-style Live Canvas (65% width) */}
        <div className="w-[65%] border-r border-zinc-800 flex flex-col bg-zinc-950 p-8 overflow-y-auto">
          <div className="max-w-3xl w-full mx-auto flex flex-col gap-4">
            <div className="flex items-center gap-2 text-zinc-500 text-xs font-mono">
              <FileText className="w-4 h-4 text-zinc-400" />
              <span>LIVE ARTIFACT CANVAS &bull; REAL-TIME AGENT OUTPUT</span>
            </div>
            
            <div className="min-h-[500px] bg-zinc-900/30 border border-zinc-800/80 rounded-xl p-6 font-mono text-sm leading-relaxed whitespace-pre-wrap text-zinc-200 shadow-2xl">
              {canvasContent}
            </div>
          </div>
        </div>

        {/* Right Side: Weft Zero-Latency Engine Sidebar (35% width) */}
        <div className="w-[35%] bg-zinc-900/30 flex flex-col border-l border-zinc-800/60 overflow-y-auto">
          <div className="p-4 border-b border-zinc-800/80 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-400" />
              <span className="text-xs font-semibold tracking-wide uppercase text-zinc-300">Weft Orchestration Bus</span>
            </div>
            <span className="text-[11px] font-mono text-emerald-400 bg-emerald-950/60 border border-emerald-800/40 px-2 py-0.5 rounded">
              Moss In-Process: Active
            </span>
          </div>

          <div className="flex-1 p-4 flex flex-col gap-4">
            {/* Researcher Agent Box */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex flex-col gap-2">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                <span className="text-xs font-semibold text-blue-400 flex items-center gap-1.5">
                  <Terminal className="w-3.5 h-3.5" /> Researcher Agent
                </span>
                <span className="text-[10px] text-zinc-500 font-mono">Parallel Worker 1</span>
              </div>
              <div className="text-xs font-mono text-zinc-400 min-h-[60px] max-h-[100px] overflow-y-auto flex flex-col gap-1">
                {researcherLogs.length === 0 ? (
                  <span className="text-zinc-600 italic">Awaiting task initiation...</span>
                ) : (
                  researcherLogs.map((log, i) => (
                    <div key={i} className="text-zinc-300">&gt; {log}</div>
                  ))
                )}
              </div>
            </div>

            {/* Moss Shared Memory Layer (Center Highlight) */}
            <div className={`border rounded-lg p-3.5 transition-all duration-300 ${
              activeSignal 
                ? "bg-amber-950/20 border-amber-500/50 shadow-lg shadow-amber-500/10" 
                : "bg-zinc-900/60 border-zinc-800"
            }`}>
              <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80">
                <span className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                  <Zap className="w-4 h-4 fill-amber-400 text-amber-400" /> Moss Shared Memory Bus
                </span>
                <span className="text-[10px] font-mono text-zinc-400">Zero-Latency Sync</span>
              </div>

              <div className="mt-2.5">
                {activeSignal ? (
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 bg-rose-950 text-rose-300 border border-rose-800/60 rounded">
                        SIGNAL: {activeSignal.signal_type}
                      </span>
                      <span className="text-xs font-mono text-emerald-400 font-semibold">
                        ⚡ {activeSignal.latency_ms} ms
                      </span>
                    </div>
                    <p className="text-xs font-mono text-zinc-300 bg-zinc-950/80 p-2.5 rounded border border-zinc-800/80 leading-relaxed">
                      {activeSignal.message}
                    </p>
                    <div className="flex items-center gap-1.5 text-[10px] text-zinc-500 font-mono">
                      <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                      <span>Transmitted in-process to all active agents</span>
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-zinc-600 font-mono py-3 text-center">
                    SessionIndex idle &bull; Polling latency &lt;3ms
                  </div>
                )}
              </div>
            </div>

            {/* Writer Agent Box */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex flex-col gap-2">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                <span className="text-xs font-semibold text-purple-400 flex items-center gap-1.5">
                  <Terminal className="w-3.5 h-3.5" /> Writer Agent
                </span>
                <span className="text-[10px] text-zinc-500 font-mono">Parallel Worker 2</span>
              </div>
              <div className="text-xs font-mono text-zinc-400 min-h-[60px] max-h-[100px] overflow-y-auto flex flex-col gap-1">
                {writerLogs.length === 0 ? (
                  <span className="text-zinc-600 italic">Awaiting task initiation...</span>
                ) : (
                  writerLogs.map((log, i) => (
                    <div key={i} className="text-zinc-300">&gt; {log}</div>
                  ))
                )}
              </div>
            </div>

            {/* Technical Proof Card */}
            <div className="mt-auto bg-zinc-950 border border-zinc-800/80 rounded-lg p-3 text-[11px] font-mono text-zinc-400 flex flex-col gap-1.5">
              <div className="text-zinc-300 font-semibold flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5 text-indigo-400" /> Architecture Advantage
              </div>
              <div className="text-zinc-500">
                Traditional Vector DB: <span className="text-rose-400">~450ms</span>
              </div>
              <div className="text-zinc-500">
                Weft In-Process Memory: <span className="text-emerald-400">&lt;5ms</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}