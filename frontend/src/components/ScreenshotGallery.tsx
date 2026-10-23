import { t } from '../i18n/core';
import { useState } from 'react';
import { X, Camera } from 'lucide-react';
import type { Screenshot } from '../types';

interface ScreenshotGalleryProps {
  screenshots: Screenshot[];
}

export default function ScreenshotGallery({ screenshots }: ScreenshotGalleryProps) {
  const [failed, setFailed] = useState<Record<number, boolean>>({});
  const [selected, setSelected] = useState<Screenshot | null>(null);

  const getImageUrl = (screenshot: Screenshot) => {
    return `/api/scans/screenshots/${screenshot.id}/image`;
  };

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {screenshots.map((screenshot) => (
          <div
            key={screenshot.id}
            onClick={() => setSelected(screenshot)}
            className="ui-surface border border-border rounded-xl overflow-hidden cursor-pointer hover:border-accent/50 transition group"
          >
            <div className="aspect-video ui-subtle relative overflow-hidden">
              <img
                src={getImageUrl(screenshot)}
                alt={screenshot.url}
                className={`w-full h-full object-cover group-hover:scale-105 transition ${failed[screenshot.id] ? 'hidden' : ''}`}
                onError={() => setFailed(previous => ({...previous, [screenshot.id]: true}))}
                onLoad={() => setFailed(previous => ({...previous, [screenshot.id]: false}))}
              />
              {failed[screenshot.id] && <div className="absolute inset-0 flex flex-col gap-2 items-center justify-center text-gray-500 p-3 text-center">
                <Camera className="w-8 h-8" />
                <span className="text-xs">{t("Не удалось загрузить скриншот")}</span>
                <a href={getImageUrl(screenshot)} target="_blank" rel="noopener noreferrer" className="text-xs text-accent underline" onClick={e => e.stopPropagation()}>{t("Открыть файл")}</a>
              </div>}
            </div>
            <div className="p-3">
              <div className="text-sm font-mono text-accent truncate">{screenshot.url}</div>
              {screenshot.title && (
                <div className="text-xs text-gray-500 truncate mt-0.5">{screenshot.title}</div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Modal */}
      {selected && (
        <div
          onClick={() => setSelected(null)}
          className="fixed inset-0 screenshot-overlay z-50 flex items-center justify-center p-4"
        >
          <div className="screenshot-dialog max-w-5xl w-full" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <div className="font-mono text-accent">{selected.url}</div>
              <button
                onClick={() => setSelected(null)}
                className="p-2 rounded-lg text-gray-400 hover:ui-subtle"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <img
              src={getImageUrl(selected)}
              alt={selected.url}
              className="w-full rounded-xl border border-border"
            />
          </div>
        </div>
      )}
    </>
  );
}
