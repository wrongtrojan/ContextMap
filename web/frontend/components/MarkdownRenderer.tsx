"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { memo, useMemo, type Components } from "react";
import { BASE_URL } from "../lib/api-config";

const IMAGE_EXT = /\.(png|jpe?g|gif|webp|bmp|svg)$/i;

/** Map broken MinIO / relative figure URLs onto the local media API. */
export function resolveChatImageSrc(src: string | undefined): string | undefined {
  if (!src) return src;
  try {
    const bare = src.split("?")[0] ?? src;
    const filename = decodeURIComponent(bare.split("/").pop() || "");
    if (!filename || !IMAGE_EXT.test(filename)) return src;

    const looksLocalAsset =
      /academic-assets|minio/i.test(src) ||
      src.includes("/api/v1/assets/media/") ||
      !/^https?:\/\//i.test(src);

    if (looksLocalAsset) {
      return `${BASE_URL}/api/v1/assets/media/${encodeURIComponent(filename)}`;
    }
  } catch {
    /* keep original */
  }
  return src;
}

const markdownComponents: Components = {
  table: ({ children }) => (
    <div className="chat-table-wrap my-3 overflow-x-auto rounded-md border border-dracula-comment/30">
      <table className="chat-table w-full border-collapse text-left text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-dracula-current/60 text-dracula-cyan">{children}</thead>
  ),
  th: ({ children }) => (
    <th className="border-b border-dracula-comment/30 px-2.5 py-1.5 font-mono font-medium">{children}</th>
  ),
  td: ({ children }) => (
    <td className="border-b border-dracula-comment/15 px-2.5 py-1.5 align-top text-dracula-fg/90">{children}</td>
  ),
  img: ({ src, alt }) => {
    const resolved = resolveChatImageSrc(typeof src === "string" ? src : undefined);
    if (!resolved) return null;
    return (
      <figure className="my-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={resolved}
          alt={alt || "figure"}
          className="max-w-full rounded-md border border-dracula-comment/30 bg-dracula-bg"
          loading="lazy"
        />
        {alt ? (
          <figcaption className="mt-1 text-[10px] font-mono text-dracula-comment">{alt}</figcaption>
        ) : null}
      </figure>
    );
  },
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-dracula-cyan underline decoration-dracula-cyan/40 hover:decoration-dracula-cyan"
    >
      {children}
    </a>
  ),
};

const MarkdownRenderer = memo(
  ({ content }: { content: string }) => {
    const body = useMemo(() => content || "", [content]);
    return (
      <div className="prose prose-invert chat-prose max-w-none text-sm leading-relaxed">
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[rehypeKatex]}
          components={markdownComponents}
        >
          {body}
        </ReactMarkdown>
      </div>
    );
  },
  (prev, next) => prev.content === next.content,
);

export default MarkdownRenderer;
