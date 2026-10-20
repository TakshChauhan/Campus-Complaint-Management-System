import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { CampusBackgroundSlideshow } from '../components/CampusBackgroundSlideshow';
import type { CampusPhoto } from '../lib/campusPhotos';

const photos: CampusPhoto[] = [
  { id: 'a', src: '/a.webp', srcSet: '/a.webp 960w', caption: 'Lotus pond', position: '50% 50%' },
  { id: 'b', src: '/b.webp', srcSet: '/b.webp 960w', caption: 'Academic blocks', position: '50% 50%' },
];

function activeCaption() {
  return document.querySelector('.campus-bg__place')?.textContent;
}

function loadAll() {
  document.querySelectorAll('img').forEach((img) => fireEvent.load(img));
}

function setReducedMotion(reduce: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: reduce && query.includes('reduce'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

describe('CampusBackgroundSlideshow', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setReducedMotion(false);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders every photo once, decorative and with object-position', () => {
    render(<CampusBackgroundSlideshow photos={photos} />);
    const imgs = document.querySelectorAll('img');
    expect(imgs).toHaveLength(2);
    imgs.forEach((img) => expect(img).toHaveAttribute('alt', ''));
    expect(activeCaption()).toBe('Lotus pond');
  });

  it('advances every 6 seconds once the next photo has loaded, and loops', () => {
    render(<CampusBackgroundSlideshow photos={photos} />);
    act(() => loadAll());
    act(() => vi.advanceTimersByTime(5999));
    expect(activeCaption()).toBe('Lotus pond');
    act(() => vi.advanceTimersByTime(1));
    expect(activeCaption()).toBe('Academic blocks');
    act(() => vi.advanceTimersByTime(6000));
    expect(activeCaption()).toBe('Lotus pond');
  });

  it('waits for the next photo to load instead of fading to a blank frame', () => {
    render(<CampusBackgroundSlideshow photos={photos} />);
    act(() => fireEvent.load(document.querySelectorAll('img')[0]));
    act(() => vi.advanceTimersByTime(20000));
    expect(activeCaption()).toBe('Lotus pond');
  });

  it('pauses while the tab is hidden', () => {
    render(<CampusBackgroundSlideshow photos={photos} />);
    act(() => loadAll());
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    act(() => vi.advanceTimersByTime(20000));
    expect(activeCaption()).toBe('Lotus pond');
    visibility.mockReturnValue('visible');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    act(() => vi.advanceTimersByTime(6000));
    expect(activeCaption()).toBe('Academic blocks');
  });

  it('can be paused by the viewer', () => {
    render(<CampusBackgroundSlideshow photos={photos} />);
    act(() => loadAll());
    fireEvent.click(screen.getByRole('button', { name: /pause campus photo slideshow/i }));
    act(() => vi.advanceTimersByTime(20000));
    expect(activeCaption()).toBe('Lotus pond');
    expect(screen.getByRole('button', { name: /play campus photo slideshow/i })).toHaveAttribute('aria-pressed', 'true');
  });

  it('does not auto-advance when reduced motion is preferred', () => {
    setReducedMotion(true);
    render(<CampusBackgroundSlideshow photos={photos} />);
    act(() => loadAll());
    act(() => vi.advanceTimersByTime(30000));
    expect(activeCaption()).toBe('Lotus pond');
    expect(screen.queryByRole('button', { name: /pause/i })).not.toBeInTheDocument();
  });

  it('clears its timer on unmount', () => {
    const { unmount } = render(<CampusBackgroundSlideshow photos={photos} />);
    act(() => loadAll());
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
