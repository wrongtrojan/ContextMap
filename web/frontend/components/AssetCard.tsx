"use client";
import { FileText, PlayCircle, Loader2, Cloud, Zap } from 'lucide-react';
import type { Asset } from '../lib/types'; 

interface AssetCardProps {
  asset: Asset;
  onSelect: (id: string) => void;
  isSelected: boolean;
  isUploadingLocal?: boolean; 
}

export default function AssetCard({ asset, onSelect, isSelected, isUploadingLocal }: AssetCardProps) {
  const isIdle = asset.status === 'idle';
  const isSyncing = asset.status === 'syncing';
  const isReady = asset.status === 'ready';
  const isCurrentlyUploading = isIdle && isUploadingLocal;

  return (
    <div 
      onClick={() => isReady && onSelect(asset.id)}
      className={`
        min-w-80 p-3 border rounded flex flex-col justify-between transition-all duration-500 relative overflow-hidden
        ${isSelected 
          ? 'border-dracula-purple ring-1 ring-dracula-purple shadow-[0_0_15px_rgba(189,147,249,0.15)] bg-dracula-current' 
          : 'border-dracula-comment bg-dracula-bg'
        }
        ${isReady 
          ? 'cursor-pointer hover:border-dracula-pink hover:bg-dracula-current' 
          : 'cursor-default opacity-100' /* 强制不置灰，即使不能点击 */
        }
        ${isCurrentlyUploading ? 'border-dracula-orange shadow-[0_0_10px_rgba(255,184,108,0.15)]' : ''}
        ${isSyncing ? 'border-dracula-yellow shadow-[0_0_10px_rgba(241,250,140,0.15)]' : ''}
      `}
    >
      {/* 顶部信息栏 */}
      <div className="flex items-start justify-between z-10">
        <div className="flex items-center gap-3">
          <div className="transition-colors duration-300">
            {asset.type === 'pdf' ? (
              <FileText className={(isReady || isCurrentlyUploading || isSyncing) ? "text-dracula-cyan" : "text-dracula-comment"} size={24} />
            ) : (
              <PlayCircle className={(isReady || isCurrentlyUploading || isSyncing) ? "text-dracula-pink" : "text-dracula-comment"} size={24} />
            )}
          </div>
          
          <div className="overflow-hidden">
            <p className={`text-sm font-bold truncate ${isReady ? 'text-dracula-fg' : 'text-dracula-fg'}`}>
              {asset.name}
            </p>
            <p className="text-[10px] text-dracula-comment uppercase font-mono tracking-tighter">
              {asset.type} {isCurrentlyUploading ? "• Remote_Link" : isIdle ? "• Local_Cache" : "• Cloud_Source"}
            </p>
          </div>
        </div>
        
        <div className={`text-[9px] font-mono px-1.5 py-0.5 rounded border uppercase tracking-widest transition-all ${
          isSyncing ? 'border-dracula-yellow text-dracula-yellow animate-pulse' : 
          isCurrentlyUploading ? 'border-dracula-orange text-dracula-orange animate-pulse' :
          isReady ? 'border-dracula-green text-dracula-green' : 'border-dracula-comment text-dracula-comment bg-dracula-current'
        }`}>
          {isCurrentlyUploading ? 'Transferring' : isIdle ? 'Idle' : asset.status}
        </div>
      </div>

      {/* 中间状态展示区 */}
      <div className="mt-4 min-h-6 z-10">
        {isSyncing ? (
          /* 解析中：展示真实进度条 */
          <>
            <div className="flex justify-between text-[10px] mb-1.5 font-mono text-dracula-yellow">
              <span className="flex items-center gap-1">
                <Loader2 size={10} className="animate-spin" /> ANALYZING_STRUCTURE...
              </span>
              <span>{Math.round(asset.progress)}%</span>
            </div>
            <div className="w-full bg-dracula-current h-1 rounded-full overflow-hidden border border-dracula-comment/20">
              <div 
                className="h-full bg-dracula-cyan shadow-[0_0_8px_rgba(139,233,253,0.6)] transition-all duration-700" 
                style={{ width: `${Math.max(asset.progress, 10)}%` }} 
              />
            </div>
          </>
        ) : isCurrentlyUploading ? (
          /* 上传中：不显示具体进度百分比，显示无限循环滚动条 */
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-dracula-orange">
              <Zap size={10} className="animate-bounce" /> INITIALIZING_STREAMS...
            </div>
            <div className="w-full bg-dracula-current h-1 rounded-full overflow-hidden relative border border-dracula-comment/20">
               <div className="absolute inset-0 bg-dracula-orange/20 animate-pulse" />
               <div className="h-full w-1/3 bg-dracula-orange shadow-[0_0_8px_rgba(255,184,108,0.6)] animate-infinite-scroll" />
            </div>
          </div>
        ) : isIdle ? (
          /* 待机：不置灰，显示提示文字 */
          <div className="flex items-center gap-2 text-[10px] font-mono text-dracula-purple/80">
            <span className="animate-pulse">●</span>
            <span className="italic">{">_ READY_FOR_SYNC_INVOCATION"}</span>
          </div>
        ) : (
          /* 完成状态 */
          <div className="text-[10px] font-mono text-dracula-green/90 font-bold flex items-center gap-1.5">
            <Zap size={10} /> DATA_ANALYSIS_COMPLETED
          </div>
        )}
      </div>

      {/* 底部装饰条 */}
      <div className="flex justify-between mt-3 items-center">
        <div className="flex gap-1">
           {/* 简单的状态点 */}
           <div className={`w-1 h-1 rounded-full ${isReady ? 'bg-dracula-green' : 'bg-dracula-comment'}`} />
           <div className={`w-1 h-1 rounded-full ${isSyncing ? 'bg-dracula-yellow animate-ping' : 'bg-dracula-comment'}`} />
        </div>
        
        {isReady ? (
          <div className="flex items-center gap-1.5 bg-dracula-green/10 px-2 py-0.5 rounded-sm border border-dracula-green/20">
            <div className="w-1.5 h-1.5 rounded-full bg-dracula-green shadow-[0_0_5px_#50fa7b]" />
            <span className="text-[9px] text-dracula-green font-bold font-mono tracking-tighter">DATA_STABLE</span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 opacity-60">
            <Cloud size={11} className="text-dracula-comment" />
            <span className="text-[9px] text-dracula-comment font-mono uppercase tracking-tighter">
              {isCurrentlyUploading ? "Transfer" : "Pending"}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}