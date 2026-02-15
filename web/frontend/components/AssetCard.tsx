"use client";
import { FileText, PlayCircle, Loader2, UploadCloud } from 'lucide-react';
import type { Asset } from '../lib/types'; 

interface AssetCardProps {
  asset: Asset;
  onSelect: (id: string) => void;
  isSelected: boolean;
}

export default function AssetCard({ asset, onSelect, isSelected }: AssetCardProps) {
  // 状态样式映射
  const isIdle = asset.status === 'idle';
  const isSyncing = asset.status === 'syncing';
  const isReady = asset.status === 'ready';

  return (
    <div 
      onClick={() => isReady && onSelect(asset.id)}
      className={`
        min-w-80 p-3 border rounded flex flex-col justify-between transition-all duration-300
        ${isSelected 
          ? 'border-dracula-purple ring-1 ring-dracula-purple shadow-[0_0_15px_rgba(189,147,249,0.15)] bg-dracula-current' 
          : 'border-dracula-comment bg-dracula-bg'
        }
        ${isReady 
          ? 'cursor-pointer hover:border-dracula-pink hover:bg-dracula-current opacity-100' 
          : 'cursor-not-allowed'
        }
        ${isIdle ? 'border-dashed opacity-40 grayscale' : 'border-solid'}
      `}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          {/* 图标根据状态变换颜色 */}
          <div className={`${isIdle ? 'text-dracula-comment' : ''}`}>
            {asset.type === 'pdf' ? (
              <FileText className={isReady ? "text-dracula-cyan" : "text-dracula-comment"} size={24} />
            ) : (
              <PlayCircle className={isReady ? "text-dracula-pink" : "text-dracula-comment"} size={24} />
            )}
          </div>
          
          <div className="overflow-hidden">
            <p className={`text-sm font-bold truncate ${isReady ? 'text-dracula-fg' : 'text-dracula-comment'}`}>
              {asset.name}
            </p>
            <p className="text-[10px] text-dracula-comment uppercase font-mono tracking-tighter">
              {asset.type} {isIdle && "• Pending"}
            </p>
          </div>
        </div>
        
        {/* 状态 Badge */}
        <div className={`text-[10px] font-mono px-1.5 py-0.5 rounded border uppercase tracking-widest ${
          isSyncing ? 'border-dracula-yellow text-dracula-yellow animate-pulse' : 
          isReady ? 'border-dracula-green text-dracula-green' : 'border-dracula-comment text-dracula-comment bg-dracula-current'
        }`}>
          {isIdle ? 'UPLOADED' : asset.status}
        </div>
      </div>

      <div className="mt-3 min-h-5">
        {isSyncing ? (
          <>
            <div className="flex justify-between text-[10px] mb-1 font-mono text-dracula-yellow">
              <span className="flex items-center gap-1">
                <Loader2 size={10} className="animate-spin" /> ANALYZING_CORE...
              </span>
              <span>{Math.round(asset.progress)}%</span>
            </div>
            <div className="w-full bg-dracula-current h-1.5 rounded-full overflow-hidden border border-dracula-comment/30">
              <div 
                className="bg-dracula-cyan h-full transition-all duration-500 shadow-[0_0_8px_rgba(139,233,253,0.5)]" 
                style={{ width: `${asset.progress}%` }}
              />
            </div>
          </>
        ) : isIdle ? (
          <div className="text-[10px] font-mono text-dracula-comment italic">
            {">_ WAITING_FOR_SYNC_COMMAND"}
          </div>
        ) : (
          <div className="text-[10px] font-mono text-dracula-comment opacity-0 group-hover:opacity-100">
            {">_ ACCESS_GRANTED"}
          </div>
        )}
      </div>

      {/* 右下角状态提示 */}
      <div className="flex justify-end mt-2 items-center gap-2">
        {isIdle && (
          <div className="flex items-center gap-1.5">
            <UploadCloud size={12} className="text-dracula-comment" />
            <span className="text-[9px] text-dracula-comment font-mono uppercase">Stored_on_Disk</span>
          </div>
        )}
        {isSyncing && <span className="text-[9px] text-dracula-yellow font-mono animate-pulse">VRAM_ACTIVE</span>}
        {isReady && (
          <div className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-dracula-green shadow-[0_0_5px_#50fa7b]" />
            <span className="text-[10px] text-dracula-green font-bold font-mono">STABLE</span>
          </div>
        )}
      </div>
    </div>
  );
}