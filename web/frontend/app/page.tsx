"use client";
import { useState, useEffect } from 'react';
import { RefreshCw, Upload, Activity, MessageSquare, FileText, PanelLeftClose, PanelLeftOpen, Send } from 'lucide-react';
import type { Asset } from '../lib/types';
import AssetCard from '../components/AssetCard';
import { API_ENDPOINTS } from '../lib/api-config';

export default function ScaffoldingPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [isOutlineOpen, setIsOutlineOpen] = useState(true);

  // 核心状态锁定
  const [isSyncing, setIsSyncing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  // --- 1. 归一化与工具函数 ---
  const normalizeAsset = (backendAsset: any): Asset => {
    const id = backendAsset.asset_id || backendAsset.id;
    // 强制检查后端返回的 status 字段
    const isReady = backendAsset.status === 'ready';

    return {
      id: id,
      name: backendAsset.display_name || backendAsset.name || 'Unknown Asset',
      type: backendAsset.type || (backendAsset.name?.endsWith('.mp4') ? 'video' : 'pdf'),
      status: isReady ? 'ready' : (backendAsset.status || 'idle'),
      progress: isReady ? 100 : (backendAsset.progress || 0),
      outline: backendAsset.outline || [],
      raw_url: backendAsset.raw_url,
      preview_url: backendAsset.preview_url
    };
  };

  const formatAnchor = (anchor: number, type?: 'pdf' | 'video') => {
    if (type === 'video') {
      const minutes = Math.floor(anchor / 60);
      const seconds = Math.floor(anchor % 60);
      return `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }
    return `P.${Math.floor(anchor) + 1}`;
  };

  // --- 2. 页面刷新拦截 ---
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isUploading || isSyncing) {
        e.preventDefault();
        e.returnValue = "系统正在处理中，刷新将导致进度丢失";
        return e.returnValue;
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isUploading, isSyncing]);

  // --- 3. 初始加载 ---
  useEffect(() => {
    const initLoad = async () => {
      try {
        const res = await fetch(API_ENDPOINTS.ASSET_MAP);
        const data = await res.json();
        if (data.status === "success" && Array.isArray(data.data)) {
          setAssets(data.data.map(normalizeAsset));
        }
      } catch (e) {
        console.error("Init load failed", e);
      }
    };
    initLoad();
  }, []);

  // --- 4. 修改后的核心状态轮询 ---
  useEffect(() => {
    let timer: NodeJS.Timeout;

    const fetchStatus = async () => {
      try {
        const res = await fetch(API_ENDPOINTS.STATUS);
        const data = await res.json();

        // 【核心修改点】: 当状态变为 IDLE 且前端正在同步时
        if (data.status === "IDLE" && isSyncing) {
          // 1. 第一步：强行视觉收尾（UI 瞬间满格）
          setAssets(prev => prev.map(asset => ({
            ...asset,
            progress: 100,
            status: 'ready' // 先在前端乐观地更新为 ready
          })));

          // 2. 第二步：短暂停留后关闭同步锁，并从后端同步最终数据（包含大纲等）
          setTimeout(async () => {
            setIsSyncing(false);
            const assetRes = await fetch(API_ENDPOINTS.ASSET_MAP);
            const assetData = await assetRes.json();
            if (assetData.status === "success") {
              setAssets(assetData.data.map(normalizeAsset));
            }
          }, 800); // 给 800ms 让用户看清“满格”的状态
          return;
        }

        // 正在处理中
        if (data.status === "INGESTING") {
          setIsSyncing(true);
          setAssets(prev => prev.map(asset => {
            // 只更新非 ready 的资产
            if (asset.status !== 'ready') {
              // 优先级：Pipeline 进度 > AI-Synthesis 进度 > 保底 15%
              const prog = (data.progress["Pipeline"] ?? data.progress["AI-Synthesis"]) ?? 15;
              return { ...asset, status: 'syncing', progress: prog };
            }
            return asset;
          }));
        }
      } catch (e) {
        console.error("Polling error:", e);
      }
    };

    if (isSyncing) {
      timer = setInterval(fetchStatus, 2000);
    }

    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isSyncing]);

  // --- 5. 业务逻辑函数 ---
  const handleGlobalSync = async () => {
    if (assets.length === 0 || isSyncing || isUploading) return;

    setIsSyncing(true);
    // 初始点击后，给一个 10% 的初始视觉反馈
    setAssets(prev => prev.map(a => a.status !== 'ready' ? { ...a, status: 'syncing', progress: 10 } : a));
    
    try {
      await fetch(API_ENDPOINTS.SYNC, { method: 'POST' });
    } catch (err) {
      console.error("Sync trigger failed:", err);
      setIsSyncing(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile || isSyncing) return;

    setIsUploading(true);
    const tempId = `temp-${Date.now()}`;
    const newAsset: Asset = {
      id: tempId,
      name: selectedFile.name,
      type: selectedFile.name.toLowerCase().endsWith('.mp4') ? 'video' : 'pdf',
      status: 'idle',
      progress: 0
    };

    setAssets(prev => [newAsset, ...prev]);
    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const response = await fetch(API_ENDPOINTS.UPLOAD, { method: 'POST', body: formData });
      const data = await response.json();

      if (data.status === "success") {
        setAssets(prev => prev.map(a =>
          a.id === tempId ? { ...a, id: data.filename, status: 'idle', progress: 100 } : a
        ));
      } else {
        setAssets(prev => prev.filter(a => a.id !== tempId));
        alert("Upload Failed: " + data.message);
      }
    } catch (err) {
      setAssets(prev => prev.filter(a => a.id !== tempId));
    } finally {
      setIsUploading(false);
      e.target.value = "";
    }
  };

  // --- 渲染部分保持一致，仅确保 AssetCard 接收正确的 props ---
  return (
    <div className="flex flex-col h-screen w-full bg-dracula-bg text-dracula-fg overflow-hidden font-sans">
      <header className="h-12 border-b border-dracula-comment shrink-0 flex items-center px-4 justify-between bg-dracula-bg z-20">
        <div className="flex items-center gap-2 font-bold text-dracula-purple">
          <Activity size={18} className="text-dracula-cyan" />
          Multi-Modal Academic Agent <span className="text-dracula-comment font-normal text-sm">| Lab</span>
        </div>
        
        <div className="flex items-center gap-3 px-3 py-1 bg-dracula-current rounded-full border border-dracula-comment">
           <div className={`w-2 h-2 rounded-full shadow-sm ${
             isUploading ? 'bg-dracula-orange animate-pulse' : 
             isSyncing ? 'bg-dracula-yellow animate-pulse' : 'bg-dracula-green opacity-50'
           }`} />
           <span className="text-[10px] font-mono font-bold tracking-tighter">
             {isUploading ? "UPLOADING" : isSyncing ? "INGESTING" : "SYSTEM_IDLE"}
           </span>
        </div>
      </header>

      <main className="flex flex-1 overflow-hidden min-h-0">
        <div className="flex-1 flex border-r border-dracula-comment relative overflow-hidden bg-dracula-bg">
          <aside className={`${isOutlineOpen ? 'w-80' : 'w-0'} transition-all duration-300 border-r border-dracula-comment bg-dracula-bg overflow-y-auto custom-scrollbar`}>
            <div className="p-4 w-80">
              <h3 className="text-xs font-bold text-dracula-comment uppercase mb-4 tracking-widest flex items-center gap-2">
                <Activity size={14} /> 结构化大纲
              </h3>
              
              {selectedAssetId ? (
                <div className="space-y-4">
                  {assets.find(a => a.id === selectedAssetId)?.outline?.map((item, idx) => (
                    <div key={idx} className="group">
                      <button 
                        onClick={() => {}} // 待实现的 handleJump
                        className="w-full text-left text-sm font-bold text-dracula-cyan hover:text-dracula-pink transition-colors mb-1"
                      >
                        {idx + 1}. {item.heading}
                      </button>
                      <p className="text-[10px] text-dracula-comment leading-relaxed mb-2 line-clamp-2 italic">
                        {item.summary}
                      </p>
                      
                      <div className="pl-3 border-l border-dracula-comment space-y-2 ml-1">
                        {item.sub_points?.map((sub, sIdx) => (
                          <div key={sIdx} className="hover:bg-dracula-current p-1 rounded transition-all cursor-pointer">
                            <div className="text-[11px] text-dracula-fg flex justify-between">
                              <span className="truncate pr-2">• {sub.heading}</span>
                              <span className="text-dracula-purple font-mono shrink-0">
                                {formatAnchor(sub.anchor, assets.find(a => a.id === selectedAssetId)?.type)}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 text-sm border border-dashed border-dracula-comment text-dracula-comment font-mono italic text-center rounded">
                  {"> WAIT_SELECT"}
                </div>
              )}
            </div>
          </aside>

          <section className="flex-1 bg-dracula-current relative flex items-center justify-center">
            <button onClick={() => setIsOutlineOpen(!isOutlineOpen)} className="absolute left-4 top-4 z-30 p-2 bg-dracula-bg border border-dracula-comment rounded hover:bg-dracula-comment text-dracula-fg transition-colors">
              {isOutlineOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
            </button>
            <div className="flex flex-col items-center gap-2 text-dracula-comment">
              <FileText size={48} />
              <p className="text-sm italic font-mono uppercase tracking-widest">Viewer_Standby</p>
            </div>
          </section>
        </div>

        <aside className="w-112.5 flex flex-col bg-dracula-bg shrink-0 overflow-hidden border-l border-dracula-comment">
          <div className="p-4 border-b border-dracula-comment flex items-center gap-2 font-medium text-dracula-pink">
            <MessageSquare size={18} /> 智能研讨
          </div>
          <div className="flex-1 p-4 overflow-y-auto space-y-4 font-mono text-sm">
            <div className="bg-dracula-current p-3 rounded border border-dracula-comment text-dracula-fg">
              [SYSTEM]: 准备就绪。请选择已解析的资产开始研讨。
            </div>
          </div>
          <div className="p-4 border-t border-dracula-comment bg-dracula-bg">
            <div className="relative">
              <input type="text" placeholder="Terminal > _" className="w-full bg-dracula-current text-dracula-fg pl-4 pr-10 py-3 rounded border border-dracula-comment focus:border-dracula-purple focus:outline-none font-mono" />
              <button className="absolute right-2 top-2.5 p-1.5 text-dracula-purple hover:text-dracula-pink"><Send size={20} /></button>
            </div>
          </div>
        </aside>
      </main>

      <footer className="h-64 border-t border-dracula-comment bg-dracula-bg p-4 z-10 shrink-0 shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4">
            <h3 className="text-sm font-bold flex items-center gap-2">
              <Upload size={16} className="text-dracula-green" /> 学习资产管理系统
            </h3>
            
            {assets.some(a => a.status === 'idle') && (
              <button 
                onClick={handleGlobalSync}
                disabled={isSyncing || isUploading}
                className="flex items-center gap-2 px-3 py-1 bg-dracula-current border border-dracula-purple text-dracula-purple rounded text-[10px] font-bold hover:bg-dracula-purple hover:text-dracula-bg transition-all disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <RefreshCw size={12} className={isSyncing ? 'animate-spin' : ''} />
                {isSyncing ? "ANALYZING_ALL..." : isUploading ? "WAIT_FOR_UPLOAD" : "SYNC ALL ASSETS"}
              </button>
            )}
          </div>

          <label className={`px-4 py-1.5 rounded text-xs font-bold transition-all uppercase cursor-pointer ${(isSyncing || isUploading) ? 'bg-dracula-comment text-dracula-bg cursor-not-allowed opacity-50' : 'bg-dracula-green text-dracula-bg hover:bg-dracula-yellow'}`}>
            {isUploading ? "Uploading..." : "Upload New"}
            <input type="file" className="hidden" onChange={handleUpload} accept=".pdf,.mp4" disabled={isSyncing || isUploading} />
          </label>
        </div>

        <div className="flex gap-4 overflow-x-auto min-h-32 pb-2 custom-scrollbar">
          {assets.map(asset => (
            <div key={asset.id} className={`transition-all duration-500 ${isUploading && asset.id.toString().startsWith('temp') ? 'opacity-60' : 'opacity-100'}`}>
              <AssetCard 
                asset={asset} 
                onSelect={(id) => setSelectedAssetId(id)}
                isSelected={selectedAssetId === asset.id}
                isUploadingLocal={isUploading && asset.id.toString().startsWith('temp')}
              />
            </div>
          ))}
        </div>
      </footer>
    </div>
  );
}