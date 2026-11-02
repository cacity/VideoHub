import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Citation, WebSource, time } from './learning-api';

type MdNode = { type: string; value?: string; url?: string; children?: MdNode[] };
export function safeWebUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined;
  } catch { return undefined; }
}

// Convert reference tokens in prose to local links in the Markdown AST.
// Leave code blocks, inline code and existing links untouched.
function referencePlugin(citations: Citation[], sources: WebSource[]) {
  return () => (tree: MdNode) => {
    const visit = (parent: MdNode) => {
      if (!parent.children || ['link', 'code', 'inlineCode', 'html'].includes(parent.type)) return;
      parent.children = parent.children.flatMap(node => {
        if (node.type !== 'text' || !node.value) { visit(node); return [node]; }
        return node.value.split(/(\[cue:[^\]]+\]|\[web:[^\]]+\])/g).filter(Boolean).map(part => {
          const cue = /^\[cue:([^\]]+)\]$/.exec(part);
          const web = /^\[web:([^\]]+)\]$/.exec(part);
          if (cue) {
            const value = citations.find(c => c.id === cue[1]);
            return value ? { type: 'link', url: '#videohub-cue-' + encodeURIComponent(value.id), children: [{ type: 'text', value: time(value.start) }] }
              : { type: 'text', value: '' };
          }
          if (web) {
            const value = sources.find(s => s.id === web[1]);
            return value && safeWebUrl(value.url) ? { type: 'link', url: '#videohub-web-' + encodeURIComponent(value.id), children: [{ type: 'text', value: '[来源 ' + value.id + ']' }] }
              : { type: 'text', value: '' };
          }
          return { type: 'text', value: part };
        });
      });
    };
    visit(tree);
  };
}

export const LearningMarkdown = React.memo(function LearningMarkdown({ text, citations = [], sources = [], seek = () => {} }: {
  text: string; citations?: Citation[]; sources?: WebSource[]; seek?: (t: number) => void;
}) {
  return <div className="learning-markdown"><ReactMarkdown remarkPlugins={[remarkGfm, referencePlugin(citations, sources)]}
    components={{
      a: ({ href, children }) => {
        const cue = citations.find(c => href === '#videohub-cue-' + encodeURIComponent(c.id));
        if (cue) return <button type="button" className="inline-citation" title={cue.text} onClick={() => seek(cue.start)}>{children}</button>;
        const source = sources.find(s => href === '#videohub-web-' + encodeURIComponent(s.id));
        const url = safeWebUrl(source?.url || href || '');
        return url ? <a href={url} title={source?.title} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>;
      },
      // Do not silently load images from model-generated URLs.
      img: ({ alt }) => <span className="markdown-image-alt">[图片：{alt || '未加载'}]</span>,
      table: ({ children }) => <div className="markdown-table"><table>{children}</table></div>,
    }}>{text}</ReactMarkdown></div>;
});
