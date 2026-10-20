import { memo, useEffect, useState } from 'react';
import { usePageVisible, usePrefersReducedMotion } from '../hooks/useMediaState';
import { Icon } from './ui/Icon';
import { CampusPhoto } from '../lib/campusPhotos';
import './CampusBackgroundSlideshow.css';

interface Props {
  photos: CampusPhoto[];
  /** Time each photo stays fully visible before the next fade begins (ms). */
  intervalMs?: number;
  /** Crossfade duration (ms). */
  fadeMs?: number;
  /** Show the caption with the place name and the pause control. */
  showCaption?: boolean;
}

/**
 * Full-bleed, crossfading background of real DAU campus photographs.
 *
 * - Every photo stays mounted, so a transition is an opacity change only: no
 *   layout shift, no re-decode flash.
 * - The next photo is shown only after it has loaded, so slow networks never
 *   fade to a blank frame.
 * - Auto-advance pauses in hidden tabs, when the viewer presses pause, and is
 *   disabled entirely under prefers-reduced-motion.
 * - A single timeout drives the cycle and is cleared on every change/unmount.
 */
function CampusBackgroundSlideshowImpl({ photos, intervalMs = 6000, fadeMs = 1200, showCaption = true }: Props) {
  const [active, setActive] = useState(0);
  const [loaded, setLoaded] = useState<Set<number>>(() => new Set());
  const [userPaused, setUserPaused] = useState(false);
  const visible = usePageVisible();
  const reducedMotion = usePrefersReducedMotion();

  const canAnimate = photos.length > 1 && !reducedMotion;
  const running = canAnimate && visible && !userPaused;
  const next = photos.length > 0 ? (active + 1) % photos.length : 0;
  const nextReady = loaded.has(next);

  useEffect(() => {
    if (!running || !nextReady) return;
    const id = window.setTimeout(() => setActive(next), intervalMs);
    return () => window.clearTimeout(id);
  }, [running, nextReady, next, intervalMs]);

  const markLoaded = (index: number) =>
    setLoaded((prev) => {
      if (prev.has(index)) return prev;
      const copy = new Set(prev);
      copy.add(index);
      return copy;
    });

  if (photos.length === 0) return null;
  const current = photos[active];

  return (
    <div className="campus-bg" style={{ ['--campus-fade' as string]: `${fadeMs}ms` }} data-testid="campus-slideshow">
      <div className="campus-bg__frames" aria-hidden="true">
        {photos.map((photo, index) => (
          <img
            key={photo.id}
            className={['campus-bg__img', index === active && 'is-active'].filter(Boolean).join(' ')}
            src={photo.src}
            srcSet={photo.srcSet}
            sizes="100vw"
            alt=""
            draggable={false}
            decoding="async"
            // First photo is the LCP image; the rest load eagerly too because
            // there are only a few and they must be ready before their fade.
            // (lower-case attribute: React 18 does not know the camelCase prop.)
            {...({ fetchpriority: index === 0 ? 'high' : 'low' } as Record<string, string>)}
            style={{ objectPosition: photo.position }}
            ref={(el) => {
              // Cached images can finish before React attaches onLoad.
              if (el && el.complete && el.naturalWidth > 0) markLoaded(index);
            }}
            onLoad={() => markLoaded(index)}
            data-active={index === active}
          />
        ))}
      </div>
      <div className="campus-bg__scrim" aria-hidden="true" />
      {showCaption ? (
        <div className="campus-bg__caption">
          <span className="campus-bg__place">{current.caption}</span>
          {canAnimate ? (
            <button
              type="button"
              className="campus-bg__toggle"
              onClick={() => setUserPaused((p) => !p)}
              aria-label={userPaused ? 'Play campus photo slideshow' : 'Pause campus photo slideshow'}
              aria-pressed={userPaused}
            >
              <Icon name={userPaused ? 'play' : 'pause'} size={14} />
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** Memoised: parent form state changes (typing) never re-render the slideshow. */
export const CampusBackgroundSlideshow = memo(CampusBackgroundSlideshowImpl);
export default CampusBackgroundSlideshow;
