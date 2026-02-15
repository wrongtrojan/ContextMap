"use client";
import { useState } from 'react';
import { RefreshCw, Upload, Activity, MessageSquare, FileText, PanelLeftClose, PanelLeftOpen, Send } from 'lucide-react';
import type { Asset } from '../lib/types';
import AssetCard from '../components/AssetCard';
import { API_ENDPOINTS } from '../lib/api-config';

export default function ScaffoldingPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [isOutlineOpen, setIsOutlineOpen] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false); // 全局同步状态
  const [isUploading, setIsUploading] = useState(false);

  // 1. 全局同步解析函数
  const handleGlobalSync = async () => {
    if (assets.length === 0 || isSyncing || isUploading) return;

    setIsSyncing(true);
    // 先把所有非 ready 的资产状态设为 syncing
    setAssets(prev => prev.map(a => a.status !== 'ready' ? { ...a, status: 'syncing', progress: 5 } : a));

    try {
      // 对接 post /api/v1/ingest/sync
      const response = await fetch(API_ENDPOINTS.SYNC, { method: 'POST' });
      
      if (response.ok) {
        // TODO: 这里开启轮询 get /api/v1/ingest/status
        // 演示目的：模拟解析完成
        setTimeout(() => {
          setAssets(prev => prev.map(a => ({ ...a, status: 'ready', progress: 100 })));
          setIsSyncing(false);
        }, 3000);
      }
    } catch (err) {
      console.error("Sync error:", err);
      setIsSyncing(false);
    }
  };

  // 2. 上传逻辑保持不变，但新资产默认为 'idle'
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile || isUploading || isSyncing) return;

    setIsUploading(true); // 开启上传锁

    // 1. 生成唯一 ID 和临时资产对象 (乐观更新)
    const tempId = `temp-${Date.now()}`;
    const newAsset: Asset = {
      id: tempId,
      name: selectedFile.name,
      type: selectedFile.name.toLowerCase().endsWith('.mp4') ? 'video' : 'pdf',
      status: 'idle', // 初始为灰色 idle 状态
      progress: 0
    };

    // 立即更新 UI，让用户看到卡片出现在左侧第一位
    setAssets(prev => [newAsset, ...prev]);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      // 2. 使用 XMLHttpRequest 或 Fetch 控制器来追踪真实上传进度
      // 注意：普通 fetch 无法原生追踪上传进度，我们这里采用“模拟进度”或直接等待
      // 为了代码简洁，我们先实现逻辑闭环
      const response = await fetch(API_ENDPOINTS.UPLOAD, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (data.status === "success") {
        // 3. 上传完成，将卡片变为“就绪”或保持“待同步”
        setAssets(prev => prev.map(a => 
          a.id === tempId ? { ...a, id: data.filename, status: 'idle', progress: 100 } : a
        ));
        console.log("Upload finished. Asset ready for SYNC.");
      } else {
        // 失败处理：移除卡片
        setAssets(prev => prev.filter(a => a.id !== tempId));
        alert("Upload Failed: " + data.message);
      }
    } catch (err) {
      setAssets(prev => prev.filter(a => a.id !== tempId));
      console.error("Network error:", err);
    } finally {
      setIsUploading(false); // 释放上传锁
      e.target.value = "";
    }
  };

  return (
    <div className="flex flex-col h-screen w-full bg-dracula-bg text-dracula-fg overflow-hidden">
      <header className="h-12 border-b border-dracula-comment shrink-0 flex items-center px-4 justify-between bg-dracula-bg z-20">
        <div className="flex items-center gap-2 font-bold text-dracula-purple">
          <Activity size={18} className="text-dracula-cyan" />
          Multi-Modal Academic Agent <span className="text-dracula-comment font-normal text-sm">| Lab</span>
        </div>
      </header>

      <main className="flex flex-1 overflow-hidden min-h-0">
        {/* 左侧区域 */}
        <div className="flex-1 flex border-r border-dracula-comment relative overflow-hidden bg-dracula-bg">
          <aside className={`${isOutlineOpen ? 'w-80' : 'w-0'} transition-all duration-300 border-r border-dracula-comment bg-dracula-bg overflow-y-auto`}>
            <div className="p-4 w-80">
              <h3 className="text-xs font-bold text-dracula-comment uppercase mb-4 tracking-widest">结构化大纲</h3>
              <div className="p-2 text-sm border border-transparent text-dracula-cyan font-mono italic">
                {selectedAssetId ? "> 加载资产大纲..." : "> 等待选择资产"}
              </div>
            </div>
          </aside>

          <section className="flex-1 bg-dracula-current relative flex items-center justify-center">
            <button 
              onClick={() => setIsOutlineOpen(!isOutlineOpen)}
              className="absolute left-4 top-4 z-30 p-2 bg-dracula-bg border border-dracula-comment rounded hover:bg-dracula-comment text-dracula-fg transition-colors"
            >
              {isOutlineOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
            </button>
            <div className="flex flex-col items-center gap-2 text-dracula-comment">
              <FileText size={48} />
              <p className="text-sm italic font-mono uppercase">Viewer_Standby</p>
            </div>
          </section>
        </div>
        {/* 右侧对话区 - 宽度固定为 450px */}
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

      {/* 3. 底部管理区域 - 满足你的全量解析需求 */}
      <footer className="h-64 border-t border-dracula-comment bg-dracula-bg p-4 z-10 shrink-0">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4">
            <h3 className="text-sm font-bold flex items-center gap-2">
              <Upload size={16} className="text-dracula-green" /> 学习资产管理系统
            </h3>
            
            {/* 全量解析按钮 */}
            {assets.some(a => a.status === 'idle') && (
              <button 
                onClick={handleGlobalSync}
                disabled={isSyncing}
                className="flex items-center gap-2 px-3 py-1 bg-dracula-current border border-dracula-purple text-dracula-purple rounded text-[10px] font-bold hover:bg-dracula-purple hover:text-dracula-bg transition-all disabled:opacity-50"
              >
                <RefreshCw size={12} className={isSyncing ? 'animate-spin' : ''} />
                {isSyncing ? "ANALYZING_ALL..." : "SYNC ALL ASSETS"}
              </button>
            )}
          </div>

          <label className="bg-dracula-green text-dracula-bg px-4 py-1.5 rounded text-xs font-bold hover:bg-dracula-yellow transition-all uppercase cursor-pointer">
            Upload New
            <input type="file" className="hidden" onChange={handleUpload} accept=".pdf,.mp4" />
          </label>
        </div>

        <div className="flex gap-4 overflow-x-auto min-h-32">
          {assets.length === 0 ? (
            <div className="flex-1 border border-dracula-comment border-dashed rounded flex items-center justify-center text-dracula-comment text-xs italic font-mono">
              {"[WAITING_FOR_UPLOAD]"}
            </div>
          ) : (
            assets.map(asset => (
              <AssetCard 
                key={asset.id} 
                asset={asset} 
                onSelect={(id) => setSelectedAssetId(id)}
                isSelected={selectedAssetId === asset.id}
              />
            ))
          )}
        </div>
      </footer>
    </div>
  );
}